"""Paired, self-authored diagnostic fixtures. Model-visible data excludes gold/tests.

Within a pair only the deployed contract changes; options and problem stay equal.
This is a controlled diagnostic pilot, not a real-repository repair benchmark.
"""
import csv
import hashlib
import random
import unicodedata
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP

VERSION = "paired-contracts-1"
METHODS = {"full": "完整输出", "errors": "简单错误过滤", "structured": "保留配置与错误", "no_log": "无日志对照", "oracle": "人工关键行参考（oracle）"}
TASK = "Repair the helper to comply with the deployed runtime contract. Select one candidate implementation. Do not assume that a convention used in another deployment applies here."


def _families():
    return {
        "threshold": dict(split="dev", before="def resolve(value):\n    return 10",
            codes=["return 10 if value is None else int(value)", "return 10 if value is None or value == 0 else int(value)", "return max(0, int(value or 10))", "return 0 if value is None else int(value)"],
            funcs=[lambda x: 10 if x is None else int(x), lambda x: 10 if x is None or x == 0 else int(x), lambda x: max(0, int(x or 10)), lambda x: 0 if x is None else int(x)],
            contracts=["default=10; missing=None; zero_is=explicit_value; negative_values=valid", "default=10; missing=None; zero_is=default_sentinel; negative_values=valid"],
            inputs=[None, 0, -2, 4, "7"]),
        "unicode": dict(split="dev", before="def normalize(text):\n    return text.strip()",
            codes=["return unicodedata.normalize('NFC', text).strip().lower()", "return unicodedata.normalize('NFKC', text).strip().lower()", "return text.encode('ascii', 'ignore').decode().strip().lower()", "return text.strip().lower()"],
            funcs=[lambda x: unicodedata.normalize("NFC", x).strip().lower(), lambda x: unicodedata.normalize("NFKC", x).strip().lower(), lambda x: x.encode("ascii", "ignore").decode().strip().lower(), lambda x: x.strip().lower()],
            contracts=["normalization=NFC; case=lower; whitespace=strip; preserve_accents=true", "normalization=NFKC; case=lower; whitespace=strip; preserve_accents=true"],
            inputs=[" ＡＢＣ ", "CAFÉ", "①", " E\u0301 ", " Fine "]),
        "delimiter": dict(split="dev", before="def parse_row(line):\n    return [line]",
            codes=["return next(csv.reader([line], delimiter=','))", "return next(csv.reader([line], delimiter=';'))", "return line.split(',')", "return line.split(';')"],
            funcs=[lambda x: next(csv.reader([x], delimiter=",")), lambda x: next(csv.reader([x], delimiter=";")), lambda x: x.split(","), lambda x: x.split(";")],
            contracts=["delimiter=comma; quoted_fields=true; doubled_quotes=escape; preserve_whitespace=true", "delimiter=semicolon; quoted_fields=true; doubled_quotes=escape; preserve_whitespace=true"],
            inputs=['"a,b";c', '"a;b",c', '"say ""hi""",ok', '"say ""hi"";ok', "a,b;c"]),
        "rounding": dict(split="holdout", before="def amount(text):\n    return text",
            codes=["return str(Decimal(text).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN))", "return str(Decimal(text).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))", "return str(round(float(text), 2))", "return str(int(float(text)))"],
            funcs=[lambda x: str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)), lambda x: str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), lambda x: str(round(float(x), 2)), lambda x: str(int(float(x)))],
            contracts=["precision=0.01; rounding=ROUND_HALF_EVEN; input=decimal_string; output=fixed_decimal_string", "precision=0.01; rounding=ROUND_HALF_UP; input=decimal_string; output=fixed_decimal_string"],
            inputs=["2.345", "2.355", "-2.345", "0", "1.005"]),
        "path_case": dict(split="holdout", before="def same_key(left, right):\n    return False",
            codes=["return left == right", "return left.casefold() == right.casefold()", "return left.strip() == right.strip()", "return left.lower().replace(' ', '') == right.lower().replace(' ', '')"],
            funcs=[lambda a: a[0] == a[1], lambda a: a[0].casefold() == a[1].casefold(), lambda a: a[0].strip() == a[1].strip(), lambda a: a[0].lower().replace(" ", "") == a[1].lower().replace(" ", "")],
            contracts=["key_comparison=case_sensitive; whitespace=significant", "key_comparison=unicode_casefold; whitespace=significant"],
            inputs=[("Readme", "README"), ("straße", "STRASSE"), (" a", "a"), ("x", "x"), ("a b", "ab")]),
    }


