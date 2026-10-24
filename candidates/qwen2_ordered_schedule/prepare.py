"""Source-only two-file overlay; no full owner/run admission or imports."""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve(strict=True).parent

def compose(root, output):
    root=Path(root).resolve(strict=True);output=Path(output).absolute()
    pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
    original=(root/pins['selected_schedule_input_path']).read_bytes()
    candidate=(HERE/'schedule.py').read_bytes()
    if hashlib.sha256(original).hexdigest()!=pins['selected_schedule_before_sha256']:
        raise ValueError('published selected schedule changed')
    if hashlib.sha256(candidate).hexdigest()!=pins['selected_schedule_after_sha256']:
        raise ValueError('ordered schedule postimage changed')
    if output.exists():raise ValueError('fresh overlay output required')
    dest=output/'candidates/qwen2_resident_matrix/production_qk16_model'
    dest.mkdir(parents=True)
    for name in ('schedule.py','ordered_work.py'):
        (dest/name).write_bytes((HERE/name).read_bytes())
    record=dict(status='PARTIAL_SOURCE_OVERLAY_NO_OWNER_RUNTIME_ADMISSION',
                files={name:hashlib.sha256((dest/name).read_bytes()).hexdigest()
                       for name in ('schedule.py','ordered_work.py')},
                default_enabled=False,full_block=False,native_executed=False)
    (output/'COMPOSITION.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(compose(args.source_root,args.output),indent=2))
