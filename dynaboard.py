#!/usr/bin/env python3
"""DynaBoard: single-player board-game benchmark for language models.

The benchmark emits natural-language puzzle prompts and deterministic answer
keys.  Each instance is a finite-state board game with randomized board size,
start/goal locations, obstacles, portals, turn-dependent movement rules, and an
optional turn-dependent wind effect.  The solver uses breadth-first search, so
the answer key is the shortest valid sequence of chosen moves.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


Coord = tuple[int, int]


@dataclass(frozen=True)
class Move:
    name: str
    dx: int
    dy: int


@dataclass(frozen=True)
class TurnRule:
    label: str
    moves: tuple[Move, ...]


@dataclass(frozen=True)
class WindRule:
    period: int
    move: Move


@dataclass(frozen=True)
class GameInstance:
    instance_id: str
    width: int
    height: int
    start: int
    goal: int
    blocked: tuple[int, ...]
    portals: tuple[tuple[int, int], ...]
    rules: tuple[TurnRule, ...]
    wind: WindRule | None
    max_turns: int


@dataclass(frozen=True)
class Step:
    turn: int
    rule: str
    move: str
    from_space: int
    chosen_landing: int
    final_space: int
    note: str | None = None


@dataclass(frozen=True)
class Solution:
    solvable: bool
    turns: int | None
    moves: tuple[str, ...]
    path: tuple[Step, ...]


@dataclass(frozen=True)
class ModelResponse:
    output: str
    reasoning: object | None = None
    reasoning_details: object | None = None


MOVE_POOL = (
    Move("hop north 1", 0, -1),
    Move("hop south 1", 0, 1),
    Move("hop east 1", 1, 0),
    Move("hop west 1", -1, 0),
    Move("leap north 2", 0, -2),
    Move("leap south 2", 0, 2),
    Move("leap east 2", 2, 0),
    Move("leap west 2", -2, 0),
    Move("zig northeast", 1, -1),
    Move("zig northwest", -1, -1),
    Move("zag southeast", 1, 1),
    Move("zag southwest", -1, 1),
    Move("long jump east 3", 3, 0),
    Move("long jump west 3", -3, 0),
    Move("drop south 3", 0, 3),
    Move("climb north 3", 0, -3),
    Move("knight east-north", 2, -1),
    Move("knight east-south", 2, 1),
    Move("knight west-north", -2, -1),
    Move("knight west-south", -2, 1),
)


def space_to_coord(space: int, width: int) -> Coord:
    zero_based = space - 1
    return zero_based % width, zero_based // width


def coord_to_space(coord: Coord, width: int) -> int:
    x, y = coord
    return y * width + x + 1


def in_bounds(coord: Coord, width: int, height: int) -> bool:
    x, y = coord
    return 0 <= x < width and 0 <= y < height


def apply_move(space: int, move: Move, game: GameInstance) -> int | None:
    x, y = space_to_coord(space, game.width)
    next_coord = x + move.dx, y + move.dy
    if not in_bounds(next_coord, game.width, game.height):
        return None
    next_space = coord_to_space(next_coord, game.width)
    if next_space in game.blocked:
        return None
    return next_space


def portal_map(game: GameInstance) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for a, b in game.portals:
        mapping[a] = b
        mapping[b] = a
    return mapping


def apply_forced_effects(space: int, turn: int, game: GameInstance) -> tuple[int, str | None]:
    notes: list[str] = []
    portals = portal_map(game)
    if space in portals:
        destination = portals[space]
        notes.append(f"portal sends {space} to {destination}")
        space = destination

    if game.wind is not None and turn % game.wind.period == 0:
        blown = apply_move(space, game.wind.move, game)
        if blown is not None:
            notes.append(f"wind pushes to {blown}")
            space = blown
            if space in portals:
                destination = portals[space]
                notes.append(f"portal sends {space} to {destination}")
                space = destination
        else:
            notes.append("wind is blocked")

    return space, "; ".join(notes) if notes else None


def solve(game: GameInstance) -> Solution:
    """Return the shortest solution under the game's exact transition rules."""
    state_period = math.lcm(len(game.rules), game.wind.period if game.wind is not None else 1)
    queue: deque[tuple[int, int, tuple[Step, ...], tuple[str, ...]]] = deque()
    queue.append((game.start, 0, (), ()))
    visited = {(game.start, 0)}

    while queue:
        space, turns_taken, path, moves = queue.popleft()
        if space == game.goal:
            return Solution(True, turns_taken, moves, path)
        if turns_taken >= game.max_turns:
            continue

        turn = turns_taken + 1
        rule = game.rules[(turn - 1) % len(game.rules)]
        for move in rule.moves:
            landing = apply_move(space, move, game)
            if landing is None:
                continue
            final_space, note = apply_forced_effects(landing, turn, game)
            next_state = final_space, turn % state_period
            if next_state in visited:
                continue
            visited.add(next_state)
            step = Step(
                turn=turn,
                rule=rule.label,
                move=move.name,
                from_space=space,
                chosen_landing=landing,
                final_space=final_space,
                note=note,
            )
            queue.append((final_space, turn, path + (step,), moves + (move.name,)))

    return Solution(False, None, (), ())


