import argparse
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import dynaboard
from dynaboard import (
    GameInstance,
    ModelResponse,
    Move,
    TurnRule,
    WindRule,
    extract_moves,
    generate_dataset,
    generate_instance,
    game_from_record,
    load_env_file,
    replay_moves,
    run_benchmark,
    score_moves,
    solve,
    to_record,
)


class DynaBoardTests(unittest.TestCase):
    def test_generation_is_deterministic(self) -> None:
        first = generate_instance(seed=42, index=3)
        second = generate_instance(seed=42, index=3)
        self.assertEqual(first, second)
        self.assertEqual(solve(first), solve(second))

    def test_generated_instances_are_solvable(self) -> None:
        for index in range(10):
            game = generate_instance(seed=7, index=index)
            solution = solve(game)
            self.assertTrue(solution.solvable)
            self.assertIsNotNone(solution.turns)
            self.assertGreaterEqual(solution.turns, 2)
            self.assertLessEqual(solution.turns, game.max_turns)
            self.assertEqual(solution.path[-1].final_space, game.goal)

    def test_record_contains_prompt_and_answer_key(self) -> None:
        game = generate_instance(seed=5, index=0)
        record = to_record(game)
        self.assertIn("prompt", record)
        self.assertIn("answer", record)
        self.assertIn("Movement rules change by turn", record["prompt"])
        self.assertIn('"moves"', record["prompt"])
        self.assertTrue(record["answer"]["solvable"])
        self.assertGreater(len(record["answer"]["moves"]), 0)

    def test_solver_tracks_wind_phase(self) -> None:
        game = GameInstance(
            instance_id="wind-phase-regression",
            width=5,
            height=1,
            start=1,
            goal=3,
            blocked=(),
            portals=(),
            rules=(
                TurnRule("odd-numbered turns", (Move("hop east 1", 1, 0),)),
                TurnRule("even-numbered turns", (Move("hop west 1", -1, 0),)),
            ),
            wind=WindRule(period=3, move=Move("one space east", 1, 0)),
            max_turns=8,
        )
        solution = solve(game)
        self.assertTrue(solution.solvable)
        self.assertEqual(solution.turns, 3)
        self.assertEqual(solution.path[-1].final_space, 3)

    def test_generate_dataset_writes_jsonl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "dataset.jsonl"
            generate_dataset(seed=11, count=2, output=str(output), output_format="jsonl")
            records = [line for line in output.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(records), 2)
            self.assertIn('"prompt"', records[0])
            self.assertIn('"answer"', records[0])

    def test_load_env_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            env = Path(tmpdir) / ".env"
            env.write_text(
                "\n".join(
                    [
                        "# comment",
                        "OPENROUTER_API_KEY='test-key'",
                        'OPENROUTER_MODEL="test/model"',
                    ]
                ),
                encoding="utf-8",
            )
            values = load_env_file(str(env))
            self.assertEqual(values["OPENROUTER_API_KEY"], "test-key")
            self.assertEqual(values["OPENROUTER_MODEL"], "test/model")

    def test_extract_moves_from_json_response(self) -> None:
        response = '```json\n{"moves": ["hop east 1", "zig northeast"]}\n```'
        self.assertEqual(extract_moves(response), ["hop east 1", "zig northeast"])

    def test_score_moves_normalizes_case_and_spacing(self) -> None:
        score = score_moves([" Hop   East 1 "], ["hop east 1"])
        self.assertTrue(score["exact"])

    def test_game_from_record_replays_answer_key(self) -> None:
        record = to_record(generate_instance(seed=13, index=0))
        game = game_from_record(record)
        moves = record["answer"]["moves"]
        valid, path, error = replay_moves(game, moves)
        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(path[-1].final_space, game.goal)

    def test_score_moves_marks_valid_optimal_solution_correct(self) -> None:
        record = to_record(generate_instance(seed=17, index=0))
        game = game_from_record(record)
        expected = record["answer"]["moves"]
        score = score_moves(expected, expected, game)
        self.assertTrue(score["valid"])
        self.assertTrue(score["optimal"])
        self.assertTrue(score["correct"])

    def test_run_benchmark_writes_reasoning_logs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            dataset = Path(tmpdir) / "dataset.jsonl"
            log = Path(tmpdir) / "logs.jsonl"
            record = to_record(generate_instance(seed=23, index=0))
            dataset.write_text(json.dumps(record) + "\n", encoding="utf-8")
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OPENROUTER_MODEL=test/model\n", encoding="utf-8")

            def fake_call_openrouter(**_kwargs: object) -> ModelResponse:
                return ModelResponse(
                    output=json.dumps({"moves": record["answer"]["moves"]}),
                    reasoning="matched each turn against the changing move rules",
                )

            original_call_openrouter = dynaboard.call_openrouter
            dynaboard.call_openrouter = fake_call_openrouter
            try:
                run_benchmark(
                    argparse.Namespace(
                        dataset=str(dataset),
                        output=None,
                        log=str(log),
                        env=str(env_path),
                        api_key="test-key",
                        limit=None,
                        temperature=0.0,
                        max_tokens=2048,
                        timeout=60,
                    )
                )
            finally:
                dynaboard.call_openrouter = original_call_openrouter

            log_records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(log_records), 1)
            self.assertEqual(log_records[0]["id"], record["id"])
            self.assertEqual(log_records[0]["model"], "test/model")
            self.assertEqual(log_records[0]["reasoning"], "matched each turn against the changing move rules")
            self.assertEqual(json.loads(log_records[0]["output"])["moves"], record["answer"]["moves"])


if __name__ == "__main__":
    unittest.main()
