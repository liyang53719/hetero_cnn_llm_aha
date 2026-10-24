"""Compose existing selected/direct sources, then exact owner opt-in overlay.

Source only. No runtime imports, arithmetic/native execution, or full admission.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
HERE=Path(__file__).resolve(strict=True).parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def compose(source_root,output):
    root=Path(source_root).resolve(strict=True);output=Path(output).absolute()
    pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
    if output.exists():raise ValueError('fresh source overlay required')
    path=root/'candidates/qwen2_selected_direct_transport/prepare.py'
    expected=pins['harness_and_composer_pins']['candidates/qwen2_selected_direct_transport/prepare.py']
    if sha(path)!=expected:raise ValueError('direct composer changed')
    dep=root/'candidates/qwen2_ordered_schedule'
    for name,key in [('schedule.py','ordered_schedule_sha256'),('ordered_work.py','ordered_work_sha256')]:
        if sha(dep/name)!=pins[key]:raise ValueError('published ordered dependency changed')
    spec=importlib.util.spec_from_file_location('_pinned_direct_composer',path)
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    with tempfile.TemporaryDirectory() as temp:
        staged=Path(temp)/'staged'
        previous.compose(root,staged)
        runtime=staged/'candidates/qwen2_resident_matrix'
        for rel,pin in pins['inputs'].items():
            if sha(runtime/rel)!=pin['before_sha256']:raise ValueError('direct postimage mismatch: '+rel)
            source=HERE/'postimage'/rel
            if sha(source)!=pin['after_sha256']:raise ValueError('owner postimage mismatch: '+rel)
            (runtime/rel).write_bytes(source.read_bytes())
        for name in ('schedule.py','ordered_work.py'):
            (runtime/'production_qk16_model'/name).write_bytes((dep/name).read_bytes())
        (runtime/'production_qk16_model/ordered_owner.py').write_bytes((HERE/'ordered_owner.py').read_bytes())
        files={str(p.relative_to(staged)):sha(p) for p in staged.rglob('*.py')}
        record=dict(status='COMPOSED_OPT_IN_SOFTWARE_OWNER_ONLY',files=files,
                    default_enabled=False,full_numeric_admission=False,rtl_executed=False)
        (staged/'ORDERED_OWNER_COMPOSITION.json').write_text(json.dumps(record,indent=2)+'\n')
        shutil.copytree(staged,output)
    return record
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    print(json.dumps(compose(a.source_root,a.output),indent=2))
