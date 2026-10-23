"""csvjson — convert between CSV and JSON in both directions, with explicit failure modes.

    python csvjson.py to-json people.csv --indent 2
    python csvjson.py to-json people.tsv --delimiter '\t' --strict
    python csvjson.py to-csv rows.json --missing ""
    cat rows.json | python csvjson.py to-csv -

Design notes
------------
* CSV -> JSON keeps every value as a string. Type inference is deliberately absent:
  a zip code, a phone number and an account id must not silently become numbers.
* JSON -> CSV takes an array of flat objects, unions their keys in first-seen order,
  and fills missing keys so every row has the same width.
* Errors are reported on stderr with a non-zero exit code, never as a half-written file.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

__version__ = "1.0.0"

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_USAGE = 64


class ConversionError(Exception):
    """A problem with the input, reported to the caller instead of a traceback."""


def _read_text(source: str, encoding: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    try:
        return path.read_text(encoding=encoding)
    except FileNotFoundError as exc:
        raise ConversionError(f"no such file: {source}") from exc
    except UnicodeDecodeError as exc:
        raise ConversionError(f"{source} is not valid {encoding}: {exc}") from exc


def _write_text(destination: str | None, text: str, encoding: str) -> None:
    if destination in (None, "-"):
        sys.stdout.write(text)
        return
    Path(destination).write_text(text, encoding=encoding)


def csv_to_json(
    text: str,
    delimiter: str = ",",
    *,
    strict: bool = False,
    indent: int = 2,
    sort_keys: bool = False,
) -> list[dict[str, str]]:
    """Parse CSV text into a list of dictionaries, one per data row."""
    if len(delimiter) != 1:
        raise ConversionError("delimiter must be exactly one character")
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=strict)
    if reader.fieldnames is None:
        raise ConversionError("input has no header row")
    header = [name.strip() if name is not None else "" for name in reader.fieldnames]
    if any(name == "" for name in header):
        raise ConversionError("header contains an empty column name")
    if len(set(header)) != len(header):
        raise ConversionError(f"header has duplicate column names: {header}")

    rows: list[dict[str, str]] = []
    for line_no, row in enumerate(reader, start=2):
        if row.get(None) is not None:
            raise ConversionError(
                f"row {line_no} has more fields than the {len(header)} in the header"
            )
        record = {}
        for name in header:
            value = row.get(name)
            record[name] = "" if value is None else value
        if sort_keys:
            record = dict(sorted(record.items()))
        rows.append(record)
    return rows


def json_to_csv(
    text: str,
    delimiter: str = ",",
    *,
    missing: str = "",
    strict: bool = False,
    newline: str = "\n",
) -> str:
    """Convert a JSON array of flat objects into CSV text."""
    if len(delimiter) != 1:
        raise ConversionError("delimiter must be exactly one character")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConversionError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ConversionError("top-level JSON must be an array of objects")
    if not data:
        raise ConversionError("the array is empty, so there is nothing to write")

    columns: list[str] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ConversionError(f"item {index} is {type(item).__name__}, expected an object")
        for key in item:
            if key not in columns:
                columns.append(key)
        for key, value in item.items():
            if isinstance(value, (dict, list)) and strict:
                raise ConversionError(
                    f"item {index} field {key!r} is nested; flatten it or drop --strict"
                )

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=columns, delimiter=delimiter, lineterminator=newline,
        extrasaction="ignore", restval=missing,
    )
    writer.writeheader()
    for item in data:
        row = {}
        for key in columns:
            value = item.get(key, missing)
            if value is None:
                value = missing
            elif isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            row[key] = value
        writer.writerow(row)
    return buffer.getvalue()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="csvjson", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"csvjson {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    to_json = sub.add_parser("to-json", help="CSV file -> JSON array")
    to_json.add_argument("source", help="CSV path, or - for stdin")
    to_json.add_argument("-o", "--output", help="write here instead of stdout")
    to_json.add_argument("-d", "--delimiter", default=",", help="single-character delimiter (default ,)")
    to_json.add_argument("--encoding", default="utf-8")
    to_json.add_argument("--indent", type=int, default=2, help="0 for one compact line")
    to_json.add_argument("--sort-keys", action="store_true", help="sort fields alphabetically")
    to_json.add_argument("--strict", action="store_true", help="reject malformed CSV quoting")

    to_csv = sub.add_parser("to-csv", help="JSON array -> CSV file")
    to_csv.add_argument("source", help="JSON path, or - for stdin")
    to_csv.add_argument("-o", "--output", help="write here instead of stdout")
    to_csv.add_argument("-d", "--delimiter", default=",", help="single-character delimiter (default ,)")
    to_csv.add_argument("--encoding", default="utf-8")
    to_csv.add_argument("--missing", default="", help="value for keys absent from a row")
    to_csv.add_argument("--strict", action="store_true", help="refuse nested objects or arrays")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        text = _read_text(args.source, args.encoding)
        if args.command == "to-json":
            rows = csv_to_json(
                text, args.delimiter, strict=args.strict,
                indent=args.indent, sort_keys=args.sort_keys,
            )
            payload = json.dumps(rows, ensure_ascii=False, indent=args.indent or None)
            if args.indent == 0:
                payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
            _write_text(args.output, payload + "\n", args.encoding)
        else:
            payload = json_to_csv(
                text, args.delimiter, missing=args.missing, strict=args.strict,
            )
            _write_text(args.output, payload, args.encoding)
    except ConversionError as exc:
        print(f"csvjson: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except BrokenPipeError:
        return EXIT_OK
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
