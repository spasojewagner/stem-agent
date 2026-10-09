import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stem.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return Settings(api_key="test", web=False, tool_timeout=60, runs_dir=tmp_path / "runs")


@pytest.fixture
def reference():
    return lambda name: ROOT / "tests" / "reference" / f"{name}_reference.py"
