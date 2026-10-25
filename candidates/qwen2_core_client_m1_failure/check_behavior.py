"""Bounded post-cleanup evidence qualification for exactly normal_m1.

Pure stdlib; importing performs no I/O or execution. Not a simulator, numerical
oracle, full FIRRTL validator, nor proof that a log alone originated in hardware.
The caller must first prove exit0, cleanup, immutable classes/JARs and argv pins.
"""
import hashlib
import codecs
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit

STATUS = 'PASS_NORMAL_M1_TREADLE_SCRIPTED_ENDPOINT_BEHAVIOR_ONLY'
PASS = re.compile(r'CORE_CASE_PASS case=normal_m1 m=1 cycles=(\d+) groups=(\d+) qkAcceptedSteps=(\d+) accounting512Steps=(\d+) results=(\d+) dones=(\d+) scoreWrites=(\d+) targetPrefix= ownerAccepts=(\d+) pvRequests=(\d+) pvReturns=(\d+) requestHoldChecks=(\d+) holdChecksByPort=\(group,(\d+)\),\(memory,(\d+)\),\(pv,(\d+)\),\(step,(\d+)\) memoryAccepted=(\d+) memoryReturned=(\d+) outputBytes=(\d+) numerical_matrix_verified=false')
PASS_FIELDS = ('cycles','groups','qkAcceptedSteps','accounting512Steps','results','dones','scoreWrites','ownerAccepts','pvRequests','pvReturns','requestHoldChecks','hold_group','hold_memory','hold_pv','hold_step','memoryAccepted','memoryReturned','outputBytes')
OBS = re.compile(r'OBS cycle=(\d+) token=(\d+) head=(\d+) phase=(\d+) lane=(\d+) selected=(\d+) faults=(\d+) scoreWrite=(true|false) scoreIndex=(\d+) scoreData=(\d+) max=(\d+) resultReady=(true|false)')
MODULE = re.compile(rb'  module ([A-Za-z_][A-Za-z0-9_$]*)\s*:\s*(?:@\[.*\])?\s*$')
CIRCUIT = re.compile(rb'circuit OrderedQkBehaviorCore\s*:\s*(?:@\[.*\])?\s*$')

def need(ok, why):
    if not ok:
        raise ValueError(why)

def regular(path, limit):
    p=Path(path);s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and not p.is_symlink(), 'regular evidence file')
    need(0<s.st_size<=limit, 'bounded nonempty evidence file')
    return s

def identity(s):
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns

def low_ir(path, e):
    """Stream only declaration/no-blackbox evidence; never build an IR AST.

    FIRRTL2 lowering may rename/deduplicate/expand modules. No claim of matching
    the prior CHIRRTL byte representation or complete low-IR legality is made.
    """
    before=regular(path,e['max_low_ir_bytes']);h=hashlib.sha256()
    modules=set();circuits=0;lines=0;total=0
    with Path(path).open('rb') as f:
        for line in iter(lambda:f.readline(e['max_ir_line_bytes']+1),b''):
            total+=len(line);lines+=1;h.update(line)
            need(len(line)<=e['max_ir_line_bytes'] and lines<=e['max_ir_lines'] and total<=e['max_low_ir_bytes'], 'bounded IR line/count/bytes')
            text=line.decode('utf8');code=text.split('@[',1)[0].strip()
            need(not re.search(r'\b(?:extmodule|intmodule|intrinsic|defname)\b',code), 'no external/intrinsic/blackbox declaration')
            if re.match(r'^(?:(?:public|private)\s+)?circuit\b',code):
                need(CIRCUIT.fullmatch(line.rstrip(b'\r\n')) is not None,'exact low FIRRTL circuit')
                circuits+=1
            if re.match(r'^(?:(?:public|private)\s+)?module\b',code):
                m=MODULE.fullmatch(line.rstrip(b'\r\n'));need(m is not None,'parsed low module declaration')
                n=m[1].decode();need(n not in modules,'duplicate low module')
                modules.add(n);need(len(modules)<=e['max_ir_modules'],'bounded low modules')
    need(circuits==1 and 'OrderedQkBehaviorCore' in modules,'low circuit/top present')
    need(identity(before)==identity(Path(path).lstat()),'low IR changed during read')
    return dict(path=str(path),bytes=total,sha256=h.hexdigest(),line_count=lines,module_count=len(modules),
                no_external_or_intrinsic_declarations=True,full_firrtl_semantic_validation=False)

