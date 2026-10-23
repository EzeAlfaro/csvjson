"""Tests for csvjson. Run with: python -m pytest -q"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from csvjson import ConversionError, csv_to_json, json_to_csv  # noqa: E402


def test_csv_to_json_basic():
    rows = csv_to_json("name,age\nAda,36\nGrace,45\n")
    assert rows == [{"name": "Ada", "age": "36"}, {"name": "Grace", "age": "45"}]


def test_values_stay_strings():
    rows = csv_to_json("zip,amount\n01234,1.50\n")
    assert rows[0]["zip"] == "01234"
    assert rows[0]["amount"] == "1.50"


def test_quoted_commas_and_quotes():
    text = 'name,note\n"Lovelace, Ada","said ""hello"""\n'
    rows = csv_to_json(text)
    assert rows == [{"name": "Lovelace, Ada", "note": 'said "hello"'}]


def test_semicolon_and_tab_delimiters():
    assert csv_to_json("a;b\n1;2\n", ";") == [{"a": "1", "b": "2"}]
    assert csv_to_json("a\tb\n1\t2\n", "\t") == [{"a": "1", "b": "2"}]


def test_missing_trailing_values_become_empty():
    rows = csv_to_json("a,b,c\n1,,\n")
    assert rows == [{"a": "1", "b": "", "c": ""}]


def test_sort_keys():
    rows = csv_to_json("b,a\n2,1\n", sort_keys=True)
    assert list(rows[0]) == ["a", "b"]


def test_duplicate_header_rejected():
    with pytest.raises(ConversionError):
        csv_to_json("a,a\n1,2\n")


def test_empty_header_rejected():
    with pytest.raises(ConversionError):
        csv_to_json("a,\n1,2\n")


def test_no_header_rejected():
    with pytest.raises(ConversionError):
        csv_to_json("")


def test_extra_field_rejected():
    with pytest.raises(ConversionError):
        csv_to_json("a,b\n1,2,3\n")


def test_bad_delimiter_rejected():
    with pytest.raises(ConversionError):
        csv_to_json("a,b\n1,2\n", ";;")


def test_json_to_csv_union_of_keys():
    payload = json.dumps([{"a": 1, "b": 2}, {"a": 3, "c": 4}])
    out = json_to_csv(payload)
    assert out.splitlines()[0] == "a,b,c"
    assert out.splitlines()[1] == "1,2,"
    assert out.splitlines()[2] == "3,,4"


def test_json_to_csv_missing_value_override():
    out = json_to_csv(json.dumps([{"a": 1, "b": 2}, {"a": 3}]), missing="NA")
    assert out.splitlines()[2] == "3,NA"


def test_json_to_csv_null_and_bool():
    out = json_to_csv(json.dumps([{"a": None, "b": True}]))
    assert out.splitlines()[1] == ",true"


def test_json_to_csv_nested_inlined_unless_strict():
    payload = json.dumps([{"a": {"x": 1}}])
    assert 'x' in json_to_csv(payload)
    with pytest.raises(ConversionError):
        json_to_csv(payload, strict=True)


def test_json_to_csv_escaping_roundtrip():
    original = [{"name": "Lovelace, Ada", "note": 'said "hello"'}]
    csv_text = json_to_csv(json.dumps(original))
    assert csv_to_json(csv_text) == [{"name": "Lovelace, Ada", "note": 'said "hello"'}]


def test_json_to_csv_rejects_non_array():
    with pytest.raises(ConversionError):
        json_to_csv('{"a": 1}')


def test_json_to_csv_rejects_scalar_items():
    with pytest.raises(ConversionError):
        json_to_csv("[1, 2]")


def test_json_to_csv_rejects_empty_array():
    with pytest.raises(ConversionError):
        json_to_csv("[]")


def test_cli_roundtrip(tmp_path):
    csv_path = tmp_path / "in.csv"
    json_path = tmp_path / "out.json"
    back_path = tmp_path / "back.csv"
    csv_path.write_text("name,note\nAda,\"a,b\"\n", encoding="utf-8")

    first = subprocess.run(
        [sys.executable, str(ROOT / "csvjson.py"), "to-json", str(csv_path), "-o", str(json_path)],
        capture_output=True, text=True,
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(json_path.read_text(encoding="utf-8")) == [{"name": "Ada", "note": "a,b"}]

    second = subprocess.run(
        [sys.executable, str(ROOT / "csvjson.py"), "to-csv", str(json_path), "-o", str(back_path)],
        capture_output=True, text=True,
    )
    assert second.returncode == 0, second.stderr
    assert back_path.read_text(encoding="utf-8").splitlines()[0] == "name,note"


def test_cli_missing_file_exit_code(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "csvjson.py"), "to-json", str(tmp_path / "nope.csv")],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "no such file" in result.stderr


def test_cli_stdin_to_stdout():
    result = subprocess.run(
        [sys.executable, str(ROOT / "csvjson.py"), "to-json", "-", "--indent", "0"],
        input="a,b\n1,2\n", capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[{"a":"1","b":"2"}]'