def task_ids(split="dev"):
    return [f"{name}-{variant}" for name, f in _families().items() if f["split"] == split for variant in (0, 1)]


def fixture(task_id):
    family, variant = task_id.rsplit("-", 1)
    if family not in _families() or variant not in ("0", "1"):
        raise ValueError("未知诊断任务")
    f = _families()[family]
    return family, int(variant), f


def options(task_id, seed):
    family, _, f = fixture(task_id)
    order = list(range(4))
    rng = random.Random(f"{family}:{seed}:options")
    rng.shuffle(order)
    return [{"id": chr(65 + i), "code": f["codes"][index], "index": index} for i, index in enumerate(order)]


def public_task(task_id, seed=7):
    _, _, f = fixture(task_id)
    return {"task": TASK, "before": f["before"], "candidates": [{"id": o["id"], "code": o["code"]} for o in options(task_id, seed)]}


def raw_log(task_id, seed=7, noise=60):
    family, variant, f = fixture(task_id)
    rng = random.Random(f"{family}:{seed}:log")
    anchor = rng.randrange(max(1, noise))
    lines = ["[RUN] command=python -m pytest; exit_code=1", "[ENV] python=3; suite=deployment_checks"]
    for i in range(noise):
        if i == anchor:
            lines.append("[CONFIG] " + f["contracts"][variant])
        lines.append(f"tests/test_batch_{i:04d}.py PASSED batch={rng.randrange(100, 999)}")
    lines += ["[ERROR] AssertionError: implementation violates the deployed contract", "[RESULT] 1 failed; inspect configuration before choosing a replacement"]
    return "\n".join(lines)


def view(task_id, method, seed=7, noise=60, budget=1200):
    if method not in METHODS:
        raise ValueError("未知输入条件")
    raw = raw_log(task_id, seed, noise)
    lines = raw.splitlines()
    if method == "full":
        selected = lines
    elif method == "no_log":
        return "[No tool output supplied in this control condition.]"
    elif method == "oracle":
        selected = [line for line in lines if line.startswith("[CONFIG]")]
    elif method == "errors":
        selected = [line for line in lines if line.startswith(("[ERROR]", "[RESULT]"))]
    else:
        selected = [line for line in lines if line.startswith(("[CONFIG]", "[ENV]", "[ERROR]", "[RESULT]", "[RUN]"))]
    if method == "full":
        return raw
    marker = "[Some source lines omitted; the original log remains available.]"
    kept = [marker]
    for line in selected:
        if len("\n".join(kept + [line])) <= budget:
            kept.append(line)
    return "\n".join(kept)


def read_log(task_id, start, count, seed=7, noise=60):
    lines = raw_log(task_id, seed, noise).splitlines()
    start = max(1, int(start))
    count = max(1, min(100, int(count)))
    return {"start": start, "total_lines": len(lines), "lines": [f"{i+1}: {lines[i]}" for i in range(start-1, min(start-1+count, len(lines)))]}


def grade(task_id, choice, seed=7):
    _, variant, f = fixture(task_id)
    chosen = next((o for o in options(task_id, seed) if o["id"] == choice), None)
    if chosen is None:
        return {"success": False, "passed": 0, "total": len(f["inputs"])}
    passed = 0
    for value in f["inputs"]:
        try:
            passed += f["funcs"][chosen["index"]](value) == f["funcs"][variant](value)
        except Exception:
            pass
    return {"success": passed == len(f["inputs"]), "passed": passed, "total": len(f["inputs"])}


def manifest():
    data = [(t, public_task(t), raw_log(t), fixture(t)[2]["contracts"][fixture(t)[1]]) for split in ("dev", "holdout") for t in task_ids(split)]
    return hashlib.sha256(repr(data).encode()).hexdigest()