def check_log(raw, e, run_root):
    need(0<len(raw)<=e['max_log_bytes'],'bounded log')
    text=raw.decode('utf8');need('\x1b' not in text and '\x00' not in text,'plain UTF8 report')
    lines=text.splitlines();need(len(lines)<=e['max_log_lines'],'bounded log lines')
    need(all(len(x.encode('utf8'))<=e['max_log_line_bytes'] for x in lines),'bounded log line')
    origins={};ready=[];passes=[];observations=[];summaries={}
    expected_summaries={
        'Total number of tests run:':'Total number of tests run: 1',
        'Suites:':'Suites: completed 1, aborted 0',
        'Tests:':'Tests: succeeded 1, failed 0, canceled 0, ignored 0, pending 0',
        'All tests passed.':'All tests passed.'}
    for i,line in enumerate(lines):
        if line.startswith('CORE_CLASS_ORIGIN '):
            parts=line.split(' ');need(len(parts)==3,'origin record shape');_,name,uri=parts
            need(name in e['class_origins'] and name not in origins,'unique exact class origin')
            u=urlsplit(uri);need(u.scheme=='file' and not u.netloc and not u.query and not u.fragment,'local origin URI')
            want=e['class_origins'][name].replace('${NEW_RUN_ROOT}',str(run_root))
            need(unquote(u.path).rstrip('/')==want.rstrip('/'),'exact class origin path')
            origins[name]=dict(line=i,uri=uri)
        elif line.startswith('CORE_SIM_READY'):
            need(line=='CORE_SIM_READY case=normal_m1 m=1 backend=treadle2 scripted_matrix=true','only selected M1 ready')
            ready.append(i)
        elif line.startswith('CORE_CASE_PASS'):
            m=PASS.fullmatch(line);need(m is not None,'exact M1 terminal evidence grammar')
            passes.append((i,dict(zip(PASS_FIELDS,map(int,m.groups())))))
        elif line.startswith('OBS '):
            m=OBS.fullmatch(line);need(m is not None,'bounded OBS grammar')
            need(len(observations)<408,'no excess ordered vector observations')
            observations.append((i,m.groups()))
        elif line.startswith(('CORE_','OBS','INJECT','FOREIGN_RECOVERY')):
            raise ValueError('unexpected case/control marker')
        for prefix,exact in expected_summaries.items():
            if line.startswith(prefix):
                need(line==exact and prefix not in summaries,'one successful ScalaTest case summary')
                summaries[prefix]=i
        need('*** FAILED ***' not in line and '*** ABORTED ***' not in line,'no ScalaTest failure marker')
    need(set(origins)==set(e['class_origins']) and len(ready)==len(passes)==1,'complete origins/one ready/one terminal')
    need(set(summaries)==set(expected_summaries),'complete ScalaTest completion evidence')
    pi,counts=passes[0]
    need(max(x['line'] for x in origins.values())<ready[0]<pi<min(summaries.values()),'origin/ready/terminal/completion order')
    need(12<=counts['cycles']<=99997,'body clock cap, excludes framework1 and explicit2')
    for k,v in e['expected_counts'].items():need(counts[k]==v,'independent exact M1 count '+k)
    hs=[counts['hold_'+p] for p in ('group','memory','pv','step')]
    need(all(0<=x<=counts['cycles'] for x in hs) and sum(hs)==counts['requestHoldChecks'] and 0<sum(hs)<=4*counts['cycles'],'observed per-port request hold counts and sum')
    need(len(observations)==408,'12 heads x (16 scan+16 fold+1 scale+1 retire)')
    previous=-1;by_phase={str(p):0 for p in (1,2,3,4)}
    for index,(li,g) in enumerate(observations):
        cycle,token,head,phase,lane,selected,faults=map(int,g[:7]);sw=g[7]=='true'
        scoreindex,scoredata,maxscore=map(int,g[8:11]);rr=g[11]=='true'
        h,offset=divmod(index,34)
        expected_phase=1 if offset<16 else 2 if offset<32 else 3 if offset==32 else 4
        expected_lane=offset if offset<16 else offset-16 if offset<32 else 15
        need(ready[0]<li<pi and previous<cycle<counts['cycles'],'monotonic body observations')
        if offset:need(cycle==previous+1,'consecutive selected-vector phase clocks')
        need((token,head,phase,lane,selected,faults)==(0,h,expected_phase,expected_lane,0,0),'independent M1 phase/lane/head/fault order')
        need(not rr and sw==(phase==4),'held result and real score write-site retirement')
        if sw:need(scoreindex==0 and scoredata==0,'actual M1 zero score retire')
        need(0<=scoreindex<1024 and 0<=scoredata<2**32 and 0<=maxscore<2**32,'owner observation field widths')
        previous=cycle;by_phase[str(phase)]+=1
    return dict(counts=counts,body_clock_steps=counts['cycles'],framework_reset_steps=1,
                explicit_reset_steps=2,interpreted_clock_steps_including_resets=counts['cycles']+3,
                vector_phase_clock_counts=by_phase,class_origins=origins,
                scala_test_cases_passed=1,ordered_observation_count=408,
                stalled_request_hold_covered_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]>0],
                stalled_request_hold_uncovered_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]==0],
                log_bytes=len(raw),log_sha256=hashlib.sha256(raw).hexdigest(),
                warnings=[x for x in lines if '[W005]' in x])

