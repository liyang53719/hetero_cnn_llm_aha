"""Narrow actual-owner Scala/CHIRRTL gate. Never invokes an RTL backend."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.dense_a_hold_chisel.prepare import prepare, require, sha
from candidates.qwen2_resident_matrix.raw_kv.run_unit import run_group
from candidates.qwen2_resident_matrix.raw_kv_parent.run_unit import memory_audit_parent, failure_diagnostics, _modules

MAVEN = 'https://repo.maven.apache.org/maven2/'
LOCK = 'chisel/rope_hardware_oracle/maven-lock.json'
LOCK_SHA = 'e15bbf22b74552ed6a4fc61a7137564c2543488d928cbdff77f27af2dfd3204b'
PLUGIN = 'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
TOTAL_SECONDS = 420
STAGES = {'dependencies': 120, 'compile': 180, 'elaborate': 90}
JAVA = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
EXPECTED = {f'owner_hold{hold}_full{full}.fir' for hold in (0,1) for full in (0,1)}


def dependencies():
    lock = ROOT / LOCK
    require(sha(lock) == LOCK_SHA, 'existing Maven lock drift')
    # Same selection as scripts/check_matrix_interface_candidate.py.
    selected = {p:h for p,h in json.loads(lock.read_text())['artifacts'].items()
                if p.endswith('.jar') and '_2.12' not in p and '/2.12.' not in p
                and not p.startswith('org/scala-sbt/')}
    require(len(selected) == 87 and PLUGIN in selected, 'exact frontend dependency selection')
    for path,digest in selected.items():
        require(not path.startswith('/') and '..' not in Path(path).parts and
                re.fullmatch('[0-9a-f]{64}', digest), 'invalid dependency identity')
    return selected


def fetch(cache):
    cache = Path(cache)
    def one(item):
        name,digest = item
        target = cache / name
        if not target.exists():
            with urllib.request.urlopen(MAVEN+name, timeout=60) as response:
                data = response.read()
            require(hashlib.sha256(data).hexdigest() == digest, 'downloaded dependency drift: '+name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        require(sha(target) == digest, 'cached dependency drift: '+name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, sorted(dependencies().items())))


def memory_audit(text, enabled):
    # Check the ORIGINAL emitted FIFO depth first. Only that one numeric depth
    # is normalized to reuse the frozen exhaustive bank/module/type audit.
    matches = list(re.finditer(r'^\s*cmem\s+ram\s*:\s*\{[^\n]*\}\s*\[(\d+)\]', text, re.M))
    require(len(matches)==1, 'one actual operand Queue required')
    match = matches[0]
    depth = int(match.group(1))
    require(depth == (3 if enabled else 4), 'A-hold FIFO depth mismatch')
    normalized = text[:match.start(1)]+'4'+text[match.end(1):]
    result = memory_audit_parent(normalized)
    result['operand_fifo']['depth'] = depth
    expected = {'heldA': 'UInt<16>[128]', 'heldAK': 'UInt<12>',
                'heldAGeneration': 'UInt<32>', 'pendingAGeneration': 'UInt<32>',
                'heldAValid': 'UInt<1>'}
    found = {}
    for name,shape in re.findall(r'^\s*reg(?:reset)?\s+(\w+)\s*:\s*(.*?),\s*clock',text,re.M):
        if name in expected:
            require(name not in found, 'duplicated hold register')
            found[name] = re.sub(r'\s+', '', shape)
    require(found == (expected if enabled else {}), 'emitted hold register inventory mismatch')
    selected = re.findall(r'^\s*reg(?:reset)?\s+selected\s*:\s*(.*?),\s*clock',text,re.M)
    require(len(selected)==1, 'one actual bank request register')
    read_a = re.findall(r'\breadActivation\s*:\s*UInt<1>', selected[0])
    require(len(read_a)==int(enabled), 'optional readActivation register mismatch')
    result.update(hold_payload_bits=2048 if enabled else 0,
                  added_hold_control_bits=78 if enabled else 0,
                  useful_operand_payload_bytes=1216 if enabled else 1280,
                  declared_fifo_and_hold_payload_bits=depth*4359+(2048 if enabled else 0),
                  physical_area_or_timing_measured=False)
    return result


def register_inventory(text):
    result={}
    for module,body in _modules(text).items():
        fields=re.findall(r'^\s*reg(?:reset)?\s+(\w+)\s*:\s*(.*?),\s*clock',body,re.M)
        require(len(fields)==len({name for name,_ in fields}), 'duplicate register name')
        result[module]={name:re.sub(r'\s+','',shape) for name,shape in fields}
    return result


def register_delta(off, on):
    before,after=register_inventory(off),register_inventory(on)
    owner='TransposedDenseDownOwner';bank='TransposedDownDenseBanks'
    added=set(after[owner])-set(before[owner])
    require(added=={'heldA','heldAK','heldAGeneration','pendingAGeneration','heldAValid'},
            'unexpected added owner register')
    require({k:v for k,v in after[owner].items() if k not in added}==before[owner],
            'existing owner register changed')
    require(set(after[bank])==set(before[bank]), 'added/removed bank register')
    require({k:v for k,v in after[bank].items() if k!='selected'}==
            {k:v for k,v in before[bank].items() if k!='selected'}, 'existing bank register changed')
    selected_before=before[bank]['selected'][1:-1].split(',')
    selected_after=after[bank]['selected'][1:-1].split(',')
    require(sorted(selected_after)==sorted(selected_before+['readActivation:UInt<1>']),
            'bank request register grew beyond one control bit')
    q0=next(k for k in before if k not in (owner,bank))
    q1=next(k for k in after if k not in (owner,bank))
    # Chisel Queue3/4 both use 2-bit enqueue/dequeue pointers and maybe_full.
    require(before[q0]==after[q1], 'operand FIFO control register shape changed')
    return {'added_owner_registers':{k:after[owner][k] for k in sorted(added)},
            'added_bank_request_bits':1, 'added_payload_bits':2048,
            'added_control_bits':78,'fifo_control_shape_unchanged':True,
            'existing_other_registers_unchanged':True}


def verify_frozen_inputs(out, cache, receipt, selected):
    """Recheck exactly the recorded bytes before compilation and before PASS."""
    require(sha(HERE/'source_pins.json')==receipt['source_pins_sha256'], 'source pin file changed during frontend')
    require(sha(ROOT/'.github/workflows/qwen2-dense-a-hold-frontend.yml')==receipt['workflow_sha256'],
            'workflow changed during frontend')
    for path,digest in receipt['inputs'].items():
        require(sha(ROOT/path)==digest, 'repository source changed during frontend: '+path)
    actual={p.name:sha(p) for p in (out/'source').glob('*.scala')}
    require(set(actual)==set(receipt['generated'])-{'AHoldElaborate.scala'},
            'generated Scala file set changed during frontend')
    actual['AHoldElaborate.scala']=sha(HERE/'AHoldElaborate.scala')
    require(actual==receipt['generated'], 'generated Scala/emitter changed during frontend')
    require(dependencies()==selected, 'dependency lock selection changed during frontend')
    for path,digest in selected.items():
        require(sha(cache/path)==digest, 'dependency jar changed during frontend: '+path)


def run(out, cache):
    out,cache = Path(out).resolve(),Path(cache).resolve()
    require(not out.exists(), 'fresh frontend output required')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'status':'STARTED','stages':[], 'scala_compiled':False,
              'chirrtl_generated':False,'rtl_generated':False,
              'hardware_protocol_executed':False,'arithmetic_executed':False,
              'full_business_block_acceptance':False,
              'budget':{'total_seconds':TOTAL_SECONDS,'stages_seconds':STAGES,
                        'java_heap_mib':1024,'java_active_processors':1,
                        'download_workers':4}}
    def save():
        (out/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    def command(stage, argv):
        remaining = TOTAL_SECONDS-5-(time.monotonic()-start)
        require(remaining>0, 'frontend total deadline exhausted')
        budget = min(STAGES[stage],remaining)
        entry = {'name':stage,'status':'RUNNING','budget_seconds':budget}
        report['stages'].append(entry);save();t=time.monotonic()
        log = out/(stage+'.log')
        try:
            with log.open('w') as stream:
                rc = run_group(argv,cwd=ROOT,env=dict(os.environ),log=stream,timeout=budget)
            entry.update(exit_code=rc,status='PASS' if rc==0 else 'FAIL',seconds=time.monotonic()-t)
            save();require(rc==0, 'frontend '+stage+' failed')
        except BaseException as error:
            entry.update(status='TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'FAIL',seconds=time.monotonic()-t)
            (out/'diagnostic.txt').write_text(failure_diagnostics(log,prefixes=((out,'<OUT>'),(ROOT,'<REPO>')),stage=stage,error=str(error)))
            save();raise
    save()
    try:
        receipt=prepare(out/'source')
        sources=dict(receipt['generated_sha256'])
        emitter=HERE/'AHoldElaborate.scala'
        sources['AHoldElaborate.scala']=sha(emitter)
        pins=json.loads((HERE/'source_pins.json').read_text())
        source_receipt={'generated':sources,'inputs':pins['inputs'],
                        'source_pins_sha256':sha(HERE/'source_pins.json'),
                        'workflow_sha256':sha(ROOT/'.github/workflows/qwen2-dense-a-hold-frontend.yml')}
        (out/'source-sha256.json').write_text(json.dumps(source_receipt,indent=2,sort_keys=True)+'\n')
        selected=dependencies()
        command('dependencies',[sys.executable,str(HERE/'check_frontend.py'),'--fetch-only','--cache',str(cache)])
        verify_frozen_inputs(out,cache,source_receipt,selected)
        (out/'dependency-sha256.json').write_text(json.dumps({'lock_sha256':LOCK_SHA,'origin':MAVEN,'jars':selected},indent=2,sort_keys=True)+'\n')
        cp=':'.join(str(cache/path) for path in sorted(selected))
        classes=out/'classes';classes.mkdir()
        inputs=sorted((out/'source').glob('*.scala'))+[emitter]
        command('compile',JAVA+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
                  '-Xplugin:'+str(cache/PLUGIN),'-language:reflectiveCalls','-d',str(classes)]+list(map(str,inputs)))
        report['scala_compiled']=True;save()
        command('elaborate',JAVA+['-cp',str(classes)+':'+cp,'heteronpu.continuous.AHoldElaborate',str(out/'chirrtl')])
        report['chirrtl_generated']=True;save()
        actual={p.name:p for p in (out/'chirrtl').glob('*.fir')}
        require(set(actual)==EXPECTED, 'four exact CHIRRTL configurations required')
        report['configurations']={name:{'sha256':sha(path),'bytes':path.stat().st_size,
            'resources':memory_audit(path.read_text(),bool(int(name[len('owner_hold')])))}
            for name,path in sorted(actual.items())}
        report['register_delta']={str(full):register_delta(
            actual[f'owner_hold0_full{full}.fir'].read_text(),
            actual[f'owner_hold1_full{full}.fir'].read_text()) for full in (0,1)}
        verify_frozen_inputs(out,cache,source_receipt,selected)
        report['precompile_and_postflight_hashes_equal']=True
        require(time.monotonic()-start<=TOTAL_SECONDS, 'frontend total deadline exhausted')
        report.update(status='PASS_FRONTEND_ONLY',wall_seconds=time.monotonic()-start);save()
        return report
    except BaseException as error:
        if not (out/'diagnostic.txt').exists():
            (out/'diagnostic.txt').write_text(failure_diagnostics(None,prefixes=((out,'<OUT>'),(ROOT,'<REPO>')),stage='prepare_or_audit',error=str(error)))
        report.update(status='FAILED',wall_seconds=time.monotonic()-start);save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--fetch-only',action='store_true')
    args=parser.parse_args()
    if args.fetch_only:
        require(args.out is None,'fetch-only cannot produce frontend evidence');fetch(args.cache)
    else:
        require(args.out is not None,'--out required');run(args.out,args.cache)
