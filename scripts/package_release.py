"""Package public source and examples, never a virtualenv or local credentials."""
import argparse
import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = [".gitattributes", ".gitignore", "README.md", "README.zh-CN.md", "LICENSE", "CHANGELOG.md", "VERIFICATION.md", "requirements.txt", "lab.py", "server.py", "test_lab.py", "model_tasks.py", "model_client.py", "model_experiment.py", "test_model_experiment.py", "start-demo.cmd"]
FOLDERS = ["web", "examples", "previews", "scripts", "docs", ".github"]


def package(version):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version):
        raise ValueError("Version must look like v0.1.0")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / f"agent-budget-lab-{version}.zip"
    paths = [ROOT / name for name in ROOT_FILES]
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in sorted(paths):
            if not path.is_file():
                raise FileNotFoundError(path)
            info = zipfile.ZipInfo(str(Path(f"agent-budget-lab-{version}") / path.relative_to(ROOT)).replace("\\", "/"), date_time=(2026, 11, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = path.read_bytes()
            if path.suffix not in {".jpg", ".png"}:
                data = data.replace(b"\r\n", b"\n")
                if path.suffix == ".cmd":
                    data = data.replace(b"\n", b"\r\n")
            target.writestr(info, data)
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = output / "SHA256SUMS.txt"
    sums.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"{archive}\n{digest}\n{sums}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v0.1.0")
    package(parser.parse_args().version)
