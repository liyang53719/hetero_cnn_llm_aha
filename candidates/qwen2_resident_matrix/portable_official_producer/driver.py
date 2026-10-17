"""Fresh same-host official M16 producer. Source proposal; execution closed.

The future reviewed parent owns launch/nonce/tiny qualification and completion.
This child has no authority to qualify itself or to start a Public/M128 run.
All tensors stay in its fresh private workspace. Imports are cold until a phase
is explicitly called. No historical tensor, NPZ or PASS is an input.
"""
from contextlib import contextmanager
import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import stat
import sys
import time

PROFILE = 'qwen2-official-bf16-consumer-host-v1'
STATUS = 'COMPLETE_FRESH_M16_REFERENCE_OUTPUTS'
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
IMPORTED_DRIVER_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
IMPORTED_LOCK_SHA = hashlib.sha256((HERE / 'source-lock.json').read_bytes()).hexdigest()
RUNNER_SHA = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
TABLE_SHA = '5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045'
POLICY_SHA = '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'
METHODS = ('official_self_cache', 'independent_self_cache')
CLAIMS = dict(actual_chain_executed=False, full_public_admission=False,
    full_29_node_acceptance=False, rtl_execution=False,
    hardware_recipe_acceptance=False, old_pass_inherited=False)
TOP_KEYS = {'schema','profile','status','rows','past_tokens','attempt_nonce','ci','host',
    'runtime_identity','runtime_observation','source_sha256','source_manifest_sha256',
    'driver_sha256','source_lock_sha256','payload','readonly','sequential','reduced',
    'native','dispatch','libraries','claims','original_small_gate_revalidated'}
CONTEXT_KEYS={'schema','profile','parent_pid','root','workspace','created_ns','deadline_ns',
    'attempt_nonce','ci','host','driver_sha256','source_lock_sha256','tiny_result_sha256'}


