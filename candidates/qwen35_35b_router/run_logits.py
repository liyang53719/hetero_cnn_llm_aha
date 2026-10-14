"""Cold-default, pinned saved-postnorm router logits diagnostic/replay gate.

Only --run-actual admits numerical execution, and requires every fixture path.
No download, live producer handoff, router-tail owner, public command or RTL.
"""
import argparse
import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IDENTITY = HERE / 'logits_identity.json'
SCOPE = 'PINNED_SAVED_POSTNORM_ACTUAL_TYPED_ROUTER_LOGITS_ONLY'
REQUIRED = ('producer_m16', 'producer_m128', 'payload', 'runtime_root',
            'matrix_library', 'matrix_receipt', 'vector_library', 'out')


def require(ok, why):
    if not ok:
        raise ValueError('35B router logits gate: ' + why)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    path = Path(path).resolve(strict=True)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def same_file(path, expected, label):
    observed = record(path)
    require(all(observed[k] == expected[k] for k in ('bytes', 'sha256')), label + ' bytes/hash')
    return observed


def identity_unchanged(expected, identity_path=IDENTITY):
    require(record(identity_path) == expected, 'identity file changed during invocation')


def execution_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def source_identity(root=ROOT, identity_path=IDENTITY):
    identity = json.loads(Path(identity_path).read_bytes())
    require(identity['schema'] == 1 and identity['base_commit'] ==
            '8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689', 'identity schema/base')
    require(identity['repository'] == 'liyang53719/hetero_cnn_llm_aha', 'repository identity')
    for group in ('base_sources', 'candidate_sources'):
        require(bool(identity[group]), 'nonempty source identity map')
        for name, digest in identity[group].items():
            path = Path(root) / name
            require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                    path.resolve().is_relative_to(Path(root).resolve()), 'source containment')
            require(sha(path) == digest, 'source drift: ' + name)
    return identity


def imported_source_identity(identity):
    """Reject an imported repository implementation outside the frozen map."""
    pins = {**identity['base_sources'], **identity['candidate_sources']}
    observed = {}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).is_absolute():
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py' and not path.is_relative_to(ROOT / 'work'):
                relative = str(path.relative_to(ROOT))
                require(relative in pins and sha(path) == pins[relative], 'unpinned imported source: ' + relative)
                observed[relative] = pins[relative]
    return observed


def cold_source_gate(identity):
    """Check the exact upstream class without importing arithmetic dependencies."""
    source = ROOT / 'config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py'
    raw = source.read_bytes()
    classes = [node for node in ast.parse(raw).body if isinstance(node, ast.ClassDef)
               and node.name == 'Qwen3_5MoeTopKRouter']
    require(len(classes) == 1, 'one complete official router class')
    node = classes[0]
    exact = b''.join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    require(hashlib.sha256(exact).hexdigest() == identity['router_class_sha256'], 'official class pin')
    config = json.loads((source.parent / 'config.json').read_bytes())['text_config']
    require((config['hidden_size'], config['num_experts'], config['num_experts_per_tok']) ==
            (2048, 256, 8), 'original router geometry')


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-actual', action='store_true')
    for field in REQUIRED:
        ap.add_argument('--' + field.replace('_', '-'), type=Path)
    return ap


def validate_arguments(args):
    if args.run_actual:
        require(all(getattr(args, key) is not None for key in REQUIRED),
                '--run-actual requires all explicit fixture paths and --out')
    else:
        require(not any(getattr(args, key) is not None for key in REQUIRED if key != 'out'),
                'fixture paths require --run-actual')
    if args.out is not None:
        require(not args.out.exists() and not args.out.is_symlink() and
                args.out.resolve().is_relative_to(ROOT / 'work'), 'fresh ignored work output required')


