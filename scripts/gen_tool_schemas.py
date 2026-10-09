"""Write tools/schemas/<group>.openapi.json from the tool models.

uv run python scripts/gen_tool_schemas.py           # regenerate
uv run python scripts/gen_tool_schemas.py --check   # exit 1 if files are out of date
"""

from __future__ import annotations

import argparse
import json
import sys

from tools.openapi import build_openapi, schema_path
from tools.registry import ACTION_GROUPS


def render(group: str) -> str:
    return json.dumps(build_openapi(group), indent=2, ensure_ascii=False) + "\n"  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for group in ACTION_GROUPS:
        path = schema_path(group)
        text = render(group)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path}")
    if stale:
        print(f"out of date: {', '.join(stale)}; run scripts/gen_tool_schemas.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
