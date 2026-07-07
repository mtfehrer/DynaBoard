import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dynaboard import (
    GameInstance,
    Move,
    TurnRule,
    WindRule,
    extract_moves,
    generate_dataset,
    generate_instance,
    game_from_record,
    load_env_file,
    replay_moves,
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


if __name__ == "__main__":
    unittest.main()
