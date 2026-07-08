#!/usr/bin/env python3
import os
import json
import glob

def main():
    # Base paths
    website_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(website_dir)
    results_dir = os.path.join(project_dir, "results")
    
    print(f"Project root: {project_dir}")
    print(f"Results dir: {results_dir}")

    # 1. Load all games from any datasets (.jsonl) in the project directory
    dataset_games = {}
    dataset_paths = glob.glob(os.path.join(project_dir, "*.jsonl"))
    for path in dataset_paths:
        print(f"Loading dataset: {os.path.basename(path)}")
        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    game_id = record.get("id")
                    if game_id:
                        dataset_games[game_id] = {
                            "game": record.get("game"),
                            "prompt": record.get("prompt"),
                            "answer": record.get("answer"),
                            "difficulty": record.get("difficulty", "hard")
                        }
                except Exception as e:
                    print(f"Error parsing line {line_no} in {path}: {e}")

    print(f"Loaded {len(dataset_games)} game definitions from datasets.")

    # 2. Find all model results in the results directory
    # Format expected: results/<model_slug>-results.jsonl
    results_files = glob.glob(os.path.join(results_dir, "*-results.jsonl"))
    
    models_summary = {}
    test_cases_map = {} # game_id -> { "id", "game", "prompt", "answer", "results": {} }
    
    for rf_path in results_files:
        filename = os.path.basename(rf_path)
        model_slug = filename.replace("-results.jsonl", "")
        print(f"\nProcessing results for: {model_slug}")
        
        # Determine the matching logs file
        # Try <model_slug>-logs.jsonl and <model_slug>-logs.json
        lf_path_jsonl = os.path.join(results_dir, f"{model_slug}-logs.jsonl")
        lf_path_json = os.path.join(results_dir, f"{model_slug}-logs.json")
        lf_path = None
        if os.path.exists(lf_path_jsonl):
            lf_path = lf_path_jsonl
        elif os.path.exists(lf_path_json):
            lf_path = lf_path_json
            
        logs_map = {}
        if lf_path:
            print(f"Found matching logs: {os.path.basename(lf_path)}")
            with open(lf_path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log_rec = json.loads(line)
                        game_id = log_rec.get("id")
                        if game_id:
                            logs_map[game_id] = {
                                "reasoning": log_rec.get("reasoning"),
                                "output": log_rec.get("output"),
                                "prompt": log_rec.get("prompt")
                            }
                    except Exception as e:
                        print(f"Error parsing log line {line_no} in {lf_path}: {e}")
        else:
            print(f"Warning: No matching logs found for {model_slug}")

        # Parse results file
        results_records = []
        with open(rf_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    res_rec = json.loads(line)
                    results_records.append(res_rec)
                except Exception as e:
                    print(f"Error parsing results line {line_no} in {rf_path}: {e}")

        if not results_records:
            print(f"No records found in results file {filename}. Skipping.")
            continue

        # Aggregate metrics
        total_cases = 0
        correct_cases = 0
        exact_cases = 0
        optimal_cases = 0
        total_latency = 0.0
        model_display_name = results_records[0].get("model", model_slug)

        for res in results_records:
            game_id = res.get("id")
            if not game_id:
                continue
            
            total_cases += 1
            if res.get("correct") is True:
                correct_cases += 1
            if res.get("exact") is True:
                exact_cases += 1
            if res.get("optimal") is True:
                optimal_cases += 1
            
            total_latency += float(res.get("latency_seconds", 0) or 0)

            # Get logs
            log = logs_map.get(game_id, {})
            
            # Get game definition
            dataset_game = dataset_games.get(game_id, {})
            if not dataset_game:
                print(f"Warning: game_id {game_id} not found in loaded datasets.")
                # fallback placeholder game structure
                dataset_game = {
                    "game": {
                        "instance_id": game_id,
                        "width": 3,
                        "height": 3,
                        "start": 1,
                        "goal": 9,
                        "blocked": [],
                        "portals": [],
                        "rules": [],
                        "wind": None,
                        "difficulty": "unknown"
                    },
                    "prompt": log.get("prompt", ""),
                    "answer": {
                        "solvable": True,
                        "turns": res.get("expected_turns"),
                        "moves": res.get("expected_moves"),
                        "path": []
                    },
                    "difficulty": "unknown"
                }

            # Initialize game instance in global map if not present
            if game_id not in test_cases_map:
                test_cases_map[game_id] = {
                    "id": game_id,
                    "difficulty": dataset_game["difficulty"],
                    "game": dataset_game["game"],
                    "prompt": dataset_game["prompt"],
                    "answer": dataset_game["answer"],
                    "results": {}
                }

            # Add this model's result for this game
            test_cases_map[game_id]["results"][model_display_name] = {
                "correct": res.get("correct") is True,
                "exact": res.get("exact") is True,
                "optimal": res.get("optimal") is True,
                "latency_seconds": res.get("latency_seconds"),
                "predicted_moves": res.get("predicted_moves", []),
                "predicted_turns": res.get("predicted_turns"),
                "replay_path": res.get("replay_path", []),
                "replay_error": res.get("replay_error"),
                "reasoning": log.get("reasoning", "No reasoning provided."),
                "output": log.get("output", res.get("response", ""))
            }

        # Calculate statistics
        avg_latency = total_latency / total_cases if total_cases > 0 else 0
        accuracy = correct_cases / total_cases if total_cases > 0 else 0
        exact_rate = exact_cases / total_cases if total_cases > 0 else 0
        optimal_rate = optimal_cases / total_cases if total_cases > 0 else 0

        models_summary[model_display_name] = {
            "model_name": model_display_name,
            "accuracy": accuracy,
            "exact_match_rate": exact_rate,
            "optimal_rate": optimal_rate,
            "avg_latency": avg_latency,
            "total_cases": total_cases,
            "correct_cases": correct_cases,
            "exact_cases": exact_cases,
            "optimal_cases": optimal_cases
        }

    # Format output JSON
    output_data = {
        "summary": {
            "total_games": len(test_cases_map),
            "models_count": len(models_summary)
        },
        "models": models_summary,
        "test_cases": list(test_cases_map.values())
    }

    # Write output to results_data.json
    output_path = os.path.join(website_dir, "results_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, sort_keys=True)

    print(f"\nSuccessfully compiled results to {output_path}!")
    print(f"Models summary details:")
    for model_name, stats in models_summary.items():
        print(f" - {model_name}: Accuracy={stats['accuracy']:.1%}, Avg Latency={stats['avg_latency']:.2f}s")

if __name__ == "__main__":
    main()
