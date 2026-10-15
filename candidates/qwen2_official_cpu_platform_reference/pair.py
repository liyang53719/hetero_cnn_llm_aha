"""Two externally certified fresh successes; local payload equality, never freeze.

No arithmetic, download, certificate creation, or retry occurs on import/default.
The original one-use guard owns each 120/122-second capture. Detailed receipts,
identities, payloads and logs stay local. Only fixed aggregate enums are public.
"""
import contextlib
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
from . import policy as P, validator as V

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUNS=('new01','new02')
WORK='work/qwen2_official_cpu_platform_reference'
AUTH='candidates/qwen2_official_cpu_platform_authorization'
LOGS='work/qwen2_official_cpu_platform_pair_logs'
CHUNK=1<<20
RUN_CAP=34*(1<<20)
TOTAL_CAP=69*(1<<20)
PHASE='NOT_STARTED'
STAGES=('wrapper-boundary-before','worker-start','source-and-raw-boundary-before',
    'raw13-load','numeric-import-and-runtime-identity','official-holder-construction-and-raw-bindings',
    'official-prefix-execution','official-tail-execution','observations29-and-semantic-validation',
    'source-and-raw-boundary-after','write-payloads','worker-complete-awaiting-wrapper-validation',
    'wrapper-boundary-after','validated-awaiting-seal')
STATUS='NEW_PLATFORM_REFERENCE_OBSERVATIONS_PENDING_REVIEW'
SEALED='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED'
COMMON_EXCLUDED=frozenset(('external_certificate_sha256',))
DIGEST_FIELDS=frozenset(('sha256','native_sha256','token_major_sha256'))


def need(ok,message):
    if not ok:raise ValueError(message)


def phase(value):
    global PHASE
    need(value in {'NOT_STARTED','COLD','ADMIT_NEW01','ADMIT_NEW02','PREPARE_BINDINGS',
        'CAPTURE_NEW01','CAPTURE_NEW02','VALIDATE_NEW01','VALIDATE_NEW02',
        'PAIR_PRECHECK','PAIR_COMPARE','PAIR_POSTCHECK','WRITE_AGGREGATE'},'fixed phase')
    PHASE=value


def canonical(path):
    path=Path(path)
    need(path.is_absolute() and path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),
        'canonical unaliased path')
    return path


def private(relative):
    path=Path(relative)
    need(not path.is_absolute() and '..' not in path.parts,'relative private path')
    return canonical(ROOT/path)


def same(left,right):return V.F.same(left,right)


def stat_id(value):
    return tuple(getattr(value,key) for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))


def file_identity(path,cap=RUN_CAP):
    path=canonical(path);before=path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<=before.st_size<=cap,'bounded regular nonlinked file')
    digest=hashlib.sha256();size=0
    with path.open('rb') as stream:
        need(stat_id(os.fstat(stream.fileno()))==stat_id(before),'file changed at open')
        for block in iter(lambda:stream.read(CHUNK),b''):
            size+=len(block);need(size<=cap,'bounded file');digest.update(block)
        need(stat_id(os.fstat(stream.fileno()))==stat_id(before),'file changed during read')
    canonical(path);need(stat_id(path.stat())==stat_id(before) and size==before.st_size,'file changed after read')
    return dict(bytes=size,sha256=digest.hexdigest())


def read_json(path,cap=262144):
    file_identity(path,cap)
    return V.parse(path.read_bytes())


def run_out(run):
    need(run in RUNS,'fixed fresh run')
    return private(WORK+'/'+run+'/bootstrap')


def guard_log(run):return private(LOGS+'/'+run+'/reference_guard.log')


