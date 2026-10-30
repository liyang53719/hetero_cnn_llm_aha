"""Inactive source candidate: fixed155 compile and original HIGH/official LOW only.
Uses the existing supervisor; no Verilator frontend, SV, native backend, or numerics.
"""
import argparse, hashlib, importlib.util, json, os, pathlib, re, shutil, subprocess, sys, time, stat

P = pathlib.Path
D = P(__file__).resolve().parent
TREE = 12_081_306_272
JOB_SECONDS = 3600
EXPECTED_NAMES = {'FfnTileSiluBridge.scala', 'FfnResidentCoordinator.scala',
    'QwenOwnerProtocol.scala', 'HostBlockCommandsV4.scala', 'HostBlockTopV4.scala',
    'UnifiedMoeRouterNumericalOwnerV2.scala', 'UnifiedMoeRouterPipelineBindingV2.scala',
    'UnifiedMoeRuntimeExpertLoopV4.scala'}

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    with P(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def load(path):
    path = P(path)
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 << 20, 'bounded regular metadata')
    return json.loads(path.read_text())

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def selected_sources(repo, original, overlay, fixed):
    paths = list(map(P, fixed.checked_paths(repo, repo / 'candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json', original)))
    need(overlay['schema'] == 'FIXED155_OBSERVER_OVERLAY8_V1' and overlay['source_count'] == 155, 'fixed155 overlay scope')
    rows = overlay['files']
    need(len(rows) == 8 and {r['name'] for r in rows} == EXPECTED_NAMES, 'exact eight named observer overrides')
    overrides = {}
    for row in rows:
        rel = P(row['path'])
        need(not rel.is_absolute() and '..' not in rel.parts and rel.name == row['name'], 'relative named observer source')
        path = repo / rel
        need(path.is_file() and not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'observer pin')
        overrides[row['name']] = path
    need(len(paths) == 155 and len({p.name for p in paths}) == 155 and EXPECTED_NAMES <= {p.name for p in paths}, 'fixed155 selection')
    return [overrides.get(path.name, path) for path in paths]

def completed(result):
    return (result.get('native_exit') == 0 and result.get('errors') == []
        and (result.get('cleanup_proof') or {}).get('status') == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'
        and (result.get('log_capture') or {}).get('pipe_eof_observed') is True
        and (result.get('log_capture') or {}).get('gzip_finalized') is True)

def java_command(java, heap, cp, main, args=()):
    return [str(java), '-XX:-UsePerfData', '-XX:ActiveProcessorCount=1',
        '-XX:ReservedCodeCacheSize=128m', '-Xss4m', '-Xmx' + heap, '-cp', cp, main, *args]

def preflight_census(roots, caps):
    """One read-only admission sample, not atomic containment or a new monitor.

    Same root/lstat/inode rules as the unchanged original supervisor. Reserve
    stage dir/home/tmp/log/rss plus lock/STARTED/RESULT (eight entries).
    """
    unique = []
    for root in sorted({P(p).absolute() for p in roots}, key=lambda p: len(p.parts)):
        if not any(root.is_relative_to(parent) for parent in unique):
            unique.append(root)
    count, total, largest = 0, 0, 0
    seen = set()
    def unreadable(error):
        raise error
    for root in unique:
        need(root.is_dir() and not root.is_symlink(), 'preflight existing regular root')
        for base, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
            for name in dirs + files:
                path = P(base) / name
                try:
                    st = path.lstat()
                except FileNotFoundError:
                    continue
                count += 1
                need(count + 8 <= caps['max_entries'], 'preflight entry cap with stage reserve')
                if stat.S_ISLNK(st.st_mode):
                    continue
                need(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode), 'preflight nonregular entry')
                if stat.S_ISREG(st.st_mode):
                    key = (st.st_dev, st.st_ino)
                    if key not in seen:
                        seen.add(key)
                        total += st.st_size
                        largest = max(largest, st.st_size)
        need(shutil.disk_usage(root).free >= caps['min_free_disk_bytes'], 'preflight disk reserve')
    need(count + 8 <= caps['max_entries'], 'preflight entry cap with stage reserve')
    need(total <= caps['watch_tree_bytes'], 'preflight aggregate tree cap')
    need(largest <= caps['file_bytes'], 'preflight file cap')
    return dict(entries=count, reserved_entries=8, bytes=total, largest_file_bytes=largest)

