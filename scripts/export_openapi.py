from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI schema to disk.")
    parser.add_argument(
        "--output",
        default="contracts/openapi.json",
        help="Path to write the OpenAPI JSON file.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for the JSON output.",
    )
    return parser.parse_args()


def main() -> int:
    from app.api.main import app

    args = parse_args()
    output_path = (PROJECT_ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=args.indent, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