def authorization(run):
    need(run in RUNS,'fixed certificate run')
    base=AUTH+'/'+run+'/'
    pins=read_json(private(base+'EXTERNAL_PINS.json'),4096)
    V.exact(pins,('schema','certificate_sha256','source_closure_sha256'))
    need(type(pins['schema']) is int and pins['schema']==1,'external pin schema')
    for key in ('certificate_sha256','source_closure_sha256'):
        V.digest(pins[key]);need(pins[key]!='0'*64,'real external pin')
    path=private(base+'SOURCE_CERTIFICATE.json');identity=file_identity(path,262144)
    need(identity['sha256']==pins['certificate_sha256'],'external certificate byte drift')
    need(V.source_digest(ROOT)==pins['source_closure_sha256'],'actual reviewed source closure drift')
    return pins,path.read_bytes()


@contextlib.contextmanager
def configured(run):
    need(os.getenv('QWEN2_CI_RUNTIME_PROFILE')==P.PROFILE and os.getenv('ATEN_CPU_CAPABILITY')=='avx2',
        'explicit new profile')
    need('QWEN2_REFERENCE_REPEAT_RUN' not in os.environ,'old repeat protocol forbidden')
    pins,_=authorization(run)
    mapping=dict(QWEN2_NEW_REFERENCE_RUN=run,
        QWEN2_BOOTSTRAP_CERTIFICATE_SHA256=pins['certificate_sha256'],
        QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256=pins['source_closure_sha256'])
    old={key:os.environ.get(key) for key in mapping}
    for key in mapping:
        need(old[key] in (None,'',mapping[key]),'external environment pin conflict')
    try:
        os.environ.update(mapping);yield pins
    finally:
        for key,value in old.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def certificate_path(run):return WORK+'/EXTERNAL_'+run+'.json'


def arguments(flag,run,pins):
    return [flag,'--certificate',certificate_path(run),'--certificate-sha256',pins['certificate_sha256'],
        '--source-closure-sha256',pins['source_closure_sha256'],'--run-id',run]


