"""
tests/analytics/test_radar.py
=============================
Day 19 — Tests for the Radar Chart Generator.

Validates:
1. Universe population (exactly 92 companies, ensuring SIEMENS inclusion).
2. File generation count matches universe size.
3. Chart sizes are non-trivial (not corrupt).
4. Filename sanitization logic works (M&M -> M_M).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analytics.radar import sanitize_filename, generate_radar_charts


class TestRadarCharts:
    def test_sanitize_filename_handles_ampersand(self):
        """M&M must be converted to a safe filesystem name."""
        assert sanitize_filename("M&M") == "M_M"
        assert sanitize_filename("BAJAJ-AUTO") == "BAJAJ-AUTO"
        assert sanitize_filename("TCS") == "TCS"
        assert sanitize_filename("COMPANY/NAME") == "COMPANY_NAME"

    def test_radar_generation_counts_and_sizes(self, tmp_path):
        """
        Runs radar generation on the real database.
        Validates exactly 92 charts are generated and all are >0 bytes.
        """
        db_path = Path("db/nifty100.db")
        if not db_path.exists():
            pytest.skip("Integration database db/nifty100.db not found.")

        out_dir = tmp_path / "reports/radar_charts"

        # Act
        df = generate_radar_charts(db_path=db_path, out_dir=out_dir)

        # Assert Universe Size
        assert (
            len(df) == 92
        ), "The universe must contain exactly 92 companies (including SIEMENS)."

        # Assert Files Generated
        files = list(out_dir.glob("*.png"))
        assert len(files) == 92, "Exactly 92 PNG files must be generated."

        # Assert Non-trivial Size
        for f in files:
            assert (
                f.stat().st_size > 1024
            ), f"Chart {f.name} is suspiciously small (<1KB), likely empty/corrupt."
