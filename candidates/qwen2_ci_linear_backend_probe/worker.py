"""One synthetic BF16 Linear call in an explicitly selected fresh child.

No checkpoint, business model, reference, warmup or numerical acceptance. The
completion enum does not identify the backend: the parent must independently
inspect its local captured backend verbose output. Default is cold.
"""
import argparse
import importlib
import json
from pathlib import Path
from candidates.qwen2_fullblock_ci_execution import platform, platform_avx2

ROOT=Path(__file__).resolve().parents[2]
MODES=('enabled','disabled')


def need(ok,message):
    if not ok:raise ValueError(message)


def initialize():
    # Keep original location/version/native/source/environment gates intact.
    executable=platform.location(ROOT)
    pins=platform.sources(ROOT)
    current=platform_avx2.initialize()
    need(current.get('expected_runtime_matches') is True and
         current.get('native_five_match') is True and
         current.get('environment_matches') is True,'incompatible observed runtime')
    need(platform.same(current,platform._expected(pins)),'exact observed runtime required')
    need(platform.location(ROOT)==executable,'interpreter location changed')
    return importlib.import_module('torch')


def run(mode=None):
    if mode is None:return dict(schema=1,status='NOT_EXECUTED',mode='none')
    need(type(mode) is str and mode in MODES,'explicit fixed probe mode required')
    torch=initialize()
    enabled=mode=='enabled'
    torch.backends.mkldnn.enabled=enabled
    need(torch.backends.mkldnn.enabled is enabled,'explicit mkldnn setting failed')
    with torch.no_grad():
        # Meta construction avoids random CPU parameter initialization. Both
        # parameters are replaced by deterministic, nonzero CPU BF16 constants.
        linear=torch.nn.Linear(1536,1536,bias=True,device='meta',dtype=torch.bfloat16)
        linear.weight=torch.nn.Parameter(torch.full((1536,1536),0.0625,
            dtype=torch.bfloat16,device='cpu'),requires_grad=False)
        linear.bias=torch.nn.Parameter(torch.full((1536,),0.03125,
            dtype=torch.bfloat16,device='cpu'),requires_grad=False)
        x=torch.full((1,128,1536),0.125,dtype=torch.bfloat16,device='cpu')
        linear.eval()
        output=linear(x)  # Exactly one actual Linear call; no readback or warmup.
        del output
    return dict(schema=1,status='SYNTHETIC_LINEAR_COMPLETED',mode=mode)


class SafeParser(argparse.ArgumentParser):
    def error(self,message):raise ValueError('invalid worker arguments')


def main(argv=None):
    mode=None
    try:
        parser=SafeParser(description=__doc__,add_help=False)
        parser.add_argument('--mode',choices=MODES)
        args=parser.parse_args(argv);mode=args.mode
        result=run(mode)
    except BaseException:
        # Detailed backend stdout/stderr is captured locally by the parent.
        # Never echo arbitrary exception text, tensors, paths, or arguments.
        result=dict(schema=1,status='SYNTHETIC_LINEAR_REJECTED',mode=mode if mode in MODES else 'none')
    print(json.dumps(result,sort_keys=True))
    return 2 if result['status']=='SYNTHETIC_LINEAR_REJECTED' else 0


if __name__=='__main__':raise SystemExit(main())
