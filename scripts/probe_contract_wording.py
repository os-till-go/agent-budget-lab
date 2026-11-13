"""Small real-model wording diagnostic; does not change the demo protocol/data.

Default: inspect the two evidence strings without calling a model.
--run: 4 local/explicitly-configured model calls, paired with an existing oracle run.
This is development diagnosis after observing failures, not held-out evaluation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_tasks as tasks
from model_client import ModelClient
from model_experiment import SYSTEM, normalize, run_one, summarize

ROOT = Path(__file__).resolve().parents[1]
REPHRASINGS = {
    "default=10; missing=None; zero_is=explicit_value; negative_values=valid":
        "If value is None, return the default 10. If value is zero, return zero. Otherwise convert value to an integer. Keep negative values unchanged.",
    "default=10; missing=None; zero_is=default_sentinel; negative_values=valid":
        "If value is None or zero, return the default 10. Otherwise convert value to an integer. Keep negative values unchanged.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Make four real model calls")
    parser.add_argument("--baseline", default="examples/model/qwen25-7b-oracle.json")
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(REPHRASINGS, indent=2))
        return
    baseline_path = ROOT / args.baseline
    old = json.loads(baseline_path.read_text(encoding="utf-8"))
    client = ModelClient()
    status = client.status()
    if status["model"] != old["model"]["model"] or status.get("digest") != old["model"].get("digest"):
        raise ValueError("Use the same model and digest as the baseline")
    if old["protocol_version"] != "diagnostic-v3" or old["dataset_sha256"] != tasks.manifest() or old["system_prompt_sha256"] != hashlib.sha256(SYSTEM.encode()).hexdigest():
        raise ValueError("Baseline protocol, dataset or prompt differs")
    config = normalize({"task_ids": ["threshold-0", "threshold-1"], "methods": ["oracle"], "seed": 7, "repeats": 2, "max_queries": 0})
    original_raw_log = tasks.raw_log

    def rephrased_log(*a, **kw):
        text = original_raw_log(*a, **kw)
        for original, replacement in REPHRASINGS.items():
            text = text.replace(original, replacement)
        return text

    result = {"id": uuid.uuid4().hex[:12], "kind": "development-wording-diagnostic-v1", "started_at": datetime.now(timezone.utc).isoformat(), "baseline": {"file": args.baseline, "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest()}, "model": status, "config": config, "rephrasings": REPHRASINGS, "limitations": ["Observed development failures before designing this probe.", "Only four threshold observations, no independent holdout.", "The evidence wording changes; do not pool with diagnostic-v3 compression results.", "No hidden answers or acceptance tests are supplied to the model."], "rows": []}
    out = ROOT / "runs" / (result["id"] + ".json")
    out.parent.mkdir(exist_ok=True)
    # Counterbalance the order across repeats, keeping the same paired option order.
    schedule = [("threshold-0", 0), ("threshold-1", 0), ("threshold-1", 1), ("threshold-0", 1)]
    with patch.object(tasks, "raw_log", rephrased_log):
        for tid, rep in schedule:
            result["rows"].append(run_one(client, tid, "oracle", config, rep))
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"id": result["id"], "done": len(result["rows"]), "total": 4}), flush=True)
            if result["rows"][-1]["status"] == "request_error":
                break
    result["state"] = "completed" if len(result["rows"]) == 4 and result["rows"][-1]["status"] != "request_error" else "stopped_on_error"
    result["summary"] = summarize(result["rows"])
    result["comparisons"] = [{"task": row["task_id"], "seed": row["seed"], "original_success": next(r["success"] for r in old["rows"] if r["task_id"] == row["task_id"] and r["repeat"] == row["repeat"]), "rephrased_success": row["success"], "choice": row["choice"]} for row in result["rows"]]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out), "state": result["state"], "comparisons": result["comparisons"], "summary": result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
