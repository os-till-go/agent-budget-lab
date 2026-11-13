"""Two real Ollama calls isolating rule interpretation from patch-ID selection.

No candidate code is supplied. This changed task is a development diagnostic,
not another condition of the repair benchmark. Default only prints the plan.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_client import ModelClient
from probe_contract_wording import REPHRASINGS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = {"type": "object", "properties": {"when_none": {"type": "integer"}, "when_zero": {"type": "integer"}, "when_minus_two": {"type": "integer"}}, "required": ["when_none", "when_zero", "when_minus_two"], "additionalProperties": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Two rule-interpretation probes, no candidate code, no held-out tasks.")
        return
    client = ModelClient()
    if client.provider != "ollama":
        raise ValueError("This diagnostic uses native Ollama structured output")
    result = {"id": uuid.uuid4().hex[:12], "kind": "development-rule-interpretation-v1", "started_at": datetime.now(timezone.utc).isoformat(), "model": client.status(), "schema": SCHEMA, "rows": [], "limitations": ["Two observed development cases only.", "Task and output schema differ from patch selection; do not pool accuracies.", "No candidates are supplied; this does not prove the model can interpret Python code."]}
    for index, contract in enumerate(REPHRASINGS.values()):
        messages = [{"role": "system", "content": "Read the runtime contract. Report the expected integer outputs for value=None, value=0 and value=-2. Return only JSON with keys when_none, when_zero, when_minus_two."}, {"role": "user", "content": contract}]
        request = {"model": client.model, "messages": messages, "stream": False, "format": SCHEMA, "options": {"temperature": 0, "seed": 7, "num_predict": 100, "num_ctx": 8192}}
        started = time.perf_counter()
        raw = client._request("/api/chat", request)
        expected = {"when_none": 10, "when_zero": 0 if index == 0 else 10, "when_minus_two": -2}
        try:
            parsed = json.loads(raw.get("message", {}).get("content", ""))
        except ValueError:
            parsed = None
        result["rows"].append({"variant": index, "request": request, "raw_response": raw, "parsed": parsed, "expected": expected, "success": parsed == expected, "elapsed_ms": round((time.perf_counter()-started)*1000, 2)})
    result["state"] = "completed"
    path = ROOT / "runs" / (result["id"] + ".json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(path), "results": [{"variant": r["variant"], "parsed": r["parsed"], "success": r["success"]} for r in result["rows"]]}, indent=2))


if __name__ == "__main__":
    main()
