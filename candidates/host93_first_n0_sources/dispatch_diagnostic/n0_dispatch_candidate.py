"""Independent N0 dispatch diagnostic candidate. Source-only unless --execute.

The original frozen AVX512 reference worker/PINS/PASS gate remain unchanged.
Observe natural dispatch before thread setters; never set an ISA override or
load a profile. Only two fixed observed-capability/build pairs permit forward.
Dual frozen output identities are hard gates, but never reference acceptance.
The external supervisor owns process-tree RSS, wall, logs and cleanup.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time

PINS_BYTES = 6364
PINS_SHA256 = 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8'
F32_BYTES = 786432
F32_SHA256 = '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'
BF16_BYTES = 393216
BF16_SHA256 = 'bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2'
CODES = frozenset(('FLAGS','PATH','FILE','SIZE','SHA','CHANGED','SOURCE','INPUT',
    'RUNTIME','DISPATCH','DEADLINE','RESOURCE','OUTPUT','HASH_MISMATCH','UNEXPECTED'))

class Rejected(ValueError):
    def __init__(self, code):
        assert code in CODES
        self.code = code
        super().__init__(code)

def need(ok, code):
    if not ok:
        raise Rejected(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def path(value):
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and p.resolve() == p and
         not any(x.is_symlink() for x in (p, *p.parents)), 'PATH')
    return p

def read_checked(value, pin, *, retain=True):
    """Stream a fixed regular file; reject links, growth, identity or content drift."""
    p = path(value)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode), 'FILE')
        need(before.st_size == pin['bytes'], 'SIZE')
        h, chunks, total = hashlib.sha256(), [], 0
        while True:
            b = os.read(fd, min(1048576, pin['bytes'] + 1 - total))
            if not b:
                break
            total += len(b)
            need(total <= pin['bytes'], 'SIZE')
            h.update(b)
            if retain:
                chunks.append(b)
        after = os.fstat(fd)
        fields = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(fields(before) == fields(after) == fields(p.stat()), 'CHANGED')
        need(total == pin['bytes'] and h.hexdigest() == pin['sha256'], 'SHA')
        return b''.join(chunks) if retain else {'bytes': total, 'sha256': h.hexdigest()}
    finally:
        os.close(fd)

def load_pins(pins_path):
    pins = json.loads(read_checked(pins_path, {'bytes':PINS_BYTES,'sha256':PINS_SHA256}))
    output = pins['output']
    need((output['bytes'],output['sha256'],output['native_bytes'],output['native_sha256']) ==
         (F32_BYTES,F32_SHA256,BF16_BYTES,BF16_SHA256), 'SOURCE')
    return pins

def official_node(raw, pin):
    """Select one complete unchanged original node, with source and AST pins."""
    text = raw.decode('utf8')
    matches = [n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'Qwen2RMSNorm']
    need(len(matches) == 1, 'SOURCE')
    node = matches[0]
    source = ast.get_source_segment(text, node)
    need((node.lineno,node.end_lineno) == (pin['line_start'],pin['line_end']) and
         source == pin['source'] and sha(source.encode()) == pin['source_sha256'] and
         sha(ast.dump(node,include_attributes=False).encode()) == pin['ast_sha256'], 'SOURCE')
    return node

def source_buffers(repo, pins):
    buffers = {name:read_checked(repo/name, identity) for name,identity in pins['sources'].items()}
    frozen = json.loads(buffers['candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json'])
    need(frozen['outputs']['n0'] == pins['output'], 'SOURCE')
    return buffers

def output_identity(native, widened):
    """Pure fixed denominator/identity gate. No caller-provided expected hash."""
    native_identity = {'bytes':len(native),'sha256':sha(native)}
    widened_identity = {'bytes':len(widened),'sha256':sha(widened)}
    exact_native = native_identity == {'bytes':BF16_BYTES,'sha256':BF16_SHA256}
    exact_widened = widened_identity == {'bytes':F32_BYTES,'sha256':F32_SHA256}
    return dict(native=native_identity,fp32le=widened_identity,
                native_exact=exact_native,fp32le_exact=exact_widened,
                accepted=exact_native and exact_widened)

def no_external_actions(event, args):
    if event in ('os.fork','os.forkpty','os.posix_spawn','os.exec','os.system',
                 'subprocess.Popen','socket.__new__','socket.connect','socket.getaddrinfo'):
        raise Rejected('RUNTIME')

def limits(shared_stop, spec):
    now = time.monotonic()
    need(math.isfinite(shared_stop), 'DEADLINE')
    remaining = min(spec['wall_seconds'], shared_stop - now - spec['cleanup_postflight_reserve_seconds'])
    need(remaining > 0 and signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'DEADLINE')
    need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'DEADLINE')
    def expired(*_):
        raise Rejected('DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    cpu = resource.getrusage(resource.RUSAGE_SELF)
    cap = math.ceil(cpu.ru_utime + cpu.ru_stime) + spec['cpu_seconds']
    for kind, value in ((resource.RLIMIT_CPU,cap),(resource.RLIMIT_AS,spec['address_space_bytes']),
                        (resource.RLIMIT_FSIZE,spec['private_output_bytes']),(resource.RLIMIT_CORE,0)):
        _, hard = resource.getrlimit(kind)
        value = value if hard == resource.RLIM_INFINITY else min(value,hard)
        resource.setrlimit(kind,(value,value))

def runtime_before(runtime, python, profile, pins):
    need(sys.implementation.name == 'cpython' and sys.byteorder == 'little' and
         list(sys.version_info[:len(profile['version'])]) == profile['version'], 'RUNTIME')
    need(Path(sys.executable).resolve() == python, 'RUNTIME')
    identities = {'python':read_checked(python,profile,retain=False)}
    for name,pin in pins['runtime_native_files'].items():
        if name != 'python':
            relative = pin['path'].split('site-packages/',1)[1]
            identities[name] = read_checked(runtime/relative,pin,retain=False)
    for relative,pin in pins['runtime_sources'].items():
        read_checked(runtime/relative,pin,retain=False)
    return identities

def write_new(out, name, raw):
    need(type(raw) is bytes and len(raw) <= 4194304, 'OUTPUT')
    with (out/name).open('xb') as f:
        need(f.write(raw) == len(raw), 'OUTPUT')

CAPABILITIES = ('DEFAULT', 'AVX2', 'AVX512', 'OTHER')
KNOWN_BUILDS = {
    'AVX512': '4f3cd65dc58472ed223329fa5ab743d0a360e777accb4001b511fc418c78128b',
    'AVX2': '4096ae2ff210db4a4da17fe7e5ef17c7715c4e4dc5d4175a9357b83bf820075a',
}
GATES = ('source','raw2','native','environment','import','version','capability',
         'thread','build','forward','postflight')
STAGES = ('SOURCE','RAW2','RUNTIME_IDENTITY','ENVIRONMENT','RUNTIME_IMPORT',
          'VERSION','CAPABILITY','THREAD','BUILD','OFFICIAL_N0','POSTFLIGHT','COMPLETE')
STATUSES = ('NOT_COMPLETED','CANDIDATE_HASH_MISMATCH','CANDIDATE_EXACT_MATCH')
SAFE_MARKERS = frozenset(('N0_DISPATCH_CANDIDATE_NOT_EXECUTED','CANDIDATE_EXACT_MATCH',
                         'CANDIDATE_HASH_MISMATCH:HASH_MISMATCH')) | frozenset(
                         'NOT_COMPLETED:' + code for code in CODES)
PUBLIC_KEYS = ('schema','scope','status','code','stage','expected_capability',
               'observed_capability','capability_observed','gates_reached','gates_passed',
               'full_shape_verified','hashes_checked','bf16_sha_exact','f32_sha_exact',
               'dual_sha_exact','reference_accepted','baseline_adopted','dut_executed','rtl_executed','fullblock_executed')

def finite_capability(value):
    """Never stringify or retain arbitrary observed runtime values."""
    return value if type(value) is str and value in CAPABILITIES[:3] else 'OTHER'

def allowed_build(capability):
    """Explicit diagnostic allowlist; no pins mutation or environment profile."""
    need(type(capability) is str and capability in KNOWN_BUILDS, 'DISPATCH')
    return KNOWN_BUILDS[capability]

def new_report():
    return dict(schema=1,scope='INDEPENDENT_N0_DISPATCH_CANDIDATE',
        status='NOT_COMPLETED',code='UNEXPECTED',stage='SOURCE',
        expected_capability='AVX512',observed_capability='OTHER',capability_observed=False,
        gates_reached=dict.fromkeys(GATES,False),gates_passed=dict.fromkeys(GATES,False),
        full_shape_verified=False,hashes_checked=False,bf16_sha_exact=False,
        f32_sha_exact=False,dual_sha_exact=False,reference_accepted=False,
        baseline_adopted=False,dut_executed=False,rtl_executed=False,fullblock_executed=False)

def enter_gate(report, gate, stage):
    report.update(stage=stage, gates_reached={**report['gates_reached'], gate:True})

def pass_gate(report, gate):
    report['gates_passed'][gate] = True

def public_projection(report):
    """Exact finite schema only. Reject incoherent claims before serialization."""
    need(type(report) is dict and set(PUBLIC_KEYS) <= report.keys(), 'OUTPUT')
    result = {key:report[key] for key in PUBLIC_KEYS}
    need(type(result['schema']) is int and result['schema'] == 1 and
         type(result['scope']) is str and result['scope'] == 'INDEPENDENT_N0_DISPATCH_CANDIDATE' and
         type(result['status']) is str and result['status'] in STATUSES and
         (result['code'] is None or (type(result['code']) is str and result['code'] in CODES)) and
         type(result['stage']) is str and result['stage'] in STAGES and
         type(result['expected_capability']) is str and result['expected_capability'] == 'AVX512' and
         type(result['observed_capability']) is str and result['observed_capability'] in CAPABILITIES,
         'OUTPUT')
    for key in ('capability_observed','full_shape_verified','hashes_checked',
                'bf16_sha_exact','f32_sha_exact','dual_sha_exact','reference_accepted',
                'baseline_adopted','dut_executed','rtl_executed','fullblock_executed'):
        need(type(result[key]) is bool, 'OUTPUT')
    need(not result['baseline_adopted'] and not result['dut_executed'] and
         not result['reference_accepted'] and not result['rtl_executed'] and
         not result['fullblock_executed'], 'OUTPUT')
    for key in ('gates_reached','gates_passed'):
        gates = result[key]
        need(type(gates) is dict and set(gates) == set(GATES) and
             all(type(gates[g]) is bool for g in GATES), 'OUTPUT')
        result[key] = dict(gates)
    reached, passed = result['gates_reached'],result['gates_passed']
    for index, gate in enumerate(GATES):
        need(not passed[gate] or reached[gate], 'OUTPUT')
        need(not reached[gate] or all(passed[prior] for prior in GATES[:index]), 'OUTPUT')
    need(reached['source'], 'OUTPUT')
    if result['status'] != 'CANDIDATE_EXACT_MATCH':
        last_reached = max(index for index, gate in enumerate(GATES) if reached[gate])
        need(result['stage'] == STAGES[last_reached], 'OUTPUT')
    need(not result['capability_observed'] or reached['capability'], 'OUTPUT')
    need(result['capability_observed'] or result['observed_capability'] == 'OTHER', 'OUTPUT')
    need(not passed['capability'] or (result['capability_observed'] and
         result['observed_capability'] in KNOWN_BUILDS), 'OUTPUT')
    need(not result['full_shape_verified'] or reached['forward'], 'OUTPUT')
    need(not result['hashes_checked'] or (result['full_shape_verified'] and reached['forward']), 'OUTPUT')
    need(not passed['forward'] or result['hashes_checked'], 'OUTPUT')
    need(result['hashes_checked'] or not (result['bf16_sha_exact'] or result['f32_sha_exact']), 'OUTPUT')
    need(result['dual_sha_exact'] == (result['hashes_checked'] and
         result['bf16_sha_exact'] and result['f32_sha_exact']), 'OUTPUT')
    if result['status'] == 'CANDIDATE_EXACT_MATCH':
        need(all(passed.values()) and result['dual_sha_exact'] and result['code'] is None and
             result['stage'] == 'COMPLETE', 'OUTPUT')
    elif result['status'] == 'CANDIDATE_HASH_MISMATCH':
        need(all(passed.values()) and result['hashes_checked'] and not result['dual_sha_exact'] and
             result['code'] == 'HASH_MISMATCH' and result['stage'] == 'POSTFLIGHT', 'OUTPUT')
    else:
        need(result['code'] in CODES and result['code'] != 'HASH_MISMATCH' and
             result['stage'] != 'COMPLETE', 'OUTPUT')
    return result

def validate_public_observation(value):
    """Validate an untrusted published projection; return a fresh finite copy."""
    need(type(value) is dict and set(value) == set(PUBLIC_KEYS), 'OUTPUT')
    return public_projection(value)

def receipt_projection(report):
    """A secondary projection error cannot replace the recorded primary code."""
    try:
        return public_projection(report)
    except Exception:
        code = report.get('code')
        if type(code) is str and code in CODES:
            raise Rejected(code) from None
        raise

def recover(args, pins):
    """Exactly one forward, exact original raw2/capture bindings and exports."""
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')
    need(not any(k.split('.')[0] in ('torch','numpy','transformers') for k in sys.modules), 'RUNTIME')
    limits(args.shared_stop,pins['limits'])
    repo,runtime,python = path(args.repo),path(args.runtime_root),path(args.python)
    out = path(args.out)
    need(out.parent.is_dir() and not os.path.lexists(out), 'PATH')
    out.mkdir(mode=0o700)
    report = new_report()
    try:
        enter_gate(report,'source','SOURCE')
        buffers = source_buffers(repo,pins)
        node = official_node(buffers[pins['official_class']['path']],pins['official_class'])
        pass_gate(report,'source')
        enter_gate(report,'raw2','RAW2')
        raw = {name:read_checked(getattr(args,name),pin) for name,pin in pins['raw2'].items()}
        pass_gate(report,'raw2')
        need(args.python_profile == 'ci31214', 'FLAGS')
        profile = pins['python_profiles']['ci31214']
        enter_gate(report,'native','RUNTIME_IDENTITY')
        before = runtime_before(runtime,python,profile,pins)
        report.update(source_identities=pins['sources'],input_identities=pins['raw2'],runtime_before=before,
                      python_profile=args.python_profile,runtime_requirements=pins['runtime_requirements'])
        pass_gate(report,'native')
        enter_gate(report,'environment','ENVIRONMENT')
        # Preserve every original required value and forbidden override.
        required = dict(OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',PYTHONNOUSERSITE='1')
        need(all(os.environ.get(k) == v for k,v in required.items()) and
             all(k not in os.environ for k in ('ATEN_CPU_CAPABILITY','MKL_CBWR','ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA')),
             'RUNTIME')
        pass_gate(report,'environment')
        sys.addaudithook(no_external_actions)
        sys.path.insert(0,str(runtime))
        enter_gate(report,'import','RUNTIME_IMPORT')
        import numpy as np
        import torch
        from torch import nn
        pass_gate(report,'import')
        enter_gate(report,'version','VERSION')
        expected = pins['runtime_requirements']
        need(np.__version__ == expected['numpy'] and str(torch.__version__) == expected['torch'] and
             torch.version.git_version == expected['torch_commit'], 'RUNTIME')
        pass_gate(report,'version')
        enter_gate(report,'capability','CAPABILITY')
        report.update(observed_capability=finite_capability(torch.backends.cpu.get_cpu_capability()),
                      capability_observed=True)
        candidate_build = allowed_build(report['observed_capability'])
        pass_gate(report,'capability')
        enter_gate(report,'thread','THREAD')
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        need(torch.get_num_threads() == 4 and torch.get_num_interop_threads() == 1 and
             torch.are_deterministic_algorithms_enabled(), 'RUNTIME')
        pass_gate(report,'thread')
        enter_gate(report,'build','BUILD')
        need(sha(torch.__config__.show().encode()) == candidate_build, 'RUNTIME')
        need(Path(torch._C.__file__).resolve() == runtime/'torch/_C.cpython-312-x86_64-linux-gnu.so' and
             Path(np._core._multiarray_umath.__file__).resolve() == runtime/'numpy/_core/_multiarray_umath.cpython-312-x86_64-linux-gnu.so', 'RUNTIME')
        pass_gate(report,'build')
        enter_gate(report,'forward','OFFICIAL_N0')
        namespace = {'torch':torch,'nn':nn}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(repo/pins['official_class']['path']),'exec'),namespace)
        def tensor(name):
            spec = pins['raw2'][name]
            value = torch.from_numpy(np.frombuffer(raw[name],dtype='<u2').copy()).view(torch.bfloat16).reshape(spec['shape'])
            need(value.dtype == torch.bfloat16 and list(value.shape) == spec['shape'], 'INPUT')
            return value
        x = tensor('embedding')[:128].unsqueeze(0).contiguous()
        norm = namespace['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
        norm.weight = nn.Parameter(tensor('gamma'),requires_grad=False)
        need(not norm.training and not norm.weight.requires_grad and
             sha(norm.weight.detach().contiguous().view(torch.uint8).numpy().tobytes()) == pins['raw2']['gamma']['sha256'], 'INPUT')
        with torch.inference_mode():
            n0 = norm(x)
        need(list(n0.shape) == [1,128,1536] and n0.dtype == torch.bfloat16 and
             list(n0.stride()) == [196608,1536,1] and n0.storage_offset() == 0 and
             n0.is_contiguous() and bool(torch.isfinite(n0).all()), 'OUTPUT')
        report['full_shape_verified'] = True
        data = n0.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
        native = n0.contiguous().view(torch.uint8).numpy().tobytes()
        report['output'] = output_identity(native,data)
        report.update(hashes_checked=True,bf16_sha_exact=report['output']['native_exact'],
                      f32_sha_exact=report['output']['fp32le_exact'],
                      dual_sha_exact=report['output']['accepted'])
        pass_gate(report,'forward')
        # Every tensor file stays private and explicitly candidate-named.
        if not report['output']['accepted']:
            write_new(out,'candidate.observed.n0.f32le',data)
            write_new(out,'candidate.observed.n0.bf16le',native)
        enter_gate(report,'postflight','POSTFLIGHT')
        need(source_buffers(repo,pins) == buffers, 'CHANGED')
        for name,pin in pins['raw2'].items():
            need(read_checked(getattr(args,name),pin) == raw[name], 'CHANGED')
        report['runtime_after'] = runtime_before(runtime,python,profile,pins)
        need(report['runtime_after'] == before and torch.get_num_threads() == 4 and
             torch.get_num_interop_threads() == 1 and torch.are_deterministic_algorithms_enabled(), 'CHANGED')
        need(time.monotonic() < args.shared_stop - 5, 'DEADLINE')
        pass_gate(report,'postflight')
        need(report['output']['accepted'], 'HASH_MISMATCH')
        write_new(out,'candidate.exact.n0.f32le',data)
        write_new(out,'candidate.exact.n0.bf16le',native)
        read_checked(out/'candidate.exact.n0.f32le',{'bytes':F32_BYTES,'sha256':F32_SHA256},retain=False)
        read_checked(out/'candidate.exact.n0.bf16le',{'bytes':BF16_BYTES,'sha256':BF16_SHA256},retain=False)
        report.update(status='CANDIDATE_EXACT_MATCH',code=None,stage='COMPLETE',reference_accepted=False)
    except Rejected as error:
        report.update(code=error.code,status='CANDIDATE_HASH_MISMATCH' if error.code == 'HASH_MISMATCH' else 'NOT_COMPLETED')
    except (MemoryError,TimeoutError):
        report.update(code='RESOURCE')
    except Exception:
        report.update(code='UNEXPECTED')
    finally:
        projection = receipt_projection(report)
        write_new(out,'RECEIPT.json',(json.dumps(report,sort_keys=True,indent=2)+'\n').encode())
        write_new(out,'PUBLIC_OBSERVATION.json',(json.dumps(projection,sort_keys=True,indent=2)+'\n').encode())
    return report

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('repo','embedding','gamma','runtime-root','python','out','pins'):
        ap.add_argument('--'+key)
    ap.add_argument('--python-profile',choices=('ci31214',),default='ci31214')
    ap.add_argument('--shared-stop',type=float)
    ap.add_argument('--execute',action='store_true')
    args=ap.parse_args(argv)
    if not args.execute:
        print('N0_DISPATCH_CANDIDATE_NOT_EXECUTED')
        return 0
    try:
        need(all(getattr(args,k) is not None for k in ('repo','embedding','gamma','runtime_root','python','out','pins','shared_stop')), 'FLAGS')
        report=recover(args,load_pins(args.pins))
        print(report['status'] + ('' if report['code'] is None else ':'+report['code']))
        return 0 if report['status'] == 'CANDIDATE_EXACT_MATCH' else 1
    except Rejected as error:
        print('NOT_COMPLETED:'+error.code)
    except Exception:
        print('NOT_COMPLETED:UNEXPECTED')
    return 1

if __name__ == '__main__':
    raise SystemExit(main())
