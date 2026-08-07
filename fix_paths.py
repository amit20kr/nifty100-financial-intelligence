"""
Rewrite the path-bootstrap header in all 8 Streamlit page files.

Old approach: messy 3-line inline snippet that counted parent dirs
New approach: single-line `import src.dashboard.utils.path_setup`

This script is safe to re-run — it is idempotent.
"""

import glob
import re

PAGES_GLOB = "src/dashboard/pages/*.py"

# Pattern that matches any of the old bootstrap variants we've used
OLD_PATTERNS = [
    # Variant 1: the inline 6-line snippet
    r"# ── path bootstrap.*?# ─{10,}\n\n",
    # Variant 2: the fix_paths.py output (3 lines)
    r"import sys, os\nsys\.path\.insert\(0.*?\n.*?path_setup\n\n",
]

NEW_HEADER = """\
# ── permanent path fix (must be first) ──────────────────────────────────────
# Uses an absolute file path so it works even before the project root is on
# sys.path (Streamlit's page runner strips the project root from sys.path).
import importlib.util as _ilu, pathlib as _pl
_ps = _pl.Path(__file__).resolve().parent.parent / "utils" / "path_setup.py"
_spec = _ilu.spec_from_file_location("path_setup", _ps)
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
del _ilu, _pl, _ps, _spec, _mod  # clean up bootstrap names
# ─────────────────────────────────────────────────────────────────────────────

"""

files = glob.glob(PAGES_GLOB)
for fpath in sorted(files):
    if fpath.endswith("__init__.py"):
        continue

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip ALL known old bootstrap variants
    cleaned = content
    for pattern in OLD_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)

    # Also strip a bare "import src.dashboard.utils.path_setup" line if present
    # (so we don't double-add)
    cleaned = re.sub(
        r"^#.*?path fix.*?\n.*?path_setup.*?# noqa.*?\n#.*?\n\n",
        "",
        cleaned,
        flags=re.MULTILINE | re.DOTALL,
    )
    # Strip leftover solo import line
    cleaned = re.sub(
        r"^import src\.dashboard\.utils\.path_setup.*?\n",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = cleaned.lstrip("\n")

    new_content = NEW_HEADER + cleaned

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[OK] Updated: {fpath}")

print("\nAll pages updated. path_setup is now a single import line in every file.")
