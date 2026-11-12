"""Two reproducible, local experiments. No network or model API is used."""
from __future__ import annotations

import csv
import io
import random
import re
import time
import unicodedata
from functools import lru_cache

LABELS = ["billing", "account", "delivery", "technical"]
LABEL_NAMES = {"billing": "账单付款", "account": "账户登录", "delivery": "物流配送", "technical": "技术故障"}

CASES = {
    "unicode": {
        "title": "明明都是 ABC，为什么匹配失败？",
        "task": "修复文本规范化函数，同时保留重音字符。",
        "file": "nlp/normalize.py",
        "before": "def normalize(text):\n    return text.strip().lower()",
        "clue": "[RUNTIME] normalization=NFKC; preserve accents; input includes full-width Unicode characters",
        "needles": ["normalization=NFKC", "preserve accents"],
        "tests": [("  ＡＢＣ  ", "abc"), ("CAFÉ", "café"), ("ｈｅｌｌｏ", "hello"), ("  fine  ", "fine"), ("①", "1")],
        "options": [
            {"id": "strip", "label": "只清理首尾空格", "code": "return text.strip()"},
            {"id": "lower", "label": "清理空格并转小写", "code": "return text.strip().lower()"},
            {"id": "nfkc", "label": "NFKC 规范化，再清理空格并转小写", "code": "return unicodedata.normalize('NFKC', text).strip().lower()"},
            {"id": "ascii", "label": "丢掉非 ASCII 字符", "code": "return text.encode('ascii', 'ignore').decode().strip().lower()"},
        ],
    },
    "threshold": {
        "title": "用户输入的 0，被悄悄改成了 10",
        "task": "修复阈值读取：0 是合法值，只有 None 才使用默认值。",
        "file": "nlp/config.py",
        "before": "def threshold(raw):\n    return int(raw or 10)",
        "clue": "[CONFIG] threshold=0 is explicit user input; missing means None; default=10; negatives are valid",
        "needles": ["missing means None", "negatives are valid"],
        "tests": [(0, 0), (None, 10), (-2, -2), (7, 7), ("0", 0)],
        "options": [
            {"id": "truthy", "label": "使用 raw or 10", "code": "return int(raw or 10)"},
            {"id": "none", "label": "只在 raw is None 时使用默认值", "code": "return 10 if raw is None else int(raw)"},
            {"id": "zero", "label": "所有缺失或零值均返回 0", "code": "return int(raw or 0)"},
            {"id": "clamp", "label": "使用默认值并截断负数", "code": "return max(0, int(raw or 10))"},
        ],
    },
    "csv": {
        "title": "客户名里有逗号，字段就错位了",
        "task": "修复 CSV 行解析，支持引号内逗号与双引号转义。",
        "file": "nlp/ingest.py",
        "before": "def parse_row(line):\n    return line.split(',')",
        "clue": '[SOURCE] delimiter=comma; quoting=RFC4180; escaped quotes use double quotes; preserve field contents',
        "needles": ["quoting=RFC4180", "preserve field contents"],
        "tests": [('"Lee, Ada",support', ["Lee, Ada", "support"]), ('"say ""hi""",ok', ['say "hi"', "ok"]), ("a,b,c", ["a", "b", "c"]), ('"",x', ["", "x"]), ('"a,b",c,d', ["a,b", "c", "d"])],
        "options": [
            {"id": "comma", "label": "按每个逗号分割", "code": "return line.split(',')"},
            {"id": "pipe", "label": "改为竖线分割", "code": "return line.split('|')"},
            {"id": "csv", "label": "使用 Python 标准 CSV 解析器", "code": "return next(csv.reader([line]))"},
            {"id": "remove", "label": "先删除引号，再按逗号分割", "code": "return line.replace(chr(34), '').split(',')"},
        ],
    },
}