def admitted_execute(supervisor, argv, run, lock, caps, env, pins, resource_gate):
    preflight_census(caps['extra_watch_roots'], caps)
    return supervisor.execute(argv, run, lock, caps, env, pins, resource_gate=resource_gate)

def run(a, ownership):
    repo = a.repo.resolve()
    need(subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == a.source_sha, 'exact source checkout')
    subprocess.run(['git', '-C', str(repo), 'diff', '--quiet', 'HEAD', '--'], check=True)
    identity = load(a.identity)
    need(set(identity) == {'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'}, 'original six-field identity')
    need(identity['source_commit'] != identity['launch_commit'] and all(re.fullmatch('[0-9a-f]{40}', identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')), 'actual distinct source/launch identities')
    event = load(os.environ['GITHUB_EVENT_PATH'])
    need(event.get('before') == identity['source_commit'] and event.get('after') == identity['launch_commit'] and event.get('ref') == 'refs/heads/main', 'independent source/launch push')
    need(identity['source_commit'] == a.source_sha and identity['launch_commit'] == os.environ['GITHUB_SHA']
        and str(identity['run_id']) == os.environ['GITHUB_RUN_ID'] and os.environ['GITHUB_RUN_ATTEMPT'] == '1', 'actual independent first job identity')
    clock = load(a.job_start)
    need(clock['schema'] == 'SAME_JOB_START_V1' and clock['run_id'] == identity['run_id'] and clock['launch_commit'] == identity['launch_commit']
        and clock['job_budget_seconds'] == JOB_SECONDS, 'same first-step job clock')
    started = clock['started_monotonic']
    need(type(started) in (int, float) and 0 <= time.monotonic() - started < JOB_SECONDS, 'job deadline')
    need(sha(a.source_pins) == a.source_pins_sha256, 'reviewed source closure digest')
    pins = {}
    for row in load(a.source_pins)['files']:
        rel = P(row['path'])
        need(not rel.is_absolute() and '..' not in rel.parts, 'relative closure path')
        p = repo / rel
        need(p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'source closure drift')
        pins[str(p.resolve())] = row['sha256']
    for p in (D / 'run_ir_only.py', D / 'inventory_host.py', D / 'check_ir.py', D / 'OVERLAY.json'):
        need(pins.get(str(p)) == sha(p), 'IR entry source independently pinned')
    work = a.work
    need(work.is_absolute() and not work.exists() and not any(p.is_symlink() for p in (work, *work.parents)), 'new independent job work root')
    need(shutil.disk_usage(work.parent).free >= TREE + (8 << 30), 'unchanged aggregate plus free8GiB admission')
    available = int(next(x for x in P('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1]) * 1024
    need(available >= 13 << 30, 'conservative existing memory admission')
    work.mkdir()
    st = work.stat()
    ownership.update(path=str(work), dev=st.st_dev, ino=st.st_ino)
    pipeline = repo / 'candidates/ci_frontend_pipeline_r2_20261029'
    material = repo / 'candidates/ci_frontend_materialization_r2_20261029'
    original_root = repo / 'candidates/fresh_original_top_recovery_20261028'
    sys.path.insert(0, str(pipeline))
    import supervise_multiroot as supervisor
    sys.path.insert(0, str(material))
    import fresh_host
    fresh_host.reject_injection(os.environ)
    contract = dict(schema='BOUNDED_FRESH_HOST_V1', **{k: identity[k] for k in ('run_id', 'source_commit', 'launch_commit')})
    fresh_host.validate_contract(contract, identity)
    contract_path = work / 'HOST_CONTRACT.json'
    contract_path.write_text(json.dumps(contract) + '\n')
    pins[str(contract_path)] = sha(contract_path)
    py = str(P('/usr/bin/python3').resolve())
    java = P(os.environ['JAVA_HOME_21_X64']) / 'bin/java'
    pins[py] = sha(py)
    env = {k: os.environ[k] for k in ('HOME', 'ImageVersion', 'ImageOS', 'JAVA_HOME_21_X64', 'GITHUB_RUN_ID', 'GITHUB_SHA', 'GITHUB_RUN_ATTEMPT')}
    env.update(PATH='/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MAKEFLAGS='-j1')
    stages = []
    aliases = {}
    jdk_aliases = []
    def stage(name, argv, wall=300, rss=1, heap_as=4, tree=TREE, cpu=None, ir_specific=False):
        need(time.monotonic() - started + wall + 90 < JOB_SECONDS, 'whole-job cleanup/summary reserve')
        for path, target in aliases.items():
            need(str(P(path).resolve(strict=True)) == target, 'inventoried alias drift')
        caps = dict(jdk_aliases=jdk_aliases, wall_seconds=wall, cleanup_seconds=45 if ir_specific else 30, file_bytes=(384 << 20) if ir_specific else 536870912,
            tree_bytes=tree, log_bytes=(8 << 20) if ir_specific else 16_777_216, raw_log_bytes=(16 << 20) if ir_specific else 33_554_432,
            max_entries=20000 if ir_specific else 100000, per_process_as_bytes=heap_as << 30,
            per_process_cpu_seconds=cpu or wall, rss_bytes=rss << 30, cpu_seconds=cpu or wall,
            extra_watch_roots=[str(repo), str(work)], min_free_disk_bytes=8 << 30,
            watch_tree_bytes=TREE)
        result = admitted_execute(supervisor, argv, str(work / name), str(work / 'exclusive.lock'), caps, env, pins,
            resource_gate={'min_available_memory': (rss + 1) << 30, 'min_disk_free': 8 << 30})
        stages.append(dict(name=name, native_exit=result.get('native_exit'), error_count=len(result.get('errors') or []),
            elapsed_seconds=result.get('elapsed_seconds'), observed_peak_rss=result.get('observed_peak_rss'), complete=completed(result)))
        (work / 'STAGES.json').write_text(json.dumps(stages, indent=2) + '\n')
        need(completed(result), 'stage incomplete: ' + name)
        return result
    fresh_args = ['--fresh-host-contract', str(contract_path), '--fresh-host-contract-sha256', sha(contract_path)]
    stage('jdk', [py, '-B', str(material / 'inventory_runner_jdk.py'), '--java-home', str(java.parent.parent), '--output', str(work / 'jdk.json'), *fresh_args])
    stage('compile_tools', [py, '-B', str(pipeline / 'inventory_compile_tools.py'), '--output', str(work / 'compile-tools.json')])
    stage('jars', [py, '-B', str(original_root / 'restore_inputs.py'), '--download-jars'], wall=600)
    stage('verilator_bytes', [py, '-B', str(material / 'materialize_verilator.py'), '--output', str(work / 'verilator'), '--execute-reviewed-acquisition'])
    stage('runtime_identity', [py, '-B', str(D / 'inventory_host.py'), '--materialization', str(material), '--contract', str(contract_path), '--contract-sha256', sha(contract_path), '--java-home', str(java.parent.parent), '--verilator-root', str(work / 'verilator'), '--compile-inventory', str(work / 'compile-tools.json'), '--output', str(work / 'host.json')])
    host = load(work / 'host.json')
    pins.update(host['pins'])
    aliases.update(host['aliases'])
    jdk = load(work / 'jdk.json')
    home = java.parent.parent.resolve(strict=True)
    for row in jdk['files']:
        p = home / row['path']
        if 'symlink' in row:
            need(p.is_symlink() and os.readlink(p) == row['symlink'] and str(p.resolve(strict=True)) == row['resolved_target'], 'JDK alias identity')
            jdk_aliases.append(dict(path=str(p), link=row['symlink'], target=row['resolved_target']))
            if 'external_dependency' in row:
                dep = row['external_dependency']
                target = p.resolve(strict=True)
                need(row['path'] == 'lib/security/cacerts' and str(target) == '/etc/ssl/certs/adoptium/cacerts' and not target.is_symlink() and target.stat().st_size == dep['bytes'] and 0 <= dep['bytes'] <= 4 * 1024**2 and sha(target) == dep['sha256'], 'original public JDK external dependency pin')
                pins[str(target)] = dep['sha256']
        else:
            need(p.is_file() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'JDK complete file pin')
            pins[str(p)] = row['sha256']
    original = load(original_root / 'SOURCE_AND_TOOLCHAIN_PINS.json')
    fixed = module('original_fixed_sources', material / 'fixed_sources.py')
    sources = selected_sources(repo, original, load(D / 'OVERLAY.json'), fixed)
    jars, plugins = [], []
    for row in original['jars']:
        p = original_root / 'cache' / row['maven_path']
        need(p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'original JAR identity')
        pins[str(p)] = row['sha256']
        (plugins if row['role'] == 'plugin' else jars).append(str(p))
    need(len(jars) == 106 and len(plugins) == 1, 'exact ordered107 JAR closure')
    for p in sources:
        need(pins.get(str(p.resolve())) == sha(p), 'selected source belongs reviewed closure')
    cp = ':'.join(jars)
    stage('compile155', java_command(java, '2g', cp, 'scala.tools.nsc.Main', ['-classpath', cp, '-Xplugin:' + plugins[0], '-Xplugin-require:chiselplugin', '-language:reflectiveCalls', '-d', '.', *map(str, sources)]), rss=3, heap_as=8, tree=256 << 20)
    classes = sorted((work / 'compile155').rglob('*.class'))
    need(0 < len(classes) <= 20000, 'fresh compiled class inventory')
    for p in classes:
        pins[str(p)] = sha(p)
    stage('original_ir', java_command(java, '4g', str(work / 'compile155') + ':' + cp, 'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'), wall=480, rss=5, heap_as=12, tree=1 << 30, cpu=420, ir_specific=True)
    result = module('original_ir_artifact_check', D / 'check_ir.py').inspect(work / 'original_ir')
    need(time.monotonic() - started < JOB_SECONDS - 30, 'summary deadline reserve')
    result.update(scope='ORIGINAL_HIGH_AND_OFFICIAL_LOW_ONLY', numerical_pass=False,
        source_commit=identity['source_commit'], launch_commit=identity['launch_commit'], run_id=identity['run_id'], stages=stages, canonical_pass=False, target_host_qualified=False)
    raw = json.dumps(result, indent=2) + '\n'
    need(len(raw.encode()) <= 65536, 'bounded summary only')
    (work / 'IR_SUMMARY.json').write_text(raw)

def write_failure_summary(work, ownership, exc):
    # Never mutate a pre-existing/rejected directory, even to write diagnostics.
    if ownership.get('path') != str(work):
        return False
    try:
        fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != (ownership.get('dev'), ownership.get('ino')):
            return False
        summary = dict(scope='ORIGINAL_HIGH_AND_OFFICIAL_LOW_ONLY', status='FAILED_OR_INCOMPLETE',
            exception_class=type(exc).__name__, numerical_pass=False,
            canonical_pass=False, target_host_qualified=False)
        stages = work / 'STAGES.json'
        if stages.is_file() and not stages.is_symlink():
            summary['stages'] = load(stages)
        raw = json.dumps(summary, indent=2) + '\n'
        if len(raw.encode()) > 65536:
            return False
        try:
            out = os.open('IR_SUMMARY.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except OSError:
            return False
        with os.fdopen(out, 'w') as f:
            f.write(raw)
        return True
    finally:
        os.close(fd)

def main():
    p = argparse.ArgumentParser()
    for key in ('repo', 'work', 'identity', 'job-start', 'source-pins'):
        p.add_argument('--' + key, type=P, required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--source-pins-sha256', required=True)
    p.add_argument('--execute-reviewed-ir-only', action='store_true')
    a = p.parse_args()
    need(a.execute_reviewed_ir_only, 'explicit IR-only scope required')
    ownership = {}
    try:
        run(a, ownership)
    except Exception as exc:
        write_failure_summary(a.work, ownership, exc)
        raise

if __name__ == '__main__':
    main()
