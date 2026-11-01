"""Test helpers: pluribus engine checkout on sys.path (via scripts/_repo.py), skip when local data is missing."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _repo import PLURIBUS as REPO  # noqa: E402,F401


def need(*paths):
    for p in paths:
        if not os.path.exists(p):
            pytest.skip(f"local data missing: {p}")
