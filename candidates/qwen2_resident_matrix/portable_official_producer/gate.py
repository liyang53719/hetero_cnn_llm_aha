"""New-profile M16 outer provenance gate; no provisioning or producer launcher.

This module does not grant numerical/consumer acceptance. A future reviewed
supervisor owns child creation. It must use the exact original generated runner,
then call the original run_gate(..., small_gate=...) in the new M128 child. That
function independently revalidates every M16 array against current embeddings.
The live ParentAttempt below cannot be restored from an archived PASS receipt.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import struct
import subprocess
import time

from ..raw_kv_native_qk_run import phase
from ..raw_kv_native_qk_run import dispatch_diagnostic as diagnostic

PROFILE = 'qwen2-official-bf16-consumer-host-v1'
ORIGINAL = 'scripts/qwen2_layer0_model_gate.py'
ORIGINAL_SHA = '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'
RUNNER_SHA = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
SOURCE_MANIFEST_SHA = '4e0f86922cdc268f245aa0105e03fbae617add5da8b3609e3799b12ca72943b8'
CONTRACT_SHA = '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'
PAYLOAD_PIN_SHA = '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'
INPUT_M16_SHA = '271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c'
ISA_OVERRIDES = ('ATEN_CPU_CAPABILITY', 'ONEDNN_MAX_CPU_ISA', 'DNNL_MAX_CPU_ISA',
    'ONEDNN_CPU_ISA_HINTS', 'DNNL_CPU_ISA_HINTS', 'MKL_ENABLE_INSTRUCTIONS',
    'OPENBLAS_CORETYPE', 'NPY_DISABLE_CPU_FEATURES')
THREAD_KEYS = ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')
MAX_JSON = 1024 * 1024
# Imported executable helpers and files read by those helpers. The 350-file map
# is historical provenance; these six files are the existing execution closure
# for THIS metadata gate. Recipes/provisioning have separate future selections.
EXECUTING_SOURCE = {
    ORIGINAL: ORIGINAL_SHA,
    'spec/numerical_contract.md': CONTRACT_SHA,
    'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/phase.py': '80260ac9b2f389c7a320d60242a1b777cd23733b9348616c315e7d151365cdef',
    'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/dispatch_diagnostic.py': '03dd92ac8f3b4488a447cb11c5bd92dca6de93d2f34cbf7ae0f943fb46cac958',
    'candidates/qwen2_resident_matrix/raw_kv_native_qk/kernel.py': 'b99d9fb204ae37a466934fcfcba6944aef0ecfeeb902a4061267d528775e10f2',
    'candidates/qwen2_resident_matrix/raw_kv_native_qkv/kernel.py': '7ad23b2989b4c84bc4d8bfd443aaea8161f6e315db72d6d20a0692906b3eb28e',
}
IMPORTED_MODULE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok, reason):
    if not ok:
        raise ValueError('portable producer: ' + reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def same(a, b):
    return encoded(a) == encoded(b)


def strict_json(raw):
    need(type(raw) is bytes and len(raw) <= MAX_JSON, 'JSON bound')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('portable producer: nonfinite JSON')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    # Exponent overflow (1e999) does not go through parse_constant.
    encoded(value)
    return value


def safe_file(path, *, limit=MAX_JSON):
    """No symlink components, aliases, special files, or changing reads."""
    path = Path(path).absolute()
    need(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink path')
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
         'file type, alias, or size')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        need((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'open race')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'changing file')
    need(len(raw) == before.st_size and len(raw) <= limit, 'short or oversized read')
    return raw


def exclusive_json(path, value):
    raw = encoded(value)
    need(len(raw) <= MAX_JSON, 'receipt bound')
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return sha(raw)


def verify_sources(root, source_map):
    root = Path(root).resolve()
    need(type(source_map) is dict and len(source_map) == 350 and
         sha(encoded(source_map)) == SOURCE_MANIFEST_SHA, 'original source closure')
    need(root == phase.ROOT.resolve(), 'helpers must come from selected closure')
    for name, expected in source_map.items():
        need(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts
             and digest(expected), 'source map entry')
    for name, expected in EXECUTING_SOURCE.items():
        need(sha(safe_file(root / name, limit=8 * MAX_JSON)) == expected, 'source drift: ' + name)
    need(sha(safe_file(__file__)) == IMPORTED_MODULE_SHA, 'new gate module changed')
    return SOURCE_MANIFEST_SHA


def verify_runner(root, path):
    original = safe_file(Path(root) / ORIGINAL)
    generated = safe_file(path)
    need(sha(original) == ORIGINAL_SHA and sha(generated) == RUNNER_SHA, 'runner source identity')
    def functions(raw):
        return {n.name: n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef)}
    before, after = functions(original), functions(generated)
    for name in ('native_forward', 'runtime_identity', 'validate_small_gate', 'compare',
                 'stage_verdict', 'expected_shapes', 'audit_semantics'):
        need(ast.dump(before[name]) == ast.dump(after[name]), 'original function drift: ' + name)
    need(ast.get_source_segment(original.decode(), before['native_forward']) ==
         ast.get_source_segment(generated.decode(), after['native_forward']), 'official forward bytes changed')
    return RUNNER_SHA


def environment():
    need(not any(k in os.environ for k in ISA_OVERRIDES), 'ISA override present')
    return {k: os.environ.get(k) for k in THREAD_KEYS}


def host_identity():
    """Local host/boot identity, not a guessed CPU ISA or remote host assertion."""
    need(os.uname().sysname == 'Linux' and os.uname().machine == 'x86_64', 'host family')
    boot = Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    need(len(boot) == 36, 'boot observation unavailable')
    return dict(host_sha256=sha(os.uname().nodename.encode()), boot_sha256=sha(boot),
                machine='x86_64', system='Linux')


def validate_identity(identity):
    keys = {'python', 'torch', 'numpy', 'transformers', 'device', 'attention', 'model_revision',
        'forward_revision', 'source_sha256', 'installed_sources_verified_exact', 'torch_build',
        'numpy_build', 'cache_utils_sha256', 'mask_utils_sha256', 'activations_sha256',
        'runner_sha256', 'independent_qkv_recipe'}
    need(type(identity) is dict and set(identity) == keys, 'runtime identity inventory')
    fixed = dict(python='3.12.15', torch='2.10.0+cpu', numpy='2.3.5', transformers='4.40.1',
        device='cpu', attention='eager', model_revision='ba1cf1846d7df0a0591d6c00649f57e798519da8',
        forward_revision='9fe3f585bb4ea29f209dc705d269fbe292e1128f',
        installed_sources_verified_exact=True, runner_sha256=RUNNER_SHA)
    need(all(same(identity[k], v) for k, v in fixed.items()), 'runtime profile')
    for name in ('cache_utils_sha256', 'mask_utils_sha256', 'activations_sha256'):
        need(digest(identity[name]), 'helper hash')
    for name in ('torch_build', 'numpy_build'):
        need(type(identity[name]) is str and 0 < len(identity[name].encode()) <= 65536, 'build identity')
    tree = ast.parse(safe_file(phase.ROOT / ORIGINAL))
    expected = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'SOURCE_HASHES' for t in n.targets)))
    need(same(identity['source_sha256'], expected), 'official installed sources')
    return sha(encoded(identity))


def check_m16_metadata(result, *, identity, source_map, library, qkv_library, payload_sha):
    """Original source-bound 29-stage/9-semantics projection; no arrays loaded."""
    validate_identity(identity)
    need(same(result.get('identity'), identity), 'same actual runtime identity')
    need(result.get('model_id') == 'Qwen/Qwen2-1.5B-Instruct', 'model identity')
    need(same(result.get('blas_environment'), environment()), 'thread environment')
    need(result.get('input') ==
        'genuine checkpoint embedding rows for explicit sequential token IDs, no tokenizer/template', 'input policy')
    need(result.get('manifest_whole_checkpoint_hash_verified') is False, 'checkpoint claim')
    for mode in ('bf16', 'fp32'):
        stage = result['modes'][mode]['phases'][0]['stages']
        need(stage['x']['actual_f32_sha256'] == INPUT_M16_SHA and
             stage['x']['reference_f32_sha256'] == INPUT_M16_SHA, 'official embedding rows')
        for name, item in stage.items():
            dtype = 'torch.bfloat16' if mode == 'bf16' and name != 'softmax_fp32' else 'torch.float32'
            need(item.get('actual_storage_dtype') == dtype and digest(item.get('actual_storage_sha256')), 'storage type')
            for k in ('shape', 'native_export_shape', 'independent_export_shape'):
                need(type(item.get(k)) is list and all(type(v) is int and v > 0 for v in item[k]), 'shape types')
    report = phase.project_result(result, tokens=16, result_sha256=sha(encoded(result)),
        source_sha256=source_map, contract_sha256=CONTRACT_SHA, generated_module_sha256=RUNNER_SHA,
        library=library, qkv_library=qkv_library, payload_manifest_sha256=payload_sha)
    need(report['native_acceptance'] is True, 'original M16 numerical report failed')
    return report


def check_dispatch(observations):
    """Preserve exact observed dispatch, including an explicitly unobserved state.

    This is a producer observation policy only, never consumer acceptance or an
    ISA-equivalence statement. Unsupported execution/truncation is rejected.
    """
    need(type(observations) is dict and set(observations) == {'bf16', 'fp32'}, 'dispatch inventory')
    for item in observations.values():
        diagnostic.validate_verbose(item)
        need(item['status'] in ('COMPLETE_DIAGNOSTIC', 'NO_ONEDNN_EXECUTION_OBSERVED') or
             diagnostic.has_only_informational_unknowns(item), 'incomplete dispatch execution')
    bf16 = observations['bf16']
    if bf16['status'] != 'NO_ONEDNN_EXECUTION_OBSERVED':
        need(bf16['exec_records'] == 9, 'BF16 execution inventory')
        roles = {}
        for record in bf16['records']:
            need(record['primitive'] == 'matmul' and
                 all(record['descriptors'].get(k, {}).get('dtype') == 'bf16' for k in ('src', 'wei', 'dst')),
                 'BF16 execution kind or dtype')
            roles[record['role']] = roles.get(record['role'], 0) + record['count']
        need(roles == dict(QKV_KV=2, DENSE_HIDDEN=2, MLP=3, QK=1, PV=1), 'M16 observed execution roles')
    return json.loads(encoded(observations))


def owned_child_identity(pid):
    base = Path('/proc') / str(pid)
    raw_stat = (base / 'stat').read_text()
    fields = raw_stat[raw_stat.rfind(')') + 2:].split()
    need(len(fields) >= 20 and int(fields[1]) == os.getpid(), 'kernel child ownership')
    return dict(pid=pid, parent_pid=int(fields[1]), start_ticks=int(fields[19]))


def observe_owned_child(pid, command):
    """Observe kernel parent, start tick, and argv; never trust Popen.args alone.

    This proves only the currently observed process, not that it will never exec
    again or that an unreviewed driver executed the original producer. That
    ownership/source continuity remains a required future supervisor boundary.
    """
    base = Path('/proc') / str(pid)
    identity = owned_child_identity(pid)
    argv = (base / 'cmdline').read_bytes()
    need(argv == b'\x00'.join(x.encode() for x in command) + b'\x00', 'kernel command observation')
    need(same(owned_child_identity(pid), identity), 'child changed during command observation')
    return dict(**identity, command_sha256=sha(encoded(command)))


def check_export_scalars(result, directory):
    """Check actual file inventory/hashes plus finite and BF16 storage boundaries.

    This deliberately does not replace the original array-based small gate.
    """
    phase.verify_exports(result, directory, 16)
    inventory = {}
    for mode in ('bf16', 'fp32'):
        stages = result['modes'][mode]['phases'][0]['stages']
        for name, entry in stages.items():
            for kind in ('native', 'independent'):
                relative = entry[kind + '_file']
                raw = safe_file(Path(directory) / relative, limit=8 * MAX_JSON)
                need(sha(raw) == entry[kind + '_file_sha256'], 'export changed')
                for (word,) in struct.iter_unpack('<I', raw):
                    need(word & 0x7f800000 != 0x7f800000, 'nonfinite exported value')
                    if mode == 'bf16' and name != 'softmax_fp32':
                        need(word & 0xffff == 0, 'BF16 exported storage drift')
                inventory[relative] = dict(sha256=sha(raw), bytes=len(raw))
    need(len(inventory) == 116, 'complete export inventory')
    return inventory


class ParentAttempt:
    """Live supervisor-owned fresh attempt; archived JSON cannot resume it.

    command is the exact command selected by a future reviewed supervisor. This
    module does not create that command, start it, approve it, or authorize it.
    The process handle stays in the parent. Plain booleans/exit integers are not
    accepted as observations. Caller-supplied command/identity remain trusted
    integration inputs until a separately reviewed supervisor binds them to the
    real runtime_identity/Recipe/payload APIs. No such integration ships here.
    """
    def __init__(self, directory, *, root, source_map, runner, identity, payload_sha,
                 payload_tensor_map_sha, library, qkv_library, command, deadline_ns):
        self.root = Path(root).resolve()
        self.source_map = strict_json(encoded(source_map))
        verify_sources(self.root, self.source_map)
        verify_runner(self.root, runner)
        self.runner = Path(runner)
        self.identity = strict_json(encoded(identity))
        validate_identity(self.identity)
        need(all(digest(x) for x in (payload_sha, payload_tensor_map_sha)), 'payload identity')
        need(type(command) is list and command and all(type(x) is str and x and '\x00' not in x for x in command), 'exact command')
        need(type(deadline_ns) is int and time.monotonic_ns() < deadline_ns <= time.monotonic_ns() + 900 * 10**9, 'deadline')
        self.directory = Path(directory).absolute()
        need(not self.directory.exists() and not self.directory.is_symlink(), 'fresh directory required')
        need(all(not p.is_symlink() for p in self.directory.parents), 'directory symlink')
        self.directory.mkdir(mode=0o700)
        self.command = list(command)
        self.library, self.qkv_library = strict_json(encoded(library)), strict_json(encoded(qkv_library))
        need(same(self.identity['independent_qkv_recipe'], phase.combined_identity(library, qkv_library)), 'recipe identity')
        self.challenge = dict(schema=1, profile=PROFILE, attempt_nonce=secrets.token_hex(32),
            created_ns=time.monotonic_ns(), deadline_ns=deadline_ns, host=host_identity(),
            created_boot_ticks=time.clock_gettime_ns(time.CLOCK_BOOTTIME) * os.sysconf('SC_CLK_TCK') // 10**9,
            parent_pid=os.getpid(), source_manifest_sha256=SOURCE_MANIFEST_SHA,
            gate_dependencies_sha256=sha(encoded(EXECUTING_SOURCE)), gate_module_sha256=IMPORTED_MODULE_SHA,
            runner_sha256=RUNNER_SHA, runtime_identity_sha256=sha(encoded(self.identity)),
            payload_manifest_sha256=payload_sha, payload_tensor_map_sha256=payload_tensor_map_sha,
            payload_pin_sha256=PAYLOAD_PIN_SHA, contract_sha256=CONTRACT_SHA,
            input_policy=dict(batch=1, tokens=16, past_tokens=0, carried=False,
                token_ids=list(range(16)), position_ids=list(range(16)),
                embedding_rows_sha256=INPUT_M16_SHA, intermediate_preloads=0),
            command_sha256=sha(encoded(command)), blas_environment=environment())
        self.challenge_sha = exclusive_json(self.directory / 'ATTEMPT.json', self.challenge)
        self.process = None
        self.receipt_sha = None
        self.consumed = False

    def _current(self):
        need(os.getpid() == self.challenge['parent_pid'], 'only original parent may admit')
        need(time.monotonic_ns() < self.challenge['deadline_ns'], 'stale attempt')
        need(same(host_identity(), self.challenge['host']), 'host or boot changed')
        need(same(environment(), self.challenge['blas_environment']), 'environment changed')
        need(sha(safe_file(self.directory / 'ATTEMPT.json')) == self.challenge_sha, 'changed attempt')
        verify_sources(self.root, self.source_map)
        verify_runner(self.root, self.runner)

    def bind_started_child(self, process):
        """Bind one still-unreaped handle, immediately after supervisor launch."""
        self._current()
        need(self.process is None and self.receipt_sha is None, 'already bound')
        need(not (self.directory / 'native16').exists() and
             not (self.directory / 'native16').is_symlink(), 'preexisting M16 evidence')
        need(type(process) is subprocess.Popen and process.returncode is None and
             type(process.pid) is int and process.pid > 0 and same(process.args, self.command), 'child handle/command')
        self.ownership = observe_owned_child(process.pid, self.command)
        need(self.ownership['start_ticks'] >= self.challenge['created_boot_ticks'], 'preexisting child')
        self.process = process
        self.bound_ns = time.monotonic_ns()
        self.bound_wall_ns = time.time_ns()

    def observe_m16_exit(self, result_path, dispatch):
        """Wait for the exact bound child; only then fsync a durable receipt.

        No process is launched here. Nonzero exit, timeout, incomplete/changed
        outputs or failed original report leaves no usable completion receipt.
        """
        self._current()
        need(self.process is not None and self.receipt_sha is None, 'unbound or repeated wait')
        need(same(owned_child_identity(self.process.pid),
                  {k: self.ownership[k] for k in ('pid', 'parent_pid', 'start_ticks')}), 'child identity changed before wait')
        timeout = (self.challenge['deadline_ns'] - time.monotonic_ns()) / 1e9
        observed = self.process.wait(timeout=max(0, timeout))
        need(type(observed) is int and observed == 0 and self.process.returncode == 0, 'observed child exit not zero')
        result_path = Path(result_path).absolute()
        need(result_path == self.directory / 'native16' / 'RESULT.json', 'fresh M16 result location')
        need(result_path.stat().st_mtime_ns >= self.bound_wall_ns and
             result_path.stat().st_ctime_ns >= self.bound_wall_ns, 'stale M16 evidence')
        raw = safe_file(result_path)
        result = strict_json(raw)
        check_m16_metadata(result, identity=self.identity, source_map=self.source_map,
            library=self.library, qkv_library=self.qkv_library,
            payload_sha=self.challenge['payload_manifest_sha256'])
        inventory = check_export_scalars(result, result_path.parent)
        dispatch = check_dispatch(dispatch)
        self._current()
        need(sha(safe_file(result_path)) == sha(raw), 'result changed during observation')
        receipt = dict(schema=1, profile=PROFILE, status='OBSERVED_M16_ZERO_EXIT',
            attempt_sha256=self.challenge_sha, attempt_nonce=self.challenge['attempt_nonce'],
            child_pid=self.process.pid, bound_ns=self.bound_ns, observed_ns=time.monotonic_ns(),
            ownership=self.ownership,
            command_observation='AT_BIND_ONLY_SOURCE_CONTINUITY_UNPROVEN',
            observed_exit_code=observed, wait_completed=True, command_sha256=self.challenge['command_sha256'],
            result_sha256=sha(raw), exports=inventory, dispatch=dispatch,
            runtime_identity_sha256=self.challenge['runtime_identity_sha256'],
            source_manifest_sha256=SOURCE_MANIFEST_SHA,
            numerical_acceptance=False, consumer_acceptance=False, original_revalidation_required=True)
        self.receipt_sha = exclusive_json(self.directory / 'OBSERVED_EXIT.json', receipt)
        return self.receipt_sha

    def m128_prerequisites(self, *, current_identity, payload_sha, payload_tensor_map_sha):
        """Consume this live attempt once and require original small-gate replay.

        The return value is a prerequisite binding, NOT an execution permit or
        numerical PASS. An actual M128 run remains closed until a reviewed
        supervisor invokes original run_gate with this exact small-gate path.
        """
        self._current()
        need(not self.consumed and self.receipt_sha is not None, 'missing fresh observed exit or reused admission')
        validate_identity(current_identity)
        need(same(current_identity, self.identity), 'current runtime differs')
        need(payload_sha == self.challenge['payload_manifest_sha256'] and
             payload_tensor_map_sha == self.challenge['payload_tensor_map_sha256'], 'current payload differs')
        raw = safe_file(self.directory / 'OBSERVED_EXIT.json')
        need(sha(raw) == self.receipt_sha, 'changed observed-exit receipt')
        receipt = strict_json(raw)
        need(receipt['attempt_sha256'] == self.challenge_sha and
             receipt['attempt_nonce'] == self.challenge['attempt_nonce'] and
             receipt['observed_exit_code'] == 0 and type(receipt['observed_exit_code']) is int and
             receipt['wait_completed'] is True and
             self.challenge['created_ns'] <= receipt['bound_ns'] <= receipt['observed_ns'] < self.challenge['deadline_ns'],
             'outer observation binding')
        path = self.directory / 'native16' / 'RESULT.json'
        result_raw = safe_file(path)
        need(sha(result_raw) == receipt['result_sha256'], 'changed M16 result')
        result = strict_json(result_raw)
        check_m16_metadata(result, identity=current_identity, source_map=self.source_map,
            library=self.library, qkv_library=self.qkv_library, payload_sha=payload_sha)
        need(same(check_export_scalars(result, path.parent), receipt['exports']), 'changed/missing exports')
        check_dispatch(receipt['dispatch'])
        self._current()
        need(sha(safe_file(path)) == receipt['result_sha256'] and
             sha(safe_file(self.directory / 'OBSERVED_EXIT.json')) == self.receipt_sha, 'final receipt drift')
        self.consumed = True
        return dict(profile=PROFILE, status='OUTER_BINDING_VALID_ORIGINAL_REVALIDATION_REQUIRED',
            small_gate=path, m16_result_sha256=receipt['result_sha256'],
            observed_exit_receipt_sha256=self.receipt_sha,
            execution_authorized=False, numerical_acceptance=False, consumer_acceptance=False,
            old_pass_inherited=False, backend_order_proven=False)


def production_launch(*args, **kwargs):
    raise RuntimeError('source-only proposal: provisioning and production launch are closed')
