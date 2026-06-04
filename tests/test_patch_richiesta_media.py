"""Regression: do not patch url_media onto long text messages."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_richiesta_row_expects_media_patch_text_message() -> None:
    long_text = (
        "I just got my new blood test results back. My GGT is at 85, "
        "triglycerides at 240."
    )
    assert main._richiesta_row_expects_media_patch(long_text) is False


def test_richiesta_row_expects_media_patch_filename() -> None:
    assert main._richiesta_row_expects_media_patch("discharge_summary.pdf") is True


def test_richiesta_row_expects_media_patch_placeholder() -> None:
    assert main._richiesta_row_expects_media_patch("[Media attachment]") is True
