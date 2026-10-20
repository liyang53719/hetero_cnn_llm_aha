"""Single fixed owner diagnostic: accepted compiled model, fresh driver compile/link/run."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import time
import types

MIB = 1024**2
CONFIG_PIN = (3026, '851da9550b41300033be542a2ea782b288520927eb2d5d00897ac40f4253af85')
DRIVER_PIN = (1020, '50ceabdd66b261e14084c2efe0609601b63d2724293ccd7a6f47531d6baebde0')
SUPERVISION_PIN = (4391, 'ffce52ca02bb04fd24cf792b1e9a2c495d3daaa37992da0deeabeab7db9e29a6')
REUSE_GATE_PIN = (8936, 'df631aab1d0dc587c8e4b4293990ae2da71f391260981d56481495b56bef0a93')
REUSE_BINDING_PIN = (680, '12d9248eb232820913564dd5f2a806e3362cf9f90192a0c8733521ba412c4d36')
CACHE_GATE_PIN = (5313, 'bc4dc052931317d4e3c0f99bd6beb42d85073a78c2d3efcecd19e8f539756871')
HEADER_GATE_PIN = (899, 'e03ae18149849b305ba69434b78dbba9212b7f5f163d7e5bcc5c44b872b14109')
RELINK = 'candidates/host93_first_n0_sources/pc01_relink/run_relink.py'
RELINK_PIN = (19837, 'd80f19af41760b96f8a8a60d2a45faab21b2addea39bf5e805fe2a2a338e798d')
EXECUTOR = 'candidates/host93_ci_recovery/execution/host_execution.py'
EXECUTOR_PIN = (52525, 'b3470853d6b2a74b0ce75028cde553344cf3a76a12eddcb3fb8f2e169b229a1a')
CENSUS = 'candidates/host93_ci_recovery/execution/generation_diagnostics.py'
CENSUS_PIN = (51843, 'fb1b7bf9a747d02827233a820975231c151788f6aff2b54c8f7a7e589e5c0bf7')
SANITIZER = 'candidates/host93_ci_recovery/safe_build_diagnostics.py'
SANITIZER_PIN = (11942, '97ab72651c9acadf1e4d242225bdfc21dea3807aa911e448ce7330b762fa4a60')
BACKEND_PIN = {'bytes': 19076520, 'sha256': '75dd308bde0b9cb1e64b36a03ba8be38c64c2b59087dd52300fa8b43a107aeb2', 'mode': '0o700'}
INPUT_PINS = {'n0': {'bytes': 786432, 'sha256': '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'},
              'wq': {'bytes': 4718592, 'sha256': 'ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72'}}


FIXED_FAILURE_CODES = ('ARGV_OR_ENV_DRIFT', 'BINDING_OR_PROFILE_DRIFT', 'CALLER_OR_CONFIG_DRIFT', 'CPU_AFFINITY', 'CUMULATIVE_RSS_6G', 'DEPENDENCY_DRIFT', 'DRIVER_BYTES_DRIFT', 'ENTRY_T0_REQUIRED', 'EXACT_DRIVER_FILES', 'EXACT_OBSERVATION_COUNT', 'EXACT_PROJECTION_ANCHOR', 'EXACT_PROJECTION_INVERSE', 'EXACT_PROJECTION_INVERSE_COUNT', 'EXACT_THREE_COMMANDS', 'EXISTING_ACTUAL_REVIEW', 'EXISTING_BACKEND_PHASE', 'EXISTING_BACKEND_SCOPE', 'EXISTING_TINY_SCOPE', 'EXPLICIT_OWNER_MICRO_AND_ISOLATION', 'FIXED_BUILD_MAPPING', 'FIXED_CONFIG', 'FIXED_CONFIG_ORDER', 'FIXED_DATA_CHANGED', 'FIXED_DATA_PIN_REQUIRED', 'FIXED_GENERATE_MAPPING', 'FIXED_GENERATION_RECORD_PIN', 'FIXED_INTERPRETER', 'FIXED_MANIFEST_DRIFT', 'FIXED_OLD_ROOT', 'FIXED_OWNER_ABI', 'FIXED_SCALAR_OBSERVATION', 'FRESH_DISJOINT_WORK', 'FRESH_WORK_REQUIRED', 'GENERATED_CLOSURE_EMPTY', 'GENERATED_SOURCE_DRIFT', 'INCOMPLETE_PHASE_WINDOW', 'INCOMPLETE_POSTFLIGHT_WINDOW', 'INCOMPLETE_REPORT_WINDOW', 'INCOMPLETE_WORK_WINDOW', 'INHERITED_HARD_LIMIT', 'NATURAL_EXIT_OR_CLEANUP', 'OBSERVATION_DECLARATION_MISMATCH', 'ONE_CLUSTER_WITNESS', 'ORIGINAL_ARGV_ANCHOR', 'ORIGINAL_COMPILER_IDENTITY', 'ORIGINAL_GENERATION_ARGV', 'ORIGINAL_GENERATION_RECORD_DRIFT', 'OWNER_MICRO_SHARED_DEADLINE', 'PHASE_LOG_CAP', 'PRIOR_RECEIPT_DRIFT', 'PRODUCED_ELF_DRIFT', 'RUN_REQUIRES_QUALIFIED_ELF', 'SOURCE_CANONICAL', 'SOURCE_CLOSURE_DRIFT', 'SOURCE_HASH_OR_DRIFT', 'SOURCE_PIN_REQUIRED', 'SOURCE_SIZE', 'TIMER_OWNERSHIP', 'UNIQUE_ROOT_DECLARATION')

FIXED_FAILURE_CODES += ('CACHE_ACTUAL_REVIEW_SCOPE', 'CACHE_BINDING_KEYS', 'CACHE_CENSUS_DRIFT', 'CACHE_COPY_READBACK', 'CACHE_DIRECTORY', 'CACHE_EXACT_TOP_BUILD', 'CACHE_EXACT_TOTALS', 'CACHE_EXACT_TREE_SHAPE', 'CACHE_GENERATION_SCOPE', 'CACHE_ORIGINAL_TREE_DRIFT', 'CACHE_RECEIPT_DRIFT', 'CACHE_REGULAR_MEMBER', 'CACHE_ROOT_BINDING', 'CACHE_SAFE_UNIQUE_MEMBER', 'CACHE_SOURCE_ONLY_MEMBERS', 'EXACT_TWO_COMMANDS', 'OWNER_FIXED_HEADER_IDENTITY')

FIXED_FAILURE_CODES += ('REUSE_EXACT_TREE_SHAPE', 'REUSE_SAFE_UNIQUE_MEMBER', 'REUSE_DIRECTORY', 'REUSE_REGULAR_MEMBER', 'REUSE_EXACT_TOTALS', 'REUSE_ORIGINAL_TREE_DRIFT', 'REUSE_BINDING_KEYS', 'REUSE_ROOT_BINDING', 'REUSE_ACTUAL_REVIEW_SCOPE', 'REUSE_PRIOR_SCOPE', 'REUSE_BUILD_RECORD', 'REUSE_REGULAR_ARCHIVE', 'REUSE_FIXED_COPY_COUNT', 'REUSE_COPY_READBACK', 'REUSE_DEPENDENCY_RULE', 'REUSE_DEPENDENCY_EXACT_CLOSURE', 'REUSE_ORIGINAL_BYTES_DRIFT', 'REUSE_BINDING_DRIFT', 'REUSE_TOOLCHAIN_ROOT', 'REUSE_COMPILER_SEARCH', 'FRESH_RELOCATABLE_OBJECT', 'FRESH_OBJECT_DRIFT', 'FRESH_DEPENDENCY_DRIFT')

def failure_fields(error):
    boundary = getattr(error, 'safe_contract_boundary', None)
    code = getattr(error, 'safe_contract_code', None)
    if boundary == 'CLUSTER_GENERATION_WITNESS' and code in ('CLUSTER_CHILD_ARGS', 'CLUSTER_TOP_LINK', 'CLUSTER_LIBRARY_GRAPH', 'CLUSTER_INITIALIZER', 'CLUSTER_ABI', 'CLUSTER_ARTIFACTS', 'CLUSTER_CENSUS'):
        return {'failure_boundary': boundary, 'failure_code': code}
    if type(error) in (ValueError, TimeoutError) and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in FIXED_FAILURE_CODES:
        return {'failure_boundary': 'OWNER_LOCAL_MICRO_FIXED_CONTRACT', 'failure_code': error.args[0]}
    return {'failure_boundary': None, 'failure_code': None}


def need(ok, code):
    if not ok:
        raise ValueError(code)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, wanted):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and p.resolve(strict=True) == p and
         not any(q.is_symlink() for q in (p, *p.parents)), 'SOURCE_CANONICAL')
    need(type(wanted) is tuple and len(wanted) == 2 and type(wanted[0]) is int and
         0 <= wanted[0] <= MIB, 'SOURCE_PIN_REQUIRED')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size == wanted[0], 'SOURCE_SIZE')
        raw = bytearray()
        while len(raw) <= wanted[0]:
            b = os.read(fd, min(65536, wanted[0] + 1 - len(raw)))
            if not b:
                break
            raw.extend(b)
        raw = bytes(raw)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need((len(raw), hashlib.sha256(raw).hexdigest()) == wanted and
             stamp(before) == stamp(os.fstat(fd)) == stamp(p.stat(follow_symlinks=False)), 'SOURCE_HASH_OR_DRIFT')
        return raw
    finally:
        os.close(fd)


def module(path, wanted, name):
    raw = read(path, wanted)
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), m.__dict__)
    return m


def projected(raw, replacements):
    result = raw
    for old, new, count in replacements:
        need(result.count(old) == count and new not in result, 'EXACT_PROJECTION_ANCHOR')
        result = result.replace(old, new)
    inverse = result
    for old, new, count in reversed(replacements):
        need(inverse.count(new) == count, 'EXACT_PROJECTION_INVERSE_COUNT')
        inverse = inverse.replace(new, old)
    need(inverse == raw, 'EXACT_PROJECTION_INVERSE')
    return result, {'original': pin(raw), 'derived': pin(result), 'inverse_exact': True,
                    'substitutions': [{'old': a.decode(), 'new': b.decode(), 'count': n} for a,b,n in replacements]}


def owner_adapters(repo, executor):
    raw = read(repo / CENSUS, CENSUS_PIN)
    derived, census_proof = projected(raw, (
        (b'HostBlockTop__DOT__owner__DOT__matrix', b'QwenOwnerKernel__DOT__matrix', 1),
        (b'VHostBlockTop', b'VQwenOwnerKernel', 5),
        (b'VERILATED_VHOSTBLOCKTOP', b'VERILATED_VQWENOWNERKERNEL', 1)))
    census = types.ModuleType('fixed_owner_generation_census');census.__file__ = str(repo / CENSUS)
    exec(compile(derived, str(repo / CENSUS), 'exec', dont_inherit=True), census.__dict__)
    raw = read(repo / EXECUTOR, EXECUTOR_PIN)
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'cluster_generated_witness']
    need(len(nodes) == 1, 'ONE_CLUSTER_WITNESS')
    n = nodes[0]; body = b''.join(raw.splitlines(keepends=True)[n.lineno-1:n.end_lineno]) + b'\n'
    derived, witness_proof = projected(body, (
        (b'VHostBlockTop', b'VQwenOwnerKernel', 8),
        (b'len(ports) == 83', b'len(ports) == 196', 1),
        (b"'host_ports': 83", b"'owner_ports': 196", 1),
        (b'FINITE_CLUSTER_RESET_LAUNCH_WITNESS', b'FINITE_CLUSTER_OWNER_MICRO_SOURCE_WITNESS', 1)))
    ns = dict(executor.__dict__)
    exec(compile(derived, 'fixed_owner_cluster_witness', 'exec', dont_inherit=True), ns)
    return census, ns['cluster_generated_witness'], {'census': census_proof, 'witness': witness_proof}


def commands(executor, work, toolchain, closure, configuration, n0, wq):
    old = executor.commands(work, toolchain['backend'], closure, configuration)
    argv = list(old['host93_cpp_generate'])
    for flag, before, after in (
        ('--exe', str(work / 'fixtures/short_launch.cpp'), str(work / 'fixtures/owner_micro.cpp')),
        ('--top-module', 'HostBlockTop', 'QwenOwnerKernel'),
        ('--prefix', 'VHostBlockTop', 'VQwenOwnerKernel')):
        need(argv.count(flag) == 1 and argv[argv.index(flag)+1] == before, 'FIXED_GENERATE_MAPPING')
        argv[argv.index(flag)+1] = after
    anchor = str(configuration / 'precision_warnings.vlt')
    need(argv.count(anchor) == 1, 'FIXED_CONFIG_ORDER')
    argv.insert(argv.index(anchor)+1, str(work / 'fixtures/owner_readonly.vlt'))
    build = list(old['host93_cpp_compile'])
    need(build.count('VHostBlockTop.mk') == 1 and build[-1] == 'VHostBlockTop', 'FIXED_BUILD_MAPPING')
    build[build.index('VHostBlockTop.mk')] = 'VQwenOwnerKernel.mk'; build[-1] = 'VQwenOwnerKernel'
    return {'generate': argv, 'build': build, 'run': [str(work / 'obj/VQwenOwnerKernel'), str(n0), str(wq)]}


def observation_declarations(header, observations):
    need(type(observations) is list and len(observations) == 95, 'EXACT_OBSERVATION_COUNT')
    found = {}
    for kind, high, low, name in re.findall(r'\b(CData|SData|IData|QData)/\*(\d+):(\d+)\*/\s+(\w+)\s*;', header):
        need(name not in found, 'UNIQUE_ROOT_DECLARATION')
        found[name] = (kind, int(high)+1, int(low))
    rows = {}
    for x in observations:
        name, width = x['member'], x['width']
        need(name.startswith('QwenOwnerKernel__DOT__') and type(width) is int and 0 < width <= 64, 'FIXED_SCALAR_OBSERVATION')
        kind = 'CData' if width <= 8 else 'SData' if width <= 16 else 'IData' if width <= 32 else 'QData'
        need(name not in rows and found.get(name) == (kind, width, 0), 'OBSERVATION_DECLARATION_MISMATCH')
        rows[name] = {'type': kind, 'width': width}
    return rows


def accept_toolchain(value):
    need(value['status'] == 'PASS_FRESH_DERIVED_TOOLCHAIN_AND_TINY_ONLY' and
         value['source_commit'] == '4e194cc3ec8e27b18e17f80d7f99c15f984bbdae' and
         value['source_members'] == 473 and
         {k:value['backend'][k] for k in BACKEND_PIN} == BACKEND_PIN and
         value['patch']['only_changed_member'] == 'src/V3ProtectLib.cpp' and
         value['patch']['replacement_count'] == 1 and value['patch']['fresh_build_no_reused_objects'] is True and
         value['patch']['derived']['sha256'] == '380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb',
         'EXISTING_BACKEND_SCOPE')
    need(value['tiny']['status'] == 'PASS_NEW_DERIVED_FOUR_STAGE_TINY' and
         set(value['tiny']['phases']) == {'generate','compile','run','version'}, 'EXISTING_TINY_SCOPE')
    for phase in list(value['build'].values()) + list(value['tiny']['phases'].values()):
        need(type(phase['exit_code']) is int and phase['exit_code'] == 0 and phase['cleanup_confirmed'] is True,
             'EXISTING_BACKEND_PHASE')


def run(config_path, execute=False, *, started=None, source_pin=None):
    need(execute and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'EXPLICIT_OWNER_MICRO_AND_ISOLATION')
    need(type(started) is float and 0 <= time.monotonic()-started < 30, 'ENTRY_T0_REQUIRED')
    stop = started + 540
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'TIMER_OWNERSHIP')
    old_alarm = signal.getsignal(signal.SIGALRM); old_term = signal.getsignal(signal.SIGTERM); old_mask = os.umask(0o077)
    def expired(*unused):
        raise TimeoutError('OWNER_MICRO_SHARED_DEADLINE')
    signal.signal(signal.SIGALRM, expired); signal.signal(signal.SIGTERM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, stop-time.monotonic()))
    owner = {'handler': expired, 'deadline': stop}
    result = {'schema':'OWNER_DRIVER_RELINK_RUN_EXECUTION_V1', 'status':'INCOMPLETE', 'stages':[],
              'scope':'FRESH_OWNER_PORTS_DIAGNOSTIC_ONLY', 'full_job_completed':False,
              'full_block_pass':False, 'historical_host_failure_reproduced':None,
              'official_accuracy_pass':None, 'application_accuracy_pass':None,
              'typed_reference_rtl_pass':None, 'backend_rebuilt':False,
              'host_archive_reused':False, 'generation_executed':False, 'generation_cache_reused':True, 'owner_archive_reused':True, 'old_driver_object_reused':False, 'shared_seconds_cap':540, 'tail_reserved_seconds':60}
    failure, work, sup, fs, helper = None, None, None, None, None
    try:
        for kind, limit in ((resource.RLIMIT_AS,6*1024**3),(resource.RLIMIT_CPU,540),(resource.RLIMIT_FSIZE,512*MIB)):
            _, hard = resource.getrlimit(kind)
            need(hard == resource.RLIM_INFINITY or hard >= limit, 'INHERITED_HARD_LIMIT')
            resource.setrlimit(kind,(limit,limit))
        cpus = os.sched_getaffinity(0);need(bool(cpus),'CPU_AFFINITY');os.sched_setaffinity(0,{min(cpus)})
        own = read(Path(__file__).resolve(), source_pin)
        config_raw = read(config_path, CONFIG_PIN); cfg=json.loads(config_raw)
        need(set(cfg)=={'schema','repo','work','old_work','binding_source','binding','profile','dependencies',
                       'toolchain_receipt','prior_review','driver_source','driver_manifest','original_generation','n0','wq','cache','reuse_binding'} and
             cfg['schema']=='OWNER_DRIVER_RELINK_RUN_PRIVATE_BINDING_V1', 'FIXED_CONFIG')
        repo=Path(cfg['repo']);old=Path(cfg['old_work']);source=Path(cfg['driver_source'])
        relink=module(repo/RELINK, RELINK_PIN, 'owner_fixed_relink_helpers')
        helper=module(repo/'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py',
                      relink.HELPER_PIN,'owner_fixed_reference_helpers')
        g=module(repo/'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py',
                 helper.PINS['bootstrap.py'],'owner_fixed_bootstrap')
        bdir=Path(cfg['binding_source'])
        o=module(bdir/'binding_observer.py',helper.PINS['binding_observer.py'],'owner_fixed_mount_observer')
        l=module(bdir/'local_mount_profile.py',helper.PINS['local_mount_profile.py'],'owner_fixed_mount_profile')
        d=module(repo/'candidates/host93_first_n0_sources/pc01_relink/dependency_gate.py',relink.GATE_PIN,'owner_dependencies')
        supervisor=module(repo/'candidates/host93_ci_recovery/ci_support_v3.py',helper.PINS['ci_support_v3.py'],'owner_unchanged_supervisor')
        sup=module(Path(__file__).resolve().parent/'supervision.py',SUPERVISION_PIN,'owner_micro_sequence')
        cache=module(Path(__file__).resolve().parent/'cache_gate.py',CACHE_GATE_PIN,'owner_fixed_cache_gate')
        header=module(Path(__file__).resolve().parent/'header_gate.py',HEADER_GATE_PIN,'owner_fixed_header_gate')
        reuse=module(Path(__file__).resolve().parent/'reuse_gate.py',REUSE_GATE_PIN,'owner_fixed_compiled_reuse')
        fs,base,support_pins=supervisor.fixed_support(repo)
        executor=module(repo/EXECUTOR,EXECUTOR_PIN,'owner_fixed_host_helpers')
        epins,ebuffers,unused,lexical=executor.load(repo)
        census,witness,projection=owner_adapters(repo,executor)
        sanitizer=module(repo/SANITIZER,SANITIZER_PIN,'owner_fixed_sanitizer')
        braw=g.checked(Path(cfg['binding']['path']),cfg['binding']['identity']);binding=g.binding(braw,cfg['binding']['identity'],repo)
        praw=g.checked(Path(cfg['profile']['path']),cfg['profile']['identity']);profile=g.decode(praw)
        need(str(Path(sys.executable).resolve(strict=True))==binding['system_programs']['/usr/bin/python3']['path'],'FIXED_INTERPRETER')
        catalog_raw=read(Path(cfg['dependencies']),relink.CATALOG_PIN);catalog=json.loads(catalog_raw)
        for key in ('bytes','sha256','mode'):
            need(catalog['files'][catalog['programs']['g++']][key]==binding['system_programs']['/usr/bin/g++'][key],'ORIGINAL_COMPILER_IDENTITY')
        l.validate(g,o,binding,profile); dependency_before=d.verify(g,o,l,repo,catalog)
        tp=cfg['toolchain_receipt']; traw=g.checked(Path(tp['path']),tp['identity'],MIB);toolchain=g.decode(traw);accept_toolchain(toolchain)
        prior=cfg['prior_review']; prior_raw=g.checked(Path(prior['path']),prior['identity'],MIB)
        need(g.decode(prior_raw)['verdict']=='ACCEPT_ACTUAL_FIRST_N0_M128_LIMITED_TOLERANCE_PASS_WITH_EXACT_CAPTURE','EXISTING_ACTUAL_REVIEW')
        need(Path(tp['path'])==old/'toolchain/RESULT.json' and Path(toolchain['verilator_root'])==old/'toolchain/verilator','FIXED_OLD_ROOT')
        executor.verify_tools(fs,toolchain)
        manifest_raw=read(Path(cfg['driver_manifest']),DRIVER_PIN);manifest=json.loads(manifest_raw)
        need(manifest['schema']=='OWNER_MICRO_PRODUCTION_V1' and set(manifest['files'])==
             {'owner_micro.cpp','owner_inputs.inc','owner_observations.inc','owner_readonly.vlt','sha256.hpp','PORTS.json','OBSERVATIONS.json'},'EXACT_DRIVER_FILES')
        fixtures={n:g.checked(source/n,p,4*MIB,fixed_leaf=n) for n,p in manifest['files'].items()}
        ports_list=g.decode(fixtures['PORTS.json']);ports={r['name']:[r['direction'],r['width']] for r in ports_list}
        need(len(ports_list)==len(ports)==196 and sum(r['direction']=='input' for r in ports_list)==150 and
             sum(r['direction']=='output' for r in ports_list)==46,'FIXED_OWNER_ABI')
        observations=g.decode(fixtures['OBSERVATIONS.json'])
        # The SV is taken from the immutable original generation argv, never guessed from input paths.
        original_native=old/'phases/host93_cpp_generate/native.json'
        original_pin=cfg['original_generation']
        need(type(original_pin) is dict and set(original_pin)=={'bytes','sha256'},'FIXED_GENERATION_RECORD_PIN')
        generation_raw=g.checked(original_native,original_pin,MIB); original_argv=g.decode(generation_raw)['argv']
        sv={'path':original_argv[-1],'bytes':executor.SV_PIN[0],'sha256':executor.SV_PIN[1]}
        inputs=executor.closure(fs,old/'idma319',old/'retained13',old/'configuration',sv,ebuffers,fifo_valid_split=True)
        original_commands=executor.commands(old/'host_execution',toolchain['backend'],inputs,old/'configuration')
        expected_old=list(original_commands['host93_cpp_generate'])
        need(expected_old.count(str(old/'host_execution/fixtures/short_launch.cpp'))==1,'ORIGINAL_ARGV_ANCHOR')
        expected_old[expected_old.index(str(old/'host_execution/fixtures/short_launch.cpp'))]=str(old/'host_execution/fixtures/first_n0_main.cpp')
        need(expected_old==original_argv,'ORIGINAL_GENERATION_ARGV')
        source_map=executor.generation_source_map(inputs,old/'idma319',old/'retained13')
        for k in ('n0','wq'):
            need(type(INPUT_PINS[k]) is dict,'FIXED_DATA_PIN_REQUIRED')
            got=fs.identity(Path(cfg[k]),32*MIB);need({a:got[a] for a in ('bytes','sha256')}==INPUT_PINS[k],'FIXED_DATA_CHANGED')
        cache_root=g.clean(cfg['cache']['root'])
        expected_cache_argv=commands(executor,cache_root,toolchain,inputs,old/'configuration',Path(cfg['n0']),Path(cfg['wq']))['generate']
        cache_tree,cache_receipt=cache.accept(g,fs,cfg['cache'],sup,expected_cache_argv)
        reuse_raw=read(Path(cfg['reuse_binding']),REUSE_BINDING_PIN);reuse_cfg=json.loads(reuse_raw)
        need(Path(reuse_cfg['verilator_root'])==Path(toolchain['verilator_root']),'REUSE_TOOLCHAIN_ROOT')
        reuse_tree,reuse_receipt=reuse.accept(g,fs,reuse_cfg,sup)
        reuse_buffers=reuse.buffers(g,reuse_cfg)
        target=g.clean(cfg['work'])
        for p in (repo,old,bdir,source,cache_root,Path(reuse_cfg['root'])):
            p=g.clean(p);need(not target.is_relative_to(p) and not p.is_relative_to(target),'FRESH_DISJOINT_WORK')
        need(not os.path.lexists(target),'FRESH_WORK_REQUIRED');result['admission']=relink.resource_gate(target.parent)
        fs.fresh_directory(target);work=target
        for n in ('obj','fixtures','home','tmp','phases','compiler-search'):fs.fresh_directory(work/n)
        for n,raw in fixtures.items():relink.write_exact(work/'fixtures'/n,raw)
        def fixed_commands():
            return reuse.commands(catalog,work,Path(cfg['n0']),Path(cfg['wq']))
        argv=fixed_commands()
        for name in ('cc1plus','collect2','as','ld'):
            (work/'compiler-search'/name).symlink_to(catalog['programs'][name])
        env=relink.environment(catalog,work)
        generated=reuse.stage(g,fs,relink,work,reuse_buffers);binary=None;last_tree=None;generation_report=None
        result.update(projection=projection,source_count=307,include_count=8,define_count=4,
                      toolchain_receipt_identity=pin(traw),prior_review_identity=pin(prior_raw),
                      driver_manifest_identity=pin(manifest_raw),source_inputs=inputs,cpu_affinity_count=1)
        def preflight():
            need(time.monotonic()<stop-60,'INCOMPLETE_WORK_WINDOW')
            need(read(Path(__file__).resolve(),source_pin)==own and read(config_path,CONFIG_PIN)==config_raw,'CALLER_OR_CONFIG_DRIFT')
            read(Path(__file__).resolve().parent/'supervision.py',SUPERVISION_PIN)
            read(Path(__file__).resolve().parent/'cache_gate.py',CACHE_GATE_PIN)
            read(Path(__file__).resolve().parent/'header_gate.py',HEADER_GATE_PIN)
            read(Path(__file__).resolve().parent/'reuse_gate.py',REUSE_GATE_PIN)
            need(read(Path(cfg['reuse_binding']),REUSE_BINDING_PIN)==reuse_raw,'REUSE_BINDING_DRIFT')
            re_tree,re_receipt=reuse.accept(g,fs,reuse_cfg,sup)
            need(re_tree==reuse_tree and re_receipt==reuse_receipt and reuse.buffers(g,reuse_cfg)==reuse_buffers,'REUSE_ORIGINAL_BYTES_DRIFT')
            checked_cache,checked_receipt=cache.accept(g,fs,cfg['cache'],sup,expected_cache_argv)
            need(checked_cache==cache_tree and checked_receipt==cache_receipt,'CACHE_RECEIPT_DRIFT')
            for rel,wanted in ((RELINK,RELINK_PIN),(EXECUTOR,EXECUTOR_PIN),(CENSUS,CENSUS_PIN),(SANITIZER,SANITIZER_PIN)):
                read(repo/rel,wanted)
            need(read(Path(cfg['dependencies']),relink.CATALOG_PIN)==catalog_raw and
                 read(Path(cfg['driver_manifest']),DRIVER_PIN)==manifest_raw,'FIXED_MANIFEST_DRIFT')
            need(g.checked(Path(tp['path']),tp['identity'],MIB)==traw and g.checked(Path(prior['path']),prior['identity'],MIB)==prior_raw,'PRIOR_RECEIPT_DRIFT')
            need(g.checked(original_native,original_pin,MIB)==generation_raw,'ORIGINAL_GENERATION_RECORD_DRIFT')
            need(g.checked(Path(cfg['binding']['path']),cfg['binding']['identity'])==braw and
                 g.checked(Path(cfg['profile']['path']),cfg['profile']['identity'])==praw,'BINDING_OR_PROFILE_DRIFT')
            for path,wanted in ((repo/'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py',relink.HELPER_PIN),
                (repo/'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py',helper.PINS['bootstrap.py']),
                (bdir/'binding_observer.py',helper.PINS['binding_observer.py']),(bdir/'local_mount_profile.py',helper.PINS['local_mount_profile.py']),
                (repo/'candidates/host93_first_n0_sources/pc01_relink/dependency_gate.py',relink.GATE_PIN),
                (repo/'candidates/host93_ci_recovery/ci_support_v3.py',helper.PINS['ci_support_v3.py'])):
                read(path,wanted)
            for rel,wanted in support_pins.items():read(repo/rel,(wanted['bytes'],wanted['sha256']))
            l.validate(g,o,binding,profile);need(d.verify(g,o,l,repo,catalog)==dependency_before,'DEPENDENCY_DRIFT')
            executor.verify_tools(fs,toolchain);executor.stable_sources(repo,epins,ebuffers)
            need(executor.closure(fs,old/'idma319',old/'retained13',old/'configuration',sv,ebuffers,fifo_valid_split=True)==inputs,'SOURCE_CLOSURE_DRIFT')
            for n,raw in fixtures.items():
                wanted=manifest['files'][n];need(g.checked(source/n,wanted,4*MIB,fixed_leaf=n)==raw and
                    g.checked(work/'fixtures'/n,wanted,4*MIB,fixed_leaf=n)==raw,'DRIVER_BYTES_DRIFT')
            for k in ('n0','wq'):
                got=fs.identity(Path(cfg[k]),32*MIB);need({a:got[a] for a in ('bytes','sha256')}==INPUT_PINS[k],'FIXED_DATA_CHANGED')
            for n,wanted in generated.items():need(fs.identity(work/n,128*MIB)==wanted,'GENERATED_SOURCE_DRIFT')
            if binary is not None:need(d.check_binary(g,repo,catalog,work/'obj/VQwenOwnerKernel')==binary,'PRODUCED_ELF_DRIFT')
            need(fixed_commands()==argv and env==relink.environment(catalog,work),'ARGV_OR_ENV_DRIFT')
            search=work/'compiler-search'
            need(sorted(p.name for p in search.iterdir())==['as','cc1plus','collect2','ld'],'REUSE_COMPILER_SEARCH')
            for name in ('cc1plus','collect2','as','ld'):
                need((search/name).is_symlink() and str((search/name).resolve(strict=True))==catalog['programs'][name],'REUSE_COMPILER_SEARCH')
            if 'object' in result:
                g.checked(work/'obj/owner_micro.o',result['object'],64*MIB,fixed_leaf='owner_micro.o')
                g.checked(work/'obj/owner_micro.d',result['dependency_file'],MIB,fixed_leaf='owner_micro.d')
        def after_phase(name,raw,stage):
            nonlocal generated,binary,last_tree,generation_report
            need(type(raw) is bytes and len(raw)<=sup.phase_limits(name)['log_bytes'],'PHASE_LOG_CAP')
            tree=fs.tree_inventory(work/'obj',256*MIB,1024,2048,64*MIB)
            if name=='compile':
                obj_pin={k:v for k,v in fs.identity(work/'obj/owner_micro.o',64*MIB).items() if k in ('bytes','sha256')}
                obj_raw=g.checked(work/'obj/owner_micro.o',obj_pin,64*MIB,fixed_leaf='owner_micro.o')
                need(obj_raw[:4]==b'\x7fELF' and len(obj_raw)>=18 and int.from_bytes(obj_raw[16:18],'little')==1,'FRESH_RELOCATABLE_OBJECT')
                dep_pin={k:v for k,v in fs.identity(work/'obj/owner_micro.d',MIB).items() if k in ('bytes','sha256')}
                dep_raw=g.checked(work/'obj/owner_micro.d',dep_pin,MIB,fixed_leaf='owner_micro.d')
                stage['dependency_closure']=reuse.dependency_closure(g,dep_raw,work)
                result['object']=obj_pin;result['dependency_file']=dep_pin
            if name=='link':
                binary=d.check_binary(g,repo,catalog,work/'obj/VQwenOwnerKernel');result['binary']=binary
            if name=='run':
                need(binary is not None,'RUN_REQUIRES_QUALIFIED_ELF')
                # Full bounded JSONL remains opaque diagnostic data. Native zero alone does not prove target or job PASS.
                result['runtime_log_identity']=pin(raw)
                result['runtime_observation']='NATURAL_ZERO_DIAGNOSTIC_LOG_REQUIRES_INDEPENDENT_AUDIT'
            executor.save(work/(name.upper()+'_TREE.json'),tree);last_tree=tree
        # Revalidate the original natural-zero generation output; no new native phase is claimed.
        generation_report=census.collect(cache_root/'phases/generate/native.log',cache_root,source_map,sanitizer)
        census.validate_report(generation_report);executor.validate_cluster_census(generation_report)
        need(generation_report==cache_receipt['generation_census'],'CACHE_CENSUS_DRIFT')
        # Header view consists only of the twelve copied, identity-checked regular inputs.
        tree={'root':str(work),'entries':{n:{'kind':'regular',**fs.identity(work/n,32*MIB)} for n in generated}}
        result['observation_profile']=observation_declarations(header.header_text(g,tree),observations)
        result['cached_compiled_model_witness']=witness(fs,reuse_tree,lexical,ports,generation_report,True,sv['path'])
        result['generation_cache']={'scope':'EXISTING_GENERATION_REVALIDATED_READ_ONLY',
            'local_generation_executed':False,'original_outer_exit':1,'original_generation_natural_zero':True,
            'tree_identity':cache.TREE_PIN,'receipt_identity':cache.RECEIPT_PIN,'review_identity':cache.REVIEW_PIN,
            'local_generated_sources_recompiled':False,'old_absolute_fixture_inputs_pinned':True}
        result['compiled_model_reuse']={'scope':'EXISTING_OWNER_COMPILED_MODEL_REVALIDATED_READ_ONLY',
            'tree_identity':reuse.TREE_PIN,'receipt_identity':reuse.RECEIPT_PIN,'review_identity':reuse.REVIEW_PIN,
            'staged_members':len(generated),'staged_bytes':sum(x['bytes'] for x in generated.values()),
            'regular_archive':True,'old_driver_object_reused':False,'fresh_driver_dependency_closure_required':True}
        result['staged_reuse_inputs']=generated
        executor.save(work/'REUSE_ACCEPTANCE_INPUTS.json',tree)
        sup.sequence(supervisor,fs,base,work,argv,env,stop,owner,preflight,after_phase,result,
                     lambda:relink.resource_gate(work))
        preflight();need(time.monotonic()<stop-60,'INCOMPLETE_POSTFLIGHT_WINDOW')
        result.update(status='COMPLETE_THREE_SUPERVISED_PHASES_DIAGNOSTIC_ONLY',seconds=time.monotonic()-started)
    except BaseException as error:
        failure=error;result['failure_type']=type(error).__name__
        result.update(failure_fields(error))
    finally:
        if sup is not None and helper is not None:
            failure=sup.finish(fs,work,result,failure,stop,helper.write_result,
                               lambda delay:signal.setitimer(signal.ITIMER_REAL,delay))
        for action,args in ((signal.setitimer,(signal.ITIMER_REAL,0)),(signal.signal,(signal.SIGALRM,old_alarm)),
                            (signal.signal,(signal.SIGTERM,old_term)),(os.umask,(old_mask,))):
            try:action(*args)
            except BaseException as error:
                if failure is None:failure=error
    if failure is not None:raise failure
    return result


def main(argv=None,*,started=None,source_pin=None):
    import argparse
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--private-config',required=True,type=Path)
    p.add_argument('--execute-reviewed-owner-relink',action='store_true')
    args=p.parse_args(argv)
    def audit(event,unused):
        if event.startswith('socket.') or event=='urllib.Request':raise RuntimeError('NETWORK_FORBIDDEN')
    sys.addaudithook(audit)
    result=run(args.private_config,args.execute_reviewed_owner_relink,started=started,source_pin=source_pin)
    print(json.dumps({'status':result['status'],'phase_count':len(result['stages']),'full_block_pass':False}))
