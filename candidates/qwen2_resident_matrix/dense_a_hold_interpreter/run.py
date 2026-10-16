"""Bounded one-case interpretation of the real owner; no emitted RTL backend."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit,unquote

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_resident_matrix.dense_a_hold_interpreter.prepare import prepare,sha,require
from candidates.qwen2_resident_matrix.dense_a_hold_chisel.check_frontend import dependencies as base_dependencies, memory_audit, register_inventory
from candidates.qwen2_resident_matrix.raw_kv.run_unit import run_group
from candidates.qwen2_resident_matrix.raw_kv_parent.run_unit import _diagnostic_text

MAVEN='https://repo.maven.apache.org/maven2/'
WORKFLOW='.github/workflows/qwen2-dense-a-hold-interpreter.yml'
PLUGIN='org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
TOTAL_SECONDS=600
STAGES={'dependencies':120,'compile':180,'structure':30,'interpret':240}
JAVA_FLAGS=['-showversion','-Xmx2048m','-Xss4m','-XX:ActiveProcessorCount=1']
CASE='preserve every packet and private A copy with reuse=true'
CLASS_ORIGINS={
    'treadle2.TreadleTester':'edu/berkeley/cs/chiseltest_2.13/6.0.0/chiseltest_2.13-6.0.0.jar',
    'firrtl2.stage.FirrtlStage':'edu/berkeley/cs/firrtl2_2.13/6.0.0/firrtl2_2.13-6.0.0.jar',
    'chisel3.RawModule':'org/chipsalliance/chisel_2.13/6.7.0/chisel_2.13-6.7.0.jar',
    'org.json4s.JValue':'org/json4s/json4s-ast_2.13/4.1.0-M4/json4s-ast_2.13-4.1.0-M4.jar',
    'com.sun.jna.Native':'net/java/dev/jna/jna/5.14.0/jna-5.14.0.jar',
    'org.scalatest.tools.Runner':'org/scalatest/scalatest-core_2.13/3.2.19/scalatest-core_2.13-3.2.19.jar',
    'scala.Predef$':'org/scala-lang/scala-library/2.13.16/scala-library-2.13.16.jar'}


def bounded_log_lines(path):
    if path is None or not Path(path).is_file():return []
    window=128*1024
    with Path(path).open('rb') as stream:
        size=stream.seek(0,os.SEEK_END);stream.seek(0);head=stream.read(window)
        blocks=[head if size<=window else head.rsplit(b'\n',1)[0]]
        if size>window:
            stream.seek(max(window,size-window));blocks.append(stream.read(window).split(b'\n',1)[-1])
    return [re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
        for block in blocks for line in block.decode('utf-8',errors='replace').splitlines()
        if len(line.encode('utf-8'))<=1024]


def failure_progress(path):
    lines=bounded_log_lines(path)
    cycles=[int(m.group(1)) for line in lines
        if (m:=re.fullmatch(r'AHOLD_CYCLE reuse=true k=32 cycle=(\d{1,5})',line)) and int(m.group(1))<=20000]
    return {'case_begin_seen':'AHOLD_CASE_BEGIN reuse=true k=32' in lines,
        'sim_ready_seen':'AHOLD_SIM_READY reuse=true k=32' in lines,
        'last_reported_cycle':max(cycles) if cycles else None,
        'case_pass_marker_seen':any(re.fullmatch(r'AHOLD_CASE_PASS reuse=true k=32 accepted=\d{1,5} returned=\d{1,5} gathered=\d{1,5} a_reads=\d{1,5} steps=\d{1,5} cycles=\d{1,5}',line) for line in lines)}


def failure_diagnostics(path,*,prefixes=(),stage='runner',error=''):
    """Keep direct scalac/ScalaTest failure lines without source echoes or payloads."""
    chosen=[]
    for line in bounded_log_lines(path):
        selected=(re.match(r'.*\.scala:\d+(?::\d+)?:\s*error:',line)
            or re.match(r'(?:error|fatal error):',line)
            or re.search(r'\*\*\* (?:FAILED|CANCELED|ABORTED|RUN ABORTED) \*\*\*',line)
            or re.match(r'(?:Exception in thread "[^"]+" )?(?:[A-Za-z_$][\w$]*\.)*[A-Za-z_$][\w$]*(?:Exception|Error):',line)
            or re.match(r'(?:Assertion failed|assertion failed|.*(?:did not equal|was not equal to|timed out|Timeout))\b',line))
        if selected:
            clean=_diagnostic_text(line,prefixes)
            if clean and clean not in chosen:chosen.append(clean)
    if len(chosen)>10:chosen=chosen[:5]+['[intermediate diagnostic lines omitted]']+chosen[-5:]
    lines=['[A-hold interpreter failure: '+_diagnostic_text(stage,prefixes,64)+']',_diagnostic_text(error,prefixes,512)]
    lines+=chosen or ['[no selected direct compiler/test error in bounded head/tail]']
    return ('\n'.join(lines)+'\n').encode('utf-8')[:4096].decode('utf-8',errors='ignore')


def dependencies():
    lock=json.loads((HERE/'dependency-lock.json').read_text())
    require(lock['schema']==1 and lock['origin']==MAVEN and lock['jar_content_hashes_frozen'] is True,'unfrozen interpreter dependencies')
    base=base_dependencies();selected=dict(base)
    require(len(lock['removed'])==6 and len(lock['added'])==25,'explicit 6/25 dependency delta')
    for path,digest in lock['removed'].items():
        require(selected.pop(path,None)==digest,'removed dependency differs from original lock')
    for path,item in lock['added'].items():
        require(path not in selected,'new dependency already exists')
        selected[path]=item['sha256']
    require(len(selected)==106 and selected==lock['jars'] and PLUGIN in selected,'exact interpreter classpath closure')
    for path,digest in selected.items():
        require(not path.startswith('/') and '..' not in Path(path).parts and path.endswith('.jar') and re.fullmatch('[0-9a-f]{64}',digest),'invalid jar identity')
    return selected


def fetch(cache):
    cache=Path(cache)
    def one(item):
        path,digest=item;target=cache/path
        if not target.exists():
            with urllib.request.urlopen(MAVEN+path,timeout=30) as response:data=response.read(64*1024*1024+1)
            require(len(data)<=64*1024*1024 and hashlib.sha256(data).hexdigest()==digest,'downloaded dependency drift: '+path)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        require(sha(target)==digest,'cached dependency drift: '+path)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,sorted(dependencies().items())))


def result_audit(log):
    require(re.findall(r'Total number of tests run:\s*(\d+)\b',log)==['1'],'exactly one selected ScalaTest required')
    require(log.count('All tests passed')==1 and CASE in log,'missing selected case pass')
    require(not re.search(r'\*\*\* (?:FAILED|CANCELED|ABORTED) \*\*\*|(?:failed|canceled|ignored|pending|aborted) [1-9]\d*',log),'failed/canceled test cannot pass')
    markers=[line.strip() for line in log.splitlines() if line.strip().startswith('AHOLD_') and not line.strip().startswith('AHOLD_CLASS_ORIGIN ')]
    require(markers and markers[0]=='AHOLD_CASE_BEGIN reuse=true k=32','wrong first case')
    require(len(markers)>=3 and markers[1]=='AHOLD_SIM_READY reuse=true k=32','actual interpreter callback not entered')
    match=re.fullmatch(r'AHOLD_CASE_PASS reuse=true k=32 accepted=(\d+) returned=(\d+) gathered=(\d+) a_reads=(\d+) steps=(\d+) cycles=(\d+)',markers[-1])
    require(match is not None,'missing complete case counters')
    accepted,returned,gathered,a_reads,steps,cycles=map(int,match.groups())
    require(accepted==returned and accepted>0 and gathered==160 and a_reads==32 and steps==160 and 0<cycles<=20000,'packet/A-read/debt counters differ')
    expected=[f'AHOLD_CYCLE reuse=true k=32 cycle={c}' for c in range(1024,cycles+1,1024)]
    require(markers[2:-1]==expected,'missing/duplicate/unexpected cycle or case marker')
    return {'scala_tests':1,'case':CASE,'m':16,'k':32,'n':160,
        'accepted_dma_requests':accepted,'retired_dma_responses':returned,
        'bank_gathers':gathered,'a_bank_gathers':a_reads,'matrix_packets':steps,'clock_cycles':cycles}


def origin_audit(log,cache,selected):
    lines=[line.strip() for line in log.splitlines() if line.strip().startswith('AHOLD_CLASS_ORIGIN')]
    found={}
    for line in lines:
        match=re.fullmatch(r'AHOLD_CLASS_ORIGIN (\S+) (\S+)',line)
        require(match is not None,'malformed class origin')
        name,uri=match.groups();require(name in CLASS_ORIGINS and name not in found,'unexpected or repeated class origin')
        parsed=urlsplit(uri);coordinate=CLASS_ORIGINS[name]
        require(parsed.scheme=='file' and not parsed.netloc and not parsed.query and not parsed.fragment,'class origin is not local jar')
        require(Path(unquote(parsed.path)).resolve()==(cache/coordinate).resolve(),'loaded class differs from selected jar: '+name)
        require(coordinate in selected,'class origin not in frozen classpath')
        found[name]={'jar':coordinate,'sha256':selected[coordinate]}
    require(set(found)==set(CLASS_ORIGINS),'missing loaded class origins')
    return found


def structural_audit(directory):
    directory=Path(directory)
    require({p.name for p in directory.glob('*.fir')}=={'owner.fir','probe.fir'},'two exact structural tops required')
    owner=(directory/'owner.fir').read_text();probe=(directory/'probe.fir').read_text()
    require(len(re.findall(r'^\s*module AHoldProbe\s*:',probe,re.M))==1,'actual observed owner top required')
    normalized=re.sub(r'\bAHoldProbe\b','TransposedDenseDownOwner',probe)
    before=memory_audit(owner,True);after=memory_audit(normalized,True)
    require(before==after,'observation probe changes bank/Queue resource declarations')
    require(register_inventory(owner)==register_inventory(normalized),'observation probe changes state')
    return {'owner_sha256':sha(directory/'owner.fir'),'probe_sha256':sha(directory/'probe.fir'),
        'owner_bytes':len(owner.encode()),'probe_bytes':len(probe.encode()),'resources':after,
        'probe_changes_registers':False,'scope':'original CHIRRTL before memory lowering'}


def frozen_receipt(out,generated,java):
    pins=json.loads((HERE/'source_pins.json').read_text())
    return {'inputs':pins['inputs'],'generated':generated,'source_pins_sha256':sha(HERE/'source_pins.json'),
        'workflow_sha256':sha(ROOT/WORKFLOW),'dependency_lock_sha256':sha(HERE/'dependency-lock.json'),
        'java_executable':str(java),'java_executable_sha256':sha(java)}


def class_inventory(directory):
    files=[p for p in directory.rglob('*') if p.is_file()]
    require(files and all(p.suffix=='.class' for p in files),'missing or unexpected compiled output')
    return {str(p.relative_to(directory)):sha(p) for p in sorted(files)}


def verify_frozen(out,cache,receipt,selected):
    require(sha(HERE/'source_pins.json')==receipt['source_pins_sha256'],'source pins changed during qualification')
    require(sha(ROOT/WORKFLOW)==receipt['workflow_sha256'],'workflow changed during qualification')
    require(sha(HERE/'dependency-lock.json')==receipt['dependency_lock_sha256'],'dependency lock changed during qualification')
    require(sha(Path(receipt['java_executable']))==receipt['java_executable_sha256'],'Java executable changed during qualification')
    for path,digest in receipt['inputs'].items():require(sha(ROOT/path)==digest,'repository input changed: '+path)
    require({p.name:sha(p) for p in (out/'source').glob('*.scala')}==receipt['generated'],'private generated source changed')
    require(dependencies()==selected,'selected dependency closure changed')
    for path,digest in selected.items():require(sha(cache/path)==digest,'dependency jar changed: '+path)
    if 'compiled_classes' in receipt:
        require(class_inventory(out/'classes')==receipt['compiled_classes'],'compiled classes changed during qualification')


def run(out,cache):
    out,cache=Path(out).resolve(),Path(cache).resolve()
    require(not out.exists(),'fresh interpreter output required');out.mkdir(parents=True)
    start=time.monotonic()
    report={'status':'STARTED','stages':[],'scala_compiled':False,'chirrtl_generated':False,
        'interpreted_hardware_protocol':False,'emitted_rtl_simulation':False,'rtl_generated':False,
        'matrix_arithmetic':False,'full_business_block_acceptance':False,'hardware_timing_or_utilization':False,
        'budget':{'total_seconds':TOTAL_SECONDS,'stages_seconds':STAGES,'cleanup_reserve_seconds':30,
            'java_heap_mib':2048,'java_stack_mib':4,'java_active_processors':1,'download_workers':4,'max_test_cycles':20000}}
    def save():(out/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    def command(stage,argv,*,cwd=None,env=None):
        remaining=TOTAL_SECONDS-30-(time.monotonic()-start)
        require(remaining>0,'interpreter total deadline exhausted')
        budget=min(STAGES[stage],remaining);entry={'name':stage,'status':'RUNNING','budget_seconds':budget}
        report['stages'].append(entry);save();begin=time.monotonic();log=out/(stage+'.log')
        try:
            with log.open('w') as stream:rc=run_group(argv,cwd=cwd or out,env=env or dict(os.environ),log=stream,timeout=budget)
            entry.update(exit_code=rc,status='PASS' if rc==0 else 'FAIL',seconds=time.monotonic()-begin);save()
            require(rc==0,'interpreter '+stage+' failed')
        except BaseException as error:
            entry.update(status='TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'FAIL',seconds=time.monotonic()-begin)
            (out/'diagnostic.txt').write_text(failure_diagnostics(log,prefixes=((out,'<OUT>'),(ROOT,'<REPO>')),stage=stage,error=str(error)))
            save();raise
    save()
    try:
        generated=prepare(out/'source')
        executable=shutil.which('java');require(executable is not None,'Java21 executable required')
        java=Path(executable).resolve();receipt=frozen_receipt(out,generated,java)
        (out/'source-sha256.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        selected=dependencies()
        command('dependencies',[sys.executable,str(HERE/'run.py'),'--fetch-only','--cache',str(cache)])
        verify_frozen(out,cache,receipt,selected)
        (out/'dependency-sha256.json').write_text(json.dumps({'lock_sha256':receipt['dependency_lock_sha256'],'origin':MAVEN,'jars':selected},indent=2,sort_keys=True)+'\n')
        cp=':'.join(str(cache/path) for path in sorted(selected));classes=out/'classes';classes.mkdir()
        # Use an absolute Java executable and an empty PATH for JVM subprocesses.
        # The interpreter route must not find firtool, Verilator or a C++ compiler.
        guard=out/'no-external-tools';guard.mkdir();env=dict(os.environ);env['PATH']=str(guard)
        for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','CLASSPATH'):env.pop(key,None)
        jvm=[str(java)]+JAVA_FLAGS
        command('compile',jvm+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
            '-Xplugin:'+str(cache/PLUGIN),'-language:reflectiveCalls','-d',str(classes)]+
            list(map(str,sorted((out/'source').glob('*.scala')))),env=env)
        versions=re.findall(r'^(?:openjdk|java) version "([^"]+)"',(out/'compile.log').read_text(),re.M)
        require(len(versions)==1 and versions[0].startswith('21.'),'exact Java21 runtime required')
        report['java_version']=versions[0]
        receipt['compiled_classes']=class_inventory(classes)
        (out/'source-sha256.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        verify_frozen(out,cache,receipt,selected)
        report['scala_compiled']=True;save()
        command('structure',jvm+['-cp',str(classes)+':'+cp,'heteronpu.continuous.ProbeElaborate',str(out/'chirrtl')],env=env)
        report['chirrtl_generated']=True;report['structure']=structural_audit(out/'chirrtl');save()
        verify_frozen(out,cache,receipt,selected)
        command('interpret',jvm+['-cp',str(classes)+':'+cp,'org.scalatest.tools.Runner',
            '-R',str(classes),'-oW','-s','heteronpu.continuous.AHoldUnit','-z','reuse=true'],env=env)
        report['case']=result_audit((out/'interpret.log').read_text())
        report['loaded_class_origins']=origin_audit((out/'interpret.log').read_text(),cache,selected)
        require(not any(p.suffix in {'.v','.sv','.vcd','.fst','.so','.o'} for p in out.rglob('*') if p.is_file()),'unexpected emitted RTL/native/waveform artifact')
        verify_frozen(out,cache,receipt,selected)
        report['precompile_and_postflight_hashes_equal']=True
        require(time.monotonic()-start<=TOTAL_SECONDS,'interpreter total deadline exhausted')
        report.update(status='PASS_ONE_CASE_INTERPRETED_PROTOCOL',interpreted_hardware_protocol=True,wall_seconds=time.monotonic()-start);save()
        return report
    except BaseException as error:
        report['interpret_progress']=failure_progress(out/'interpret.log')
        if not (out/'diagnostic.txt').exists():(out/'diagnostic.txt').write_text(failure_diagnostics(None,prefixes=((out,'<OUT>'),(ROOT,'<REPO>')),stage='prepare_or_audit',error=str(error)))
        report.update(status='FAILED',wall_seconds=time.monotonic()-start);save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path)
    parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--fetch-only',action='store_true');args=parser.parse_args()
    if args.fetch_only:
        require(args.out is None,'fetch-only cannot claim qualification');fetch(args.cache)
    else:
        require(args.out is not None,'fresh --out required');run(args.out,args.cache)
