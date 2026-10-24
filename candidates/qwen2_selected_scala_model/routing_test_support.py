"""Test-only, stdlib-only extraction of unchanged production control classes.

The ScriptedService is the existing protocol test double extended for legacy
reply debts and acquisition accounting. It emits caller-selected synthetic words
and performs NO Matrix arithmetic. Nothing here is native/RTL/model evidence.
"""
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
import ast
import argparse
import hashlib
import json
import operator
from pathlib import Path
import struct
import sys
import types

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--source-root', required=True, type=Path)
_options, _remaining = _parser.parse_known_args()
sys.argv[:] = [sys.argv[0], *_remaining]
SOURCE_ROOT = _options.source_root.resolve(strict=True)
SOURCE_PACKAGE = SOURCE_ROOT / 'candidates/qwen2_resident_matrix'
HERE = Path(__file__).resolve().parent
PREFIX = '_qk16_routing_test'
EXTRACTED = {}


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def _package(name):
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return sys.modules[name]


def definitions(relative, names=None, *, environment=None, source=None, overlay=False):
    """Compile exact definition ASTs, never native-importing module preludes."""
    if overlay:
        need(Path(relative).parent == Path('production_qk16_model'), 'exact candidate module namespace')
    path = HERE / Path(relative).name if overlay else SOURCE_PACKAGE / relative
    source = path.read_text() if source is None else source
    tree = ast.parse(source, filename=str(path))
    selected = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                and (names is None or node.name in names)]
    if names is not None:
        need({node.name for node in selected} == set(names), 'missing exact definitions: ' + str(relative))
    module_name = PREFIX + '.' + str(relative).removesuffix('.py').replace('/', '.')
    module = types.ModuleType(module_name)
    module.__file__, module.__package__ = str(path), module_name.rpartition('.')[0]
    parent = module.__package__
    while parent:
        _package(parent)
        parent = parent.rpartition('.')[0]
    sys.modules[module_name] = module
    module.__dict__.update(Counter=Counter, Sequence=Sequence, dataclass=dataclass,
                           replace=replace, struct=struct, hashlib=hashlib,
                           operator=operator, Path=Path)
    module.__dict__.update({key: value for key, value in (environment or {}).items()
                            if not key.startswith('__')})
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), module.__dict__)
    EXTRACTED[str(relative)] = dict(sha256=hashlib.sha256(source.encode()).hexdigest(),
                                  definitions=[node.name for node in selected],
                                  source=str(path), unchanged_definition_asts=True)
    return module


# Fail closed before compiling even a definition from a different source tree.
_pins = json.loads((HERE / 'INPUT_PINS.json').read_text())
for _relative, _pin in _pins['sources'].items():
    _bytes = (SOURCE_ROOT / _relative).read_bytes()
    need(len(_bytes) == _pin['bytes'] and hashlib.sha256(_bytes).hexdigest() == _pin['sha256'],
         'source pin mismatch: ' + _relative)

arithmetic = definitions('ffn_public/prefix_arithmetic.py',
                         ('ArithmeticFault', 'finite', 'word', 'bf'))
matrix = definitions('ffn_attention/matrix_service.py', (
    'MatrixProtocolError', 'require', 'NormalGroup', 'NormalStep', '_MatrixRow',
    'MatrixValue', 'MatrixResult', 'MatrixDone', 'LegacyRequest', 'LegacyResult',
    'LegacyMatrixClient'))
client = definitions('attention_packed_owner/client.py', environment={
    **vars(matrix), 'ArithmeticFault': arithmetic.ArithmeticFault})
scripted = definitions('attention_packed_owner/test_client.py', ('_State', 'ScriptedService'),
                       environment=vars(matrix))
protocol = definitions('attention_packed_owner/protocol.py')


def load_routing():
    return definitions('production_qk16_model/routing.py', overlay=True,
                       environment={**vars(matrix), **vars(client)})


class _RoutedState(scripted._State):
    def matrix_state(self):
        return super().matrix_state() | (32 if self.service.legacy_reply is not None else 0)

    def matrix_normal_fmas(self):
        # Explicitly zero, not a shape-derived substitute for arithmetic calls.
        return 0


