"""Private same-run actual preservation; no export, upload, or oracle access.

Only actual readbacks and accepted read-only observations are inventoried.
Physical input providers and frozen reference tensors are never read here.
All records and raw bytes remain below the current private work directory.
"""
import hashlib
import json
from pathlib import Path

ACTUAL_NAMES=frozenset(('n0','qraw','qr','q','kraw','kr','k','vraw','v','kv','att',
    'o','r','n1','gate','up','act','down','y'))
ATTENTION_NAMES=frozenset(('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16',
    'softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'))


def need(ok,message):
    if not ok:raise ValueError(message)


def identity(path):
    raw=path.read_bytes()
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def _file(out,name):
    path=out/name
    need(not Path(name).is_absolute() and '..' not in Path(name).parts and
        path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),
        'private retention aliases are forbidden')
    return path


def seal(out,actual,silu,capture,report):
    out=Path(out).absolute()
    need(out.is_dir() and set(actual)==ACTUAL_NAMES,'complete actual fullblock output set required')
    need(report['whole_block_terminal'] is True and report['finalfence'] is True and
        report['actual_outputs_sealed'] is False,'retention must precede whole-launch output seal')
    host=report['execution']['host'];accepted=host['accepted']
    need(host['launch_result']['completed']==21 and host['launch_result']['jobs']==17 and
        accepted['completion_fire']==21 and accepted['owner_result_fire']==17 and accepted['result_fire']==1,
        'retention requires genuine 21/17/1 accepted terminal')
    need(capture.closed and not capture.active and set(capture.fields)==ATTENTION_NAMES and
        report['observation']['status'].startswith('COMPLETE_'),'all ten attention fields must be complete')
    inventory={}
    for name in sorted(ACTUAL_NAMES|{'silu'}):
        raw=silu if name=='silu' else actual[name].tobytes()
        path=_file(out,'actual_'+name+'.f32le')
        need(path.is_file() and path.read_bytes()==raw,'saved actual payload differs: '+name)
        spec=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        need(spec==report['sealed_actual_outputs'][name],'actual seal commitment differs: '+name)
        inventory[path.name]=spec
    # Preserve the original observer's payload, presence and frequency, rather
    # than reconstructing sparse/future values or accepting an incomplete trace.
    directory=_file(out,'attention_observation')
    need(directory.is_dir(),'actual observer directory missing')
    expected={'summary.json'}
    for name in sorted(ATTENTION_NAMES):
        for suffix,raw in (('.u32le',capture._bytes(name)),
                ('.presence',bytes(capture.fields[name]['observed'])),
                ('.count.u16le',capture._bytes(name,'frequency'))):
            filename=name+suffix;expected.add(filename)
            relative='attention_observation/'+filename;path=_file(out,relative)
            need(path.is_file() and path.read_bytes()==raw,'saved observation differs: '+name)
            inventory[relative]=identity(path)
    need({p.name for p in directory.iterdir()}==expected,'exact complete observation inventory')
    summary=_file(out,'attention_observation/summary.json')
    need(json.loads(summary.read_text())==report['observation'],'saved observer receipt differs')
    inventory['attention_observation/summary.json']=identity(summary)
    receipt=dict(schema=1,status='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE',inventory=inventory,
        scope='DIAGNOSTIC_SOFTWARE_OWNER',local_only=True,upload_authorized=False,
        oracle_payloads_read=False,reference_operands_in_execution=False,
        propagation_inputs_retained=['v','att','o','r','n1','gate','up'],
        isolation_scope='Same-run actual n1/gate/up allow later post-seal propagation isolation; no sampled verdict.')
    path=_file(out,'LOCAL_RETENTION.json')
    with path.open('x') as stream:
        json.dump(receipt,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    return receipt


def verify(out,receipt):
    out=Path(out).absolute()
    need(receipt['local_only'] is True and receipt['upload_authorized'] is False,'private-only retention contract')
    for name,spec in receipt['inventory'].items():
        need(identity(_file(out,name))==spec,'saved actual/observation changed after seal')
    saved=json.loads(_file(out,'LOCAL_RETENTION.json').read_text())
    need(saved==receipt,'private retention receipt changed')
    return True
