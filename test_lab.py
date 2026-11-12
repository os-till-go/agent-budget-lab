"""Checks for information loss, real execution, budget accounting and leakage."""
import copy
import unittest
from unittest.mock import patch
import lab


class CompressionTests(unittest.TestCase):
    def test_complete_contract_can_repair_all_cases(self):
        for case in lab.CASES:
            with self.subTest(case=case):
                self.assertTrue(lab.run_repair({"case": case, "mode": "full"})["success"])
                self.assertTrue(lab.run_repair({"case": case, "mode": "context"})["success"])

    def test_more_character_savings_can_lose_required_information(self):
        for case in lab.CASES:
            lossy = lab.run_repair({"case": case, "mode": "errors"})
            faithful = lab.run_repair({"case": case, "mode": "context"})
            self.assertGreater(lossy["saved_percent"], faithful["saved_percent"])
            self.assertFalse(lossy["success"])

    def test_executor_uses_visible_text_not_compressor_name(self):
        text = lab.compress_experiment({"case": "unicode", "mode": "context"})["compressed"]
        removed = text.replace("normalization=NFKC", "normalization=unknown")
        self.assertTrue(lab.run_repair({"case": "unicode", "mode": "errors", "override": text})["success"])
        self.assertFalse(lab.run_repair({"case": "unicode", "mode": "full", "override": removed})["success"])

    def test_manual_patch_is_really_evaluated(self):
        r = lab.run_repair({"case": "csv", "mode": "errors", "patch": "csv"})
        self.assertTrue(r["success"])
        self.assertEqual(r["tests"][1]["actual"], repr(['say "hi"', "ok"]))

    def test_budget_can_cut_essential_evidence(self):
        for mode in ("errors", "context", "custom"):
            r = lab.compress_experiment({"mode": mode, "budget": 180, "patterns": "PASSED|RUNTIME"})
            self.assertLessEqual(len(r["compressed"]), 180)

    def test_zero_and_negative_are_valid(self):
        self.assertEqual(lab.execute_patch("threshold", "none", 0), 0)
        self.assertEqual(lab.execute_patch("threshold", "none", -2), -2)
        self.assertEqual(lab.execute_patch("threshold", "none", None), 10)


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.biased = lab.probe_experiment({"seed": 7, "setting": "biased"})
        cls.balanced = lab.probe_experiment({"seed": 7, "setting": "balanced"})

    def test_reordering_keeps_full_corpus_results(self):
        for a, b in zip(self.biased["scores"], self.balanced["scores"]):
            self.assertEqual(a["dev_score"], b["dev_score"])
            self.assertEqual(a["test_score"], b["test_score"])
        self.assertTrue(all(r["kind"] == "直接请求" for r in self.biased["probe_samples"]))

    def test_all_costs_are_incremental_and_within_cap(self):
        for seed in (7, 11):
            dev = lab.make_tickets(seed + 200, 24, 0.7)
            pred = {m["id"]: [r["label"] for r in dev] for m in lab.MODELS}
            for n, budget in ((4, 96), (8, 144), (16, 240), (24, 576)):
                for kind in ("random", "probe", "halving"):
                    r = lab.select_policy(kind, pred, dev, n, budget, seed)
                    observed, spent = {}, 0
                    for item in r["trace"]:
                        expected = item["n"] - observed.get(item["candidate"], 0)
                        self.assertEqual(item["cost"], expected)
                        self.assertGreater(expected, 0)
                        observed[item["candidate"]] = item["n"]
                        spent += item["cost"]
                        self.assertEqual(item["spent"], spent)
                    self.assertEqual(spent, r["spent"])
                    self.assertLessEqual(spent, budget)
                    self.assertIn(r["selected"], observed)

    def test_changing_test_labels_cannot_change_selection(self):
        original = lab.make_tickets
        def counterfactual(seed, per_label, hard_ratio):
            rows = original(seed, per_label, hard_ratio)
            if seed == 307:
                rows = copy.deepcopy(rows)
                for row in rows:
                    row["label"] = lab.LABELS[(lab.LABELS.index(row["label"]) + 1) % len(lab.LABELS)]
            return rows
        with patch.object(lab, "make_tickets", side_effect=counterfactual):
            changed = lab.probe_experiment({"seed": 7})
        self.assertEqual([p["selected"] for p in changed["policies"]], [p["selected"] for p in self.biased["policies"]])
        self.assertNotEqual([p["test_score"] for p in changed["policies"]], [p["test_score"] for p in self.biased["policies"]])

    def test_deterministic_scores_and_trace(self):
        repeated = lab.probe_experiment({"seed": 7})
        self.assertEqual(repeated["policies"], self.biased["policies"])
        self.assertEqual(repeated["scores"], self.biased["scores"])

    def test_data_split_ids_do_not_overlap(self):
        sets = [{r["id"] for r in lab.make_tickets(seed, 20, 0.7)} for seed in (107, 207, 307)]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
