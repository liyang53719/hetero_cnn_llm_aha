#!/usr/bin/env python3
"""One explicit recovered-chain binding to the independently reviewed supervisor."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_supervisor_recovery import launch as supervisor
from candidates.qwen2_fullblock_ci_dut import gates, runner
# Only this fresh process receives these exact module bindings. The published
# supervisor and all budget/input checks remain unchanged and part of sources().
supervisor.gates=gates
supervisor.runner=runner
if __name__=='__main__':raise SystemExit(supervisor.main())
