"""Execute existing source recipes and retained-QK accepted-event model only.

No numerical model, Scala compiler, RTL generator, or native arithmetic import.
This does not interpret Scala or replace the production control implementation.
"""
import argparse
import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import types

HERE = Path(__file__).resolve().parent
P = 'candidates/qwen2_resident_matrix/'
S = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
PINS_HASH = 'b9dfbec83de5b8b90f8525a89c28bac99b683d104f208236cb3449406e3a7ac2'
PACKAGES = ('candidates', 'candidates.qwen2_resident_matrix',
            'candidates.qwen2_resident_matrix.attention_packed_stream',
            'candidates.qwen2_resident_matrix.attention_qk_owner_route',
            'candidates.qwen2_resident_matrix.attention_qk16_owner_route')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})


def verify(root):
    raw = (HERE / 'INPUT_PINS.json').read_bytes()
    need(sha(raw) == PINS_HASH, 'input manifest identity')
    pins = json.loads(raw)
    for name in PACKAGES:
        initializer = root / name.replace('.', '/') / '__init__.py'
        need(not initializer.exists() and not initializer.is_symlink(), 'unexpected package initializer')
    for name in pins['sources']:
        if name.endswith('.py'):
            source = root / name
            legacy = source.with_suffix('.pyc')
            cached = source.parent / '__pycache__'
            need(not legacy.exists() and not legacy.is_symlink() and
                 not any(cached.glob(source.stem + '.*.pyc')), 'unexpected selected-source bytecode')
    for name, record in pins['sources'].items():
        path = root / name
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'source path')
        need(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink source')
        need(path.is_file() and path.stat().st_size == record['bytes'], 'source size: ' + name)
        need(sha(path.read_bytes()) == record['sha256'], 'source identity: ' + name)
    return pins


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def bound_import(name, root):
    expected = root / (name.replace('.', '/') + '.py')
    # Reject a previous consumer's cached implementation rather than reusing it.
    if name in sys.modules:
        need(Path(sys.modules[name].__file__).resolve() == expected.resolve(), 'cached module origin')
    module = importlib.import_module(name)
    need(Path(module.__file__).resolve() == expected.resolve(), 'imported module origin')
    return module


def prepare_packages(root):
    """Anchor the selected tree's empty namespace packages without executing init files."""
    for name in PACKAGES:
        directory = str(root / name.replace('.', '/'))
        if name in sys.modules:
            module = sys.modules[name]
            need(getattr(module, '__file__', None) is None and
                 list(getattr(module, '__path__', ())) == [directory], 'cached package origin')
        else:
            module = types.ModuleType(name)
            module.__package__ = name
            module.__path__ = [directory]
            module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
            module.__spec__.submodule_search_locations = module.__path__
            sys.modules[name] = module


def compose(root, out):
    """Use the published recipes without reimplementing or changing them."""
    pins = verify(root)
    need(not out.exists() and not out.is_symlink(), 'fresh output required')
    # Imported files are hash-checked above. Only existing pure-Python source
    # recipes and control models are imported; numerical entry files are data.
    prepare_packages(root)
    sys.path.insert(0, str(root))
    production = load('qwen2_existing_production_replay', root / P / 'production_qkv_reduction/replay.py')
    donor = bound_import('candidates.qwen2_resident_matrix.attention_qk16_owner_route.prepare', root)
    for name in ('attention_qk_owner_route.prepare', 'attention_packed_stream.prepare'):
        bound_import('candidates.qwen2_resident_matrix.' + name, root)
    builder = load('qwen2_existing_qk16_builder', root / P / 'production_qk16_rebase/build_source.py')
    out.mkdir()
    prod = production.run(root, out / 'production')
    qk = donor.compose(out / 'donor')
    posts = builder.compose(out / 'production/source', out / 'donor', out / 'installed')
    expected = json.loads((root / P / 'production_qk16_rebase/POSTIMAGE_PINS.json').read_text())
    need(posts == expected, 'five production postimages')
    planned = json.loads((root / P / 'production_qk16_rebase/classcompile/PLANNED_SOURCE_PINS.json').read_text())
    repository_sources = []
    external_sources = []
    for name, digest in planned.items():
        if name.startswith('hardfloat_snapshot/hardfloat/src/main/scala/'):
            external_sources.append(name)
            continue
        selected = out / 'installed' / name
        if not selected.is_file():
            selected = out / 'production/source' / name
        need(sha(selected.read_bytes()) == digest, 'selected production closure: ' + name)
        repository_sources.append(name)
    need(len(planned) == 92 and len(repository_sources) == 72 and len(external_sources) == 20,
         'planned production source inventory')
    verify(root)
    return {'production_files': len(prod['post_sha256']), 'donor_files': len(qk),
            'installed_files': len(posts), 'postimages': posts,
            'planned_repository_scala_sources_verified': len(repository_sources),
            'external_hardfloat_source_bodies_not_verified': len(external_sources),
            'full_92_source_compiler_closure_verified': False,
            'source_files_unchanged': len(pins['sources'])}


def source_binding(root, out):
    installed = out / 'installed' / S / 'Qwen2Block.scala'
    production = out / 'production/source' / S / 'Qwen2Block.scala'
    q = installed.read_text()
    compact = lambda s: ''.join(s.split())
    for fragment in (
        'c.io.result.ready:=packedCommitted.get && !poisoned',
        'when(c.io.completion.fire){packedOwned.get:=false.B}',
        'val packedBusy=packedOwned.getOrElse(false.B)',
        'packedCommitted.get:=packedSelected.get+&1.U===packedKeys',
        '''when(state===st("attNextKey") && !poisoned && !packedQk.get.io.resetRequired){
          when(packedSelected.get+&1.U<packedKeys){
            packedSelected.get:=packedSelected.get+1.U;state:=st("attPackedSelect")
          }.elsewhen(!packedBusy){
            when(key+packedKeys<=token){key:=key+packedKeys;state:=st("attKey")}
            .otherwise{key:=0.U;sum:=0.U;state:=st("attExpRead")}
          }
        }''',
        'when(state===st("attInv")){scale:=scalarValue;col:=0.U;state:=st("attPVStart")}',
    ):
        need(compact(q).count(compact(fragment)) == 1, 'production handoff source binding')
    start = '  when(state===st("attExpRead"))'
    end = '  // Numerically stable SiLU'
    tail = lambda text: text[text.index(start):text.index(end, text.index(start))]
    need(tail(q) == tail(production.read_text()), 'existing sequential softmax/PV changed')
    contract = json.loads((root / P / 'portable_same_host_m128_launch/input-contract.json').read_text())
    bare = sha((root / S / 'Qwen2Block.scala').read_bytes())
    need(contract['inputs'][S + 'Qwen2Block.scala'] == bare and
         contract['composed_sources'][S + 'Qwen2Block.scala'] == bare,
         'M128 Scala provenance identity')
    need(sha(installed.read_bytes()) != bare, 'expected recipe postimage distinction')
    return {'bare_main_sha256': bare, 'production_preimage_sha256': sha(production.read_bytes()),
            'donor_sha256': sha((out / 'donor' / S / 'Qwen2Block.scala').read_bytes()),
            'installed_postimage_sha256': sha(installed.read_bytes()),
            'bare_main_difference': 'EXPECTED_PINNED_RECIPE_COMPOSITION_NOT_MISSING_ARCHITECTURE',
            'sequential_softmax_pv_byte_preserved': True,
            'm128_contract_binds_bare_scala_as_provenance': True,
            'm128_operationally_executes_composed_scala': False}


def exercise_retirement(root, token, base, stalls=3, done_delay=4):
    """Drive existing GatherOwner/Client. Labels are not arithmetic/mask data."""
    model = bound_import('candidates.qwen2_resident_matrix.attention_qk16_owner_route.model', root)
    stream = bound_import('candidates.qwen2_resident_matrix.attention_packed_stream.model', root)
    owner = model.GatherOwner(token, base, enabled=True)
    ticks = 0
    def tick(**kw):
        nonlocal ticks
        ticks += 1
        need(ticks <= 10000, 'bounded model tick budget')
        return owner.tick(**kw)
    tick(); tick(group_ready=True)
    for depth in range(8):
        tick(q=tuple(('q', depth, i) for i in range(16)))
        for local in range(owner.count):
            before = tick(read_ready=False)['request']
            need(before == tick(read_ready=False)['request'], 'unstable stalled read')
            request = tick(read_ready=True)['request']
            need(request[1:] == (base + local, depth * 16), 'wrong real model address')
            tick(response=(request[0], False, tuple(('k', depth, local, i) for i in range(16))))
            tick()
        need(not tick(step_ready=False)['client']['step_fire'], 'step during backpressure')
        tick(step_ready=True)
    result = stream.Result(payload=tuple(tuple((r, c) for c in range(256)) for r in range(16)))
    tick(result=result)
    for local in range(owner.count):
        need(owner.acc == tuple((i, 16 * local + i) for i in range(16)), 'selected labels reordered')
        for _ in range(stalls):
            old_lane = owner.lane
            tick(result=result, scalar_ack=False)
            need(owner.lane == old_lane and owner.client.counts['results'] == 0,
                 'fold advanced or held result retired without ACK')
            need(owner.held is result, 'held result identity lost')
        for _ in range(17):
            tick(result=result, scalar_ack=True)
        tick(result=result)
        need(owner.scores == list(range(base, base + local + 1)), 'score duplicated or skipped')
        need(owner.client.counts['results'] == 0, 'result retired before final score edge')
        if local + 1 < owner.count:
            tick(result=result); tick(result=result)
    need(owner.committed and owner.state == 'next' and owner.owned, 'last score handoff state')
    tick(result=result)
    need(owner.client.counts['results'] == 1 and owner.held is None and owner.owned,
         'result must retire exactly once without releasing ownership')
    for _ in range(done_delay):
        tick()
        need(owner.state == 'next' and owner.owned, 'advanced before matching done/completion')
        need(owner.client.counts['results'] == 1, 'duplicate result retirement')
    tick(done=(owner.tag, False))
    need(owner.owned and owner.state == 'next', 'done alone released ownership')
    tick()
    need(not owner.owned and owner.state == 'next', 'completion must release before next-cycle handoff')
    tick()
    need(owner.state == 'complete', 'group retirement did not complete')
    for _ in range(3):
        tick()
    need(owner.client.counts == {'groups': 1, 'steps': 8, 'results': 1, 'done': 1, 'completion': 1},
         'accepted event count mismatch')
    need(owner.events.count('result_ack') == owner.events.count('done_ack') ==
         owner.events.count('completion_ack') == 1, 'duplicate ACK event')
    return {'token': token, 'base': base, 'keys': owner.count, 'ticks': ticks,
            'scores': len(owner.scores), 'result_acks': 1, 'done_acks': 1,
            'completion_acks': 1, 'model_state': owner.state}


def run(root, out):
    composition = compose(root, out)
    binding = source_binding(root, out)
    cases = [exercise_retirement(root, n - 1, 0) for n in range(1, 17)]
    cases.append(exercise_retirement(root, 127, 112))
    verify(root)
    return {'schema': 1, 'status': 'INCOMPLETE',
            'bounded_slice': 'PASS_EXISTING_COMPOSITION_AND_RETAINED_QK_CONTROL_MODEL',
            'composition': composition, 'binding': binding, 'retirement_cases': cases,
            'scope': {'source_recipes_executed': True, 'existing_accepted_event_model_executed': True,
                      'scala_behavior_executed': False, 'softmax_pv_behavior_executed': False,
                      'native_arithmetic_imported': False, 'rtl_generated': False,
                      'full_m128_reexecuted': False, 'historical_acceptance_inherited': False,
                      'numerical_equivalence': False, 'hardware_cycles_claimed': False,
                      'full_block_acceptance': False, 'production_fix_required_by_observed_case': False},
            'unproven': ['production Scala dynamic behavior', 'Python six-head versus Scala per-head operational correspondence',
                         'shared-bank ACK/release and 384B panel', 'PV6 retention and final resource debt join',
                         'Scalar policy and full29 numerical acceptance'],
            'input_pins_sha256': PINS_HASH}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    limits()
    try:
        report = run(args.source_root.absolute(), args.output.absolute())
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'status': 'REJECTED', 'reason': str(exc), 'full_block_acceptance': False}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2


if __name__ == '__main__':
    sys.exit(main())