def case_list():
    return [{"id": key, **{k: val[k] for k in ("title", "task", "file", "before", "options")}} for key, val in CASES.items()]


def execute_patch(case_id, patch_id, value):
    # Explicit implementations only; submitted text is never executed.
    if case_id == "unicode":
        funcs = {"strip": lambda x: x.strip(), "lower": lambda x: x.strip().lower(), "nfkc": lambda x: unicodedata.normalize("NFKC", x).strip().lower(), "ascii": lambda x: x.encode("ascii", "ignore").decode().strip().lower()}
    elif case_id == "threshold":
        funcs = {"truthy": lambda x: int(x or 10), "none": lambda x: 10 if x is None else int(x), "zero": lambda x: int(x or 0), "clamp": lambda x: max(0, int(x or 10))}
    else:
        funcs = {"comma": lambda x: x.split(","), "pipe": lambda x: x.split("|"), "csv": lambda x: next(csv.reader([x])), "remove": lambda x: x.replace('"', "").split(",")}
    return funcs[patch_id](value)


def evaluate_patch(case_id, patch_id):
    result = []
    for value, expected in CASES[case_id]["tests"]:
        try:
            actual = execute_patch(case_id, patch_id, value)
            result.append({"input": repr(value), "expected": repr(expected), "actual": repr(actual), "passed": actual == expected})
        except Exception as exc:
            result.append({"input": repr(value), "expected": repr(expected), "actual": type(exc).__name__ + ": " + str(exc), "passed": False})
    return result


