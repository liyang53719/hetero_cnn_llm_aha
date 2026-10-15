#!/usr/bin/env python3
"""New-contract entry using the original bounded supervisor, never old freeze."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import recipe as R
import lifecycle as L

# Reuse every supervisor/capability/watchdog operation. Only the admitted pending
# worker status differs; this is not a new approval or process-control framework.
path='candidates/qwen2_fullblock_reference_m128/guard.py'
raw=R.checked(R.ROOT,path,R.parse((R.C.HERE/'dependencies.json').read_bytes())[path])
old="'status':'BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' if mode == 'bootstrap'\n                     else 'FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY'"
new="'status':'NEW_PLATFORM_REFERENCE_OBSERVATIONS_PENDING_REVIEW'"
source=raw.decode();R.need(source.count(old)==1,'exact original supervisor status gate')
source=source.replace(old,new,1)
namespace={'__name__':'_new_reference_original_guard','__file__':str(Path(__file__).resolve())}
exec(compile(source,namespace['__file__'],'exec'),namespace)


def worker(fd,mode,out):
    try:
        R.need(mode=='bootstrap','new reference freeze not available')
        R._capture(R.ROOT,R.load_pins(),Path(out),stage=mode,recipe=R,capability_fd=int(fd))
        return 0
    except BaseException:
        # Original detailed failure remains a local supervisor artifact. No
        # exception text, metadata or values are exported by this worker.
        return 2

namespace['worker']=worker
if __name__=='__main__':raise SystemExit(namespace['main']())