def need(ok, reason):
    if not ok:
        raise ValueError('fresh producer: ' + reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def strict(raw, limit=2 * 1024 * 1024):
    need(type(raw) is bytes and len(raw) <= limit, 'JSON size')
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def bad(_):
        raise ValueError('fresh producer: nonfinite JSON')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    encoded(value)
    return value


def same(left, right):
    return encoded(left) == encoded(right)


def record(workspace, path, *, limit=188043264):
    workspace, path = Path(workspace).absolute(), Path(path).absolute()
    need('..' not in workspace.parts and '..' not in path.parts and path.is_relative_to(workspace)
         and all(not p.is_symlink() for p in (path, *path.parents)), 'artifact path')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit, 'artifact type/size/alias')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        need((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), 'artifact open race')
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
        final = os.fstat(stream.fileno())
    need((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
         (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns), 'artifact drift')
    return dict(path=path.relative_to(workspace).as_posix(), bytes=info.st_size, sha256=value.hexdigest())


def resolve(workspace, item):
    need(type(item) is dict and set(item) == {'path','bytes','sha256'}, 'record keys')
    name = item['path']
    need(type(name) is str and '\\' not in name and not PurePosixPath(name).is_absolute() and
         all(p not in ('','.','..') for p in name.split('/')), 'relative artifact')
    need(type(item['bytes']) is int and 0 <= item['bytes'] <= 188043264 and digest(item['sha256']), 'record size/hash')
    path = Path(workspace) / name
    need(record(workspace, path) == item, 'record bytes changed')
    return path


def save(path, value):
    raw = encoded(value)
    need(len(raw) <= 2 * 1024 * 1024, 'metadata bound')
    with Path(path).open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return sha(raw)


def verify_sources(root):
    root = Path(root).resolve()
    need(root == ROOT, 'single selected source root')
    lock_raw = (HERE / 'source-lock.json').read_bytes()
    need(sha(lock_raw) == IMPORTED_LOCK_SHA, 'source lock drift')
    lock = strict(lock_raw)
    need(set(lock) == {'schema','sources'} and type(lock['schema']) is int and lock['schema'] == 1, 'source lock')
    need(type(lock['sources']) is dict and bool(lock['sources']), 'source lock inventory')
    for name, expected in lock['sources'].items():
        need(type(name) is str and '\\' not in name and '\x00' not in name and not PurePosixPath(name).is_absolute()
             and all(p not in ('','.','..') for p in name.split('/')) and digest(expected), 'source pin')
        need(record(root, root / name, limit=8*1024*1024)['sha256'] == expected, 'source drift')
    need(sha(Path(__file__).read_bytes()) == IMPORTED_DRIVER_SHA, 'driver drift')
    return lock['sources'], sha(lock_raw)


def workspace_path(root, workspace):
    """Reject source/output overlap before creating directories or acquiring data."""
    root, workspace = Path(root).resolve(), Path(workspace).absolute()
    need(root == ROOT and '..' not in workspace.parts, 'selected source/output paths')
    need(not workspace.is_relative_to(root) and not root.is_relative_to(workspace),
         'workspace must be disjoint from source checkout')
    need(all(not p.is_symlink() for p in (workspace, *workspace.parents)), 'workspace symlink')
    need(workspace.parent.is_dir(), 'workspace parent directory')
    return workspace


def modules(root):
    sources, lock_sha = verify_sources(root)
    # -B prevents writes, but Python can still read existing .pyc files. Fresh
    # production imports must therefore have no source-side bytecode cache and
    # no unpinned package initializer that could execute before a pinned module.
    need(sys.dont_write_bytecode and sys.pycache_prefix is None, 'cold source import mode')
    for name in sources:
        path = Path(root) / name
        if path.suffix != '.py':
            continue
        need(not path.with_suffix('.pyc').exists() and
             not any((path.parent/'__pycache__').glob(path.stem+'.*.pyc')), 'source bytecode cache')
        for parent in path.parents:
            if parent == Path(root):
                break
            initializer = parent/'__init__.py'
            if initializer.exists():
                need(initializer.relative_to(root).as_posix() in sources, 'unpinned package initializer')
    for directory in (Path(root), Path(root)/'scripts', Path(root)/'src'):
        sys.path.insert(0, str(directory))
    prefix = 'candidates.qwen2_resident_matrix.'
    names = dict(gate=prefix+'portable_official_producer.gate',
        owner=prefix+'portable_official_producer.owned_commands',
        phase=prefix+'raw_kv_native_qk_run.phase', capture=prefix+'raw_kv_native_qk_run.dispatch_capture',
        prepare=prefix+'raw_kv_native_qk.prepare', patch=prefix+'raw_kv_native_qk_run.runtime',
        qk=prefix+'raw_kv_native_qk.kernel', qkv=prefix+'raw_kv_native_qkv.kernel',
        builder=prefix+'dense_block_reduce.reference.builder', workload=prefix+'dense_block_reduce.reference.workload',
        assets=prefix+'raw_kv_public_fresh.assets', rms='qwen2_rms_rope_prefill_candidate', payload='qwen2_layer0_payload')
    found = {}
    for name,module in names.items():
        if name=='rms':
            before=found['capture'].fenv_snapshot()
            need(before==dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False),'pre-import fenv')
        found[name]=importlib.import_module(module)
        if name=='rms':
            need(found['capture'].fenv_snapshot()==before,'numerical import fenv drift')
    for module in found.values():
        path = Path(module.__file__).resolve()
        need(path.is_relative_to(root), 'mixed imported source root')
    verify_sources(root)
    return found, sources, lock_sha


def remaining(end_ns, reserve=0):
    need(type(end_ns) is int, 'typed deadline')
    seconds = (end_ns-time.monotonic_ns())/1e9-reserve
    if seconds <= 0:
        raise TimeoutError('fresh producer absolute deadline')
    return seconds


