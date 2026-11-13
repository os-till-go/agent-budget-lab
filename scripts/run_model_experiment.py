"""CLI runner; uses the same real-model engine as the browser UI."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_experiment import run_batch
import model_tasks

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", nargs="+", default=["threshold-0", "threshold-1"])
    parser.add_argument("--methods", nargs="+", default=["full", "errors", "structured", "no_log"])
    parser.add_argument("--queries", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--noise", type=int, default=60)
    parser.add_argument("--allow-holdout", action="store_true")
    args = parser.parse_args()
    result = run_batch({"task_ids": args.tasks, "methods": args.methods, "max_queries": args.queries, "repeats": args.repeats, "seed": args.seed, "noise": args.noise, "allow_holdout": args.allow_holdout}, progress=lambda r: print(json.dumps({"id": r["id"], "done": len(r["rows"]), "total": r["total"], "state": r["state"]}), flush=True))
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
