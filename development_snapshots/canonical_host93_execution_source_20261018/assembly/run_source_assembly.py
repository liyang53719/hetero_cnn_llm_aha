"""One approved fixed Host93 source assembly in this process; no native child."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import types

ASSEMBLER_REL='candidates/qwen2_resident_matrix/host93_source_recovery/assemble_host93.py'
ASSEMBLER_SHA='75a2145eea0de83ad1bbe3a7a64e1a5f14f20f9f1381f65e619fb5bd3d427641'
SOURCE_CAP=32*1024*1024


def require(ok,why):
    if not ok:raise ValueError(why)


def load_assembler(path):
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)), 'assembler path')
    require(path.stat().st_size==15592,'assembler size')
    raw=path.read_bytes()
    require(len(raw)==15592 and hashlib.sha256(raw).hexdigest()==ASSEMBLER_SHA,'assembler SHA')
    module=types.ModuleType('fixed_host93_assembler');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def bound_final_source_writes(module,output):
    original=module.write_tree
    def write_tree(root,sources):
        if root==output/'scala':
            require(len(sources)==93 and sum(len(raw) for raw in sources.values())<=SOURCE_CAP,
                    'final93 source aggregate cap before write')
        return original(root,sources)
    module.write_tree=write_tree


def expired(_signum,_frame):
    raise TimeoutError('source assembly60s absolute deadline')


def process_limits():
    allowed=os.sched_getaffinity(0);require(bool(allowed),'empty CPU affinity')
    os.sched_setaffinity(0,{min(allowed)})
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_FSIZE,(SOURCE_CAP,SOURCE_CAP))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def main():
    entry=time.monotonic();stop=entry+60
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--hardfloat-scala',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed-source',action='store_true')
    args=parser.parse_args()
    require(args.execute_reviewed_source,'separate assembly approval and explicit switch required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'inherited timer refused')
    signal.signal(signal.SIGALRM,expired)
    require(time.monotonic()<stop,'entry deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic())
    # This dedicated process is disposable; limits and handler are never relaxed.
    process_limits()
    module=load_assembler(args.repo.absolute()/ASSEMBLER_REL)
    output=module.clean_path(args.output)
    bound_final_source_writes(module,output)
    old_argv=sys.argv
    try:
        sys.argv=[str(args.repo/ASSEMBLER_REL),'--repo',str(args.repo),
                  '--assemble-reviewed-source','--hardfloat-scala',str(args.hardfloat_scala),'--output',str(output)]
        with contextlib.redirect_stdout(io.StringIO()) as captured:module.main()
    finally:
        sys.argv=old_argv
    require(time.monotonic()<stop,'source assembly deadline exhausted')
    tree=list((output/'scala').rglob('*'))
    require(not any(p.is_symlink() for p in tree),'source output symlink')
    files=[p for p in tree if p.is_file()]
    total=sum(p.stat().st_size for p in files)
    require(len(files)==93 and total<=SOURCE_CAP,'post source count/aggregate cap')
    require(len(captured.getvalue())<=65536,'assembler summary cap')
    result={'status':'SOURCE_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,
            'source_count':93,'source_bytes':total,'elapsed_seconds':time.monotonic()-entry,
            'actual_outer_exit0_elapsed60_and_source_identity_review_required':True,
            'compiler_started':False,'native_child_started':False}
    require(time.monotonic()<stop,'final source evidence deadline exhausted')
    print(json.dumps(result,sort_keys=True))
    # The timer stays armed through interpreter exit. No residual SOURCE_RECEIPT
    # alone grants success if this process fails, times out, or has unknown exit.


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
