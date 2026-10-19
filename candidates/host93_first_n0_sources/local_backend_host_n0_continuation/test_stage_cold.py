"""Parent canonical16 copy contract with tiny synthetic buffers and declared pins.
No real canonical inputs or numeric conversion are used by this fixture.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import copy,json,os,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
def rejects(fn,why):
    try:fn()
    except (ValueError,OSError):return
    raise ValueError('missing rejection '+why)
def case(bad=None):
    with tempfile.TemporaryDirectory(dir=ROOT) as t:
        root=Path(t);repo=root/'repo';dest=root/'out';providers=root/'providers';metadata=root/'metadata';reads=[];verified=[];final=[]
        sizes=[1]*13+[94920448-384-3456-13]
        spec={'providers':[{'name':'synthetic'+str(i),'output_bytes':size,'expected_output_sha256':str(i%10)*64} for i,size in enumerate(sizes)]}
        if bad=='row_count':spec['providers'].pop()
        if bad=='byte_sum':spec['providers'][0]['output_bytes']+=1
        if bad=='collision':dest.mkdir()
        key=continuation.FIRST+'inputs/CONVERSION_SPEC.json';raw=json.dumps(spec).encode();pins={key:pin(raw)}
        def read(path,size,expected):
            if path==repo/key:need(expected==pins[key],'exact conversion spec read');return raw
            reads.append(Path(path));need(size==expected['bytes'],'explicit original source pin limit')
            data=('SYNTHETIC ONLY: '+Path(path).name).encode()
            if bad=='source_drift' and reads.count(Path(path))==2:return data+b'changed'
            if bad=='read_failure':raise ValueError('synthetic pin read rejection')
            return data
        def verify(path,expected):
            verified.append(Path(path));need(path.read_bytes()==('SYNTHETIC ONLY: '+path.name).encode(),'copied exact same synthetic buffer')
        def canonical(*args):
            final.append(True)
            if bad=='canonical':raise ValueError('synthetic canonical verification refused')
        P=types.SimpleNamespace(decode=json.loads,read=read,verify_file=verify,canonical_inputs=canonical)
        call=lambda:continuation.stage_inputs(P,repo,pins,providers,metadata,dest)
        if bad=='short_write':
            with mock.patch.object(continuation.os,'write',return_value=0):rejects(call,bad)
        elif bad:rejects(call,bad)
        else:
            result=call();need(len(reads)==32 and len(set(reads))==16 and len(verified)==16 and len(final)==1,'each of16 rechecked before next, all verified')
            need(result=={'stage':'local_canonical16_copy','kind':'PARENT_DATA_ONLY','files':16,'bytes':94920448,'numeric_conversion':False,'native_started':False,'frontdoor_claim':False},'parent data-only receipt')
            need(all(oct(f.stat().st_mode&0o777)=='0o600' for f in verified),'private outputs')
        if bad in ('row_count','byte_sum','collision'):need(reads==[],'preflight refused before data copy')
        if bad=='source_drift':need(len(reads)==2 and not verified and not final,'source changed stops before destination acceptance')
case();checks.append('synthetic_declared_canonical16_pins_copy_recheck_all16_no_conversion')
for bad in ('row_count','byte_sum','collision','source_drift','read_failure','canonical','short_write'):
    case(bad);checks.append(bad+'_refused_without_claiming_completed_data_stage')
print(json.dumps({'status':'PASS_CANONICAL16_STAGE_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'real_canonical_inputs_copied':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_stage_cold.py','tests':len(checks),'checks':checks})