class RoutedScriptedService(scripted.ScriptedService):
    """Protocol-only test double. Not MatrixService and not an arithmetic array."""
    def __init__(self, *, acquired=True):
        super().__init__()
        self.lib = _RoutedState(self)
        self.legacy_reply = None
        self._owner_retired = False
        self.groups, self.events, self.step_profiles = [], [], []
        self.suppress_done = False
        if acquired:
            self.counts['owner_acquires'] = 1
        else:
            self.owner = self.mode = self.owner_tag = None

    def acquire(self, owner, mode, tag):
        matrix.require(mode == 'normal' and type(tag) is int, 'test acquisition mode/tag')
        if self.owner is not None or owner is None:
            return False
        matrix.require(not self.lib.matrix_state(), 'test acquisition before drain')
        self.owner, self.mode, self.owner_tag = owner, mode, tag
        self._owner_retired = False
        self.counts['owner_acquires'] += 1
        self.events.append(('acquire', tag, self.resource_address))
        return True

    def retire_owner_response(self, owner):
        self._check_owner(owner, 'normal')
        matrix.require(not self._owner_retired and not (self.lib.matrix_state() & (4 | 8 | 32 | 64)),
                       'test owner response before complete drain or duplicated')
        self._owner_retired = True
        self.counts['owner_responses'] += 1
        self.events.append(('owner_response', self.ticket))

    def release(self, owner):
        self._check_owner(owner, 'normal')
        matrix.require(self._owner_retired and not (self.lib.matrix_state() & (4 | 8 | 32 | 64)),
                       'test release before owner response/drain')
        self.events.append(('release', self.owner_tag, self.resource_address))
        self.owner = self.mode = self.owner_tag = None
        self.counts['owner_releases'] += 1

    def accept_group(self, owner, group):
        self._check_owner(owner, 'normal')
        matrix.require(type(group) is matrix.NormalGroup and self.legacy_reply is None,
                       'test group before legacy reply debt')
        if group.profile == 2:
            accepted = super().accept_group(owner, group)
        else:
            matrix.require((group.profile, group.opcode, group.slice_mask) == (0, 0x24, 1),
                           'test legacy PV profile/slices')
            if self.group is not None or self.reset_required:
                return False
            self.group = group
            self.ticket += 1
            self.end = False
            self.counts['normal_groups'] += 1
            accepted = True
        if accepted:
            self.groups.append(group)
            self.events.append(('group', group.profile, group.opcode, self.ticket, self.resource_address))
        return accepted

    def accept_step(self, owner, step):
        self._check_owner(owner, 'normal')
        matrix.require(self.group is not None and type(step) is matrix.NormalStep,
                       'test exact step in active group')
        if self.group.profile == 2:
            accepted = super().accept_step(owner, step)
        else:
            if self.result is not None or self.legacy_reply is not None or self.reset_required:
                return False
            matrix.require(step.emit and step.finish == step.last and
                           step.last == (step.index + 1 == self.group.steps) and
                           step.clear == (step.index == 0), 'test legacy EACH-key result')
            matrix.require(len(step.a) == 16 and len(step.b) == 256 and
                           all(type(x) is int and 0 <= x < 65536 for x in (*step.a, *step.b)),
                           'test legacy packet widths')
            self.steps.append(step)
            self.counts['normal_steps'] += 1
            raw = bytearray(16384)
            for index, word in self.words.items():
                struct.pack_into('<I', raw, index * 4, word)
            self.result = matrix.MatrixResult(0, matrix.MatrixValue(raw), step.last, False,
                                              self.ticket, self.epoch)
            self.legacy_reply = (self.ticket, self.epoch, step.last)
            self.end = step.last
            accepted = True
        if accepted:
            self.step_profiles.append(self.group.profile)
            self.events.append(('step', self.group.profile, self.ticket, step.index, step.emit, step.last))
        return accepted

    @property
    def done(self):
        return None if self.suppress_done else super().done

    def retire_result(self, owner, result):
        super().retire_result(owner, result)
        self.events.append(('result', result.ticket, result.last))

    def retire_done(self, owner, done):
        super().retire_done(owner, done)
        self.events.append(('done', done.ticket))

    def retire_legacy_reply(self, owner, ticket, epoch):
        self._check_owner(owner, 'normal')
        self._check_event(ticket, epoch)
        matrix.require(self.legacy_reply is not None and self.legacy_reply[:2] == (ticket, epoch)
                       and self.result is None
                       and (not self.legacy_reply[2] or self.group is None),
                       'test legacy reply before result/final done or duplicate')
        self.legacy_reply = None
        self.counts['legacy_replies'] += 1
        self.events.append(('legacy_reply', ticket))


def qk(index=0):
    return client.PackedRequest(0x23, (0x3f80,) * 16, (0x3f80,) * 256,
        index == 0, index == 7, 8, 255,
        tuple((r, 16 * key + r) for key in range(3) for r in range(16)) if index == 7 else ())


def pv(index=0, steps=3):
    return matrix.LegacyRequest(0x24, (0x3f80,) + (0,) * 15, (0x3f80,) * 16 + (0,) * 240,
                                index == 0, index + 1 == steps, steps, 1)


