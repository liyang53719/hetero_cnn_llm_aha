#!/usr/bin/env python3
"""One CI recovery job. Native work requires --execute and a fixed job deadline.

Only the three strictly validated evidence JSONs may be published. Private logs,
artifacts, source archives, generated RTL and tool inventories stay in --out.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B')
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import time
import traceback
import types

HERE = Path(__file__).absolute().parent
SUPPORT = ('ci_support_v2.py', 9154, '931c8d8e4b42c125617ca1058dac809723f8371ffe90205da6b0c64b0aea1a26')
PINS_SIZE = 2854
PINS_SHA = '8144c95891a347d068424c0fec160800fee08bee0f88f74f705982b3b1ac1884'
MIB = 1024**2
GIB = 1024**3
EVIDENCE = ('summary.json', 'source_hashes.json', 'stage_exits.json')
COMPONENTS = ('toolchain', 'host_emission', 'idma319', 'retained13', 'configuration', 'host_execution')
CATEGORIES = ('NONE', 'TIMEOUT', 'INPUT_OR_CONTRACT', 'SYSTEM', 'INTERRUPTED', 'UNEXPECTED')
STAGES = ('official_source473',) + tuple('host_' + x + '-' + y for y in ('version', 'micro') for x in ('autoconf', 'autom4te', 'm4', 'flex', 'bison')) + ('fresh_autoconf', 'fresh_configure', 'fresh_make') + tuple('derived_tiny_' + x for x in ('version', 'generate', 'compile', 'run')) + ('host93_java_version', 'host93_acquire_jar87', 'host93_acquire_hardfloat20', 'host93_assemble', 'host93_class', 'host93_chirrtl', 'host93_acquire_firtool', 'host93_sv', 'idma319_extract', 'retained13_assemble', 'host93_configuration', 'host93_cpp_generate', 'host93_cpp_compile', 'host93_reset_launch')
SCOPES = ('toolchain_tiny', 'fresh_host_sv', 'cpp_generated', 'cpp_compiled', 'reset_launch', 'n0_numeric', 'weights_loaded')
GENERATED_KINDS = ('derived_backend', 'host93_fir', 'host93_sv', 'host_elf')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain_path(value):
    p = Path(value)
    require(re.fullmatch('[A-Za-z0-9_/.-]+', str(p)) is not None, 'finite ASCII make-safe path required')
    require(p.is_absolute() and '..' not in p.parts, 'absolute normalized path required')
    for q in (p,) + tuple(p.parents):
        require(not q.is_symlink(), 'symlink path rejected')
    return p


def bounded_read(path, cap):
    p = plain_path(path)
    with p.open('rb') as f:
        a = os.fstat(f.fileno())
        require(stat.S_ISREG(a.st_mode) and 0 <= a.st_size <= cap, 'bounded regular input')
        raw = f.read(cap + 1)
        z = os.fstat(f.fileno())
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(raw) == a.st_size and stamp(a) == stamp(z) == stamp(p.stat()), 'stable bounded input')
    return raw


def exact(path, size, digest):
    require(type(size) is int and size >= 0 and re.fullmatch('[0-9a-f]{64}', digest or ''), 'fixed source pin bound')
    raw = bounded_read(path, size)
    require(len(raw) == size and sha(raw) == digest, 'fixed source identity before compile')
    return raw


def load(path, size, digest, name):
    raw = exact(path, size, digest)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def keys(value, names):
    require(type(value) is dict and set(value) == set(names), 'strict evidence object keys')


def pin(value, path=False):
    keys(value, ('path', 'bytes', 'sha256') if path else ('bytes', 'sha256'))
    require(type(value['bytes']) is int and 0 <= value['bytes'] <= 8*GIB and
            type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'safe content identity')
    if path:
        name = value['path']
        require(type(name) is str and len(name) <= 240 and re.fullmatch('[A-Za-z0-9_./-]+', name) and
                not name.startswith('/') and '..' not in name.split('/') and
                name.startswith(('candidates/host93_ci_recovery/', 'development_snapshots/', 'candidates/qwen2_resident_matrix/')),
                'only project-relative source names')


def validate_evidence(objects):
    keys(objects, EVIDENCE)
    summary, sources, exits = (objects[n] for n in EVIDENCE)
    keys(summary, ('schema', 'status', 'failure_category', 'completed_components', 'scope', 'seconds'))
    require(summary['schema'] == 'host93-ci-summary-v1' and summary['status'] in
            ('INCOMPLETE', 'READY_REQUIRES_ACTIONS_EXIT0') and summary['failure_category'] in CATEGORIES and
            finite(summary['seconds']) and summary['seconds'] <= 6600, 'summary values')
    completed = summary['completed_components']
    require(type(completed) is list and len(completed) == len(set(completed)) and
            all(x in COMPONENTS for x in completed) and completed == list(COMPONENTS[:len(completed)]), 'finite ordered completed components')
    keys(summary['scope'], SCOPES)
    require(all(type(x) is bool for x in summary['scope'].values()) and
            not summary['scope']['n0_numeric'] and not summary['scope']['weights_loaded'], 'finite scope flags')
    scope = summary['scope']
    require(scope['toolchain_tiny'] == ('toolchain' in completed) and
            scope['fresh_host_sv'] == ('host_emission' in completed) and
            scope['reset_launch'] == ('host_execution' in completed), 'scope/component consistency')
    require(not scope['reset_launch'] or scope['cpp_compiled'] and scope['cpp_generated'], 'scope sequencing')
    keys(sources, ('schema', 'project_sources', 'fixed_inputs', 'generated'))
    require(sources['schema'] == 'host93-ci-source-hashes-v1', 'source schema')
    require(type(sources['project_sources']) is list and len(sources['project_sources']) <= 512, 'source count')
    names = []
    for item in sources['project_sources']:
        pin(item, True); names.append(item['path'])
    require(len(names) == len(set(names)), 'unique project source identities')
    keys(sources['fixed_inputs'], ('idma_archive',))
    pin(sources['fixed_inputs']['idma_archive'])
    require(sources['fixed_inputs']['idma_archive'] == {'bytes':9926876, 'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}, 'fixed official archive identity')
    require(type(sources['generated']) is dict and set(sources['generated']) <= set(GENERATED_KINDS), 'generated identity names')
    for item in sources['generated'].values():
        pin(item)
        require(item['bytes'] > 0, 'generated identity must be nonempty')
    if sources['project_sources']:
        project_map = {item['path']:{k:item[k] for k in ('bytes','sha256')} for item in sources['project_sources']}
        canonical = (json.dumps({'schema':1,'files':project_map}, indent=2, sort_keys=True)+'\n').encode()
        require(len(canonical) == PINS_SIZE and sha(canonical) == PINS_SHA,
                'evidence must reproduce the fixed immediate project source map')
    require(not completed or bool(sources['project_sources']), 'component claim needs source identities')
    expected_generated = set()
    if scope['toolchain_tiny']: expected_generated.add('derived_backend')
    if scope['fresh_host_sv']: expected_generated.update(('host93_fir','host93_sv'))
    if scope['cpp_compiled']: expected_generated.add('host_elf')
    require(set(sources['generated']) == expected_generated, 'scope needs exact generated identities')
    if scope['fresh_host_sv']:
        require(sources['generated']['host93_fir'] == {'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'} and
                sources['generated']['host93_sv'] == {'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'},
                'scope requires the deterministic fixed FIR and SV')
    keys(exits, ('schema', 'stages'))
    require(exits['schema'] == 'host93-ci-stage-exits-v1' and type(exits['stages']) is list and len(exits['stages']) <= len(STAGES), 'stage schema/count')
    seen = []
    failed = False
    for row in exits['stages']:
        keys(row, ('name', 'status', 'exit_code', 'cleanup_confirmed', 'seconds', 'child_user_cpu_seconds', 'child_system_cpu_seconds'))
        require(row['name'] in STAGES and row['name'] not in seen and row['status'] in ('EXIT0_CLEANED', 'FAILED') and type(row['cleanup_confirmed']) is bool and finite(row['seconds']), 'stage values')
        seen.append(row['name'])
        require(row['exit_code'] is None or type(row['exit_code']) is int and -255 <= row['exit_code'] <= 255, 'stage exit')
        for name in ('child_user_cpu_seconds', 'child_system_cpu_seconds'):
            require(row[name] is None or finite(row[name]), 'stage CPU aggregate')
        if row['status'] == 'EXIT0_CLEANED':
            require(row['exit_code'] == 0 and row['cleanup_confirmed'], 'stage terminal tuple')
        else:
            failed = True
    require(not seen or bool(sources['project_sources']), 'native stage evidence needs source identities')
    if summary['status'] == 'READY_REQUIRES_ACTIONS_EXIT0':
        require(summary['failure_category'] == 'NONE' and completed == list(COMPONENTS) and
                all(scope[x] for x in SCOPES[:5]) and not failed and set(seen) == set(STAGES), 'ready requires every finite stage')
    else:
        require(summary['failure_category'] != 'NONE', 'failure status cannot hide error')
    return True


def verify_evidence(out):
    root = plain_path(out) / 'evidence'
    require(root.is_dir() and not root.is_symlink() and set(x.name for x in root.iterdir()) == set(EVIDENCE), 'exact evidence three files')
    buffers = {name: bounded_read(root / name, MIB) for name in EVIDENCE}
    require(sum(map(len, buffers.values())) <= MIB, 'safe evidence combined size')
    validate_evidence({name: decode(raw) for name, raw in buffers.items()})
    return 0


def write_json(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= MIB, 'bounded JSON output')
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(bounded_read(path, MIB) == raw, 'JSON readback')


def interrupted(_signal, _frame):
    raise TimeoutError('shared CI deadline')


def limits(total, work, cpu, address, fsize, log=MIB):
    return {'total_seconds':total,'work_seconds':work,'cpu_seconds':cpu,
            'as_bytes':address,'fsize_bytes':fsize,'log_bytes':log,'sample_rows':total+16}


# Approved finite per-process maxima. Components may only tighten these values.
# Aggregate tree limits remain component postflight acceptance, not OS hard caps.
PHASE_CAPS = {
    'official_source473': (420,400,400,512*MIB,64*MIB,2*MIB),
    'fresh_autoconf': (180,160,160,GIB,64*MIB,MIB),
    'fresh_configure': (180,160,160,GIB,64*MIB,MIB),
    'fresh_make': (3600,3570,3570,4*GIB,GIB,4*MIB),
    'derived_tiny_version': (30,10,10,512*MIB,4*MIB,MIB),
    'derived_tiny_generate': (120,90,90,GIB,8*MIB,MIB),
    'derived_tiny_compile': (300,240,240,2*GIB,32*MIB,MIB),
    'derived_tiny_run': (30,10,10,512*MIB,4*MIB,MIB),
    'host93_java_version': (30,10,10,4*GIB,2*MIB,2*MIB),
    'host93_acquire_jar87': (1200,1190,300,512*MIB,64*MIB,2*MIB),
    'host93_acquire_hardfloat20': (300,290,120,512*MIB,2*MIB,2*MIB),
    'host93_assemble': (60,45,40,512*MIB,4*MIB,2*MIB),
    'host93_class': (330,300,300,4*GIB,48*MIB,2*MIB),
    'host93_chirrtl': (90,60,60,4*GIB,48*MIB,2*MIB),
    'host93_acquire_firtool': (180,170,120,512*MIB,64*MIB,2*MIB),
    'host93_sv': (390,360,360,2*GIB,128*MIB,2*MIB),
    'idma319_extract': (60,45,40,512*MIB,4*MIB,MIB),
    'retained13_assemble': (60,45,40,512*MIB,4*MIB,MIB),
    'host93_configuration': (60,45,45,768*MIB,4*MIB,MIB),
    'host93_cpp_generate': (600,540,540,6*GIB,128*MIB,4*MIB),
    'host93_cpp_compile': (1800,1740,1740,6*GIB,512*MIB,4*MIB),
    'host93_reset_launch': (30,10,10,2*GIB,8*MIB,MIB),
}
for _name in STAGES:
    if _name.startswith('host_'):
        PHASE_CAPS[_name]=(30,10,10,512*MIB,4*MIB,65536)


def phase_limits(name, bound):
    require(name in PHASE_CAPS and type(bound) is dict, 'finite phase budget names')
    names=('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes')
    require(set(names+('sample_rows',)) <= set(bound) and
            set(bound) <= set(names+('sample_rows','tree_bytes','file_count','entry_count')),
            'finite resource keys')
    for key,maximum in zip(names,PHASE_CAPS[name]):
        require(type(bound[key]) is int and 0 < bound[key] <= maximum, 'phase resource exceeds approval')
    require(bound['work_seconds'] < bound['total_seconds'] and
            type(bound['sample_rows']) is int and 0 < bound['sample_rows'] <= bound['total_seconds']+16,
            'finite sampling cap')
    for key in ('tree_bytes','file_count','entry_count'):
        if key in bound:require(type(bound[key]) is int and 0 < bound[key] <= (4*GIB if key=='tree_bytes' else 200000), 'finite output bound')


def memory_disk_gate(folder, memory_bytes, disk_bytes):
    with open('/proc/meminfo', 'rb') as stream:
        raw = stream.read(65537)
    require(0 < len(raw) <= 65536, 'bounded fixed proc memory observation')
    raw = raw.decode('ascii')
    found = re.search(r'^MemAvailable:\s+(\d+) kB$', raw, re.M)
    require(found is not None and int(found[1])*1024 >= memory_bytes, 'available memory below fixed phase floor')
    require(shutil.disk_usage(folder).free >= disk_bytes, 'free disk below fixed phase floor')


def project_pin_map(repo):
    document = decode(exact(HERE / 'RUN_PINS.json', PINS_SIZE, PINS_SHA))
    keys(document, ('schema', 'files'))
    require(document['schema'] == 1 and type(document['files']) is dict, 'fixed source map')
    buffers = {}
    for name, row in document['files'].items():
        pin({'path':name, **row}, True)
        buffers[name] = exact(repo / name, row['bytes'], row['sha256'])
    return document['files'], buffers


def module_from(repo, pins, relative, name):
    row = pins[relative]
    return load(repo / relative, row['bytes'], row['sha256'], name)


def execute(repo, out, archive, supplied_deadline):
    started = time.monotonic()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and type(supplied_deadline) is float and
            math.isfinite(supplied_deadline) and started < supplied_deadline <= started+6600,
            'explicit current GitHub job monotonic deadline required')
    shared_stop = min(supplied_deadline, started+6600)
    work_stop = shared_stop-5
    require(work_stop > started, 'shared evidence reserve unavailable')
    repo, out, archive = map(plain_path, (repo, out, archive))
    require(repo.is_dir() and out.parent.is_dir() and not os.path.lexists(out) and
            not out.is_relative_to(repo) and not repo.is_relative_to(out), 'fresh disjoint private workroot')
    support = load(HERE / SUPPORT[0], SUPPORT[1], SUPPORT[2], 'verified_ci_support_v2')
    support.deadline_ready()
    old_mask = os.umask(0o077)
    old_alarm = signal.signal(signal.SIGALRM, interrupted)
    old_term = signal.signal(signal.SIGTERM, interrupted)
    signal.setitimer(signal.ITIMER_REAL, work_stop-time.monotonic())
    owner = {'handler':interrupted,'deadline':work_stop}
    stages, completed, generated, source_rows = [], [], {}, []
    scopes = {x:False for x in SCOPES}
    failure = None
    try:
        out.mkdir(mode=0o700)
        (out/'private').mkdir(mode=0o700)
        (out/'phases').mkdir(mode=0o700)
        (out/'home').mkdir(mode=0o700)
        (out/'tmp').mkdir(mode=0o700)
        pins, buffers = project_pin_map(repo)
        source_rows = [{'path':name,**row} for name,row in sorted(pins.items())]
        exact(archive,9926876,'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce')
        base_support, base_plan, _ = support.fixed_support(repo)
        def call_phase(name, argv, cwd, environment, bound):
            require(name in STAGES and name not in {x['name'] for x in stages}, 'one finite phase invocation')
            require(time.monotonic() < work_stop-15, 'shared work window exhausted')
            phase_limits(name, bound)
            if name in ('host93_cpp_generate','host93_cpp_compile'):
                memory_disk_gate(out,8*GIB,3*GIB)
            began=time.monotonic()
            evidence=out/'phases'/name
            row={'name':name,'status':'FAILED','exit_code':None,'cleanup_confirmed':False,'seconds':0.0,
                 'child_user_cpu_seconds':None,'child_system_cpu_seconds':None}
            stages.append(row)
            print(json.dumps({'phase':name,'status':'START'},sort_keys=True),flush=True)
            try:
                record, raw, usage=support.run_phase(base_support,base_plan,name,argv,cwd,evidence,environment,bound,work_stop,owner)
                row.update(status='EXIT0_CLEANED',exit_code=record['exit_code'],cleanup_confirmed=record['cleanup_confirmed'],
                           child_user_cpu_seconds=usage['child_user_cpu_seconds'],child_system_cpu_seconds=usage['child_system_cpu_seconds'])
                return {'record':record,'raw_log':raw,'usage':usage,'evidence_root':str(evidence)}
            finally:
                row['seconds']=round(time.monotonic()-began,6)
                print(json.dumps({'phase':name,'status':row['status'],'seconds':row['seconds']},sort_keys=True),flush=True)
        prefix='candidates/host93_ci_recovery/'
        tool=module_from(repo,pins,prefix+'toolchain/ci_toolchain.py','verified_ci_toolchain')
        tools=tool.run(repo,out/'toolchain',call_phase)
        completed.append('toolchain');scopes['toolchain_tiny']=True
        generated['derived_backend']={k:tools['backend'][k] for k in ('bytes','sha256')}
        emission=module_from(repo,pins,prefix+'emission/host_emission.py','verified_ci_host_emission')
        host=emission.run(repo,out/'emission',call_phase)
        completed.append('host_emission');scopes['fresh_host_sv']=True
        generated['host93_fir']={k:host['fir'][k] for k in ('bytes','sha256')}
        generated['host93_sv']={k:host['sv'][k] for k in ('bytes','sha256')}
        environment={'PATH':'/usr/bin:/bin','HOME':str(out/'home'),'TMPDIR':str(out/'tmp'),'LC_ALL':'C','LANG':'C','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        entry=decode(buffers[prefix+'idma319/ENTRY.json'])
        extractor=repo/(prefix+'idma319/extract_idma.py')
        idma=out/'idma319'
        call_phase('idma319_extract',[sys.executable,'-I','-S','-B','-c',entry['bootstrap'],str(extractor),'--archive',str(archive),'--out',str(idma)],out,environment,limits(60,45,40,512*MIB,4*MIB))
        completed.append('idma319')
        retained=out/'retained13'
        call_phase('retained13_assemble',[sys.executable,'-I','-S','-B',str(repo/(prefix+'retained13/run_retained13.py')),'--repo',str(repo),'--out',str(retained)],out,environment,limits(60,45,40,512*MIB,4*MIB))
        completed.append('retained13')
        entry=decode(buffers[prefix+'configuration/ENTRY.json'])
        configuration=out/'configuration'
        # ENTRY supplies the immutable same-buffer bootstrap; source path is caller-bound.
        argv=[sys.executable,'-I','-S','-B','-c',entry['argv_prefix'][5],str(repo/(prefix+'configuration/generate_4vlt.py')),
              '--repo',str(repo),'--sv',host['sv']['path'],'--idma-root',str(idma/'sources'),'--out',str(configuration)]
        call_phase('host93_configuration',argv,out,environment,limits(60,45,45,768*MIB,4*MIB))
        completed.append('configuration')
        execution=module_from(repo,pins,prefix+'execution/host_execution.py','verified_ci_host_execution')
        result=execution.run(repo,out/'host_execution',call_phase,tools,host,idma,retained,configuration)
        completed.append('host_execution')
        for name in ('cpp_generated','cpp_compiled','reset_launch'):scopes[name]=True
        generated['host_elf']={k:result['elf'][k] for k in ('bytes','sha256')}
        # All fixed source content is checked again after the final native phase.
        for name,row in pins.items():exact(repo/name,row['bytes'],row['sha256'])
        exact(archive,9926876,'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce')
    except BaseException as error:
        failure=error
        if (out/'private').is_dir():
            try:
                with (out/'private'/'failure.txt').open('x') as stream:traceback.print_exc(file=stream)
            except BaseException:pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, max(0.001,shared_stop-time.monotonic()))
        try:
            category='NONE' if failure is None else ('TIMEOUT' if isinstance(failure,TimeoutError) else 'INPUT_OR_CONTRACT' if isinstance(failure,(ValueError,KeyError,AssertionError)) else 'SYSTEM' if isinstance(failure,OSError) else 'INTERRUPTED' if isinstance(failure,(KeyboardInterrupt,SystemExit)) else 'UNEXPECTED')
            summary={'schema':'host93-ci-summary-v1','status':'READY_REQUIRES_ACTIONS_EXIT0' if failure is None else 'INCOMPLETE',
                     'failure_category':category,'completed_components':completed,'scope':scopes,'seconds':round(time.monotonic()-started,6)}
            sources={'schema':'host93-ci-source-hashes-v1','project_sources':source_rows,
                     'fixed_inputs':{'idma_archive':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}},'generated':generated}
            objects={'summary.json':summary,'source_hashes.json':sources,'stage_exits.json':{'schema':'host93-ci-stage-exits-v1','stages':stages}}
            validate_evidence(objects)
            evidence=out/'evidence';evidence.mkdir(mode=0o700)
            for name,value in objects.items():write_json(evidence/name,value)
            verify_evidence(out)
            require(time.monotonic()<shared_stop,'evidence final shared deadline')
        except BaseException as report_error:
            if failure is None:failure=report_error
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,old_alarm);signal.signal(signal.SIGTERM,old_term);os.umask(old_mask)
    print(json.dumps({'status':'READY_REQUIRES_ACTIONS_EXIT0' if failure is None else 'INCOMPLETE'},sort_keys=True),flush=True)
    return 0 if failure is None else 1


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--repo',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--idma-archive',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--verify-evidence',action='store_true')
    parser.add_argument('--job-deadline',type=float)
    args=parser.parse_args(argv)
    if args.verify_evidence:
        require(not args.execute and args.repo is None and args.idma_archive is None and args.job_deadline is None,'evidence-only arguments')
        return verify_evidence(args.out)
    if not args.execute:
        require(args.repo is not None and args.idma_archive is None and args.job_deadline is None,'source-only arguments')
        pins,_=project_pin_map(plain_path(args.repo))
        print(json.dumps({'status':'SOURCE_ONLY_NOT_NATIVE_OR_FULL_JOB_QUALIFIED','fixed_files':len(pins)},sort_keys=True))
        return 0
    require(args.repo is not None and args.idma_archive is not None and args.job_deadline is not None,'complete execution arguments')
    return execute(args.repo,args.out,args.idma_archive,args.job_deadline)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'INCOMPLETE','error_category':type(error).__name__ if type(error) in (ValueError,OSError,TimeoutError,FileNotFoundError) else 'UNEXPECTED'},sort_keys=True),flush=True)
        raise SystemExit(1)
