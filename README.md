# DynaBoard

This repository contains DynaBoard, a small Python benchmark generator for single-player
board-game reasoning tasks.  Each puzzle randomizes:

- board dimensions and numbered spaces
- start and goal positions
- blocked spaces
- optional bidirectional portals
- turn-dependent movement rules
- optional periodic wind effects

The included solver is deterministic breadth-first search over the finite game
state, so each emitted answer key is the shortest sequence of chosen moves.

## Usage

Generate a JSONL dataset:

```bash
python3 dynaboard.py generate --seed 123 --count 100 --output dynaboard_games.jsonl
```

Choose a difficulty:

```bash
python3 dynaboard.py generate --seed 123 --count 100 --difficulty easy --output dynaboard_easy.jsonl
python3 dynaboard.py generate --seed 123 --count 100 --difficulty medium --output dynaboard_medium.jsonl
python3 dynaboard.py generate --seed 123 --count 100 --difficulty hard --output dynaboard_hard.jsonl
```

`hard` is the original benchmark behavior. `easy` uses a single fixed movement
rule with no blocked spaces, portals, or wind, and keeps shortest paths to at
most 6 turns. `medium` uses smaller rule cycles and caps shortest paths at 10
turns while allowing limited blocked spaces, portals, and wind.

Create a `.env` file with your OpenRouter settings:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=openai/gpt-4.1-mini
```

Run the benchmark against the generated dataset:

```bash
python3 dynaboard.py run --dataset dynaboard_games.jsonl --output results.jsonl
```

Write per-test-case reasoning and output logs while running the benchmark:

```bash
python3 dynaboard.py run --dataset dynaboard_games.jsonl --output results.jsonl --log logs.jsonl
```

For a quick smoke test, run only the first few records:

```bash
python3 dynaboard.py run --dataset dynaboard_games.jsonl --limit 5
```

Generate readable prompts and answer keys:

```bash
python3 dynaboard.py generate --seed 123 --count 3 --format text
```

Each JSONL record includes:

- `id`: stable instance id
- `difficulty`: `easy`, `medium`, or `hard`
- `prompt`: natural-language model prompt
- `answer`: shortest move sequence and traced path
- `game`: structured game definition

Each result JSONL record includes:

- `id`: benchmark instance id
- `model`: OpenRouter model name
- `response`: raw model response
- `exact`: whether the returned move list exactly matched the answer key
- `predicted_moves` and `expected_moves`

Each log JSONL record includes:

- `id`: benchmark instance id
- `model`: OpenRouter model name
- `reasoning`: provider reasoning text, when returned
- `reasoning_details`: provider structured reasoning details, when returned
- `output`: final model output used for scoring

Run tests:

```bash
python3 -m unittest
```
