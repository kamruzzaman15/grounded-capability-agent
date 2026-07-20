"""Pure, deterministic tests for the calculator tool."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools import calculator  # noqa: E402


def test_annual_cost_notion():
    assert calculator("10 * 20 * 12")["result"] == 2400


def test_annual_cost_clickup():
    assert calculator("7 * 20 * 12")["result"] == 1680


def test_percentage():
    r = calculator("(7.9 - 4.2) / 4.2 * 100")
    assert abs(r["result"] - 88.0952) < 0.01


def test_rejects_names():
    assert not calculator("__import__('os').system('echo hi')")["ok"]


def test_rejects_syntax_error():
    assert not calculator("4 +")["ok"]


def test_rejects_attribute_access():
    assert not calculator("(1).__class__")["ok"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("calculator tests OK")
