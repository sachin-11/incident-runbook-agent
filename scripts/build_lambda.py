"""Build the tool Lambda bundle in build/lambda/ without Docker.

    uv run python scripts/build_lambda.py

Installs the runtime dependency (pydantic, pinned to the version in uv.lock) as manylinux arm64
wheels for Python 3.12, then copies the `tools` and `observability` packages. boto3 comes from
the Lambda runtime. Every tool function uses this one bundle with its own handler.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "lambda"
PACKAGES = ("tools", "observability")
RUNTIME_DEPS = ("pydantic",)
PLATFORM = "aarch64-manylinux2014"  # Lambda arm64 (Graviton)
PYTHON = "3.12"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    pins = [f"{dep}=={version(dep)}" for dep in RUNTIME_DEPS]
    subprocess.run(  # noqa: S603 (fixed argv, no shell)
        [  # noqa: S607 (uv is a required dev tool)
            "uv",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(OUT),
            "--python-platform",
            PLATFORM,
            "--python-version",
            PYTHON,
            "--only-binary",
            ":all:",
            *pins,
        ],
        check=True,
    )
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "README.md")
    for pkg in PACKAGES:
        shutil.copytree(ROOT / pkg, OUT / pkg, ignore=ignore)
    size_kb = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) // 1024
    print(f"built {OUT} ({size_kb} KB) with {', '.join(pins)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
