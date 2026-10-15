#!/usr/bin/env python3
"""Explicit diagnostic supervisor; no legacy numerical acceptance alias."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_exact64_diagnostic_fullblock.supervisor import main
if __name__=='__main__':raise SystemExit(main())
