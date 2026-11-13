"""Offline contract checks. Fake transport responses are never research results."""
import json
import unittest
from unittest.mock import patch
import model_experiment as experiment
from model_client import ModelClient, ModelError
import model_tasks as tasks


class ScriptedClient:
    provider = "ollama"
    def __init__(self, actions):
        self.actions = iter(actions)
    def chat(self, messages, seed, allow_query=False):
        value = next(self.actions)
        if isinstance(value, Exception):
            raise value
        return {"content": json.dumps(value), "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": None}, "resolved_model": "test-double", "finish_reason": "stop", "elapsed_ms": 1}
    def status(self):
        return {"model": "test-double"}


def answer(choice):
    return {"action": "answer", "choice": choice}


QUERY = {"action": "read_log", "start": 1, "count": 100}


class PairedTaskTests(unittest.TestCase):
    def test_only_runtime_evidence_changes_within_pairs(self):
        for family in ("threshold", "unicode", "delimiter"):
            a, b = family+"-0", family+"-1"
            self.assertEqual(tasks.public_task(a), tasks.public_task(b))
            self.assertEqual(tasks.view(a, "no_log"), tasks.view(b, "no_log"))
            self.assertEqual(tasks.view(a, "errors"), tasks.view(b, "errors"))
            self.assertNotEqual(tasks.view(a, "full"), tasks.view(b, "full"))
            # No constant candidate can pass both runtime contracts.
            self.assertFalse(any(tasks.grade(a, c)["success"] and tasks.grade(b, c)["success"] for c in "ABCD"))

    def test_rules_do_not_require_gold_or_case_specific_keywords(self):
        with patch.object(tasks, "raw_log", return_value="[CONFIG] arbitrary_unseen_condition=yes\nnoise\n[ERROR] failed"):
            out = tasks.view("threshold-0", "structured")
        self.assertIn("arbitrary_unseen_condition", out)
        self.assertNotIn("\nnoise", out)

    def test_whole_line_budget_and_source_query_bounds(self):
        for method in ("errors", "structured", "oracle"):
            out = tasks.view("threshold-0", method, budget=180)
            self.assertLessEqual(len(out), 180)
            for line in out.splitlines()[1:]:
                self.assertIn(line, tasks.raw_log("threshold-0").splitlines())
        excerpt = tasks.read_log("threshold-0", -100, 9999)
        self.assertEqual(excerpt["start"], 1)
        self.assertLessEqual(len(excerpt["lines"]), 100)

    def test_reserved_families_are_not_dev_or_enabled_implicitly(self):
        self.assertFalse(set(tasks.task_ids()) & set(tasks.task_ids("holdout")))
        with self.assertRaises(ValueError):
            experiment.normalize({"task_ids": ["rounding-0"]})


class RunnerTests(unittest.TestCase):
    def config(self, queries=2):
        return experiment.normalize({"max_queries": queries})

    def test_retrieval_uses_original_and_accumulates_actual_usage(self):
        r = experiment.run_one(ScriptedClient([QUERY, answer("B")]), "threshold-0", "errors", self.config())
        self.assertEqual((r["queries"], r["model_calls"], r["input_tokens"], r["output_tokens"]), (1, 2, 200, 40))
        self.assertIn("zero_is=explicit_value", r["trace"][1]["messages"][-1]["content"])
        self.assertGreater(len(r["trace"][1]["messages"]), len(r["trace"][0]["messages"]))

    def test_query_cap_and_no_log_control_cannot_be_bypassed(self):
        for method, cap in (("errors", 1), ("no_log", 0)):
            r = experiment.run_one(ScriptedClient([QUERY, QUERY, QUERY]), "threshold-0", method, self.config(1))
            self.assertEqual(r["queries"], cap)
            self.assertEqual(r["model_calls"], cap+1)
            self.assertEqual(r["status"], "invalid_action")

    def test_gold_feedback_cannot_change_model_conversation(self):
        first = experiment.run_one(ScriptedClient([QUERY, answer("B")]), "threshold-0", "errors", self.config())
        with patch.object(tasks, "grade", return_value={"success": True, "passed": 999, "total": 999}):
            changed = experiment.run_one(ScriptedClient([QUERY, answer("B")]), "threshold-0", "errors", self.config())
        self.assertEqual(first["trace"], changed["trace"])
        for call in first["trace"]:
            supplied = json.loads(call["messages"][1]["content"])
            self.assertFalse({"task_id", "gold", "tests", "method", "variant"} & supplied.keys())

    def test_failed_transport_is_not_retried_or_counted_as_zero_usage(self):
        r = experiment.run_one(ScriptedClient([ModelError("unavailable")]), "threshold-0", "errors", self.config())
        self.assertEqual(r["model_calls"], 1)
        self.assertIsNone(r["input_tokens"])
        self.assertFalse(r["success"])
        batch = experiment.run_batch({}, ScriptedClient([ModelError("unavailable")]), persist=False)
        self.assertEqual(batch["state"], "stopped_on_error")
        self.assertEqual(len(batch["rows"]), 1)

    def test_candidate_order_is_paired_but_changes_across_repeats(self):
        r = experiment.run_batch({"methods": ["no_log"], "repeats": 2}, ScriptedClient([answer("A")]*4), persist=False)
        self.assertEqual(len(r["rows"]), 4)
        self.assertEqual({x["seed"] for x in r["rows"]}, {7, 8})
        self.assertEqual(r["summary"][0]["complete_pairs"], 2)

    def test_compatible_usage_is_reported_without_inventing_cache_counts(self):
        with patch.dict("os.environ", {"ABL_PROVIDER": "compatible", "ABL_BASE_URL": "https://example.com/v1", "ABL_MODEL": "test"}):
            client = ModelClient()
        with patch.object(client, "_request", return_value={"model": "pinned-model", "choices": [{"message": {"content": '{"action":"answer","choice":"B"}'}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 123, "completion_tokens": 45}}) as transport:
            result = client.chat([{"role": "user", "content": "test"}])
        self.assertEqual(result["usage"], {"input_tokens": 123, "output_tokens": 45, "cached_input_tokens": None})
        self.assertEqual(result["resolved_model"], "pinned-model")
        self.assertEqual(transport.call_args.args[0], "/chat/completions")

    def test_native_schema_exposes_only_actions_still_available(self):
        with patch.dict("os.environ", {"ABL_PROVIDER": "ollama", "ABL_BASE_URL": "http://127.0.0.1:11434"}):
            client = ModelClient()
        with patch.object(client, "_request", return_value={"message": {"content": "{}"}, "prompt_eval_count": 50, "eval_count": 10}) as transport:
            client.chat([], allow_query=False)
            self.assertEqual(transport.call_args.args[1]["format"]["properties"]["action"]["enum"], ["answer"])
            client.chat([], allow_query=True)
            self.assertIn("read_log", transport.call_args.args[1]["format"]["properties"]["action"]["enum"])

    def test_endpoint_cannot_embed_credentials_or_send_plaintext_remotely(self):
        for url in ("http://example.com", "https://user:password@example.com", "https://example.com?key=secret"):
            with patch.dict("os.environ", {"ABL_BASE_URL": url}):
                with self.assertRaises(ValueError):
                    ModelClient()


if __name__ == "__main__":
    unittest.main()
