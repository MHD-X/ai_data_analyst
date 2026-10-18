"""Compatibility wrapper for the narrative module.

The canonical implementation lives in core.narrative; the UI helper stays
as a thin alias to avoid import mismatches.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.narrative import *  # noqa: F401,F403