def validate_fixtures(args, identity):
    from . import payload, reference
    fixtures = identity['fixtures']
    inputs, producers = {}, {}
    for m in (16, 128):
        directory = getattr(args, 'producer_m' + str(m)).resolve(strict=True)
        expected = fixtures['cases'][str(m)]
        same_file(directory / 'summary.json', expected['producer_summary'], 'producer summary')
        raw, summary_path, input_path = reference.producer(directory, expected['producer_summary']['sha256'], m)
        same_file(input_path, expected['input'], 'saved postnorm fixture')
        producer = json.loads(summary_path.read_bytes())
        for key in ('matrix_library', 'vector_library'):
            require(all(producer[key][k] == fixtures[key][k] for k in ('bytes', 'sha256')),
                    'producer native identity: ' + key)
        inputs[m] = raw
        producers[m] = dict(summary=record(summary_path), input=record(input_path))
    same_file(args.payload / 'manifest.json', fixtures['payload_manifest'], 'payload manifest')
    _, weights = payload.load(args.payload, fixtures['payload_manifest']['sha256'])
    weight = weights['layers.0.mlp.gate.weight']
    require(len(weight) == fixtures['weight']['bytes'] and
            hashlib.sha256(weight).hexdigest() == fixtures['weight']['sha256'], 'original router weight')
    for key in ('matrix_library', 'vector_library'):
        same_file(getattr(args, key), fixtures[key], key)
    for name, digest in identity['runtime']['sha256'].items():
        require(sha(args.runtime_root / name) == digest, 'runtime artifact drift: ' + name)
    compiler = shutil.which('gcc')
    require(compiler is not None, 'gcc required')
    same_file(compiler, fixtures['reference_compiler'], 'reference compiler')
    return inputs, producers, weight


def compare_outputs(actual, official, independent, m):
    from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
    require(all(len(raw) == m * 256 * 2 for raw in (actual, official, independent)), 'full logits shape')
    comparisons = dict(official=compare_finite_bf16(actual, official),
                       independent_c_pair=compare_finite_bf16(actual, independent))
    require(all(item['bit_mismatches'] == 0 for item in comparisons.values()), 'exact full-N256 logits')
    return comparisons


def replay(m, raw_input, weight, library, vector_path, out, identity):
    """Execution receives input/weight only; references are compared by caller later."""
    import numpy as np
    from ..qwen35_gdn_prefill import typed_dense as dense
    from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
    from ..qwen35_35b_prefill.projection_owner import LargeKProjectionOwner, PrefixWorkspace
    from ..qwen35_35b_prefill.projection_driver import TypedLargeKProjectionDriver
    from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
    from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
    # Freeze this lazily imported adapter before executing the first issue.
    from ..qwen2_resident_matrix.dense_block_reduce import vector_add_model  # noqa: F401

    imported_source_identity(identity)

    packed = np.frombuffer(weight, '<u2').reshape(256, 2048).T.copy().tobytes()
    lib = configure_library(ctypes.CDLL(str(library)))
    require(lib.td_reset() == 0, 'initial isolated Matrix reset')
    matrix, vector = dense.MatrixService(lib), Vector16(vector_path, exception_policy=IEEE_POLICY)
    owner = LargeKProjectionOwner(PrefixWorkspace(0x100000000, 16384, 1, split_k=2048))
    memory = dense.TypedMemory()
    memory.add_readonly(0x100000, raw_input)
    memory.add_readonly(0x200000, packed)
    memory.allocate_output(0x400000, m * 256 * 2)
    profile = ReductionProfile('diagnostic_35b_router_n256_pair_high_two_k1024',
                               ((0, 1024), (1024, 2048)), True, sha(HERE / 'reference.c'))
    job = dense.down.Job(m=m, k=2048, n=256, tag=35701, a=0x100000, b=0x200000,
                         dst=0x400000, activation_bf16=True, weight_bf16=True,
                         output_bf16=True, write_bytes=m * 256 * 2)
    driver = TypedLargeKProjectionDriver(owner, matrix, memory, job, vector=vector,
                                         profile=profile, sum_identity=36701)
    resources = (id(memory), id(owner), id(owner.a_banks), id(owner.b_banks),
                 matrix.resource_address, vector.resource_address)
    started = time.monotonic()
    try:
        for _ in range(2_000_000):
            driver.tick()
            if driver.response is not None:
                break
    finally:
        # Preserve partial state on timeout or arithmetic/transport failure.
        (out / 'owner.json').write_text(json.dumps(driver.report(), indent=2) + '\n')
    require(driver.response == (job.tag, None, job.write_bytes), 'successful accepted terminal')
    require(driver.output.published and not driver.output.readonly, 'actual writeback publication')
    require(driver.output.written == driver.output.acknowledged == set(range(0, job.write_bytes, 64)),
            'exact write/ACK coverage')
    require(driver.counts['write_data_bytes'] == driver.counts['ack_bytes'] == job.write_bytes,
            'exact output byte counts')
    require(memory.pending is None and matrix.owner is None and vector.client is None and
            owner.tiles.idle and not owner.tiles.leased and owner.lease is None, 'all resources drained')
    require(resources == (id(memory), id(owner), id(owner.a_banks), id(owner.b_banks),
                          matrix.resource_address, vector.resource_address), 'same physical resources')
    require(driver.a.raw() == raw_input and driver.b.raw() == packed, 'unchanged actual inputs')
    result = driver.output.raw()
    (out / 'actual.logits.bf16le').write_bytes(result)
    # Owner reports contain detailed trace payloads and stay under ignored work/.
    return result, dict(m=m, elements=m * 256, output=record(out / 'actual.logits.bf16le'),
                        owner_receipt=record(out / 'owner.json'), counts=dict(driver.counts),
                        resources_drained=True, resources_retained=True, output_published=True,
                        input_readonly=True, host_seconds=time.monotonic() - started)