@contextmanager
def bounded(end_ns):
    """Bound non-child phases. Owned commands require this timer to be disarmed."""
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'one timer owner')
    signals = (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)
    old = {s:signal.getsignal(s) for s in signals}
    def expired(signum, frame):
        raise TimeoutError('fresh producer phase deadline or cancellation')
    try:
        for s in signals:
            signal.signal(s, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining(end_ns))
        yield
        remaining(end_ns)
    finally:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, set(signals))
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for s, handler in old.items():
                signal.signal(s, handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def phase_end(overall, seconds):
    remaining(overall)
    return min(overall, time.monotonic_ns()+seconds*10**9)


def compile_recipe(m, kernel, out, end_ns, status):
    """Control-only overlay: original C++/FLAGS/receipt/verify stay exact.

    Never call kernel.build/_compile: their historical spawn/reap ownership
    sequence is not the reviewed portable consumer ownership sequence.
    """
    start = time.monotonic_ns()
    end_ns = min(end_ns, start+kernel.TOTAL*10**9)
    frozen, compiler = kernel.source_snapshot(), kernel.compiler_identity()
    out.mkdir()
    (out/kernel.CPP).write_bytes(kernel.source_bytes())
    argv = [compiler['path'], *kernel.FLAGS, str(out/kernel.CPP), '-o', str(out/kernel.LIBRARY)]
    m['owner'].run(ROOT, argv, cwd=out, log=out/'compile.log', end_ns=end_ns-10**9)
    need(kernel.source_snapshot() == frozen and kernel.compiler_identity() == compiler, 'compiler/source changed')
    kernel._atomic(out/kernel.RECEIPT, dict(schema=1, profile=kernel.PROFILE, status=status,
        returncode=0, numerical_execution=False, official_framework_acceptance=False, **frozen,
        compiler=compiler, argv=argv, library_sha256=kernel.sha(kernel.read(out/kernel.LIBRARY)),
        elapsed_seconds=(time.monotonic_ns()-start)/1e9, total_budget_seconds=kernel.TOTAL))
    result = kernel.verify(out)
    remaining(end_ns)
    return result


def prepare_sources_and_libraries(root, workspace, end_ns):
    m, sources, _ = modules(root)
    workspace = Path(workspace).absolute()
    generated = workspace/'generated'
    with bounded(phase_end(end_ns, 40)):
        prepared = m['prepare'].prepare(generated)
        need(prepared['generated_module_sha256'] == m['patch'].INTERMEDIATE_GENERATED_MODULE_SHA256, 'paired runner intermediate')
        m['patch'].apply_dispatch_patch(generated, {'sources':sources})
        runner = generated/m['qk'].ORIGINAL
        m['gate'].verify_runner(root, runner)
    # Keep the original combined 30-second library phase; each receipt retains
    # its own original TOTAL=30 ceiling. No deadline is silently enlarged.
    library_end = phase_end(end_ns, 30)
    qkv = compile_recipe(m, m['qkv'], workspace/'qkv_library', library_end, 'COMPILED_QKV_RECIPE')
    qk = compile_recipe(m, m['qk'], workspace/'qk_library', library_end, 'COMPILED_QK_RECIPE')
    compiler=m['qk'].compiler_identity()
    m['owner'].run(root,[compiler['path'],'--version'],cwd=workspace,log=workspace/'compiler-version.log',end_ns=phase_end(end_ns,10))
    version=(workspace/'compiler-version.log').read_bytes()
    need(0<len(version)<=4096,'compiler version bound')
    save(workspace/'COMPILER.json',dict(**compiler,version=version.decode('utf-8').splitlines()[0]))
    return runner, qkv, qk


def collect_fresh_payload(root, workspace, end_ns):
    m, _, _ = modules(root)
    directory = Path(workspace)/'payload'
    need(not directory.exists() and not directory.is_symlink(), 'fresh official acquisition only')
    with bounded(phase_end(end_ns, 240)):
        m['payload'].collect(Path(root), directory)
        manifest, payload = m['payload'].load_payload(Path(root), directory)
        need(len(payload) == 13 and sum(map(len,payload.values())) == 94382080, 'fixed official payload inventory')
        need(sum(len(r['http_ranges']) for r in manifest['tensors']) == 22, 'fixed range inventory')
    return manifest


def compiler_record(m,workspace):
    value=strict((Path(workspace)/'COMPILER.json').read_bytes())
    need(set(value)=={'path','sha256','version'} and type(value['version']) is str and 0<len(value['version'])<=4096,'compiler observation')
    need({k:value[k] for k in ('path','sha256')}==m['qk'].compiler_identity(),'current compiler differs')
    return value


def external_digest(path):
    path=Path(path).resolve(strict=True)
    before=path.stat();need(stat.S_ISREG(before.st_mode) and before.st_size<=2**32,'runtime file')
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    after=path.stat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'runtime file drift')
    return value.hexdigest()


