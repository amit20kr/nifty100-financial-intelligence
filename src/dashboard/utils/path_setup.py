"""
path_setup.py — Permanent sys.path fix for Streamlit multipage apps.

WHY THIS EXISTS
---------------
When Streamlit serves a page from pages/, it temporarily inserts the pages/
directory into sys.path[0] and removes the project root. This means any
`from src.X import Y` fails with ModuleNotFoundError: No module named 'src'.

HOW IT WORKS (permanently, without pip install -e .)
------------------------------------------------------
Instead of counting parent directories with .parent.parent.parent (fragile —
breaks if files are renamed or moved), we locate the project root by searching
upward from THIS file for the .env file, which is guaranteed to exist only at
the project root. This is robust to refactoring.

USAGE — add ONE line at the top of every page file, BEFORE any src.* import:
    import src.dashboard.utils.path_setup  # noqa: F401

The module executes setup() on first import and is then a no-op on re-import
(Python's module cache prevents re-execution).
"""
import sys
from pathlib import Path


def _find_project_root() -> Path:
    """Walk upward from this file to find the directory containing .env"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".env").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "pytest.ini").exists():
            return parent
    # Fallback: 4 levels up from this file's location
    # utils/ -> dashboard/ -> src/ -> project_root
    return Path(__file__).resolve().parent.parent.parent.parent


# Execute immediately on first import — idempotent on subsequent imports
_ROOT = _find_project_root()
_ROOT_STR = str(_ROOT)
if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)
