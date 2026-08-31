import argparse
import os
import sys

import pandas as pd

from .engine import GoPlayEngine


def _detect_input_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm"):
        return "excel"
    return "csv"


def _build_sample(input_path: str, input_format: str, header_row: int) -> str:
    """Read the header and first few rows so Claude sees the real column names."""
    if input_format == "excel":
        sheets = pd.read_excel(input_path, header=header_row, sheet_name=None)
        parts = []
        for name, sheet in sheets.items():
            parts.append(f"# Sheet: {name}\n{sheet.head(3).to_csv(index=False)}")
        return "\n".join(parts)

    df = pd.read_csv(input_path, header=header_row, nrows=3)
    return df.to_csv(index=False)


def _default_output_path(input_path: str, input_format: str) -> str:
    root, _ = os.path.splitext(input_path)
    ext = ".xlsx" if input_format == "excel" else ".csv"
    return f"{root}.transformed{ext}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goplay",
        description="Self-healing document and CSV transformation engine powered by Claude.",
    )
    parser.add_argument("input", help="Path to the input CSV or Excel file.")
    parser.add_argument(
        "prompt",
        help="Plain-English description of the transformation you want.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path for the transformed file "
        "(default: <input>.transformed.<ext>). Ignored for aggregation queries.",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "excel"],
        help="Override input format detection.",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=0,
        help="0-indexed header row for files with non-standard headers (default: 0).",
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (defaults to the ANTHROPIC_API_KEY environment variable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 2

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: no API key provided. Set ANTHROPIC_API_KEY or pass --api-key.",
            file=sys.stderr,
        )
        return 2

    input_format = args.format or _detect_input_format(args.input)
    output_path = args.output or _default_output_path(args.input, input_format)

    try:
        sample = _build_sample(args.input, input_format, args.header_row)
    except Exception as e:
        print(f"Error reading input file: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    engine = GoPlayEngine(api_key=api_key)
    success, message = engine.execute_transformation_with_repair(
        input_csv_path=args.input,
        output_csv_path=output_path,
        user_prompt=args.prompt,
        df_sample_str=sample,
        input_format=input_format,
        header_row=args.header_row,
    )

    print(message)
    if not success:
        return 1
    if os.path.exists(output_path):
        print(f"\n✅ Wrote output to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
