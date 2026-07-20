"""
conftest.py
===========
Shared pytest fixtures for the Nifty 100 test suite.

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 2
"""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the absolute project root directory."""
    return Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def raw_data_dir(project_root: Path) -> Path:
    """Return the path to data/raw/."""
    return project_root / "data" / "raw"


@pytest.fixture(scope="session")
def supporting_data_dir(project_root: Path) -> Path:
    """Return the path to data/supporting/."""
    return project_root / "data" / "supporting"
