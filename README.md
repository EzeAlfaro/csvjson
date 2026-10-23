# csvjson

Convert between CSV and JSON in both directions, with explicit failure modes and no
silent type coercion. Python 3.10+, standard library only.

```bash
python csvjson.py to-json people.csv --indent 2
python csvjson.py to-json exports.tsv --delimiter '\t' --strict
python csvjson.py to-csv rows.json --missing ""
cat rows.json | python csvjson.py to-csv -
```

## Why another converter

Most one-file converters do three things that break real pipelines:

1. **They guess types.** `01234` becomes `1234`, `1.50` becomes `1.5`, an account id loses
   its leading zero. Here every CSV value stays a string, exactly as written.
2. **They write a partial file and then fail.** Both directions build the full output in
   memory and only write when the conversion finished, so a bad row cannot leave a
   half-written result behind.
3. **They accept ambiguous headers.** Empty and duplicate column names are rejected with
   the reason, because `{"": "x"}` is not a field anyone can address later.

## CSV to JSON

| Option | Meaning |
| --- | --- |
| `-d, --delimiter` | One character: `,` (default), `;`, `\t`, `\|` |
| `--encoding` | Input encoding, default `utf-8` |
| `--indent` | `2` (default), any width, or `0` for one compact line |
| `--sort-keys` | Alphabetical field order, useful for stable diffs |
| `-o, --output` | Write to a file instead of stdout |
| `--strict` | Reject malformed quoting instead of repairing it |

Rejected with exit code `2` and a message naming the row: duplicate header names, an empty
header name, a row with more fields than the header, an empty input, a delimiter that is not
one character.

## JSON to CSV

Accepts an array of flat objects. Columns are the union of every object's keys in first-seen
order, so rows do not need identical shape.

| Option | Meaning |
| --- | --- |
| `--missing` | Value written for a key absent from a row, default empty string |
| `--strict` | Refuse nested objects/arrays instead of inlining them as JSON |
| `-d, --delimiter` | Output delimiter |
| `-o, --output` | Write to a file instead of stdout |

`null` is written as the `--missing` value, booleans as `true`/`false`, and nested values as
compact JSON unless `--strict` is set.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Converted |
| 2 | Input problem, named on stderr |
| 64 | Bad usage (argparse) |

## Tests

```bash
python -m pytest -q
```

22 tests cover quoted delimiters and quotes, semicolon/tab input, missing trailing values,
duplicate and empty headers, extra fields, every documented error path, the union-of-keys
behaviour, null/boolean handling, nested values with and without `--strict`, a CSVâ†’JSONâ†’CSV
round trip that must preserve `a,b` and quoted text, CLI file output, CLI exit code on a
missing file, and stdin to stdout.