def generate_log(case_id, noise=140, seed=7):
    case = CASES[case_id]
    rng = random.Random(seed)
    lines = ["================ local text pipeline: test session ================", "platform win32 -- Python 3 -- offline controlled fixture", f"rootdir: ./workspace/{case_id}"]
    anchor = max(1, min(noise - 1, noise // 3))
    for i in range(noise):
        if i == anchor:
            lines.append(case["clue"])
        lines.append(f"tests/test_pipeline.py::test_batch_{i:04d} PASSED [{int((i+1)/max(noise,1)*100):3d}%] -- batch={rng.randrange(10,99)}")
    lines.extend(["", "============================= FAILURES =============================", f"FAILED tests/test_{case_id}.py::test_edge_case", f"  File \"{case['file']}\", line 2, in pipeline", f"    {case['before'].splitlines()[-1].strip()}", "E   AssertionError: actual output differs from expected on edge cases", f"SUMMARY: {noise} passed, 1 failed; inspect the runtime contract before patching"])
    return "\n".join(lines)


def compress_log(log, mode, budget=1100, patterns=""):
    lines = log.splitlines()
    if mode == "full":
        return log
    if mode == "errors":
        selected = [line for line in lines if re.search(r"FAILED|FAILURES|AssertionError|^E |SUMMARY|File ", line)]
    elif mode in ("context", "custom"):
        expression = r"\[RUNTIME\]|\[CONFIG\]|\[SOURCE\]|FAILED|AssertionError|^E |SUMMARY|File "
        if mode == "custom":
            if len(patterns) > 300:
                raise ValueError("自定义关键词最多 300 字符。")
            # Literal keywords avoid regex denial of service and are easy to edit.
            terms = [term.strip() for term in patterns.split("|") if term.strip()]
            selected = [line for line in lines if any(term.lower() in line.lower() for term in terms)]
        else:
            selected = [line for line in lines if re.search(expression, line)]
        selected = ["[summary] passing test lines omitted; original evidence stays in the local log"] + selected
    else:
        raise ValueError("未知压缩方式")
    text = "\n".join(selected)
    # The cap applies after selection; this loss is visible and evaluated.
    if len(text) > budget:
        text = text[:max(0, budget - 30)] + "\n[truncated: character budget]"
    return text


def compress_experiment(params):
    case_id = params.get("case", "unicode")
    if case_id not in CASES:
        raise ValueError("未知案例")
    noise = max(10, min(600, int(params.get("noise", 140))))
    budget = max(120, min(12000, int(params.get("budget", 1100))))
    mode = params.get("mode", "errors")
    log = generate_log(case_id, noise, int(params.get("seed", 7)))
    compressed = compress_log(log, mode, budget, params.get("patterns", ""))
    if isinstance(params.get("override"), str):
        compressed = params["override"][:100000]
    return {"original": log, "compressed": compressed, "original_chars": len(log), "compressed_chars": len(compressed), "saved_percent": round(100 * (1 - len(compressed) / len(log)), 1), "mode": mode, "case": case_id}


def run_repair(params):
    experiment = compress_experiment(params)
    case_id, visible = experiment["case"], experiment["compressed"]
    # Same transparent diagnosis policy for every compression method. It sees only
    # visible text, not hidden tests, annotations or the requested compressor mode.
    policies = {"unicode": ("normalization=NFKC", "nfkc", "lower"), "threshold": ("missing means None", "none", "truthy"), "csv": ("quoting=RFC4180", "csv", "comma")}
    signal, targeted, fallback = policies[case_id]
    chosen = params.get("patch", "auto")
    if chosen == "auto":
        chosen = targeted if signal in visible else fallback
    if chosen not in {o["id"] for o in CASES[case_id]["options"]}:
        raise ValueError("未知修复选项")
    tests = evaluate_patch(case_id, chosen)
    option = next(x for x in CASES[case_id]["options"] if x["id"] == chosen)
    return {**experiment, "patch": chosen, "patch_label": option["label"], "patch_code": option["code"], "tests": tests, "passed": sum(t["passed"] for t in tests), "total": len(tests), "success": all(t["passed"] for t in tests), "evidence": [{"text": s, "retained": s in visible} for s in CASES[case_id]["needles"]], "executor": "固定规则诊断器；不是 LLM。可手动选择修复，模拟你自己看到日志后的决策。"}


# Synthetic support tickets. Labels denote the requested action, not every topic
# mentioned in the text. The corpus is self-authored and generated locally.
REQUESTS = {
    "billing": ["refund the payment", "send my invoice", "fix the duplicate charge", "cancel this subscription", "check my credit card charge", "correct the bill"],
    "account": ["reset my password", "unlock my login", "recover my account", "change my email address", "help with sign in", "restore account access"],
    "delivery": ["track my parcel", "change the shipping address", "locate the missing package", "check delivery status", "reschedule the shipment", "find my tracking number"],
    "technical": ["fix the app crash", "repair the server error", "debug the blank screen", "resolve the network timeout", "fix the broken upload", "restart the failing application"],
}
TOPICS = {"billing": "payment invoice billing refund", "account": "password login account access", "delivery": "parcel shipping delivery package", "technical": "crash server error application"}


def make_tickets(seed, per_label, hard_ratio):
    rng = random.Random(seed)
    records = []
    for label in LABELS:
        for i in range(per_label):
            request = rng.choice(REQUESTS[label])
            hard = rng.random() < hard_ratio
            if hard:
                other = rng.choice([l for l in LABELS if l != label])
                distractor = rng.choice(TOPICS[other].split())
                template = rng.choice([
                    "This is not a {other} issue. Please {request}.",
                    "My {other} problem is already resolved. Now I need to {request}.",
                    "Do not route this to {other}. The actual request is to {request}.",
                    "I mentioned {other} earlier, but my current request is to {request}.",
                ])
                text = template.format(other=distractor, request=request)
            else:
                text = rng.choice(["Please {request}.", "Can you {request}?", "I need you to {request}."]).format(request=request)
            # IDs are excluded from text to prevent accidental label shortcuts.
            records.append({"text": text, "label": label, "kind": "含干扰信息" if hard else "直接请求", "id": f"{seed}-{label}-{i}"})
    rng.shuffle(records)
    return records


MODELS = [
    {"id": "keywords", "name": "关键词捷径", "detail": "从左到右遇到第一个关键词就决定类别"},
    {"id": "word_nb", "name": "词袋 · NB", "detail": "词级 TF-IDF + 朴素贝叶斯"},
    {"id": "word_lr", "name": "词袋 · LR", "detail": "词级 TF-IDF + 逻辑回归"},
    {"id": "bigram_nb", "name": "双词组 · NB", "detail": "1–2 gram TF-IDF + 朴素贝叶斯"},
    {"id": "bigram_lr", "name": "双词组 · LR", "detail": "1–2 gram TF-IDF + 逻辑回归"},
    {"id": "char_lr", "name": "字符组 · LR", "detail": "字符 3–5 gram TF-IDF + 逻辑回归"},
]


def keyword_predict(text):
    lookup = {term: label for label in LABELS for term in TOPICS[label].split()}
    # Additional training-vocabulary terms; no gold labels are consulted.
    lookup.update({"subscription": "billing", "bill": "billing", "email": "account", "tracking": "delivery", "shipment": "delivery", "upload": "technical", "network": "technical", "screen": "technical"})
    return next((lookup[word] for word in re.findall(r"[a-z]+", text.lower()) if word in lookup), "billing")


@lru_cache(maxsize=8)
def fitted_pool(seed):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.pipeline import make_pipeline
    train = make_tickets(seed + 100, 90, 0.65)
    x, y = [r["text"] for r in train], [r["label"] for r in train]
    fitted, timings = {}, {}
    for spec in MODELS[1:]:
        mid = spec["id"]
        vector = TfidfVectorizer(analyzer="char", ngram_range=(3, 5)) if mid == "char_lr" else TfidfVectorizer(ngram_range=(1, 2) if "bigram" in mid else (1, 1))
        clf = MultinomialNB(alpha=0.3) if mid.endswith("nb") else LogisticRegression(C=5, max_iter=400, random_state=seed)
        model = make_pipeline(vector, clf)
        start = time.perf_counter()
        model.fit(x, y)
        timings[mid] = round((time.perf_counter() - start) * 1000, 2)
        fitted[mid] = model
    timings["keywords"] = 0
    return train, fitted, timings


def predictions(pool, rows):
    text = [r["text"] for r in rows]
    return {"keywords": [keyword_predict(t) for t in text], **{mid: model.predict(text).tolist() for mid, model in pool.items()}}


def accuracy(pred, rows, n=None):
    n = len(rows) if n is None else n
    return sum(pred[i] == rows[i]["label"] for i in range(n)) / n


def select_policy(kind, pred, dev, probe_n, budget, seed):
    ids = [m["id"] for m in MODELS]
    rng = random.Random(seed + 500)
    observed, trace = {}, []
    spent = 0
    def observe(mid, n):
        nonlocal spent
        previous = observed.get(mid, (0, 0))[0]
        extra = n - previous
        if extra <= 0 or spent + extra > budget:
            return False
        score = accuracy(pred[mid], dev, n)
        spent += extra
        observed[mid] = (n, score)
        trace.append({"candidate": mid, "n": n, "score": round(score * 100, 2), "cost": extra, "spent": spent})
        return True
    def ranking(candidates):
        # Ties use the same predefined candidate order for every policy.
        return sorted(candidates, key=lambda m: (-observed[m][1], ids.index(m)))
    if kind == "random":
        order = ids.copy()
        rng.shuffle(order)
        for mid in order:
            observe(mid, len(dev))
    else:
        for mid in ids:
            observe(mid, probe_n)
        candidates = ranking(list(observed))
        if kind == "probe":
            # Commit to the small-probe ranking, then validate in that order.
            for mid in candidates:
                observe(mid, len(dev))
        elif kind == "halving":
            while len(candidates) > 1:
                candidates = ranking(candidates)[:max(1, (len(candidates) + 1) // 2)]
                level = min(len(dev), max(observed[m][0] for m in candidates) * 3)
                for mid in candidates:
                    observe(mid, min(level, observed[mid][0] + budget - spent))
                if spent >= budget or all(observed[m][0] == len(dev) for m in candidates):
                    break
            if candidates and spent < budget:
                mid = ranking(candidates)[0]
                observe(mid, min(len(dev), observed[mid][0] + budget - spent))
        else:
            raise ValueError("未知筛选策略")
    if not observed:
        raise ValueError("预算太小，无法开始评价")
    # Evidence from different fidelities is not ranked as if equally reliable.
    max_n = max(n for n, _ in observed.values())
    finalists = [mid for mid, (n, _) in observed.items() if n == max_n]
    chosen = ranking(finalists)[0]
    return {"id": kind, "selected": chosen, "spent": spent, "budget": budget, "selection_n": observed[chosen][0], "selection_score": round(observed[chosen][1] * 100, 2), "trace": trace}


def probe_experiment(params):
    start = time.perf_counter()
    seed = max(0, min(99999, int(params.get("seed", 7))))
    probe_n = max(4, min(24, int(params.get("probe_n", 8))))
    budget = max(96, min(576, int(params.get("budget", 144))))
    if budget < probe_n * len(MODELS):
        raise ValueError("预算至少需要覆盖所有候选的一轮小试验。")
    setting = params.get("setting", "biased")
    if setting not in ("biased", "balanced"):
        raise ValueError("未知初筛分布")
    train, pool, timings = fitted_pool(seed)
    dev = make_tickets(seed + 200, 24, 0.7)
    if setting == "biased":
        easy = [r for r in dev if r["kind"] == "直接请求"]
        hard = [r for r in dev if r["kind"] != "直接请求"]
        # Enrich ONLY the small prefix with easy tickets; retain the exact same
        # full development corpus. Distribution shift is an explicit intervention.
        dev = easy[:probe_n] + hard + easy[probe_n:]
    pred_dev = predictions(pool, dev)
    policies = [select_policy(k, pred_dev, dev, probe_n, budget, seed) for k in ("random", "probe", "halving")]
    # Only after selection, score the independently generated held-out tickets.
    test = make_tickets(seed + 300, 36, 0.75)
    pred_test = predictions(pool, test)
    scores = []
    for spec in MODELS:
        mid = spec["id"]
        scores.append({**spec, "probe_score": round(accuracy(pred_dev[mid], dev, probe_n) * 100, 2), "dev_score": round(accuracy(pred_dev[mid], dev) * 100, 2), "test_score": round(accuracy(pred_test[mid], test) * 100, 2), "fit_ms": timings[mid]})
    by_id = {s["id"]: s for s in scores}
    for policy in policies:
        policy["test_score"] = by_id[policy["selected"]]["test_score"]
        policy["dev_score"] = by_id[policy["selected"]]["dev_score"]
    examples = [{**row, "true_name": LABEL_NAMES[row["label"]], "predictions": {mid: LABEL_NAMES[p[i]] for mid, p in pred_test.items()}} for i, row in enumerate(test) if pred_test["keywords"][i] != row["label"]][:8]
    if not examples:
        examples = test[:4]
    return {"seed": seed, "setting": setting, "probe_n": probe_n, "budget": budget, "train_n": len(train), "dev_n": len(dev), "test_n": len(test), "scores": scores, "policies": policies, "probe_samples": [{**r, "true_name": LABEL_NAMES[r["label"]]} for r in dev[:probe_n]], "test_examples": examples, "elapsed_ms": round((time.perf_counter() - start) * 1000), "protocol": "自制合成工单；候选模型真实训练。预算单位=一个候选读取一个带标签的开发样本。候选训练成本对各策略相同，单独显示；测试集只在选择结束后评分，不回流选择器。相同模板族不代表真实业务泛化。"}
