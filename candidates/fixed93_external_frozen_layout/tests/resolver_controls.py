"""Synthetic file/path controls only. Never open project frozen data or a model."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

HERE = Path(__file__).resolve().parents[1]

def need(ok, message):
    if not ok:
        raise AssertionError(message)

def reject(fn):
    try:
        fn()
    except (ValueError, TypeError, KeyError, FileNotFoundError):
        return
    raise AssertionError('negative accepted')

def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def run(output):
    start = time.monotonic()
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'use -I -S -B')
    output = Path(output).absolute()
    need(output.resolve() == output and not output.exists(), 'fresh synthetic output required')
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    signal.alarm(15)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    denied = []
    relative_write_probe = {'name': None}
    def audit(event, args):
        if event.startswith(('ctypes.', 'subprocess.', 'socket.')) or event in ('os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn'):
            denied.append(event); raise RuntimeError('native/process/network denied')
        if event == 'import' and args[0].split('.')[0] in {'ctypes', 'numpy', 'torch', 'candidates'}:
            denied.append('import'); raise RuntimeError('DUT/native import denied')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).absolute()
            mode, flags = args[1:]
            writing = (type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = path.is_relative_to(output) if writing else (path.is_relative_to(output) or path.is_relative_to(HERE) or str(path).startswith(sys.base_prefix+'/lib/'))
            if writing and not Path(os.fsdecode(args[0])).is_absolute() and args[0] == relative_write_probe['name']:
                allowed = True  # Exact synthetic dir_fd probe reaches the later real guard.
            if not allowed:
                denied.append('open'); raise RuntimeError('foreign file access denied')
    sys.addaudithook(audit)
    output.mkdir()
    source = HERE/'overlay/frozen_layout.py'
    before = pin(source.read_bytes())
    spec = importlib.util.spec_from_file_location('_synthetic_frozen_layout', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    serial = 0
    def fixture():
        nonlocal serial
        serial += 1
        folder = output/f'f{serial:02d}'
        candidate, inp, ref = folder/'candidate', folder/'inputs', folder/'reference'
        for p in (candidate, inp/'typed', inp/'raw', ref/'first', ref/'proof'):
            p.mkdir(parents=True, exist_ok=True)
        paths = {'work/qwen2_recovered_inputs/typed/a.bin': inp/'typed/a.bin',
                 'work/qwen2_recovered_inputs/raw/a.bin': inp/'raw/a.bin',
                 'work/qwen2_recovered_reference/first/a.f32le': ref/'first/a.f32le'}
        for i, p in enumerate(paths.values()):
            p.write_bytes(bytes([i+1])*4)
        files = {n: pin(p.read_bytes()) for n, p in paths.items()}
        roots = dict(zip(module.PREFIXES, (str(inp), str(ref))))
        def create():
            return module.FrozenLayout(roots, files, candidate=candidate, declaration={})
        return candidate, roots, files, paths, create
    checks = []
    c, roots, files, paths, make = fixture(); x = make(); first = next(iter(files))
    need(x.read(first) == b'\1'*4 and x.identity(first) == files[first] and x.logical(x.path(first)) == first, 'same logical/physical identity')
    need(x.finish()['files'] == 3, 'batch file identity')
    checks.append('same_fd_read_hash_and_bidirectional_identity')
    for name in ('../escape', '/tmp/input', 'work//x', './work/x', 'work/qwen2_recovered_inputs/typed/missing.bin', 'work/qwen2_recovered_inputs_extra/a.bin'):
        reject(lambda name=name: x.path(name))
    reject(lambda: x.logical(c/'missing'))
    checks.append('unknown_absolute_escape_and_noncanonical_logical_rejected')
    c, roots, files, paths, make = fixture(); target = next(iter(paths.values())); alias = target.with_name('alias.bin'); alias.symlink_to(target)
    name = next(iter(files)); paths[name] = alias
    files['work/qwen2_recovered_inputs/typed/alias.bin'] = files[name]
    reject(make); checks.append('symlink_file_rejected')
    c, roots, files, paths, make = fixture(); target = next(iter(paths.values())); os.link(target, target.with_name('hardlink.bin'))
    reject(make); checks.append('hardlink_nlink_rejected')
    c, roots, files, paths, make = fixture(); alias = c.parent/'alias'; alias.symlink_to(Path(roots[module.PREFIXES[0]])); roots[module.PREFIXES[0]] = str(alias)
    reject(make); checks.append('symlink_root_rejected')
    c, roots, files, paths, make = fixture(); name = next(iter(files)); files[name]['bytes'] = True
    reject(make); checks.append('strict_pin_types_rejected')
    c, roots, files, paths, make = fixture(); name = next(iter(files)); files[name]['sha256'] = '0'*64
    x = make(); reject(lambda: x.identity(name)); checks.append('wrong_content_pin_rejected')
    c, roots, files, paths, make = fixture(); x = make(); name = next(iter(files)); paths[name].write_bytes(b'xxxx')
    reject(lambda: x.read(name)); reject(x.finish); checks.append('drift_after_inventory_before_open_rejected')
    c, roots, files, paths, make = fixture(); x = make(); name = next(iter(files)); target = paths[name]; original_open = module.os.open
    def replacing_open(path, flags, *a, **kw):
        replacement = target.with_name('replacement.bin'); replacement.write_bytes(b'\1'*4); replacement.replace(target)
        return original_open(path, flags, *a, **kw)
    module.os.open = replacing_open
    try: reject(lambda: x.identity(name))
    finally: module.os.open = original_open
    checks.append('stat_open_replacement_rejected')
    c, roots, files, paths, make = fixture(); x = make(); name = next(iter(files)); target = paths[name]; original_fdopen = module.os.fdopen
    class MutatingReader:
        def __init__(self, fd, *a, **kw): self.stream = original_fdopen(fd, *a, **kw); self.changed = False
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def fileno(self): return self.stream.fileno()
        def read(self, count):
            raw = self.stream.read(count)
            if not self.changed:
                self.changed = True; target.write_bytes(b'xxxx')
            return raw
    module.os.fdopen = MutatingReader
    try: reject(lambda: x.identity(name))
    finally: module.os.fdopen = original_fdopen
    checks.append('during_same_fd_read_drift_rejected')
    c, roots, files, paths, make = fixture(); x = make(); name = next(n for n in files if '.f32le' in n); calls = []; original_open = module.os.open
    def record_open(*args, **kw): calls.append(args[0]); return original_open(*args, **kw)
    module.os.open = record_open
    try:
        need(x.stat_reference(name)['payload_opened'] is False, 'stat boundary')
        reject(lambda: x.read(name)); need(not calls, 'reference before-seal must not open')
        need(x.read(name, reference_opened=True) == b'\3'*4 and len(calls) == 1, 'explicit low-level opened state')
    finally: module.os.open = original_open
    checks.append('reference_stat_only_and_explicit_read_state')
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
        reject(lambda raw=raw: module.parse(raw))
    checks.append('duplicate_and_nonfinite_metadata_rejected')
    # A final fixture installs the real permanent hook. It is deliberately
    # retained under output; tests never request deletion of protected files.
    c, roots, _, _, _ = fixture()
    # Replace this unused small fixture with a genuine76-item declaration.
    inp, ref = (Path(roots[k]) for k in module.PREFIXES)
    names = ([module.PREFIXES[0]+'/typed/r'+str(i)+'.bin' for i in range(14)] +
             [module.PREFIXES[0]+'/raw/r'+str(i)+'.bin' for i in range(13)] +
             [module.REFERENCE_PREFIX+'r'+str(i)+'.f32le' for i in range(29)] +
             [module.REFERENCE_PREFIX+'mask.bf16le'] +
             [module.PREFIXES[0]+'/ARTIFACTS.json'] +
             [module.REFERENCE_PREFIX+'m'+str(i)+'.json' for i in range(12)] +
             [module.PREFIXES[1]+'/proof/p'+str(i)+'.json' for i in range(6)])
    files, paths = {}, {}
    for i, name in enumerate(names):
        prefix = next(k for k in module.PREFIXES if name.startswith(k+'/'))
        path = Path(roots[prefix])/name[len(prefix)+1:]
        raw = bytes([i+1])*4; path.write_bytes(raw); paths[name] = path; files[name] = pin(raw)
    copies = json.dumps(dict(files=files)).encode(); (c/'contract').mkdir()
    (c/module.COPY_FILE).write_bytes(copies)
    declaration = dict(schema=module.SCHEMA, roots=roots, files=files,
                       copy_manifest=pin(copies), read_only=True, copy_payloads=False)
    raw = json.dumps(declaration).encode(); (c/module.LAYOUT_FILE).write_bytes(raw)
    manifest = dict(preparation_files={module.COPY_FILE:pin(copies),module.LAYOUT_FILE:pin(raw)})
    manifest_raw = json.dumps(manifest).encode(); (c/'SOURCE_MANIFEST.json').write_bytes(manifest_raw)
    bad = copy.deepcopy(manifest); bad['preparation_files'][module.LAYOUT_FILE]['sha256'] = '0'*64
    reject(lambda: module.load(c,bad))
    oldenv = os.environ.get('QWEN2_FIXED93_SOURCE_MANIFEST_SHA256')
    os.environ['QWEN2_FIXED93_SOURCE_MANIFEST_SHA256'] = '0'*64
    reject(lambda: module.load(c))
    if oldenv is None: del os.environ['QWEN2_FIXED93_SOURCE_MANIFEST_SHA256']
    else: os.environ['QWEN2_FIXED93_SOURCE_MANIFEST_SHA256'] = oldenv
    x = module.load(c,manifest)
    need(len(x.files)==76 and sum(x.is_reference(n) for n in x.files)==30,'real load exact76/30')
    checks.append('real_pinned_layout_load_exact76_and_wrong_manifest_pin_rejection')
    target = next(iter(paths.values()))
    readonly = target.read_bytes()
    for op in (lambda: target.write_bytes(b'xxxx'), lambda: os.unlink(target),
               lambda: os.rename(target, c/'moved'), lambda: os.link(target, c/'alias'),
               lambda: os.rename(c.parent, output/'moved_parent'),
               lambda: os.symlink('../inputs/typed/r0.bin', c/'symlink'),
               lambda: (Path(roots[module.PREFIXES[0]])/'unknown.bin').write_bytes(b'x')):
        reject(op)
    need(target.read_bytes() == readonly, 'write guard changed data')
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        relative_write_probe['name'] = target.name
        try: reject(lambda: os.open(target.name, os.O_WRONLY, dir_fd=fd))
        finally: relative_write_probe['name'] = None
        reject(lambda: os.unlink(target.name, dir_fd=fd))
        reject(lambda: os.rename(target.name, 'renamed.bin', src_dir_fd=fd, dst_dir_fd=fd))
        reject(lambda: os.link(target.name, 'linked.bin', src_dir_fd=fd, dst_dir_fd=fd))
    finally: os.close(fd)
    checks.append('real_permanent_write_mutation_parent_and_dirfd_guard')
    need(before == pin(source.read_bytes()) and not denied, 'source drift or denied external boundary')
    result = dict(status='PASS_SYNTHETIC_RESOLVER_CONTROLS_ONLY', groups=len(checks), checks=checks,
                  resolver=before, elapsed_seconds=time.monotonic()-start,
                  maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  denied_boundary_attempts=denied, native_executed=False, DUT_executed=False,
                  real_frozen_inputs_read=False, real_preflight_executed=False, actual_authorized=False)
    (output/'RESULT.json').write_text(json.dumps(result, indent=2)+'\n')
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True); args = p.parse_args()
    print(json.dumps(run(args.output), sort_keys=True))