def observed_libc_files():
    raw=Path('/proc/self/maps').read_text();need(len(raw)<=4*1024*1024,'runtime mapping bound')
    result={}
    for name in ('libm.so.6','libc.so.6'):
        paths={line.split()[-1] for line in raw.splitlines() if line.split()[-1].endswith('/'+name)}
        need(len(paths)==1,'mapped libc/libm identity')
        result[name]=external_digest(next(iter(paths)))
    return result


def runtime_observation(m, native, workspace, qkv, qk, *, load_recipe):
    before_import=m['capture'].fenv_snapshot()
    import torch
    _, identity = native.runtime_identity(ROOT)
    identity['independent_qkv_recipe'] = m['phase'].combined_identity(qk,qkv)
    identity = strict(encoded(identity))
    m['gate'].validate_identity(identity)
    m['gate'].environment()
    need(torch.version.git_version == '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0', 'Torch commit')
    need(torch.backends.mkldnn.enabled is True, 'native MKLDNN setting')
    fenv = m['capture'].fenv_snapshot()
    need(fenv == dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False), 'FP environment')
    need(before_import==fenv,'Torch import fenv drift')
    observation = dict(host=m['gate'].host_identity(), cpu=m['phase'].read_cpu_features(),
        reported_torch_capability=torch.backends.cpu.get_cpu_capability(),
        torch_commit=torch.version.git_version, mkldnn_enabled=torch.backends.mkldnn.enabled,
        compiler=compiler_record(m,workspace), libc=list(platform.libc_ver()),
        python_executable_sha256=external_digest(sys.executable),runtime_libc_sha256=observed_libc_files(),
        fenv=fenv, blas_environment=m['gate'].environment())
    recipe = None
    if load_recipe:
        from candidates.qwen2_resident_matrix.raw_kv_native_qk.adapter import Recipe
        recipe = Recipe(Path(workspace)/'qkv_library', Path(workspace)/'qk_library')
        need(same(recipe.identity(),identity['independent_qkv_recipe']), 'real recipe identity')
        need(m['capture'].fenv_snapshot() == fenv, 'recipe fenv drift')
    return identity, observation, recipe


def run_m16(root, workspace, end_ns):
    """Exact official paired forward plus all original small-gate array checks."""
    workspace = Path(workspace)
    stop = phase_end(end_ns,60)
    with bounded(stop):
        m, sources, _ = modules(root)
        runner = workspace/'generated'/m['qk'].ORIGINAL
        m['gate'].verify_runner(root,runner)
        native = m['phase']._generated(runner,RUNNER_SHA)
        qkv,qk = m['qkv'].verify(workspace/'qkv_library'),m['qk'].verify(workspace/'qk_library')
        identity, observed, recipe = runtime_observation(m,native,workspace,qkv,qk,load_recipe=True)
        capture = m['capture'].Capture(workspace/'native16_dispatch',importlib.import_module('torch'))
        result = native.run_gate(Path(root),workspace/'payload',workspace/'native16',tokens=16,
            carried=False,threads=4,small_gate=None,qkv_recipe=recipe,diagnostics=capture)
        need(same(identity,result['identity']), 'actual official runtime identity')
        raw = (workspace/'native16/RESULT.json').read_bytes()
        need(same(strict(raw),result), 'native in-memory/disk result')
        m['phase'].verify_exports(result,workspace/'native16',16)
        report = m['phase'].project_result(result,tokens=16,result_sha256=sha(raw),source_sha256=sources,
            contract_sha256=POLICY_SHA,generated_module_sha256=RUNNER_SHA,library=qk,qkv_library=qkv,
            payload_manifest_sha256=sha((workspace/'payload/manifest.json').read_bytes()))
        need(report['status'] == 'COMPLETE_NATIVE_VALIDATION', 'original native M16 numerical gate')
        # run_gate(M16) emits nine receipt semantics. Explicitly replay the
        # original array validator now; it adds all twelve checks per path.
        validate_small(m,native,workspace,identity)
        dispatch = m['gate'].check_dispatch(capture.report())
        recipe.revalidate()
        _,after,_ = runtime_observation(m,native,workspace,qkv,qk,load_recipe=False)
        need(same(after,observed), 'runtime/fenv drift')
        save(workspace/'native16/VALIDATED.json',report)
        save(workspace/'native16/DISPATCH.json',dispatch)
        save(workspace/'native16/RUNTIME.json',dict(identity=identity,observation=observed))
        verify_sources(root)
    return result, identity, observed, dispatch