def deliver(target, request, *, limit=20):
    need(target.tick(request=request)['request_fire'], 'test request not admitted')
    for _ in range(limit):
        p = target.tick(result_ready=True)
        if p['result_fire']:
            return p['result']
    raise AssertionError('bounded scripted response timeout')


def expose(target, request, *, limit=20):
    need(target.tick(request=request)['request_fire'], 'test request not admitted')
    for _ in range(limit):
        result = target.ports()['result']
        if result is not None:
            return result
        target.tick()
    raise AssertionError('bounded scripted expose timeout')


def full_qk(target, *, held=False):
    for index in range(7):
        result = deliver(target, qk(index))
        need(type(result) is client.PackedStepAccepted and result.value is None,
             'nonfinal QK must be metadata only')
    return expose(target, qk(7)) if held else deliver(target, qk(7))


def patched_owner_source(relative, *, source=None, patch_path=None):
    """Apply only the pinned owner.patch file hunks, in memory with exact context."""
    import re
    source = ((SOURCE_PACKAGE / relative).read_text() if source is None else source).splitlines(keepends=True)
    patch_path = SOURCE_PACKAGE / 'attention_packed_owner/owner.patch' if patch_path is None else patch_path
    lines = patch_path.read_text().splitlines(keepends=True)
    target = 'candidates/qwen2_resident_matrix/' + relative
    selected = False
    position, output, cursor, hunks = 0, [], 0, 0
    while position < len(lines):
        line = lines[position]
        if line.startswith('--- a/'):
            selected = line[6:].strip() == target
            position += 2
            continue
        if not selected or not line.startswith('@@'):
            position += 1
            continue
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        need(match is not None, 'test exact patch header')
        start = int(match.group(1)) - 1
        need(start >= cursor, 'test overlapping owner hunks')
        output.extend(source[cursor:start])
        cursor = start
        position += 1
        while position < len(lines) and not lines[position].startswith(('@@', '--- a/')):
            patch_line = lines[position]
            prefix, content = patch_line[0], patch_line[1:]
            need(prefix in (' ', '+', '-'), 'test unsupported owner patch line')
            if prefix in (' ', '-'):
                need(cursor < len(source) and source[cursor] == content,
                     'test owner patch context mismatch')
                cursor += 1
            if prefix in (' ', '+'):
                output.append(content)
            position += 1
        hunks += 1
    need(hunks > 0, 'test owner patch target not found')
    output.extend(source[cursor:])
    return ''.join(output)


class ScalarControlAdapter:
    """Test-only scalar operation adapter; no native arithmetic acceptance claim."""
    def __init__(self):
        self.client = None
        self.calls = Counter()
        self.acquisitions = self.releases = 0

    def acquire(self, client):
        if self.client is not None:
            return False
        self.client = client
        self.acquisitions += 1
        return True

    def release(self, client):
        need(self.client is client, 'test scalar release ownership')
        self.client = None
        self.releases += 1

    def op(self, client, operation, a, b=0, *, policy='legacy_scalar'):
        need(self.client is client, 'test scalar op ownership')
        self.calls[operation] += 1
        if operation == 'bf':
            return arithmetic.bf(a)
        av, bv = (struct.unpack('<f', struct.pack('<I', bits))[0] for bits in (a, b))
        if operation == 'add':
            result = av + bv
        elif operation == 'mul':
            result = av * bv
        elif operation == 'div':
            result = av / bv
        else:
            raise AssertionError('unneeded test scalar operation: ' + operation)
        return arithmetic.word(result)


_OWNER_MODULES = None


