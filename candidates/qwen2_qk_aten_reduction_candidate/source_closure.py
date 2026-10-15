"""Explicit tracked execution dependencies; no old failed-receipt inventory."""
import json
from pathlib import Path
import subprocess
from candidates.qwen2_qk_aten_reduction_candidate import model
HERE=Path(__file__).resolve().parent
MANIFEST=HERE/'SOURCE_DEPENDENCIES.json'

def snapshot():
    data=json.loads(MANIFEST.read_text());expected=data['tracked_sources']
    model.need(type(expected) is dict and expected,'empty dependency closure')
    tracked=set(subprocess.run(['git','ls-files','--',*expected],cwd=model.ROOT,
        check=True,capture_output=True,text=True,timeout=15).stdout.splitlines())
    model.need(tracked==set(expected),'execution dependency must be tracked')
    actual={}
    for relative,pin in expected.items():
        path=Path(relative)
        model.need(not path.is_absolute() and '..' not in path.parts and not relative.startswith('work/'),'repository source only')
        actual[relative]=model.sha(model.ROOT/path)
        model.need(actual[relative]==pin,'tracked execution dependency changed: '+relative)
    return actual

def runtime_python_snapshot(pins):
    # Only Python framework source files used by this original AST subset;
    # six native files are checked separately by the original runtime helper.
    names=('functional.py','modules/activation.py','modules/linear.py','modules/module.py')
    result={}
    for n in names:
        relative='work/runtime_recovery/site-packages/torch/nn/'+n
        expected=pins['sources'][relative]['sha256']
        result[relative]=model.sha(model.ROOT/relative)
        model.need(result[relative]==expected,'framework Python source changed')
    return result

if __name__=='__main__':
    print(json.dumps({'status':'COLD_TRACKED_DEPENDENCY_CHECK_PASS','count':len(snapshot())}))