def runtime_setup(runtime_root, identity):
    from ..qwen35_35b_rms import reference as rms
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    require(torch.set_flush_denormal(False), 'gradual underflow')
    runtime = rms.runtime_identity(runtime_root)
    require(all(runtime[k] == identity['runtime'][k] for k in
                ('torch_version', 'torch_git_revision', 'numpy_version', 'python_version', 'cpu_capability',
                 'intraop_threads', 'interop_threads', 'sha256', 'build_config_sha256')),
            'runtime identity drift')
    return runtime


def run_actual(args, identity, report):
    from ..qwen35_gdn_prefill import typed_dense as dense
    inputs, producers, weight = validate_fixtures(args, identity)
    os.environ['HETERO_35B_RUNTIME_PROFILE'] = 'recovery_20261013'
    library = dense.library_from_environment(ROOT, dict(MATRIX_SERVICE_LIBRARY=str(args.matrix_library),
                                                       MATRIX_SERVICE_COMPILE_RECEIPT=str(args.matrix_receipt)))
    vector_path = args.vector_library.resolve(strict=True)
    artifacts = [record(x) for x in (library, args.matrix_receipt, vector_path, vector_path.with_suffix('.json'))]
    report['runtime'] = runtime_setup(args.runtime_root, identity)
    report['native_artifacts'] = artifacts
    report['cases'] = []
    for m in (16, 128):
        out = args.out / ('m' + str(m))
        out.mkdir()
        started = time.monotonic()
        # Run the untouched upstream class and both strict C diagnostics fresh.
        command = [sys.executable, '-S', '-m', 'candidates.qwen35_35b_router.reference',
                   '--m', str(m), '--producer', str(getattr(args, 'producer_m' + str(m))),
                   '--producer-sha256', identity['fixtures']['cases'][str(m)]['producer_summary']['sha256'],
                   '--payload', str(args.payload), '--manifest-sha256', identity['fixtures']['payload_manifest']['sha256'],
                   '--runtime-root', str(args.runtime_root), '--out', str(out / 'reference')]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        (out / 'reference.log').write_text(process.stdout + process.stderr)
        require(process.returncode == 0, 'fresh reference failed; see ignored reference.log')
        reference_path = out / 'reference' / 'report.json'
        reference_record = record(reference_path)
        rr = json.loads(reference_path.read_bytes())
        same_file(rr['libm']['path'], identity['fixtures']['reference_libm'], 'reference libm')
        require(rr['sources_unchanged'] is True, 'reference source drift')
        report['actual_matrix_owner_executed'] = True
        report['actual_status'] = 'RUNNING'
        actual, case = replay(m, inputs[m], weight, library, vector_path, out, identity)
        # Neither official nor C output is passed into replay/execution resources.
        def checked(item):
            same_file(item['path'], item, 'fresh reference output')
            return Path(item['path']).read_bytes()
        case.update(compare_outputs(actual, checked(rr['official_logits']),
                                    checked(rr['recipes']['pair_hi_first_two_k1024']['output']), m))
        require(record(reference_path) == reference_record, 'fresh reference receipt changed')
        case.update(producer=producers[m], reference_receipt=reference_record,
                    reference_recipes={name: item['diagnostics'] for name, item in rr['recipes'].items()},
                    sequential_recipe_status='FAIL_BITEXACT_DIAGNOSTIC_ONLY',
                    total_host_seconds=time.monotonic() - started)
        expected_mismatches = identity['fixtures']['cases'][str(m)]['sequential_bit_mismatches']
        require(case['reference_recipes']['sequential_k2048']['bit_mismatches'] == expected_mismatches,
                'retained sequential failed diagnostic drift')
        require(sha(Path(rr['official_logits']['path'])) == identity['fixtures']['cases'][str(m)]['official_logits_sha256'],
                'pinned official logits drift')
        report['cases'].append(case)
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    # The initial identity object is authority. A changed lock cannot authorize
    # changed source hashes merely by passing a new source_identity() read.
    identity_unchanged(report['identity'])
    source_identity()
    identity_unchanged(report['identity'])
    report['imported_sources'] = imported_source_identity(identity)
    require(all(record(item['path']) == item for item in artifacts), 'native artifacts changed')
    validate_fixtures(args, identity)
    identity_unchanged(report['identity'])
    report.update(status='PASS_SAVED_POSTNORM_ACTUAL_TYPED_LOGITS_ONLY', actual_matrix_owner_executed=True,
                  actual_status='PASS', sources_unchanged=True, native_artifacts_unchanged=True,
                  identity_unchanged=True, execution_commit_after=execution_commit())