def generate_instance(seed: int, index: int = 0, max_attempts: int = 500) -> GameInstance:
    """Generate one deterministic, solvable puzzle from ``seed`` and ``index``."""
    rng = random.Random(seed * 1_000_003 + index)
    for attempt in range(max_attempts):
        width = rng.randint(1, 7)
        height = rng.randint(1, 7)
        if width * height < 8:
            height = max(height, 2)
            width = max(width, 4)
        total_spaces = width * height

        start = rng.randint(1, total_spaces)
        goal = rng.randint(1, total_spaces)
        while goal == start:
            goal = rng.randint(1, total_spaces)

        blocked_count = rng.randint(0, min(5, max(0, total_spaces // 5)))
        unavailable = {start, goal}
        blocked = set(rng.sample([s for s in range(1, total_spaces + 1) if s not in unavailable], blocked_count))

        portal_pairs: list[tuple[int, int]] = []
        if total_spaces >= 12 and rng.random() < 0.55:
            candidates = [s for s in range(1, total_spaces + 1) if s not in unavailable and s not in blocked]
            rng.shuffle(candidates)
            pair_count = min(rng.randint(1, 2), len(candidates) // 2)
            for pair_index in range(pair_count):
                a = candidates[2 * pair_index]
                b = candidates[2 * pair_index + 1]
                portal_pairs.append(tuple(sorted((a, b))))

        cycle = rng.randint(2, 4)
        shuffled_moves = list(MOVE_POOL)
        rng.shuffle(shuffled_moves)
        rules: list[TurnRule] = []
        cursor = 0
        for phase in range(cycle):
            move_count = rng.randint(2, 4)
            selected = shuffled_moves[cursor : cursor + move_count]
            cursor += move_count
            if len(selected) < move_count:
                rng.shuffle(shuffled_moves)
                selected.extend(shuffled_moves[: move_count - len(selected)])
            label = _phase_label(phase, cycle)
            rules.append(TurnRule(label, tuple(selected)))

        wind = None
        if rng.random() < 0.65:
            wind_move = rng.choice(
                (
                    Move("one space north", 0, -1),
                    Move("one space south", 0, 1),
                    Move("one space east", 1, 0),
                    Move("one space west", -1, 0),
                )
            )
            wind = WindRule(period=rng.randint(2, 5), move=wind_move)

        game = GameInstance(
            instance_id=f"dynaboard-{seed}-{index}-{attempt}",
            width=width,
            height=height,
            start=start,
            goal=goal,
            blocked=tuple(sorted(blocked)),
            portals=tuple(sorted(portal_pairs)),
            rules=tuple(rules),
            wind=wind,
            max_turns=max(12, total_spaces * 3),
        )
        solution = solve(game)
        if solution.solvable and 2 <= (solution.turns or 0) <= game.max_turns:
            return game

    raise RuntimeError(f"could not generate a solvable puzzle for seed={seed} index={index}")


def _phase_label(phase: int, cycle: int) -> str:
    if cycle == 2:
        return "odd-numbered turns" if phase == 0 else "even-numbered turns"
    turn_numbers = ", ".join(str(phase + 1 + cycle * n) for n in range(3))
    return f"turns congruent to {phase + 1} modulo {cycle} ({turn_numbers}, ...)"


def render_prompt(game: GameInstance) -> str:
    lines = [
        "You are playing a one-player board game.",
        f"The board is a {game.height}x{game.width} rectangle with spaces numbered left to right, top to bottom.",
        f"You start on space {game.start}. Your goal is to finish a turn on space {game.goal}.",
    ]
    if game.blocked:
        lines.append(f"You may not land on blocked spaces: {_join_numbers(game.blocked)}.")
    else:
        lines.append("There are no blocked spaces.")
    if game.portals:
        pairs = "; ".join(f"{a}<->{b}" for a, b in game.portals)
        lines.append(f"Portal pairs are {pairs}. Landing on either portal immediately moves you to its pair.")
    else:
        lines.append("There are no portals.")

    lines.append("Movement rules change by turn:")
    for rule in game.rules:
        move_text = "; ".join(_move_description(move) for move in rule.moves)
        lines.append(f"- On {rule.label}, choose exactly one of: {move_text}.")

    if game.wind is not None:
        lines.append(
            f"After your chosen move on every turn divisible by {game.wind.period}, "
            f"a gust tries to push you {game.wind.move.name}; if that push would leave the board or hit a blocked space, it does nothing."
        )
    else:
        lines.append("There are no automatic wind effects.")

    lines.append(
        "What is the shortest sequence of chosen moves that makes you finish a turn exactly on the goal space? "
        'Answer only as JSON in this form: {"moves": ["first move name", "second move name"]}.'
    )
    return "\n".join(lines)


def _move_description(move: Move) -> str:
    return f"{move.name} ({_delta_text(move.dx, move.dy)})"


def _delta_text(dx: int, dy: int) -> str:
    parts: list[str] = []
    if dx > 0:
        parts.append(f"{dx} east")
    elif dx < 0:
        parts.append(f"{abs(dx)} west")
    if dy > 0:
        parts.append(f"{dy} south")
    elif dy < 0:
        parts.append(f"{abs(dy)} north")
    return ", ".join(parts) if parts else "stay put"


def _join_numbers(numbers: Iterable[int]) -> str:
    return ", ".join(str(number) for number in numbers)


def render_answer_key(solution: Solution) -> str:
    if not solution.solvable:
        return "UNSOLVABLE"
    steps = [
        f"{step.turn}. {step.move}: {step.from_space} -> {step.chosen_landing} -> {step.final_space}"
        + (f" ({step.note})" if step.note else "")
        for step in solution.path
    ]
    move_line = "Moves: " + " | ".join(solution.moves)
    return f"Shortest length: {solution.turns}\n{move_line}\nPath:\n" + "\n".join(steps)


def to_record(game: GameInstance) -> dict[str, object]:
    solution = solve(game)
    return {
        "id": game.instance_id,
        "prompt": render_prompt(game),
        "answer": {
            "solvable": solution.solvable,
            "turns": solution.turns,
            "moves": list(solution.moves),
            "path": [asdict(step) for step in solution.path],
        },
        "game": asdict(game),
    }


def game_from_record(record: dict[str, object]) -> GameInstance:
    game = record.get("game")
    if not isinstance(game, dict):
        raise ValueError("record must include a game object")

    rules = tuple(
        TurnRule(
            str(rule["label"]),
            tuple(Move(str(move["name"]), int(move["dx"]), int(move["dy"])) for move in rule["moves"]),
        )
        for rule in game["rules"]
    )
    wind_data = game.get("wind")
    wind = None
    if isinstance(wind_data, dict):
        wind = WindRule(
            int(wind_data["period"]),
            Move(str(wind_data["move"]["name"]), int(wind_data["move"]["dx"]), int(wind_data["move"]["dy"])),
        )
    return GameInstance(
        instance_id=str(game["instance_id"]),
        width=int(game["width"]),
        height=int(game["height"]),
        start=int(game["start"]),
        goal=int(game["goal"]),
        blocked=tuple(int(space) for space in game.get("blocked", [])),
        portals=tuple(tuple(int(space) for space in pair) for pair in game.get("portals", [])),
        rules=rules,
        wind=wind,
        max_turns=int(game["max_turns"]),
    )


def load_env_file(path: str = ".env") -> dict[str, str]:
    """Load KEY=VALUE pairs from a dotenv-style file without external deps."""
    values: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def generate_dataset(seed: int, count: int, output: str | None, output_format: str) -> None:
    records = [to_record(generate_instance(seed, index)) for index in range(count)]
    if output_format == "jsonl":
        body = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    else:
        chunks: list[str] = []
        for record in records:
            answer = record["answer"]
            chunks.append(
                f"=== {record['id']} ===\n"
                f"{record['prompt']}\n\n"
                f"{render_answer_key(_solution_from_answer(answer))}"
            )
        body = "\n\n".join(chunks) + ("\n" if chunks else "")

    if output:
        Path(output).write_text(body, encoding="utf-8")
    else:
        print(body, end="")


def _solution_from_answer(answer: object) -> Solution:
    if not isinstance(answer, dict):
        raise ValueError("record answer must be an object")
    path = tuple(Step(**step) for step in answer.get("path", []))
    return Solution(
        bool(answer.get("solvable")),
        answer.get("turns"),
        tuple(answer.get("moves", [])),
        path,
    )


def iter_jsonl(path: str) -> Iterable[dict[str, object]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL record") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
            yield record


def call_openrouter(
    prompt: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    base_url: str = "https://openrouter.ai/api/v1",
) -> ModelResponse:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You solve board-game puzzles. Return only JSON with a moves array. "
                    "Use the exact move names from the prompt."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mtfehrer/DynaBoard",
            "X-Title": "DynaBoard",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from exc

    try:
        choice = body["choices"][0]
        message = choice["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected OpenRouter response: {body}") from exc
    if not isinstance(content, str):
        if body.get("choices") and body["choices"][0].get("finish_reason") == "length":
            raise RuntimeError(
                "OpenRouter returned no final answer because the model hit the max token limit; "
            )
        raise RuntimeError(f"unexpected OpenRouter message content: {content!r}")
    if not isinstance(message, dict):
        raise RuntimeError(f"unexpected OpenRouter message: {message!r}")
    return ModelResponse(
        output=content,
        reasoning=message.get("reasoning"),
        reasoning_details=message.get("reasoning_details"),
    )


def extract_moves(text: str) -> list[str]:
    """Extract a move list from the model response."""
    stripped = text.strip()
    candidates = [stripped]
    if "```" in stripped:
        parts = stripped.split("```")
        candidates.extend(part.strip() for part in parts if part.strip())
    json_start = stripped.find("{")
    json_end = stripped.rfind("}")
    if json_start != -1 and json_end > json_start:
        candidates.append(stripped[json_start : json_end + 1])

    for candidate in candidates:
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("moves"), list):
            return [str(move).strip() for move in parsed["moves"] if str(move).strip()]
        if isinstance(parsed, list):
            return [str(move).strip() for move in parsed if str(move).strip()]

    normalized = stripped.replace("\n", "|").replace(",", "|")
    if ":" in normalized:
        normalized = normalized.split(":", 1)[1]
    return [part.strip(" .\"'") for part in normalized.split("|") if part.strip(" .\"'")]


def replay_moves(game: GameInstance, predicted: list[str]) -> tuple[bool, tuple[Step, ...], str | None]:
    """Replay named moves exactly as chosen by a model."""
    space = game.start
    path: list[Step] = []
    for turn, predicted_move in enumerate(predicted, start=1):
        if turn > game.max_turns:
            return False, tuple(path), "too many moves"
        rule = game.rules[(turn - 1) % len(game.rules)]
        move = next((candidate for candidate in rule.moves if _normalize_move(candidate.name) == _normalize_move(predicted_move)), None)
        if move is None:
            allowed = ", ".join(candidate.name for candidate in rule.moves)
            return False, tuple(path), f"turn {turn}: move {predicted_move!r} is not allowed; allowed moves: {allowed}"
        landing = apply_move(space, move, game)
        if landing is None:
            return False, tuple(path), f"turn {turn}: move {predicted_move!r} leaves the board or hits a blocked space"
        final_space, note = apply_forced_effects(landing, turn, game)
        path.append(
            Step(
                turn=turn,
                rule=rule.label,
                move=move.name,
                from_space=space,
                chosen_landing=landing,
                final_space=final_space,
                note=note,
            )
        )
        space = final_space
    if space != game.goal:
        return False, tuple(path), f"ended on space {space}, not goal space {game.goal}"
    return True, tuple(path), None


def score_moves(predicted: list[str], expected: list[str], game: GameInstance | None = None) -> dict[str, object]:
    predicted_normalized = [_normalize_move(move) for move in predicted]
    expected_normalized = [_normalize_move(move) for move in expected]
    result: dict[str, object] = {
        "exact": predicted_normalized == expected_normalized,
        "predicted_moves": predicted,
        "expected_moves": expected,
        "predicted_turns": len(predicted),
        "expected_turns": len(expected),
    }
    if game is not None:
        valid, path, error = replay_moves(game, predicted)
        result["valid"] = valid
        result["optimal"] = valid and len(predicted) == len(expected)
        result["correct"] = result["optimal"]
        result["replay_error"] = error
        result["replay_path"] = [asdict(step) for step in path]
    else:
        result["correct"] = result["exact"]
    return result


def _normalize_move(move: str) -> str:
    return " ".join(move.lower().strip().split())


def run_benchmark(args: argparse.Namespace) -> None:
    env = {**load_env_file(args.env), **os.environ}
    api_key = args.api_key or env.get("OPENROUTER_API_KEY")
    model = env.get("OPENROUTER_MODEL")
    base_url = env.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    log_path = getattr(args, "log", None)
    if not api_key:
        raise SystemExit("missing OPENROUTER_API_KEY; add it to .env or pass --api-key")
    if not model:
        raise SystemExit("missing OPENROUTER_MODEL; add it to .env or pass --model")

    records = list(iter_jsonl(args.dataset))
    if args.limit is not None:
        records = records[: args.limit]

    correct = 0
    results: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []
    for index, record in enumerate(records, start=1):
        prompt = record.get("prompt")
        answer = record.get("answer")
        if not isinstance(prompt, str) or not isinstance(answer, dict):
            raise ValueError(f"record {index} must include prompt and answer object")
        expected = [str(move) for move in answer.get("moves", [])]
        game = game_from_record(record)
        started = time.time()
        try:
            model_response = call_openrouter(
                prompt=prompt,
                api_key=api_key,
                model=model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                base_url=base_url,
            )
        except RuntimeError as exc:
            latency_seconds = round(time.time() - started, 3)
            result = {
                "id": record.get("id"),
                "model": model,
                "error": str(exc),
                "latency_seconds": latency_seconds,
                "correct": False,
            }
            results.append(result)
            logs.append(
                {
                    "id": record.get("id"),
                    "model": model,
                    "reasoning": None,
                    "reasoning_details": None,
                    "output": None,
                    "error": str(exc),
                    "latency_seconds": latency_seconds,
                }
            )
            print(f"[{index}/{len(records)}] {record.get('id')}: error: {exc}")
            continue
        if isinstance(model_response, str):
            model_response = ModelResponse(output=model_response)
        response = model_response.output
        predicted = extract_moves(response)
        score = score_moves(predicted, expected, game)
        score["latency_seconds"] = round(time.time() - started, 3)
        if score["correct"]:
            correct += 1
        result = {
            "id": record.get("id"),
            "model": model,
            "response": response,
            **score,
        }
        results.append(result)
        logs.append(
            {
                "id": record.get("id"),
                "model": model,
                "reasoning": model_response.reasoning,
                "reasoning_details": model_response.reasoning_details,
                "output": model_response.output,
                "correct": score["correct"],
                "latency_seconds": score["latency_seconds"],
            }
        )
        print(
            f"[{index}/{len(records)}] {record.get('id')}: "
            f"{'correct' if score['correct'] else 'wrong'}"
        )

    output_body = "".join(json.dumps(result, sort_keys=True) + "\n" for result in results)
    if args.output:
        Path(args.output).write_text(output_body, encoding="utf-8")
    if log_path:
        log_body = "".join(json.dumps(log, sort_keys=True) + "\n" for log in logs)
        Path(log_path).write_text(log_body, encoding="utf-8")

    total = len(records)
    accuracy = correct / total if total else 0.0
    print(f"Accuracy: {correct}/{total} ({accuracy:.1%})")
    if args.output:
        print(f"Wrote results to {args.output}")
    if log_path:
        print(f"Wrote logs to {log_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser("generate", help="generate a benchmark dataset")
    generate.add_argument("--seed", type=int, default=1, help="base random seed")
    generate.add_argument("--count", type=int, default=3, help="number of instances to generate")
    generate.add_argument("--format", choices=("jsonl", "text"), default="jsonl", help="output format")
    generate.add_argument("--output", "-o", help="output file; defaults to stdout")

    run = subparsers.add_parser("run", help="run a JSONL dataset against an OpenRouter model")
    run.add_argument("--dataset", required=True, help="JSONL dataset generated by this script")
    run.add_argument("--output", "-o", help="write per-instance JSONL results")
    run.add_argument("--log", help="write per-instance JSONL logs with reasoning and output")
    run.add_argument("--env", default=".env", help="dotenv file containing OpenRouter settings")
    run.add_argument("--api-key", help="OpenRouter API key; defaults to OPENROUTER_API_KEY")
    run.add_argument("--limit", type=int, help="only run the first N records")
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=2048)
    run.add_argument("--timeout", type=int, default=60)

    parser.add_argument("--seed", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--count", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--format", choices=("jsonl", "text"), default="text", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "run":
        run_benchmark(args)
    else:
        generate_dataset(args.seed, args.count, getattr(args, "output", None), args.format)


if __name__ == "__main__":
    main()