def validate_small(m,native,workspace,identity):
    import numpy as np
    manifest,payload = m['payload'].load_payload(ROOT,workspace/'payload')
    embedding = (np.frombuffer(payload['embed_tokens.rows_0_255'],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(256,1536)
    config = strict((ROOT/native.SOURCE/'config.json').read_bytes())
    native.validate_small_gate(workspace/'native16/RESULT.json',identity,
        sha((workspace/'payload/manifest.json').read_bytes()),native.load_policy(ROOT),config,embedding,False,4)


def build_scalar_references(root,workspace,rows,end_ns):
    """Fresh sequential and reduced references; neither auxiliary verdict gates the other."""
    need(type(rows) is int and rows == 16, 'this successor implements M16 only')
    m,sources,_ = modules(root)
    workspace = Path(workspace)
    rms,builder,assets = m['rms'],m['builder'],m['assets']
    original,header,_ = builder.regenerate_sources(root)
    reduced,_ = builder.transform(original,(Path(root)/builder.PROFILE_REL).read_bytes())
    layout = rms.R.make_layout();rms.G.validate_layout(layout)
    compiler = compiler_record(m,workspace)
    records = {}
    for role,source in (('sequential',original),('reduced',reduced)):
        out=workspace/role;out.mkdir()
        (out/'candidate.cpp').write_bytes(source);(out/'block_layout.h').write_bytes(header)
        argv=[compiler['path'],*builder.FLAGS,str(out/'candidate.cpp'),'-o',str(out/'candidate')]
        # Original 10s compile request, with ownership cleanup inside that bound.
        done=m['owner'].run(root,argv,cwd=out,log=out/'compile.log',end_ns=phase_end(end_ns,10))
        save(out/'compile.json',dict(schema=1,status='COMPILED',producer=assets.PRODUCERS[role],argv=argv,
            compiler=compiler,returncode=0,source_sha256=sources,cpp_sha256=sha(source),header_sha256=sha(header),
            binary_sha256=record(workspace,out/'candidate')['sha256'],elapsed_seconds=done['elapsed_seconds'],requested_timeout_seconds=10))
        records[role]=dict(producer=assets.PRODUCERS[role],**{k:record(workspace,out/file) for k,file in
            (('cpp','candidate.cpp'),('header','block_layout.h'),('executable','candidate'),('compile','compile.json'))})
    ro=workspace/'readonly';ro.mkdir()
    with bounded(phase_end(end_ns,30)):
        rms.generate_tables(workspace/'sequential/candidate',ro/'tables.f32le')
        need(record(workspace,ro/'tables.f32le')['sha256'] == TABLE_SHA, 'original table bytes')
        _,payload=m['payload'].load_payload(Path(root),workspace/'payload')
        inputs=rms.write_arena(layout,payload,16,0,ro,ro/'tables.f32le')
        pin=m['workload'].INPUT_PINS[16]
        need(inputs['readonly_sha256']==pin['readonly_sha256'] and inputs['input_x_sha256']==pin['input_x_sha256'], 'original input/arena')
    readonly=dict(arena=record(workspace,ro/'readonly_arena.f32le'),table=record(workspace,ro/'tables.f32le'),
        input_x=record(workspace,ro/'input_x.f32le'),input_x_sha256=inputs['input_x_sha256'],intermediate_preloads=0)
    for role in ('sequential','reduced'):
        out=workspace/role;empty=out/'empty_cache.f32le';empty.write_bytes(b'')
        raw=out/'raw_stages'
        raw.mkdir(mode=0o700)
        argv=[str(out/'candidate'),str(ro/'readonly_arena.f32le'),'16',str(raw),'0',str(empty),str(empty)]
        done=m['owner'].run(root,argv,cwd=out,log=out/'stdout.log',end_ns=phase_end(end_ns,30))
        stdout=(out/'stdout.log').read_bytes();need(len(stdout)<=16384,'software stdout bound')
        ack=rms.software_ack(stdout.decode(),16,0)
        inventory=m['workload'].output_inventory(16)
        need({p.name for p in raw.iterdir()}==set(inventory),'raw output inventory')
        outputs={name:record(workspace,raw/name) for name in inventory}
        m['workload'].validate_sealed_inventory(16,outputs)
        actual=rms.C.load_actual(raw,ro/'readonly_arena.f32le',ro/'input_x.f32le',layout,16)
        semantics=rms.N.audit_semantics(actual,None,rms.G.config_for(layout),'bf16')
        need(len(semantics)==12 and all(semantics.values()),'scalar original semantics')
        # Raw caches are separately checked; load_actual reconstructs caches.
        import numpy as np
        for name in ('cache_k','cache_v'):
            cache=np.fromfile(raw/(name+'.f32le'),dtype='<f4').reshape(1,16,2,128).transpose(0,2,1,3)
            need(np.array_equal(cache.view('<u4'),actual[name].view('<u4')),'actual raw cache append')
        save(out/'run.json',dict(schema=1,status='COMPLETE_REFERENCE_ONLY',producer=assets.PRODUCERS[role],argv=argv,
            returncode=0,software_ack=ack,readonly_sha256=inputs['readonly_sha256'],input_x_sha256=inputs['input_x_sha256'],
            table_sha256=TABLE_SHA,output_sha256={n:r['sha256'] for n,r in outputs.items()},actual_chain_executed=False,
            stdout=record(workspace,out/'stdout.log'),empty_cache=record(workspace,empty),elapsed_seconds=done['elapsed_seconds'],requested_timeout_seconds=30))
        records[role].update(run=record(workspace,out/'run.json'),outputs=outputs)
        if role=='sequential':
            tensors=out/'tensors';tensors.mkdir();exported=rms.C.export_actual(actual,tensors)
            save(out/'exports.json',exported)
            records[role].update(export_receipt=record(workspace,out/'exports.json'),
                tensors={r['name']:record(workspace,tensors/r['path']) for r in exported})
    verify_sources(root)
    return readonly,records


def validate_manifest(value):
    need(type(value) is dict and set(value)==TOP_KEYS,'handoff keys')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE and value['status']==STATUS,'handoff profile')
    need(type(value['rows']) is int and value['rows']==16 and type(value['past_tokens']) is int and value['past_tokens']==0,'handoff geometry')
    need(digest(value['attempt_nonce']) and digest(value['driver_sha256']) and digest(value['source_lock_sha256']),'handoff identities')
    need(type(value['ci']) is dict and set(value['ci'])=={'commit','run_id','run_attempt'} and digest(value['ci']['commit'],40),'CI commit')
    need(all(type(value['ci'][k]) is str and value['ci'][k].isascii() and value['ci'][k].isdecimal() and int(value['ci'][k])>0 for k in ('run_id','run_attempt')),'CI run')
    need(same(value['claims'],CLAIMS) and value['original_small_gate_revalidated'] is True,'nonacceptance claims')
    need(sha(encoded(value['source_sha256']))==value['source_manifest_sha256'],'source manifest digest')
    return value


def verify_handoff(root,workspace,expected_sha256,*,decode_native=False):
    """Default hashes/metadata/current identity only; no reference array decoding.

    The parent authenticates owned zero-exit/cleanup separately. A child manifest
    cannot authorize Public or M128. decode_native is producer-only revalidation.
    """
    need(type(decode_native) is bool,'decode mode')
    workspace=workspace_path(root,workspace);path=workspace/'PRODUCER_M16.json'
    raw=path.read_bytes();need(sha(raw)==expected_sha256,'handoff manifest hash')
    value=validate_manifest(strict(raw))
    m,sources,lock_sha=modules(root)
    need(same(value['source_sha256'],sources) and value['source_lock_sha256']==lock_sha and value['driver_sha256']==IMPORTED_DRIVER_SHA,'handoff source binding')
    need(same(value['host'],m['gate'].host_identity()),'same host/boot')
    # Reuse original manifest schema for payload/readonly/scalar/native shapes;
    # the paired native identity and external consumer ELF are separate fields.
    legacy={k:value[k] for k in ('schema','rows','past_tokens','source_sha256','source_manifest_sha256','payload','readonly','sequential','reduced','native')}
    legacy.update(profile=m['assets'].PROFILE,status=m['assets'].STATUS,
        native=dict(value['native'],producer=m['assets'].NATIVE_PRODUCER),
        library=dict(receipt=value['libraries']['qkv']['receipt'],binary=value['libraries']['qkv']['binary']))
    m['assets'].validate_manifest(legacy)
    for field in ('payload','readonly','sequential','reduced','native','libraries'):
        for item in m['assets'].records(value[field]):
            resolve(workspace,item)
    m['assets'].reject_aliases(workspace,{role:list(m['assets'].records(value[role])) for role in ('payload','readonly','sequential','reduced','native','libraries')})
    m['assets']._verify_payload(workspace,legacy)
    qkv,qk=m['qkv'].verify(workspace/'qkv_library'),m['qk'].verify(workspace/'qk_library')
    native=m['phase']._generated(workspace/'generated'/m['qk'].ORIGINAL,RUNNER_SHA)
    identity,observation,_=runtime_observation(m,native,workspace,qkv,qk,load_recipe=False)
    need(same(identity,value['runtime_identity']) and same(observation,value['runtime_observation']),'current runtime binding')
    result=strict(resolve(workspace,value['native']['result']).read_bytes())
    m['gate'].check_m16_metadata(result,identity=identity,source_map=sources,library=qk,qkv_library=qkv,payload_sha=value['payload']['manifest']['sha256'])
    m['phase'].verify_exports(result,workspace/'native16',16)
    need(value['native']['producer']=='generated-paired-qkv-qk.run_gate' and value['native']['result']['path']=='native16/RESULT.json','paired native path')
    for mode in ('bf16','fp32'):
        stages=result['modes'][mode]['phases'][0]['stages']
        for method,kind in zip(METHODS,('native','independent')):
            for name,entry in stages.items():
                need(value['native']['outputs'][mode][method][name]==record(workspace,workspace/'native16'/entry[kind+'_file']),'native export record binding')
    m['gate'].check_dispatch(value['dispatch'])
    for role in ('sequential','reduced'):
        m['assets']._verify_producer(workspace,legacy,role,observation['compiler'],m['rms'])
    m['assets']._verify_exports(workspace,legacy)
    if decode_native:
        validate_small(m,native,workspace,identity)
    verify_sources(root)
    need(path.read_bytes()==raw,'handoff changed during verification')
    return value


def launch_context(root,workspace,end_ns,attempt_nonce,ci,path,expected_sha):
    """Source-bound parent launch, not a reusable serialized PASS receipt."""
    workspace=workspace_path(root,workspace)
    root,path=Path(root).resolve(),Path(path).absolute()
    need(path==workspace.parent/'PRODUCER_CONTEXT.json','fixed launch context location')
    item=record(path.parent,path,limit=65536)
    need(item['sha256']==expected_sha and digest(expected_sha),'launch context hash')
    raw=path.read_bytes()
    need(sha(raw)==expected_sha,'launch context read drift')
    value=strict(raw,65536)
    need(type(value) is dict and set(value)==CONTEXT_KEYS,'launch context fields')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']=='qwen2-fresh-same-host-producer-context-v1','launch context profile')
    need(type(value['parent_pid']) is int and value['parent_pid']==os.getppid() and value['parent_pid']>1,'actual launch parent')
    need(value['root']==str(root) and value['workspace']==str(workspace),'launch paths')
    need(value['attempt_nonce']==attempt_nonce and digest(attempt_nonce) and same(value['ci'],ci),'launch identity')
    need(type(ci) is dict and set(ci)=={'commit','run_id','run_attempt'} and digest(ci['commit'],40)
         and all(type(ci[k]) is str and ci[k].isascii() and ci[k].isdecimal() and int(ci[k])>0
                 for k in ('run_id','run_attempt')), 'launch CI identity')
    need(type(value['created_ns']) is int and type(value['deadline_ns']) is int and
         value['created_ns']<=time.monotonic_ns()<value['deadline_ns']==end_ns<=value['created_ns']+900*10**9,'launch absolute deadline')
    _,lock_sha=verify_sources(root)
    need(value['driver_sha256']==IMPORTED_DRIVER_SHA and value['source_lock_sha256']==lock_sha and digest(value['tiny_result_sha256']),'launch sources/tiny receipt')
    boot=Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    current=dict(host_sha256=sha(os.uname().nodename.encode()),boot_sha256=sha(boot),machine='x86_64',system='Linux')
    need(os.uname().sysname=='Linux' and os.uname().machine=='x86_64' and same(value['host'],current),'launch host')
    need(path.read_bytes()==raw,'launch context changed during admission')
    return value


def produce_m16(root,workspace,end_ns,*,attempt_nonce,ci,context_path,context_sha256):
    """Run only from the exact fresh, source-bound live parent context."""
    workspace=workspace_path(root,workspace)
    launch_context(root,workspace,end_ns,attempt_nonce,ci,context_path,context_sha256)
    need(digest(attempt_nonce),'live parent nonce')
    workspace=Path(workspace).absolute()
    need(not workspace.exists() and not workspace.is_symlink(),'fresh private workspace')
    workspace.mkdir(mode=0o700)
    m,sources,lock_sha=modules(root)
    m['gate'].environment()
    collect_fresh_payload(root,workspace,end_ns)
    prepare_sources_and_libraries(root,workspace,end_ns)
    result,identity,observation,dispatch=run_m16(root,workspace,end_ns)
    readonly,refs=build_scalar_references(root,workspace,16,end_ns)
    payload_manifest=strict((workspace/'payload/manifest.json').read_bytes())
    native_outputs={mode:{method:{name:record(workspace,workspace/'native16'/entry[kind+'_file'])
        for name,entry in result['modes'][mode]['phases'][0]['stages'].items()}
        for method,kind in zip(METHODS,('native','independent'))} for mode in ('bf16','fp32')}
    libraries={role:dict(binary=record(workspace,workspace/(role+'_library')/m[role].LIBRARY),
        receipt=record(workspace,workspace/(role+'_library')/m[role].RECEIPT)) for role in ('qkv','qk')}
    value=dict(schema=1,profile=PROFILE,status=STATUS,rows=16,past_tokens=0,attempt_nonce=attempt_nonce,ci=ci,
        host=observation['host'],runtime_identity=identity,runtime_observation=observation,
        source_sha256=sources,source_manifest_sha256=sha(encoded(sources)),driver_sha256=IMPORTED_DRIVER_SHA,
        source_lock_sha256=lock_sha,payload=dict(manifest=record(workspace,workspace/'payload/manifest.json'),
        tensors={r['local_name']:record(workspace,workspace/'payload'/r['file']) for r in payload_manifest['tensors']}),
        readonly=readonly,**refs,native=dict(producer='generated-paired-qkv-qk.run_gate',result=record(workspace,workspace/'native16/RESULT.json'),outputs=native_outputs),
        dispatch=dispatch,libraries=libraries,claims=CLAIMS,original_small_gate_revalidated=True)
    validate_manifest(value)
    manifest_sha=save(workspace/'PRODUCER_M16.json',value)
    verify_handoff(root,workspace,manifest_sha,decode_native=False)
    launch_context(root,workspace,end_ns,attempt_nonce,ci,context_path,context_sha256)
    remaining(end_ns)
    return dict(path=str(workspace/'PRODUCER_M16.json'),sha256=manifest_sha)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--deadline-ns',type=int,required=True)
    parser.add_argument('--attempt-nonce',required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--run-attempt',required=True)
    parser.add_argument('--context',type=Path,required=True)
    parser.add_argument('--context-sha256',required=True)
    args=parser.parse_args()
    produce_m16(args.root,args.workspace,args.deadline_ns,attempt_nonce=args.attempt_nonce,
        ci=dict(commit=args.commit,run_id=args.run_id,run_attempt=args.run_attempt),
        context_path=args.context,context_sha256=args.context_sha256)


if __name__=='__main__':
    main()
