"""One claimed official Debian Verilator original-frontend diagnostic on retained SV. Importing this stdlib module starts no work.

The execute flag is an explicit declaration, NOT proof of external root approval.
Only the admitted Perl/native planning frontend is permitted. No automatic make/CMake/child Verilator/compiler/model execution. Unknown fallback output is retained and rejected. Diagnostic completion is not plan, lint, codegen or numerical acceptance.
The original strict cleanup helper alone owns signaling and reaping authority.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time
import types

SCHEMA = 'qwen2-real-matrix-original-frontend-phase-diagnostic-supervisor-v1'
HELPER = '${STRICT_CLEANUP_SOURCE}'
HELPER_SHA = '30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
CAPS = dict(cpu_seconds=120, work_wall_seconds=150, total_wall_seconds=180,
            cleanup_reserve_seconds=30, cleanup_phase_seconds=10, postflight_reserve_seconds=20,
            affinity_count=1, address_space_bytes=4*1024**3,
            rss_sampled_bytes=2*1024**3, sample_seconds=0.1, log_hard_bytes=2*1024**2,
            output_tree_sampled_bytes=128*1024**2, single_file_hard_bytes=64*1024**2)
PHASE_SOURCE_PROOF_SHA = '131b39845dabd422f39c3ead389a971f809c7a7ac1e8e85ed3275c98bd3ab3eb'
DIAGNOSTIC_FLAGS = ['--timescale','1ns/1ps','--debugi-V3LinkCells','4','--debugi-V3LinkParse','4','--debugi-V3LinkDot','2','--debugi-V3Param','2','--debugi-V3Dead','2','--debugi-V3HierBlock','3','--debugi-V3Width','2']
SIGNALS = {signal.SIGALRM, signal.SIGTERM, signal.SIGINT}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def pin(path):
    path = Path(path)
    result = dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path), resolved_path=str(path.resolve()))
    if path.is_symlink():
        result['symlink_target'] = os.readlink(path)
    return result


def verify_pin(item):
    path = Path(item['path'])
    need(path.is_absolute() and path.is_file(), 'regular absolute pinned file: '+str(path))
    need(path.is_symlink() == ('symlink_target' in item), 'pinned symlink kind drift')
    if path.is_symlink():
        need(os.readlink(path) == item['symlink_target'], 'pinned symlink target drift')
    if 'resolved_path' in item:
        need(str(path.resolve()) == item['resolved_path'], 'pinned resolved path drift')
    need(path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], 'pin drift: '+str(path))


def walk_bounded(root):
    root=Path(root);need(root.is_dir() and not root.is_symlink(),'non-symlink root directory')
    def onerror(error):raise error
    count=0
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=onerror):
        for name in sorted(dirs+files):
            path=Path(directory)/name;info=path.lstat();count+=1
            need(count<=10000,'bounded source/output walk')
            need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),'reject symlink/special walk member')
            yield path

def exact_inventory(item):
    root=Path(item['root']);actual=[]
    for path in walk_bounded(root):
        if path.is_file() and path.name.endswith(item['suffix']):actual.append(str(path))
    need(sorted(actual)==sorted(item['files']),'exact immutable inventory drift: '+str(root))


def verify_inputs(manifest, extra_pins=()):
    verify_runtime_boundaries(manifest)
    count=0
    for rows in manifest['pins'].values():
        for item in rows:verify_pin(item);count+=1
    for item in extra_pins:verify_pin(item);count+=1
    for inventory in manifest['inventories']:exact_inventory(inventory)
    return dict(pin_checks=count,inventory_checks=len(manifest['inventories']),pass_all=True)


def verify_runtime_boundaries(manifest):
    for path in manifest['absent_paths']:
        need(not os.path.lexists(path),'runtime shadow/annotation slot must remain absent: '+path)
    for item in manifest['runtime_aliases']:
        path=Path(item['path'])
        need(path.is_symlink() and os.readlink(path)==item['target'] and str(path.resolve())==item['resolved_path'],'runtime path-component alias drift')
    for relative in manifest['fresh_cwd_absent_relative']:
        part=Path(relative)
        need(not part.is_absolute() and '..' not in part.parts,'safe fresh cwd absence slot')
        need(not os.path.lexists(Path(manifest['run_root'])/part),'fresh cwd Perl shadow slot')
    for item in (manifest['perl_executable'],manifest['frontend'],manifest['backend']):
        path=Path(item['path'])
        need(path.is_file() and os.access(path,os.X_OK),'admitted tool executable must remain executable')


def load_cleanup():
    data = Path(HELPER).read_bytes()
    need(hashlib.sha256(data).hexdigest() == HELPER_SHA, 'strict cleanup helper drift')
    module = types.ModuleType('admitted_strict_cleanup')
    module.__file__ = HELPER
    module._ADMITTED_SOURCE_SHA256 = HELPER_SHA
    exec(compile(data, HELPER, 'exec'), module.__dict__)
    return module


def validate_manifest(manifest):
    need(manifest['schema']==SCHEMA and manifest['stage']=='real-matrix-original-frontend-phase-diagnostic-only','fixed plan schema')
    need(manifest['caps']==CAPS and all(type(manifest['caps'][k]) is type(v) for k,v in CAPS.items()),'exact independently approved plan resource values/types')
    need(manifest['external_root_approval_required'] is True and manifest['automatic_retry'] is False and manifest['automatic_stage_chaining'] is False,'new root approval only/no retry/chain')
    root=Path(manifest['run_root']);oldroot=Path(manifest['retained_run_root']);sv=Path(manifest['retained_sv']['path'])
    need(root.is_absolute() and root==root.resolve() and root!=oldroot and root not in oldroot.parents and oldroot not in root.parents,'fresh disjoint canonical root')
    need(sv==oldroot/'rtl/OrderedQkRealMatrixCollection.sv' and manifest['retained_sv']['bytes']==48274540 and manifest['retained_sv']['sha256']=='c117e75ae97fb0a978e7cebe8e942a652bf1fbe927505d66092fa39b87380181','exact reviewed common SV')
    need(set(manifest['pins'])=={'tool','runtime','perl_source','input','provenance','source'},'closed roles')
    need(all(type(v) is list and v for v in manifest['pins'].values()),'nonempty role lists')
    need(manifest['frontend']['sha256']=='672a1ccf3468902f66387049f001b04f254bbcece7d5e816e3861715889bf252' and manifest['backend']['sha256']=='619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703','fixed official Debian5.032')
    need(manifest['package']['bytes']==7565144 and manifest['package']['sha256']=='238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2','fixed distribution package')
    for key in ('runtime_manifest','retained_structure_review','adapter_plan','source_admission_review','parent_python_runtime','hierarchy_proof','phase_observer','phase_source_proof','previous_failure_review'):
        p=manifest[key];verify_pin(p);need(any(p in rows for rows in manifest['pins'].values()),'loaded source/metadata automatically pinned '+key)
    need(manifest['retained_structure_review']['sha256']=='545c58fbcfb09ffbcc5ea4f3ae2bcfb9ed479b6fc4b073041ebcf4b5a3f0d276','exact actual SV independent review')
    review=json.loads(Path(manifest['retained_structure_review']['path']).read_text())
    need(review['status']=='PASS_ACTUAL_COMMON_SV_NAMESPACE_DECLARATIONS_AND_SELECTED_WIRING_ONLY' and review['root_exit']==0 and type(review['root_exit']) is int and review['cleanup_complete'] is True,'actual SV terminal prerequisite')
    need(review['sv']=={k:manifest['retained_sv'][k] for k in review['sv']},'actual retained SV identity')
    need(manifest['source_admission_review']['sha256']=='4d8a18f26dd5e2f6fc679fac82583620aa63440a03e5818f73a2fc33d42c0cd0','exact independent adapter/probe source review')
    admission=json.loads(Path(manifest['source_admission_review']['path']).read_text())
    need(admission['status']==manifest['source_admission_status'] and manifest['source_admission_status']=='PASS_CANONICAL22_ADAPTER_AND_FIVE_READONLY_PROBES_SOURCE_ONLY','adapter/probe/hierarchy independent source prerequisite')
    need(manifest['parent_python_runtime']['sha256']=='0ecbd114e9256eee254364f3e74603a64b3ae6daf7e2d0635c0d08a73d3dfa88','fixed known parent runtime superset')
    parent=json.loads(Path(manifest['parent_python_runtime']['path']).read_text())
    for p in parent['automatic_runtime_pins']:need(p in manifest['pins']['runtime'],'known parent runtime source/cache automatic')
    need(parent['runtime_pins']==manifest['parent_runtime_endpoints'] and parent['absent_paths']==manifest['parent_absent_paths'],'exact external parent endpoints')
    rt=json.loads(Path(manifest['runtime_manifest']['path']).read_text())
    need(rt['schema']=='lint-only-runtime-roles-and-endpoints-v1','inherited native frontend-only runtime closure')
    for rows in rt['pins'].values():
        for p in rows:need(any(p in row for row in manifest['pins'].values()),'original tool runtime included')
    for inv in rt['inventories']:need(inv in manifest['inventories'],'native/runtime inventories')
    need(manifest['runtime_aliases']==rt['symlink_chain'],'original runtime aliases')
    need(manifest['absent_paths']==sorted(set(rt['absent_paths']+parent['absent_paths']+[str(sv.parent/'circt.anno.json')])),'exact native+parent absence slots')
    need(manifest['fresh_cwd_absent_relative']==rt['fresh_cwd_absent_relative'],'fresh cwd slots')
    need(manifest['cleanup']['path']==HELPER and manifest['cleanup']['sha256']==HELPER_SHA and manifest['cleanup'] in manifest['pins']['source'],'automatic strict cleanup pin');verify_pin(manifest['cleanup'])
    front=Path(manifest['frontend']['path']);need(Path(manifest['backend']['path'])==front.with_name('verilator_bin') and str((front.parent/'../share/verilator').resolve())==manifest['verilator_root'],'normal frontend sibling/backend/root')
    inputs=manifest['staged_inputs'];need(inputs==manifest['pins']['input'] and len(inputs)==17,'17 staged inputs')
    names=[p['relative'] for p in inputs];need(len(set(names))==17 and names[0]=='inputs/common.sv' and names[-2:]==['inputs/config/hierarchy.vlt','inputs/config/raw_qk_m1.vlt'],'unique ordered common SV+14provider+2configs')
    need(sum(n.startswith('inputs/providers/') for n in names)==14 and set(n for n in names if n.startswith('inputs/config/'))=={'inputs/config/hierarchy.vlt','inputs/config/raw_qk_m1.vlt'},'closed config/provider roles')
    for n in names:need(not Path(n).is_absolute() and '..' not in Path(n).parts,'safe stage path')
    need({k:inputs[0][k] for k in ('path','bytes','sha256')}=={k:manifest['retained_sv'][k] for k in ('path','bytes','sha256')},'common input unchanged')
    adapter=json.loads(Path(manifest['adapter_plan']['path']).read_text());provider=adapter['source_files']
    need({(p['path'],p['bytes'],p['sha256']) for p in inputs if p['relative'].startswith('inputs/providers/')}=={(p['path'],p['bytes'],p['sha256']) for p in provider},'exact reviewed adapter/provider filelist')
    need(manifest['top']=='OrderedQkRealMatrixCore' and manifest['prefix']=='VOrderedQkRealMatrixCorePlan','selected shell not collection')
    source_argv=['${NEW_RUN_ROOT}/'+n for n in ['inputs/config/hierarchy.vlt','inputs/config/raw_qk_m1.vlt']+names[:-2]]
    expected=[manifest['perl_executable']['path'],manifest['frontend']['path'],'--no-unlimited-stack','--cc','--hierarchical','--make','cmake','-sv','--top-module',manifest['top'],'--prefix',manifest['prefix'],'--assert','--verilate-jobs','1','--threads','1','--no-timing']+DIAGNOSTIC_FLAGS+['--Mdir','${NEW_RUN_ROOT}/plan']+source_argv
    need(manifest['worker_argv']==expected,'exact CMake plan-only argv no gmake/build/exe/warning override')
    need(manifest['environment']==dict(PATH='${NEW_RUN_ROOT}/empty-path',LANG='C.UTF-8',LC_ALL='C.UTF-8',HOME='${NEW_RUN_ROOT}/home',TMPDIR='${NEW_RUN_ROOT}/tmp',VERILATOR_ROOT=manifest['verilator_root']),'minimal child environment')
    need(manifest['diagnostic_flags']==DIAGNOSTIC_FLAGS,'exact reviewed log-only source options and missing timescale default')
    need(manifest['previous_failure_review']['sha256']=='05085f645cf7868960af97179e7f5f7c1df149c697a69d7a303f2cd26f580745','original RSS failure retained')
    previous=json.loads(Path(manifest['previous_failure_review']['path']).read_text())
    need(previous['status']=='CONFIRMED_ACTUAL_SAMPLED_RSS_RESOURCE_FAIL_NO_PLAN','actual previous failure not acceptance')
    need(manifest['phase_source_proof']['sha256']==PHASE_SOURCE_PROOF_SHA,'exact independent source/binary logging basis')
    need(manifest['observation_limits']==dict(max_events=128,max_samples=4000,max_line_bytes=65536,max_log_bytes=2097152,max_json_bytes=1048576,sample_period_seconds=0.1),'exact bounded observation policy')
    need(manifest['scope']['hierarchy_plan_acceptance'] is False and manifest['scope']['numeric_acceptance'] is False,'diagnostic scope only')
    need(manifest['scope']['physical_endpoint_occurrences']==8 and manifest['scope']['full512_resources_each'] is True and manifest['scope']['collection_is_simulation_top'] is False,'no physical pruning')
    return manifest


def tree_sample(root):
    return sum(p.lstat().st_size for p in walk_bounded(root) if p.is_file())





def stage_inputs(root,manifest,*,create=False):
    root=Path(root);out=[]
    for p in manifest['staged_inputs']:
        target=root/p['relative'];need(root in target.parents,'stage path')
        if create:
            target.parent.mkdir(exist_ok=True,parents=True)
            need(all(not q.is_symlink() and q.is_dir() for q in [root,target.parent,target.parent.parent]),'stage parent kind')
            h=hashlib.sha256();count=0
            with Path(p['path']).open('rb') as src,target.open('xb') as dst:
                while True:
                    b=src.read(min(1048576,p['bytes']+1-count))
                    if not b:break
                    count+=len(b);need(count<=p['bytes'],'input growth');h.update(b);dst.write(b)
            need(count==p['bytes'] and h.hexdigest()==p['sha256'],'input copy exact');target.chmod(0o444)
        need(target.is_file() and not target.is_symlink() and (target.stat().st_mode&0o777)==0o444,'immutable staged regular')
        row=pin(target);need(row['bytes']==p['bytes'] and row['sha256']==p['sha256'],'staged bytes drift');out.append(row)
    actual={x.relative_to(root).as_posix() for x in walk_bounded(root/'inputs') if x.is_file()}
    need(actual=={p['relative'] for p in manifest['staged_inputs']},'exact staged file set')
    return out


def render_contract(value,root):
    if type(value) is str:return value.replace('${NEW_RUN_ROOT}',str(root))
    if type(value) is list:return [render_contract(v,root) for v in value]
    if type(value) is dict:return {k:render_contract(v,root) for k,v in value.items()}
    return value

def structure_check(root,manifest):
    """Only bounded terminal diagnostic log/artifact metadata, never plan qualification."""
    root=Path(root);path=root/'worker.log';need(path.is_file() and not path.is_symlink(),'regular diagnostic log')
    with path.open('rb') as stream:raw=stream.read(manifest['caps']['log_hard_bytes']+1)
    need(len(raw)<=manifest['caps']['log_hard_bytes'],'bounded log');lines=raw.decode('utf-8',errors='replace').splitlines()
    need(len(lines)<=40000 and all(len(x.encode('utf-8'))<=65536 for x in lines),'log line bounds')
    need(not any(x.lstrip().startswith('%Error') for x in lines),'native error even if exit0')
    output_scope(root,manifest)
    artifacts=[pin(p) for p in walk_bounded(root/'plan') if p.is_file()]
    return dict(status='DIAGNOSTIC_TERMINAL_METADATA_ONLY_NOT_PLAN_ACCEPTANCE',log_pin=pin(path),warning_headers=[x[:2048] for x in lines if x.lstrip().startswith('%Warning')],plan_directory_files=artifacts,plan_content_verified=False,model_cpp_generated=None,model_built=False,model_simulated=False,full_lint=False,numerical_pass=False)



def output_scope(root,manifest):
    root=Path(root);fixed={'CLAIM.json','worker.log','RECEIPT.json','PHASE_OBSERVATION.json'}|{p['relative'] for p in manifest['staged_inputs']}
    dirs={'tmp','home','empty-path','plan','inputs','inputs/providers','inputs/config'}
    for path in walk_bounded(root):
        rel=path.relative_to(root).as_posix();info=path.lstat()
        if stat.S_ISREG(info.st_mode):need(rel in fixed or (path.parent==root/'plan' and path.suffix in ('.cmake','.f','.d','.dat')),'unexpected plan/fallback artifact '+rel)
        else:need(rel in dirs,'unexpected output directory '+rel)


def load_phase_observer(manifest):
    p=manifest['phase_observer'];verify_pin(p)
    with Path(p['path']).open('rb') as stream:data=stream.read(p['bytes']+1)
    need(len(data)==p['bytes'] and hashlib.sha256(data).hexdigest()==p['sha256'],'phase observer source exact')
    module=types.ModuleType('fixed_readonly_phase_observer');module.__file__=p['path']
    exec(compile(data,p['path'],'exec'),module.__dict__)
    return module.PhaseObserver()


def save_phase_observation(observer,root,caps):
    data=observer.snapshot()
    logpath=Path(root)/'worker.log'
    need(logpath.is_file() and not logpath.is_symlink(),'observation binds regular retained log')
    need(data['log_bytes']==logpath.stat().st_size and data['log_sha256']==digest(logpath),'observation raw log identity')
    encoded=(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(encoded)<=1048576,'parent observation JSON cap')
    need(len(encoded)<=caps['single_file_hard_bytes'] and tree_sample(root)+len(encoded)<=caps['output_tree_sampled_bytes'],'observation file/tree cap')
    path=Path(root)/'PHASE_OBSERVATION.json'
    with path.open('xb') as stream:stream.write(encoded);stream.flush();need(os.fstat(stream.fileno()).st_size==len(encoded),'observation written bytes')
    p=pin(path);need(p['sha256']==hashlib.sha256(encoded).hexdigest(),'observation final hash')
    return p


def sample_gap(report, previous, sampled_at, limit):
    gap = sampled_at-previous
    report['maximum_sample_interval_seconds'] = max(report['maximum_sample_interval_seconds'],gap)
    need(0 <= gap <= limit,'RSS/tree sample interval exceeded')
    return sampled_at


def save_receipt(report, root, caps):
    """Write once only if both parent-written file and final tree fit the limits.

    If evidence cannot fit, retain CLAIM/log/output and expose failure on CLI;
    do not silently violate a cap to manufacture a complete-looking receipt.
    """
    report['receipt_saved'] = True
    encoded = (json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    try:
        need(len(encoded)<=caps['single_file_hard_bytes'],'parent receipt file hard cap exceeded')
        need(tree_sample(root)+len(encoded)<=caps['output_tree_sampled_bytes'],
             'output tree including final receipt exceeds sampled cap')
    except (ValueError,OSError) as error:
        report['errors'].append(type(error).__name__+': '+str(error))
        report['status'] = 'FAIL_OFFICIAL_FRONTEND_DIAGNOSTIC_RETAINED'
        report['hierarchy_plan_pass'] = False
        report['diagnostic_completed'] = False
        report['receipt_saved'] = False
        report['receipt_not_written_reason'] = str(error)
        return
    path = Path(root)/'RECEIPT.json'
    with path.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        need(os.fstat(stream.fileno()).st_size==len(encoded),'receipt final file size')
    need(digest(path)==hashlib.sha256(encoded).hexdigest(),'receipt final content hash')
    need(tree_sample(root)<=caps['output_tree_sampled_bytes'],'receipt final tree cap')


def group_sample(strict, owner):
    """Sample anchored original process group; not cgroup/escaped-tree confinement."""
    process = owner['process']
    cpu = rss = 0
    members = []
    names = os.listdir('/proc')
    need(len(names) <= 100000, 'bounded proc enumeration')
    for name in names:
        if not name.isascii() or not name.isdecimal():
            continue
        try:
            raw = (Path('/proc')/name/'stat').read_bytes()
        except FileNotFoundError:
            continue
        row = strict.parse_stat(raw)
        if row['group'] != process.pid:
            continue
        need(row['session'] == process.pid and row['start'] >= owner['identity']['start'], 'ambiguous group member')
        fields = raw[raw.rindex(b')')+1:].split()
        cpu += sum(int(fields[i]) for i in (11,12,13,14))/os.sysconf('SC_CLK_TCK')
        rss += max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE')
        members.append(row)
    need(any(r['pid'] == process.pid and r['start'] == owner['identity']['start'] for r in members), 'retained leader identity missing')
    return dict(cpu_seconds=cpu, rss_bytes=rss, members=members)


def _child_limits(caps, cpu):
    os.sched_setaffinity(0, {cpu})
    resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(caps['cpu_seconds']),)*2)
    resource.setrlimit(resource.RLIMIT_AS, (caps['address_space_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (caps['single_file_hard_bytes'],)*2)
    for sig in SIGNALS:
        signal.signal(sig, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, SIGNALS)


def render_worker_argv(manifest):
    return [value.replace('${NEW_RUN_ROOT}',manifest['run_root']).replace('${MANIFEST_PATH}',manifest.get('_admitted_manifest_path','')).replace('${MANIFEST_SHA256}',manifest.get('_admitted_manifest_sha256','')) for value in manifest['worker_argv']]


def _execute(manifest, *, extra_pins=()):
    """Internal engine; tests pass only explicitly synthetic Python argv/small caps.

    Public CLI always performs production validate_manifest before this function.
    """
    caps = manifest['caps']
    root = Path(manifest['run_root'])
    start = time.monotonic()
    parent_cpu_start = time.process_time()
    before_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    work_stop = start+caps['work_wall_seconds']
    absolute_stop = start+caps['total_wall_seconds']
    # Cleanup and postflight share the original reserve; never start a fresh timer budget.
    cleanup_stop = work_stop+caps['cleanup_phase_seconds']
    need(cleanup_stop<=absolute_stop-caps['postflight_reserve_seconds'], 'original cleanup/postflight allocation')
    strict = load_cleanup()
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'no inherited work alarm')
    # Atomic directory claim is never removed, even on preflight/launch failure.
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    with (root/'CLAIM.json').open('x') as stream:
        json.dump(dict(schema=SCHEMA, parent_pid=os.getpid(), started_monotonic=start,
                       stage='real-matrix-original-frontend-phase-diagnostic-only', argv=render_worker_argv(manifest), argv_template=manifest['worker_argv'], consumed=True), stream)
    report = dict(schema=SCHEMA, status='FAIL_OFFICIAL_FRONTEND_DIAGNOSTIC_RETAINED', worker_started=False,
                  numerical_pass=False, hardware_behavior_pass=False, rtl=False, rtl_simulation=False,
                  jvm_executed=False, chisel_elaboration_attempted=False, hierarchy_plan_pass=False, diagnostic_completed=False,
                  utilization='UNKNOWN_NOT_MEASURED', caps=caps, errors=[],
                  cleanup_complete=False, original_failure_retained=True,
                  process_scope='ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY',
                  preflight=None, postflight=None, offline_only=False, sv_generation_attempted=False, verilator_invocation_attempted=False, model_cpp_generated=None, model_built=False, model_simulated=False, sampled_peak_rss_bytes=0,
                  sampled_peak_output_bytes=0, sampled_peak_cpu_seconds=0, log_bytes=0,
                  maximum_sample_interval_seconds=0, exit_code=None, manifest_inputs=list(extra_pins))
    report['absolute_deadlines'] = dict(work=work_stop,cleanup=cleanup_stop,total=absolute_stop)
    owner = None
    log = None
    observer = None
    previous = {sig:signal.getsignal(sig) for sig in SIGNALS}
    previous_affinity = os.sched_getaffinity(0)
    prior_mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
    def interrupted(sig, frame):
        raise InterruptedError('supervisor signal/deadline '+str(sig))
    def fail(error):
        report['errors'].append(type(error).__name__+': '+str(error))
    try:
        for sig in SIGNALS:
            signal.signal(sig, interrupted)
        signal.setitimer(signal.ITIMER_REAL, max(.001,work_stop-time.monotonic()))
        signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask-SIGNALS)
        cpu = min(previous_affinity)
        os.sched_setaffinity(0,{cpu})
        report['preflight'] = verify_inputs(manifest, extra_pins)
        observer = load_phase_observer(manifest)
        for name in ('tmp','home','empty-path','plan','inputs'):
            (root/name).mkdir()
        report['staged_inputs_before'] = stage_inputs(root,manifest,create=True)
        argv = render_worker_argv(manifest)
        env = {k:v.replace('${NEW_RUN_ROOT}',str(root)) for k,v in manifest['environment'].items()}
        need(os.sched_getaffinity(0)=={cpu}, 'supervisor one-CPU affinity')
        report.update(executed_argv=argv, executed_environment=env, affinity_cpu=cpu)
        log = (root/'worker.log').open('xb')
        signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        verify_runtime_boundaries(manifest)
        process = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
            preexec_fn=lambda:_child_limits(caps,cpu))
        owner = dict(process=process,identity=None)
        report['worker_started'] = True
        report['verilator_invocation_attempted'] = True
        api = strict._Linux()
        strict._verify_leader(owner,api,None,api.boot())
        report['owner_identity'] = dict(owner['identity'])
        os.set_blocking(process.stdout.fileno(),False)
        signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask-SIGNALS)
        def collect():
            while True:
                need(time.monotonic()<work_stop, 'work deadline while draining log')
                try:
                    chunk = os.read(process.stdout.fileno(),65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                remaining = caps['log_hard_bytes']-report['log_bytes']
                kept = chunk[:remaining]
                log.write(kept)
                report['log_bytes'] += len(kept)
                observer.feed(kept,time.monotonic()-start)
                if len(chunk)>remaining:
                    log.flush()
                    raise ValueError('hard log cap exceeded')
            log.flush()
        last_sample = time.monotonic()
        while True:
            collect()
            sample = group_sample(strict,owner)
            cpu_seconds = sample['cpu_seconds']+time.process_time()-parent_cpu_start
            size = tree_sample(root)
            sampled_at = time.monotonic()
            last_sample = sample_gap(report,last_sample,sampled_at,caps['sample_seconds'])
            report['sampled_peak_rss_bytes'] = max(report['sampled_peak_rss_bytes'],sample['rss_bytes'])
            report['sampled_peak_cpu_seconds'] = max(report['sampled_peak_cpu_seconds'],cpu_seconds)
            report['sampled_peak_output_bytes'] = max(report['sampled_peak_output_bytes'],size)
            observer.sample(sampled_at-start,sample['rss_bytes'],cpu_seconds,size)
            need(sample['rss_bytes'] <= caps['rss_sampled_bytes'],'sampled RSS cap exceeded')
            need(cpu_seconds <= caps['cpu_seconds'],'sampled aggregate CPU cap exceeded')
            need(size <= caps['output_tree_sampled_bytes'],'sampled output tree cap exceeded')
            need(time.monotonic()<work_stop,'frontend diagnostic work deadline')
            result = os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if result is not None:
                collect()
                report['exit_code'] = result.si_status if result.si_code==os.CLD_EXITED else -result.si_status
                break
            time.sleep(min(.02,caps['sample_seconds']))
    except BaseException as error:
        fail(error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS)
        signal.setitimer(signal.ITIMER_REAL,0)
        for sig in SIGNALS:
            if sig in signal.sigpending():
                signal.sigtimedwait({sig},0)
        try:
            if owner is not None:
                try:
                    proof = strict.cleanup_owned(owner,cleanup_stop)
                    strict.validate_cleanup_proof(proof,owner=owner,stop=cleanup_stop)
                    report.update(cleanup_complete=True,cleanup_proof=proof)
                except BaseException as error:
                    fail(error)
                report['cleanup_observation'] = owner.get('strict_cleanup_observation')
            else:
                report['cleanup_not_required_no_process_started'] = True
            if log is not None:
                log.flush()
            if owner is not None and owner['process'].stdout is not None:
                owner['process'].stdout.close()
            need(time.monotonic()<absolute_stop,'original total deadline before postflight')
            signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
            signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask-SIGNALS)
            try:
                report['postflight'] = verify_inputs(manifest,extra_pins)
            except BaseException as error:
                fail(error)
            try:
                if observer is not None:
                    report['phase_observation_pin'] = save_phase_observation(observer,root,caps)
                    report['received_phase_marker_count'] = observer.snapshot()['event_count']
                size = tree_sample(root)
                report['sampled_peak_output_bytes'] = max(report['sampled_peak_output_bytes'],size)
                need(size <= caps['output_tree_sampled_bytes'],'final output tree cap exceeded')
                output_scope(root,manifest)
                report['staged_inputs_after'] = stage_inputs(root,manifest)
                if report['worker_started'] and report['exit_code'] == 0 and not report['cleanup_complete']:
                    report['structure_check_skipped_due_to_cleanup'] = True
                if (report['worker_started'] and report['exit_code'] == 0 and report['cleanup_complete']
                        and report['postflight'] is not None and not report['errors']):
                    need(report.get('received_phase_marker_count',0)>0,'no recognized source phase marker observed')
                    report['structure_check'] = structure_check(root,manifest)
            except BaseException as error:
                fail(error)
            if log is not None:
                need(os.fstat(log.fileno()).st_size == report['log_bytes'] <= caps['log_hard_bytes'],'final log cap/size')
            if report['exit_code'] != 0:
                fail(RuntimeError('diagnostic frontend did not exit zero'))
            after_children = resource.getrusage(resource.RUSAGE_CHILDREN)
            report['final_aggregate_cpu_seconds'] = (time.process_time()-parent_cpu_start +
                after_children.ru_utime+after_children.ru_stime-before_children.ru_utime-before_children.ru_stime)
            report['final_parent_and_waited_child_cpu_seconds'] = report['final_aggregate_cpu_seconds']
            report['sampled_group_plus_parent_cpu_peak_seconds'] = report['sampled_peak_cpu_seconds']
            report['complete_process_tree_cpu_seconds'] = None
            need(report['final_aggregate_cpu_seconds'] <= caps['cpu_seconds'],'final aggregate CPU cap exceeded')
            if not report['errors'] and report['cleanup_complete'] and report['postflight'] is not None:
                report['status'] = 'COMPLETE_OFFICIAL_FRONTEND_DIAGNOSTIC_ONLY'
                report['diagnostic_completed'] = True
                report['hierarchy_plan_pass'] = False
                report['model_cpp_generated'] = None
            report['elapsed_seconds'] = time.monotonic()-start
            need(time.monotonic()<absolute_stop,'original total deadline before receipt')
        except BaseException as error:
            fail(error)
            report['status'] = 'FAIL_OFFICIAL_FRONTEND_DIAGNOSTIC_RETAINED'
            report['hierarchy_plan_pass'] = False
            report['diagnostic_completed'] = False
        finally:
            # Receipt creation belongs to the same original total deadline.
            # An expired deadline/forced kill may leave only CLAIM/log evidence.
            try:
                need(time.monotonic()<absolute_stop,'total deadline before final receipt write')
                signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
                signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask-SIGNALS)
                save_receipt(report,root,caps)
                need(time.monotonic()<absolute_stop,'total deadline after final receipt write')
            finally:
                signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS)
                signal.setitimer(signal.ITIMER_REAL,0)
                for sig in SIGNALS:
                    if sig in signal.sigpending():
                        signal.sigtimedwait({sig},0)
                if log is not None:
                    log.close()
                os.sched_setaffinity(0,previous_affinity)
                for sig,handler in previous.items():
                    signal.signal(sig,handler)
                signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--execute-approved-once',action='store_true',required=True)
    args = parser.parse_args(argv)
    raw = args.manifest.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==args.manifest_sha256,'explicit manifest identity')
    data = json.loads(raw)
    validate_manifest(data)
    admitted_manifest_pin = dict(path=str(args.manifest.absolute()),bytes=len(raw),sha256=args.manifest_sha256,
                                 resolved_path=str(args.manifest.resolve()))
    data['_admitted_manifest_path']=str(args.manifest.absolute())
    data['_admitted_manifest_sha256']=args.manifest_sha256
    result = _execute(data,extra_pins=(admitted_manifest_pin,pin(Path(__file__).resolve())))
    print(json.dumps({k:result[k] for k in ('status','worker_started','cleanup_complete','exit_code','errors')}))
    return 0 if result['status']=='COMPLETE_OFFICIAL_FRONTEND_DIAGNOSTIC_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