def call(script,args,log,timeout=130):
    script=private(script);log=private(log);log.parent.mkdir(parents=True,exist_ok=True)
    # No output is streamed publicly. The original guard separately watches its
    # worker and supervisor; this outer bound is only emergency process cleanup.
    with log.open('xb') as stream:
        child=subprocess.Popen([str(Path(sys.executable).resolve()),'-B',str(script),*args],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=child.wait(timeout=timeout)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
            raise
    need(code==0,'stage did not complete successfully')


def admit():
    source=None;certificates=[]
    for run in RUNS:
        phase('ADMIT_'+run.upper())
        with configured(run) as pins:
            if source is None:source=pins['source_closure_sha256']
            need(source==pins['source_closure_sha256'],'pair must share reviewed source')
            certificates.append(pins['certificate_sha256'])
            _,raw=authorization(run)
            target=private(certificate_path(run));target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(raw)
            call(P.PACKAGE+'/issuer.py',arguments('--validate-only',run,pins),LOGS+'/'+run+'/certificate_validation.log')
    need(len(set(certificates))==2,'two separate externally certified invocations')
    return aggregate('PAIR_SOURCE_ADMITTED_PENDING_CAPTURE',0,[])


def runtime():
    # Standalone legacy adapters use sibling absolute imports. Do not replace a
    # different loaded adapter, and never put a numerical directory on sys.path.
    sys.path.insert(0,str(HERE))
    try:
        R=importlib.import_module('recipe');L=importlib.import_module('lifecycle')
    finally:sys.path.pop(0)
    need(Path(R.__file__).resolve()==HERE/'recipe.py' and Path(L.__file__).resolve()==HERE/'lifecycle.py',
        'exact new source adapters')
    need(not any(name in sys.modules for name in ('torch','numpy','transformers')),'cold verifier')
    return R,L


def inventory(out,names):
    canonical(out);need(out.is_dir() and {p.name for p in out.iterdir()}==set(names),'exact sealed inventory')
    identities={name:file_identity(out/name) for name in sorted(names)}
    need(sum(item['bytes'] for item in identities.values())<=RUN_CAP,'per-run disk cap')
    return identities


def disk_gate(reserve=0):
    total=0;directory=private(WORK)
    need(type(reserve) is int and reserve in (0,RUN_CAP),'fixed optional run reservation')
    if directory.exists():
        canonical(directory)
        for path in directory.rglob('*'):
            canonical(path)
            need(path.is_file() or path.is_dir(),'regular output tree')
            if path.is_file():
                need(path.stat().st_nlink==1,'output hardlink');total+=path.stat().st_size
    need(total+reserve<=TOTAL_CAP,'69 MiB aggregate pair cap')


def resources_checked(resources,files):
    need(type(resources) is dict,'resource evidence')
    expected=dict(returncode=0,limit_reason=None,cleanup_pids=[],rss_is_os_hard_cap=False,
        rss_limit_bytes=1536*(1<<20),independent_watchdog_enabled=False,independent_watchdog_record=None,
        overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,cleanup_grace_seconds=2,
        independent_overall_watchdog_enabled=True,
        overall_clock_started_at='run entry before source/go/input/runtime preflight')
    for key,value in expected.items():need(key in resources and same(resources[key],value),'successful original supervisor resources')
    for key,bound in (('overall_elapsed_seconds',120),('wall_seconds',120),('wall_limit_seconds',120),
        ('peak_sampled_process_tree_rss_bytes',1536*(1<<20))):
        value=resources[key];need(type(value) in (int,float) and math.isfinite(value) and 0<=value<=bound,'bounded resource value')
    need(resources['rss_poll_seconds']==0.02,'original RSS polling')
    cleanup=resources['descendant_cleanup'];V.exact(cleanup,('reaped_descendant_pids','remaining_descendants','cleanup_wait_limit_seconds'))
    need(cleanup['remaining_descendants']=={} and cleanup['cleanup_wait_limit_seconds']==2 and type(cleanup['reaped_descendant_pids']) is list,'complete descendant cleanup')
    V.exact(resources['logs'],('stdout','stderr'))
    for name,spec in resources['logs'].items():
        V.exact(spec,('total_bytes','sha256_all_observed_bytes','retained_bytes','truncated','retained_sha256'))
        need(type(spec['total_bytes']) is int and 0<=spec['total_bytes']<=16*(1<<20) and
            type(spec['retained_bytes']) is int and 0<=spec['retained_bytes']<=65536 and
            spec['retained_bytes']==min(spec['total_bytes'],65536) and
            spec['truncated'] is (spec['total_bytes']>65536),'bounded worker logs')
        V.digest(spec['sha256_all_observed_bytes']);V.digest(spec['retained_sha256'])
        need(files[name+'.log']==dict(bytes=spec['retained_bytes'],sha256=spec['retained_sha256']),'guard log identity')
    need(sum(s['total_bytes'] for s in resources['logs'].values())<=16*(1<<20),'total emitted log bound')


def observations_checked(R,pins,observations,before):
    R.fields(observations,dict(status=STATUS,stage='bootstrap',contract_id=P.policy()['contract_id'],
        numerical_acceptance_claimed=False,dut_executed=False,old_pass_inherited=False,full_29_node_acceptance=False,
        official_model_ast_nodes=38,official_activation_ast_nodes=14,official_ast_subset_executed=True,
        full_official_forward_executed=False,dynamic_cache_executed=False,transformers_imported=False,
        actual_or_typed_input_read=False,materialized_producer_payload_read=False,saved_reference_payload_read=False,
        legacy_frozen29_comparison_performed=False,source_manifest=before['source_manifest'],source_pins_sha256=R.PINS_SHA256),
        'successful new-contract observation')
    R.validate_new_observations(observations['outputs'],pins)
    R.fields(observations['boundary'],dict(unchanged=True,before_sha256=P.sha(R.encoded(before)),
        after_sha256=P.sha(R.encoded(before))),'worker boundary byte identities')
    V._platform(observations['platform_before'],observations['platform_after'])
    need(same({key:observations['platform_before'][key] for key in ('python','libpython')},before['platform_files']),
        'actual worker loaded platform binding')
    legacy=observations['legacy_contract_diagnostic'];V.exact(legacy,('status','compared_count','equal_count','records'))
    rows=legacy['records'];need(type(rows) is list and len(rows)==18,'complete legacy diagnostics')
    for i,row in enumerate(rows):
        V.exact(row,('node','equal'));need(row['node']=='NODE_%02d'%i and type(row['equal']) is bool,'fixed legacy node')
    count=sum(row['equal'] for row in rows)
    need(type(legacy['compared_count']) is int and legacy['compared_count']==18 and
        type(legacy['equal_count']) is int and legacy['equal_count']==count and
        legacy['status']==('LEGACY_CONTRACT_EQUAL' if count==18 else 'LEGACY_CONTRACT_DIFFERENT'),'honest legacy diagnostic')
    runtime=observations['runtime']
    R.fields(runtime,pins['runtime_requirements'],'arithmetic runtime requirements')
    need(same(runtime['native_files'],before['native_files']) and same(runtime['environment'],pins['capture_environment']),
        'arithmetic runtime native/environment binding')


def review_checked(R,pins,go,run):
    review_spec=go['content']['source_review']
    R.exact_keys(review_spec,('path','bytes','sha256'),'source review identity')
    review=R.parse(R.checked(ROOT,review_spec['path'],review_spec))
    # Load the same externally reviewed issuer afresh for its fixed run ID;
    # never rewrite RUN_ID or weaken the original certificate validator.
    spec=importlib.util.spec_from_file_location('_pair_issuer_'+run,HERE/'issuer.py')
    issuer=importlib.util.module_from_spec(spec);spec.loader.exec_module(issuer)
    issuer.validate_expansion(review,pins)


def validate_run(run):
    """Rehash the exact seal, resources, payloads, source/raw/native/platform now."""
    phase('VALIDATE_'+run.upper())
    with configured(run) as launch:
        R,L=runtime();pins=R.load_pins();before=L.snapshot(R,pins)
        out=run_out(run);seal=read_json(out/'SEAL.json')
        V.exact(seal,('schema','status','mode','run_id','manifest','files','resources','source_manifest',
            'numerical_acceptance_claimed','dut_executed','retries'))
        R.fields(seal,dict(schema=1,status=SEALED,mode='bootstrap',run_id=run,manifest='BOOTSTRAP_REFERENCE.json',
            source_manifest=before['source_manifest'],numerical_acceptance_claimed=False,dut_executed=False,retries=0),'completed bootstrap seal')
        names={name+'.f32le' for name in R.NAMES}|{'mask.bf16le','BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json',
            'WRAPPER_BEFORE.json','WRAPPER_AFTER.json','GO.json','STAGES.jsonl','OBSERVATIONS.json',
            'BOOTSTRAP_REFERENCE.json','stdout.log','stderr.log'}
        V.exact(seal['files'],names)
        actual=inventory(out,names|{'SEAL.json'})
        need(same({name:actual[name] for name in names},seal['files']),'guard-sealed file content identities')
        for label in ('BOUNDARY_BEFORE','BOUNDARY_AFTER','WRAPPER_BEFORE','WRAPPER_AFTER'):
            need(same(read_json(out/(label+'.json')),before),'actual source/raw/native/platform drift')
        record=read_json(out/'BOOTSTRAP_REFERENCE.json');observations=read_json(out/'OBSERVATIONS.json')
        V.exact(record,set(observations)|{'resources','wrapper_boundary_unchanged','go_identity'})
        need(same({key:record[key] for key in observations},observations) and record['wrapper_boundary_unchanged'] is True,
            'manifest must contain exact worker evidence')
        need(same(record['resources'],seal['resources']),'resource evidence consistency')
        resources_checked(seal['resources'],actual)
        observations_checked(R,pins,observations,before)
        for name,spec in observations['outputs'].items():
            need(actual[name+'.f32le']=={key:spec[key] for key in ('bytes','sha256')},'observed payload readback')
        need(actual['mask.bf16le']==dict(bytes=32768,sha256=pins['mask_contract']['native_sha256']),'native mask sidecar')
        need(sum(actual[name+'.f32le']['bytes'] for name in R.NAMES)+32768==pins['budget']['payload_bytes_per_capture'],
            'exact 29 payload byte inventory')
        stages=(out/'STAGES.jsonl').read_bytes();need(len(stages)<=16384,'bounded stage journal')
        need([V.parse(line) for line in stages.splitlines()]==[dict(stage=s) for s in STAGES],'all original success stages')
        go=read_json(out/'GO.json');V.exact(go,('receipt','content'))
        go_path=private(WORK+'/'+run+'/GO.json')
        need(same(go['receipt'],dict(path=str(go_path.relative_to(ROOT)),**file_identity(go_path,16384))) and
            same(go['content'],read_json(go_path,16384)) and same(record['go_identity'],go['receipt']),'guard GO output binding')
        R.fields(go['content'],dict(schema=1,action='single-bootstrap',run_id=run,source_manifest=before['source_manifest'],
            maximum_invocations=1,no_retry=True,exclusive_numeric_slot=True),'single invocation GO')
        review_checked(R,pins,go,run)
        cert=private(certificate_path(run))
        need(file_identity(cert,262144)['sha256']==launch['certificate_sha256'],'admitted certificate changed')
        answer=read_json(guard_log(run),262144)
        V.exact(answer,('status','out','seal','resources'))
        need(same(answer,dict(status=SEALED,out=str(out.relative_to(ROOT)),seal=actual['SEAL.json'],resources=seal['resources'])),
            'original successful guard output identity')
        # Rehash current inputs after output validation too, not only before.
        need(same(L.snapshot(R,pins),before),'source/raw/native/platform changed while validating')
        disk_gate()
        return dict(run=run,out=out,outputs=observations['outputs'],common={k:v for k,v in before.items() if k not in COMMON_EXCLUDED},
            inventory=actual,guard=file_identity(guard_log(run),262144),
            filesystem={name:stat_id((out/name).stat()) for name in actual})


def direct_equal(left,right,size):
    need(type(size) is int and 0<=size<=RUN_CAP,'bounded direct comparison')
    left=canonical(left);right=canonical(right)
    initial=(stat_id(left.stat()),stat_id(right.stat()));count=0;equal=True
    with left.open('rb') as a,right.open('rb') as b:
        need((stat_id(os.fstat(a.fileno())),stat_id(os.fstat(b.fileno())))==initial,'comparison open identity')
        while True:
            x,y=a.read(CHUNK),b.read(CHUNK)
            need(len(x)==len(y),'payload length mismatch');count+=len(x);need(count<=size,'payload grew')
            if not x:break
            if x!=y:equal=False
        need((stat_id(os.fstat(a.fileno())),stat_id(os.fstat(b.fileno())))==initial,'comparison descriptor drift')
    need(count==size and (stat_id(left.stat()),stat_id(right.stat()))==initial,'comparison file drift')
    return equal


def aggregate(status,checked,rows):
    return dict(schema=1,status=status,contract_id=P.policy()['contract_id'],checked_outputs=checked,
        equal_outputs=sum(row['equal'] for row in rows),nodes=rows,reference_freeze_available=False,
        independently_approved=False,numerical_acceptance_claimed=False,old_pass_inherited=False,dut_executed=False)


def compare_pair(receipts):
    phase('PAIR_PRECHECK');need(len(receipts)==2,'two validated runs')
    current=[validate_run(run) for run in RUNS]
    phase('PAIR_PRECHECK');need(same(current,receipts),'validated receipt identity drift before comparison')
    left,right=current;need(same(left['common'],right['common']),'same-job source/raw/native/platform required')
    names=sorted(left['outputs']);need(len(names)==29 and set(names)==set(right['outputs']),'exact pair29')
    rows=[];phase('PAIR_COMPARE')
    for i,name in enumerate(names):
        a,b=left['outputs'][name],right['outputs'][name]
        need(same({k:v for k,v in a.items() if k not in DIGEST_FIELDS},{k:v for k,v in b.items() if k not in DIGEST_FIELDS}),
            'exact dtype/geometry/layout metadata across pair')
        equal=direct_equal(left['out']/a['file'],right['out']/b['file'],a['bytes'])
        need(equal==(a['sha256']==b['sha256']),'actual byte comparison/hash evidence conflict')
        equal=equal and all(a[key]==b[key] for key in DIGEST_FIELDS)
        rows.append(dict(node='OUTPUT_%02d'%i,equal=equal))
    phase('PAIR_POSTCHECK')
    checked=[validate_run(run) for run in RUNS]
    phase('PAIR_POSTCHECK');need(same(checked,receipts),'validated receipt identity drift after comparison')
    disk_gate()
    return aggregate('NEW_REFERENCE_PAIR_EQUAL_PENDING_REVIEW' if all(row['equal'] for row in rows)
        else 'NEW_REFERENCE_PAIR_DIFFERENT_PENDING_REVIEW',29,rows)


def capture_one(run):
    phase('CAPTURE_'+run.upper())
    with configured(run) as pins:
        disk_gate(reserve=RUN_CAP)
        need(file_identity(private(certificate_path(run)),262144)['sha256']==pins['certificate_sha256'],'admission required')
        call(P.PACKAGE+'/issuer.py',arguments('--execute',run,pins),LOGS+'/'+run+'/policy_expansion.log')
        call(P.PACKAGE+'/guard.py',['--mode','bootstrap','--run-id',run,'--go',WORK+'/'+run+'/GO.json'],
            LOGS+'/'+run+'/reference_guard.log')


def capture():
    need(os.getenv('GITHUB_SHA')==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source commit identity')
    # Both admissions must have succeeded before preparing anything. Different
    # run certificates must bind the exact same immutable new source closure.
    auth=[authorization(run)[0] for run in RUNS]
    need(auth[0]['source_closure_sha256']==auth[1]['source_closure_sha256'] and
        auth[0]['certificate_sha256']!=auth[1]['certificate_sha256'],'distinct single-run admissions, common source')
    for run,pins in zip(RUNS,auth):
        need(file_identity(private(certificate_path(run)),262144)['sha256']==pins['certificate_sha256'],'both admissions required')
        need(not private(WORK+'/'+run).exists(),'never retry or overwrite a run')
    phase('PREPARE_BINDINGS')
    # The old metadata-only preparer is intentionally used once. Its C globals
    # retain the original BINDINGS path; both new workers read that same file.
    call('candidates/qwen2_fullblock_ci_reference/recipe.py',['--prepare-bindings'],LOGS+'/fresh_bindings.log')
    receipts=[]
    for run in RUNS:
        capture_one(run)
        receipts.append(validate_run(run))  # Failure here prevents new02 entirely.
    result=compare_pair(receipts);phase('WRITE_AGGREGATE')
    path=private(LOGS+'/aggregate.json')
    with path.open('xb') as stream:stream.write(P.encoded(result))
    need(same(read_json(path),result),'aggregate readback')
    return result


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            phase('COLD');V.source_digest(ROOT)
            print(json.dumps(aggregate('NOT_EXECUTED_NEW_PAIR_PENDING_REVIEW',0,[]),sort_keys=True));return 0
        need(argv in (['admit'],['capture']) and os.getenv('GITHUB_RUN_ATTEMPT')=='1','explicit first-attempt pair action')
        directory=private(LOGS);directory.mkdir(parents=True,exist_ok=True)
        with (directory/(argv[0]+'.log')).open('x') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=admit() if argv[0]=='admit' else capture()
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        # Fixed phase helps diagnose failures without leaking exception messages,
        # per-output hashes/layout, filenames or private paths into public CI.
        print(json.dumps(dict(schema=1,status='NEW_REFERENCE_PAIR_INCOMPLETE',phase=PHASE,
            error='VALIDATION_OR_EXECUTION_FAILED',numerical_acceptance_claimed=False,dut_executed=False),sort_keys=True));return 1

if __name__=='__main__':raise SystemExit(main())
