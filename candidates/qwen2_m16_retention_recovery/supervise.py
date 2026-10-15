"""Separate recovery admission; the original MODEL COMPLETE gate is unchanged."""
import argparse,json,sys
from . import audit as a
from .reference import OUT
from candidates.qwen2_m16_stage_diagnostic.supervise import supervise

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args(argv)
    if not args.execute:print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    a.g.need(not OUT.exists() and not(a.BASE/'reference').exists(),'no previous reference attempt')
    # Child rechecks the seal independently before any Torch/raw operand load.
    a.sealed()
    return supervise([sys.executable,'-B','-m','candidates.qwen2_m16_retention_recovery.reference','--execute'],a.BASE,'REFERENCE')
if __name__=='__main__':raise SystemExit(main())
