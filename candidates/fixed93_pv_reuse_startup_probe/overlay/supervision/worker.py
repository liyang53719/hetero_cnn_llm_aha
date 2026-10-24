"""One supervised fullblock child. No direct/unadmitted DUT execution path."""
import argparse
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import (CANDIDATE, OWNED, OUTPUT, need, read_budget, actual_gate,
                  read_checked, strict_json, parent_identity)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--admission-sha', required=True)
    parser.add_argument('--budget-sha', required=True)
    parser.add_argument('--deadline', type=float, required=True)
    args = parser.parse_args(argv)
    need(os.environ.get('FIXED93_FULLBLOCK_PARENT_PID') == str(os.getppid()),
         'sole supervised fullblock child required')
    need(os.environ.get('QWEN2_FIXED93_ADMISSION_SHA256') == args.admission_sha and
         os.environ.get('FIXED93_FULLBLOCK_SOURCE_SHA256') == args.manifest_sha and
         os.environ.get('FIXED93_FULLBLOCK_BUDGET_SHA256') == args.budget_sha,
         'exact inherited source/admission/budget required')
    budget = read_budget(args.budget_sha)
    lease = strict_json(read_checked(OWNED / 'LEASE.json', cap=32768))
    need(lease.get('parent') == parent_identity(os.getppid()) and
         lease.get('source_manifest_sha256') == args.manifest_sha and
         lease.get('admission_sha256') == args.admission_sha and
         lease.get('budget_sha256') == args.budget_sha and lease.get('out') == str(OUTPUT) and
         lease.get('work_stop') == args.deadline and math.isfinite(args.deadline) and
         0 < args.deadline - time.monotonic() <= budget['inner_wall_seconds'],
         'same anchored parent/whole-entry work deadline required')
    need(not OUTPUT.exists() and not os.path.lexists(OWNED / 'CONSUMED.json'), 'fresh child once namespace required')
    need(len(os.sched_getaffinity(0)) == 1, 'single inherited CPU required')
    resource.setrlimit(resource.RLIMIT_CPU, (budget['outer_wall_seconds'],) * 2)
    resource.setrlimit(resource.RLIMIT_AS, (budget['rss_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (budget['file_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # The parent retains the original absolute work_stop and WNOWAIT cleanup.
    # Leave the child's timer empty for the unchanged SparseTelemetry.start().
    # Its later started+inner timer never extends the parent's earlier stop.
    # Still no DUT imports. Parent and child both run real byte/AST preflight.
    actual_gate(args.manifest_sha, args.admission_sha, args.budget_sha, fresh=False)
    need(parent_identity(os.getppid()) == lease['parent'], 'parent identity changed before integration')
    need(time.monotonic() < lease['work_stop'] == args.deadline,
         'original parent work deadline exhausted before integration')
    sys.path.insert(0, str(CANDIDATE))
    from integration.startup_probe import main as run_main
    return run_main(['--actual', '--data', 'work/qwen2_recovered_inputs/typed',
                     '--reference', 'work/qwen2_recovered_reference/first',
                     '--out', str(OUTPUT), '--reviewed-source-manifest', args.manifest_sha])


if __name__ == '__main__':
    raise SystemExit(main())