def load_owner_modules():
    global _OWNER_MODULES
    if _OWNER_MODULES is not None:
        return _OWNER_MODULES
    prefix = definitions('ffn_public/prefix_owners.py', environment={
        **vars(arithmetic), 'BEAT_BYTES': 64, 'LANES': 16,
        'FULL_MASK': (1 << 64) - 1, 'LIMIT': 1 << 56,
        'NATIVE_ACCEPTANCE': 'NOT_EXECUTED_SYNTHETIC_CONTROL_TEST'})
    recipe_path = SOURCE_PACKAGE / 'ffn_attention/scalar_recipe.py'
    constants = {}
    for node in ast.parse(recipe_path.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL'):
                    constants[target.id] = ast.literal_eval(node.value)
    recipe = definitions('ffn_attention/scalar_recipe.py', environment={
        **vars(arithmetic), **constants,
        'value': lambda bits: struct.unpack('<f', struct.pack('<I', bits))[0]})
    packed_schedule = definitions('attention_packed_owner/schedule.py', environment={
        **vars(client), **vars(protocol), **vars(prefix), **vars(recipe)})
    selected = definitions('production_qk16_model/schedule.py', overlay=True, environment={
        **vars(packed_schedule), **vars(client), **vars(prefix), **vars(recipe)})
    routing = load_routing()
    hooks_source = patched_owner_source('attention_packed_owner/hooks.py',
        patch_path=HERE / 'selected_hooks.patch')
    need(hashlib.sha256(hooks_source.encode()).hexdigest() ==
         'e4aed930d1a3f1742c95eaf1ec92350ef5c142ed276fbacb7821d473b4cf202d',
         'selected hooks postimage changed')
    hooks = definitions('attention_packed_owner/hooks.py', source=hooks_source, environment={
        **vars(protocol), **vars(packed_schedule), **vars(selected), **vars(routing),
        **vars(client), **vars(prefix)})
    attention_source = patched_owner_source('ffn_attention/attention_owner.py')
    attention_source = patched_owner_source('ffn_attention/attention_owner.py', source=attention_source,
        patch_path=HERE / 'selected_owner.patch')
    attention = definitions('ffn_attention/attention_owner.py', source=attention_source, environment={
        **vars(arithmetic), **vars(prefix), **vars(matrix), **vars(recipe), 'packed': hooks})
    official = definitions('official_bf16/owners.py', ('OfficialAttentionOwner',),
        source=patched_owner_source('official_bf16/owners.py'), environment={
        **vars(arithmetic), **vars(prefix), **vars(attention), **vars(recipe)})
    entry = definitions('production_qk16_model/entry.py', overlay=True, environment={
        **vars(selected), 'hooks': hooks})
    _OWNER_MODULES = types.SimpleNamespace(entry=entry, prefix=prefix, recipe=recipe, packed_schedule=packed_schedule,
        selected=selected, routing=routing, hooks=hooks, attention=attention, official=official)
    return _OWNER_MODULES


def make_owner(m=2, *, schedule=True):
    modules = load_owner_modules()
    service = RoutedScriptedService(acquired=False)
    service.words = {}  # Synthetic zero Matrix result, never computed from input.
    scalar = ScalarControlAdapter()
    selected = modules.selected.ProductionQk16Schedule() if schedule else None
    owner = modules.official.OfficialAttentionOwner(service, scalar, max_tokens=128,
                                                    packed_schedule=selected)
    job = modules.prefix.Job('Attention', 0x12340001, 0x10000, 0x20000, 0x40000,
                             m, 1536, 128, m * 1536 * 4, c=0x30000)
    return modules, service, scalar, owner, job


def drive_owner(owner, job, *, limit=30000, terminal_ready=True, stall=True):
    """Drive actual unchanged owner.tick and memory ACKs, bounded synthetic IO."""
    modules = load_owner_modules()
    need(owner.tick(job=job)['job_fire'], 'test owner admission')
    pending, writes, matrix_requests, results = None, [], [], []
    for tick in range(limit):
        before = owner.ports()
        need(before['scratch'] is None, 'selected production mode unexpectedly used scratch')
        response = pending if pending is not None and (not stall or tick % 4 != 0) else None
        p = owner.tick(memory_ready=not stall or tick % 3 != 0,
            memory_response=response, response_ready=terminal_ready,
            matrix_request_ready=not stall or tick % 4 != 0,
            matrix_result_ready=not stall or tick % 6 != 0,
            service_result_ready=not stall or tick % 5 != 0,
            service_done_ready=not stall or tick % 7 != 0)
        if p['memory_response_fire']:
            need(response is pending, 'test response identity')
            pending = None
        if p['memory_fire']:
            need(pending is None, 'test second memory debt')
            request = p['memory']
            if request.write:
                need(isinstance(request.data, bytes) and len(request.data) == 64,
                     'test actual owner write packet')
                writes.append(request)
            pending = modules.prefix.MemoryResponse(request.tag,
                None if request.write else (0,) * 16)
        if p['matrix_request_fire']:
            matrix_requests.append(p['matrix'])
        if p['matrix_result_fire']:
            results.append((owner.matrix.counts['normal_results'], owner.matrix.counts['normal_done']))
        if p['response_fire']:
            need(pending is None, 'test terminal with memory debt')
            return types.SimpleNamespace(response=p['response'], writes=writes,
                matrix_requests=matrix_requests, matrix_results=results, ticks=tick + 1)
        if not terminal_ready and owner.state == 'finish':
            need(pending is None, 'test held terminal with memory debt')
            return types.SimpleNamespace(response=owner.result, writes=writes,
                matrix_requests=matrix_requests, matrix_results=results, ticks=tick + 1)
    raise AssertionError('bounded composed owner timeout: ' + owner.state + ' ' + str(owner.detail))