def main(argv=None):
    args = parser().parse_args(argv)
    validate_arguments(args)
    initial_identity = record(IDENTITY)
    identity = source_identity()
    identity_unchanged(initial_identity)
    cold_source_gate(identity)
    identity_unchanged(initial_identity)
    report = dict(scope=SCOPE, status='PASS_COLD_SOURCE_IDENTITY_ONLY', actual_status='NOT_EXECUTED',
                  actual_matrix_owner_executed=False, live_postnorm_producer_handoff=False,
                  actual_router_tail_executed=False, complete_router_owner=False,
                  command128_executed=False, rtl_executed=False, full_block=False,
                  official_model_profile_admitted=False, hardware_cycles=None, hardware_utilization=None,
                  identity=initial_identity, base_commit=identity['base_commit'],
                  execution_commit=execution_commit())
    if args.out is not None:
        args.out = args.out.resolve()
        args.out.mkdir()
    if args.run_actual:
        def deadline(*_):
            raise TimeoutError('600 second bounded reference/replay gate')
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(600)
        report['status'] = 'RUNNING'
        report['actual_status'] = 'PENDING'
        try:
            run_actual(args, identity, report)
        except BaseException as error:
            report.update(status='FAILED_OR_INTERRUPTED', actual_status='FAILED_OR_INTERRUPTED',
                          error=dict(type=type(error).__name__, message=str(error)))
            (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            raise
        finally:
            signal.alarm(0)
    if args.out is not None:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    main()