def check(run_root, expectation):
    root=Path(run_root);e=expectation
    need(e['case']=='normal_m1' and e['schema']=='qwen2-normal-m1-evidence-v1','only M1 evidence schema')
    p=root/'worker.log';before=regular(p,e['max_log_bytes']);raw=p.read_bytes()
    report=check_log(raw,e,root);need(identity(before)==identity(p.lstat()),'log changed during read')
    simulation=root/'normal_m1'/'simulation'
    need(simulation.is_dir() and not simulation.is_symlink(),'actual relative backend target')
    artifacts=[]
    for path in simulation.rglob('*'):
        need(path.is_file() and not path.is_symlink(),'no nested or special backend artifacts')
        rel=str(path.relative_to(root));need(rel in e['allowed_backend_files'],'closed backend artifact names')
        if rel==e['required_low_ir']:artifacts.append(low_ir(path,e))
        else:
            # The optional compiler annotation record is metadata, not another
            # numeric result or permission to instantiate external blackboxes.
            b=regular(path,e['max_annotation_bytes']);h=hashlib.sha256();total=0;tail=''
            decoder=codecs.getincrementaldecoder('utf8')()
            # BlackBoxTargetDirAnno alone is compiler bookkeeping, not a box.
            forbidden=('BlackBoxInline','BlackBoxPath','BlackBoxResource','BlackBoxFactories','WriteVcd','SaveFirrtlAtLoad','WriteCoverageCSV','Verilator','VcsBackend','CallResetAtStartup')
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(65536),b''):
                    h.update(block);total+=len(block);need(total<=e['max_annotation_bytes'],'bounded annotation bytes')
                    t=tail+decoder.decode(block);need(not any(x in t for x in forbidden),'no unsupported backend annotations');tail=t[-64:]
                decoder.decode(b'',final=True)
            need(total==b.st_size and identity(b)==identity(path.lstat()),'stable annotation record')
            artifacts.append(dict(path=str(path),bytes=total,sha256=h.hexdigest(),role='compiler_annotation_metadata',json_semantic_validation=False))
    need(any(x['path']==str(root/e['required_low_ir']) for x in artifacts),'mandatory low FIRRTL materialization')
    return dict(status=STATUS,case='normal_m1',evidence=report,backend_artifacts=artifacts,
                scope=dict(actual_chisel_treadle_interpretation=True,actual_core_alu_scalar_sram=True,
                           scripted_external_matrix_and_memory=True,full_matrix_numerical_pass=False,
                           fullblock_accepted=False,full128_rtl_replay=False,systemverilog_simulated=False,
                           matrix_mac_utilization=None,accounting512_steps_are_measured_mac_count=False,
                           low_firrtl_semantic_validation=False))
