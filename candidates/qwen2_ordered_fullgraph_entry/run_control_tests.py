"""Bounded pure control/schema/source-composer suite; no production execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
TESTS=('test_compose.py','test_admission.py','test_bridge.py','test_registry.py',
       'test_runner.py','test_runtime_binding.py','test_cold_binding.py','test_service_trace.py','test_cold_policy.py')
MODES={'normal':[], 'optimized':['-O'], 'isolated':['-I'], 'isolated_optimized':['-I','-O']}

def limit():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))

def pins():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir())
            if p.is_file() and p.suffix in ('.py','.json','.patch')}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    before=pins();results=[]
    if any(not (HERE/t).is_file() for t in TESTS):raise ValueError('incomplete test source')
    for mode,flags in MODES.items():
        for test in TESTS:
            command=[sys.executable,*flags,'-S','-B',str(HERE/test)]
            if test in ('test_compose.py','test_service_trace.py'):command+=['--source-root',str(a.source_root.resolve())]
            started=time.monotonic()
            record={'mode':mode,'test':test,'test_sha256':before[test]}
            try:
                r=subprocess.run(command,capture_output=True,timeout=25,preexec_fn=limit,
                    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
                stem=mode+'_'+test[:-3]
                (a.output/(stem+'.stdout')).write_bytes(r.stdout)
                (a.output/(stem+'.stderr')).write_bytes(r.stderr)
                record.update(exit_code=r.returncode,stdout_sha256=hashlib.sha256(r.stdout).hexdigest(),
                    stderr_sha256=hashlib.sha256(r.stderr).hexdigest(),timeout=False)
            except subprocess.TimeoutExpired as e:
                record.update(exit_code=None,timeout=True)
                (a.output/(mode+'_'+test+'.partial')).write_bytes((e.stdout or b'')+(e.stderr or b''))
            record['wall_seconds']=time.monotonic()-started;results.append(record)
            receipt={'source_pins':before,'runs':results,'native_task_executed':False,
                     'scope':'PURE_CONTROL_SCHEMA_SOURCE_COMPOSITION_ONLY','limits':dict(cpus=1,address_space_mib=256,cpu_seconds=20,wall_seconds=25)}
            (a.output/'RESULTS.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
            if record['timeout'] or record['exit_code']!=0:return 1
    if pins()!=before:raise ValueError('candidate source changed during test run')
    print(json.dumps({'status':'PASS_CONTROL_ONLY','runs':len(results),'numeric_status':'TEMP_NOT_EXECUTED'}))
    return 0

if __name__=='__main__':raise SystemExit(main())
