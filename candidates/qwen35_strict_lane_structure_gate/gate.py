"""Bounded structural preflight of one frozen, previously qualified CHIRRTL."""
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

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'qwen35_strict_lane_chirrtl'
TOP = 'StrictFp32MatrixLane'
MAX_BYTES = 1024 * 1024


def need(ok, why):
    if not ok:
        raise ValueError(why)


def bounded_runtime():
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'run with python -I -S -B')
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    def timeout(*_):
        raise TimeoutError('10 second structural preflight deadline')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 10)
    def audit(event, args):
        if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
            raise RuntimeError('no process or network allowed')
    sys.addaudithook(audit)


def read(path, pin=None):
    path = Path(path)
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_size <= MAX_BYTES, 'bounded regular file required')
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    with path.open('rb') as f:
        need(stamp(st) == stamp(os.fstat(f.fileno())), 'file changed before read')
        raw = f.read(MAX_BYTES + 1)
        need(stamp(st) == stamp(os.fstat(f.fileno())) == stamp(path.lstat()), 'file changed during read')
    need(len(raw) <= MAX_BYTES, 'file exceeds bound')
    if pin is not None:
        need({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} == pin, 'file pin mismatch: ' + path.name)
    return raw


def load():
    pins = json.loads(read(HERE / 'PINS.json'))
    raw = read(PREVIOUS / 'run_chirrtl.py', pins['parser'])
    tree = ast.parse(raw)
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'need', 'validate_ir'}]
    need(len(selected) == 2, 'exact existing parser functions')
    ns = {'re': re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), 'pinned_existing_parser', 'exec', dont_inherit=True), ns)
    scope = json.loads(read(PREVIOUS / 'IR_SCOPE.json', pins['scope']))
    qualification = json.loads(read(PREVIOUS / 'SUMMARY.json', pins['qualification_summary']))
    need(qualification['actual']['IR']['sha256'] == pins['ir']['sha256'], 'qualification IR binding')
    return pins, scope, ns['validate_ir']


def structure(raw, scope, parser, annotations=None):
    """Narrow existing parser, NOT a general FIRRTL parser or simulator."""
    need(len(raw) <= MAX_BYTES, 'IR size bound')
    # Do not silently discard annotation inputs: this lane admits no annotations.
    if annotations is not None:
        need(len(annotations) <= MAX_BYTES, 'annotation size bound')
        need(json.loads(annotations) == [], 'nonempty or unsupported annotations forbidden')
    need('blackbox' not in raw.decode('utf-8').lower(), 'blackbox marker forbidden')
    result = parser(raw, scope)
    edges = result['module_edges']
    visited, active = set(), set()
    def visit(name):
        need(name in edges, 'undefined instance target')
        need(name not in active, 'instance cycle')
        need(name not in visited, 'module instantiated more than once')
        active.add(name)
        instance_names = set()
        for inst, target in edges[name]:
            need(inst not in instance_names, 'duplicate instance name')
            instance_names.add(inst)
            visit(target)
        active.remove(name)
        visited.add(name)
    visit(TOP)
    need(visited == set(edges) and len(visited) == 9, 'all and only nine modules reachable')
    need(result['instance_count'] == 8, 'exact eight edges')
    # Existing grammar verifies complete port type, direction and operand identities.
    need(scope['variable_mul_operands'] == ['io.mulAddA', 'io.mulAddB'], 'operand scope')
    need(scope['module_ports']['HeteroBF16FmaMul'] == [
        'output io : { flip mulAddA : UInt<24>, flip mulAddB : UInt<24>, flip mulAddC : UInt<48>, mulAddResult : UInt<49>}'], '24x24 operand types')
    result.update(reachable_modules=sorted(visited), all_reachable_once=True,
                  variable_mul_operand_bits=[24, 24], extmodule_count=0, intmodule_count=0,
                  blackbox_markers=0, annotation_scope='absent; no external annotation claim' if annotations is None else 'explicit empty JSON array')
    return result


def qualify(work, annotations_path=None):
    pins, scope, parser = load()
    work = Path(work)
    receipts = {n: json.loads(read(work / n, pin)) for n, pin in pins['qualification_receipts'].items()}
    elab = receipts['ELABORATION_RESULT.json']
    need(elab['fir_sha256'] == pins['ir']['sha256'] and elab['sources_bound'] is True,
         'prior source/class qualification reference')
    raw = read(work / 'ir' / (TOP + '.fir'), pins['ir'])
    annotations = read(annotations_path) if annotations_path is not None else None
    result = structure(raw, scope, parser, annotations)
    return {'status': 'PASS_EXISTING_IR_STRUCTURAL_PREFLIGHT_ONLY', 'ir': pins['ir'],
            'qualification_references': pins, 'structure': result,
            'new_elaboration_executed': False, 'JVM_executed': False, 'RTL_executed': False,
            'new_runner_same_circuit_proven': False,
            'not_proven': ['hardware arithmetic or flags', 'handshake', 'new test elaboration identity',
                           'physical multiplier mapping, area or Fmax', 'full array integration']}


def main():
    bounded_runtime()
    need(2 <= len(sys.argv) <= 3, 'usage: gate.py EXISTING_QUALIFIED_WORK [ANNOTATIONS_JSON]')
    print(json.dumps(qualify(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
