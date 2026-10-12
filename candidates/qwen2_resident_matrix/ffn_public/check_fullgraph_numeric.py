#!/usr/bin/env python3
"""Freeze and execute the original public21 cold prefill, in software only.

Reuse raw input/weight identities and the original independent C++ oracle.
Actual public completion of all21 commands opens the comparison gate. No old
receipt constitutes acceptance of this new execution/source/dataflow closure.
"""
import argparse
import ctypes as C
import importlib
import importlib.util
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import check_prefix_numeric as base

require, sha, encoded, file_sha = base.require, base.sha, base.encoded, base.file_sha
EXTRA_TENSORS = {
    'wo': ('self_attn.o_proj.weight', [1536, 1536]),
    'wg': ('mlp.gate_proj.weight', [8960, 1536]),
    'wu': ('mlp.up_proj.weight', [8960, 1536]),
    'wd': ('mlp.down_proj.weight', [1536, 8960]),
    'gamma1': ('post_attention_layernorm.weight', [1536]),
}
LIBRARY_SOURCES = ('candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
                   'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp',
                   'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp')
STAGE_WIDTHS = dict(zip(('n0', 'qr', 'kr', 'v', 'q', 'k', 'att', 'o', 'r', 'n1',
                        'gate', 'up', 'act', 'down', 'y'),
                       (1536, 1536, 256, 256, 1536, 256, 1536, 1536, 1536, 1536,
                        8960, 8960, 8960, 1536, 1536)))
_modules, _loaded_hashes = None, None


def source_hashes():
    paths = set(base.source_paths())
    paths.update('candidates/qwen2_resident_matrix/ffn_public/' + n + '.py' for n in
                 ('check_fullgraph_numeric', 'fullgraph_execution', 'fullgraph_memory'))
    paths.update('candidates/qwen2_resident_matrix/ffn_attention/' + n + '.py' for n in
                 ('matrix_service', 'attention_owner', 'scalar_recipe'))
    paths.update(LIBRARY_SOURCES)
    # Arithmetic/protocol source identities also cover the endpoint's explicit
    # separation of exception flags from accepted command protocol status.
    spec = importlib.util.spec_from_file_location('fullgraph_matrix_identity',
        ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    paths.update(module.SOURCE_HASHES)
    return {p: file_sha(ROOT / p) for p in sorted(paths)}


def runtime():
    global _modules, _loaded_hashes
    if _modules is None:
        before = source_hashes()
        with base.frozen_exec(before):
            names = ('check_numeric', 'execute_numeric', 'fixture', 'model', 'prefix_execution',
                     'prefix_owners', 'prefix_arithmetic', 'fullgraph_execution', 'fullgraph_memory')
            public = [importlib.import_module(base.PREFIX + n) for n in names]
            matrix = importlib.import_module('candidates.qwen2_resident_matrix.ffn_attention.matrix_service')
            attention = importlib.import_module('candidates.qwen2_resident_matrix.ffn_attention.attention_owner')
            recipe = importlib.import_module('scripts.qwen2_block_recipe_model')
            public[2].make_qwen2_21_fixture(16)
            matrix.source_identity(); public[6].source_identity()
        _modules = (*public, matrix, attention, recipe)
        require(source_hashes() == before, 'fullgraph source changed during import')
        require(public[0].imported_python_paths(_modules) <= set(before),
                'fullgraph imported Python escaped source closure')
        _loaded_hashes = before
    require(source_hashes() == _loaded_hashes, 'fullgraph source changed after import')
    return _modules


def input_spec():
    spec, recipe = base.input_spec()
    manifest = base.checked_json(base.PAYLOAD)
    for role, (name, shape) in EXTRA_TENSORS.items():
        entries = [t for t in manifest['tensors'] if t['local_name'] == name]
        require(len(entries) == 1, 'missing/duplicate original fullgraph tensor: ' + role)
        t = entries[0]
        require(t['dtype'] == 'BF16' and t['shape'] == shape and t['bytes'] == math.prod(shape) * 2
                and Path(t['file']).name == t['file'], 'fullgraph raw weight layout differs: ' + role)
        spec['payloads'][role] = dict(path=str(Path(base.PAYLOAD).parent / t['file']),
                                    bytes=t['bytes'], sha256=t['sha256'], shape=shape)
    return spec, recipe


def load_inputs(spec, rows):
    inputs, raw = base.load_inputs(spec, rows)
    for role in ('wo', 'wg', 'wu', 'wd'):
        inputs[role] = base.transpose_bf16(raw[role], spec['payloads'][role]['shape'])
    inputs['gamma1'] = base.fp32_from_bf16(raw['gamma1'])
    return inputs


def binary_identity(compile_path):
    path = Path(compile_path).resolve()
    compiled = json.loads(path.read_text())
    argv = compiled['argv']
    flags = [v for v in argv[1:] if v.startswith('-') and v != '-o']
    require(flags == ['-shared', '-fPIC', '-O2', '-ffp-contract=off', '-fno-fast-math']
            and compiled['returncode'] == 0 and argv.count('-o') == 1,
            'fullgraph shared arithmetic strict compile policy differs')
    require(argv[-4:-2] == [str(ROOT / p) for p in LIBRARY_SOURCES[:2]],
            'fullgraph shared translation units differ or duplicate Matrix array')
    require(set(compiled['source_sha256']) == set(LIBRARY_SOURCES), 'incomplete arithmetic include closure')
    for relative, digest in compiled['source_sha256'].items():
        require(file_sha(ROOT / relative) == digest, 'compiled shared source drift: ' + relative)
    binary = Path(argv[-1]).resolve()
    require(file_sha(binary) == compiled['library_sha256'], 'shared arithmetic binary changed')
    require(argv[0] == 'g++' and subprocess.check_output(['g++', '--version'], text=True,
            timeout=10).splitlines()[0] == compiled['compiler'], 'arithmetic compiler invocation changed')
    recipe = base.checked_json(base.RECIPE + '/RESULT.json')
    provenance = recipe['source_identity']
    base.strict_flags(provenance['compile_command'], shared=False)
    generated = ROOT / base.RECIPE / 'generated'
    require(provenance['compile_command'][5:] == [str(generated / 'software_recipe.cpp'),
            '-o', str(generated / 'software_recipe')], 'original oracle compile paths changed')
    artifacts = {}
    for name, key in (('software_recipe.cpp', 'generated_cpp_sha256'),
                      ('block_layout.h', 'generated_header_sha256'), ('software_recipe', 'binary_sha256')):
        target = generated / name
        require(file_sha(target) == provenance[key], 'original oracle identity changed: ' + name)
        artifacts[str(target)] = provenance[key]
    require(json.loads((generated / 'provenance.json').read_text()) == provenance,
            'original oracle provenance differs from pinned result')
    for relative, digest in provenance['source_sha256'].items():
        require(file_sha(ROOT / relative) == digest, 'original oracle source changed: ' + relative)
    return dict(compile_receipt=str(path), compile_receipt_sha256=file_sha(path),
        library=str(binary), library_sha256=file_sha(binary), compile=compiled,
        current_resolved_compiler=base.compiler_identity(),
        oracle_provenance=provenance, oracle_artifacts=artifacts, old_pass_inherited=False)


def prepare(out, compile_path, rows=16, epoch=7):
    out = Path(out).resolve()
    require(not out.exists() and rows in (16, 128), 'new snapshot and M16/M128 required')
    helper, _, fixtures, *_ = runtime()
    before, spec = source_hashes(), input_spec()[0]
    binaries = binary_identity(compile_path)
    fixture = fixtures.make_qwen2_21_fixture(rows, epoch)
    inputs = load_inputs(spec, rows)
    require(set(inputs) == {n for n, a in fixture.allocations.items() if a.readonly},
            'raw input provider coverage differs from original fullgraph allocations')
    require(all(len(raw) == fixture.allocations[n].storage_bytes for n, raw in inputs.items()),
            'raw input extent differs from public descriptor')
    oracle, oracle_identity = base.oracle_sources(runtime()[-1])
    snapshot = dict(schema=1, status='PREPARED_PUBLIC21_FULLGRAPH_NOT_EXECUTED', rows=rows, epoch=epoch,
        source_sha256=before, source_manifest_sha256=sha(encoded(before)),
        imported_python_sha256={p: before[p] for p in sorted(helper.imported_python_paths(_modules))},
        input_spec=spec, loaded_inputs=base.identities(inputs), binaries=binaries,
        metadata=helper.metadata_identity(fixture), host_tool_identity=helper.host_tool_identity(),
        oracle_source_sha256={n: sha(raw) for n, raw in oracle.items()},
        oracle_identity=oracle_identity, oracle_compiler=base.compiler_identity(),
        public_execution_executed=False, saved_stage_payloads_read=False, native_acceptance='NOT_NATIVE_ACCEPTED')
    require(before == source_hashes(), 'source changed during fullgraph preparation')
    out.mkdir(parents=True)
    for relative, digest in before.items():
        raw = (ROOT / relative).read_bytes()
        require(sha(raw) == digest, 'source changed while snapshotting: ' + relative)
        target = out / 'frozen_sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    (out / 'frozen_oracle').mkdir()
    for name, raw in oracle.items():
        (out / 'frozen_oracle' / name).write_bytes(raw)
    for name in ('command', 'descriptor'):
        table = getattr(fixture.config, name)
        (out / (name + '_table.bin')).write_bytes(fixture.memory.mappings[table.base])
    (out / 'SNAPSHOT.json').write_bytes(encoded(snapshot))
    return out / 'SNAPSHOT.json', snapshot


def verify_snapshot(path, digest):
    path = Path(path).resolve()
    require(file_sha(path) == digest, 'fullgraph reviewed snapshot SHA differs')
    s = json.loads(path.read_text())
    require(s['status'] == 'PREPARED_PUBLIC21_FULLGRAPH_NOT_EXECUTED' and
            s['source_manifest_sha256'] == sha(encoded(s['source_sha256'])) and
            not s['public_execution_executed'] and not s['saved_stage_payloads_read'], 'invalid snapshot lifecycle')
    runtime()
    require(source_hashes() == s['source_sha256'], 'live fullgraph source differs from reviewed snapshot')
    for name, expected in s['source_sha256'].items():
        require(file_sha(path.parent / 'frozen_sources' / name) == expected, 'frozen source differs: ' + name)
    for name, expected in s['oracle_source_sha256'].items():
        require(file_sha(path.parent / 'frozen_oracle' / name) == expected, 'frozen prefix oracle differs: ' + name)
    require(input_spec()[0] == s['input_spec'] and
            binary_identity(s['binaries']['compile_receipt']) == s['binaries'], 'input/binary provenance drift')
    require(base.compiler_identity() == s['oracle_compiler'], 'oracle compiler drift')
    return s


def prerequisite(path, digest, snapshot):
    require(path is not None and digest is not None and file_sha(path) == digest,
            'M128 requires exact completed M16 receipt')
    prior = json.loads(Path(path).read_text())
    require(prior['status'] == 'PASS_PUBLIC21_FULLGRAPH_SOFTWARE_NOT_NATIVE_ACCEPTED' and prior['rows'] == 16
            and prior['source_sha256'] == prior['source_sha256_after'] == snapshot['source_sha256']
            and prior['binaries'] == snapshot['binaries'] and prior['input_spec'] == snapshot['input_spec'],
            'M16 source/input/binary or terminal status mismatch')
    result = prior['execution']['host']['launch_result']
    require(result['status'] is None and result['completed'] == 21 and result['jobs'] == 17
            and prior['execution']['host']['accepted']['result_fire'] == 1,
            'M16 lacks actual whole public terminal')
    host = prior['execution']['host']
    require([c['pc'] for c in host['completions']] == list(range(21)) and
            all(c['status'] is None for c in host['completions']) and
            host['accepted']['request_fire'] == host['accepted']['owner_result_fire'] == 17 and
            host['accepted']['completion_fire'] == 21 and not host['reset_required'],
            'M16 public handshakes/poison gate incomplete')
    require(set(prior['comparison']['whole_outputs']) == set(STAGE_WIDTHS) and
            all(v['values'] == 16 * STAGE_WIDTHS[k] for k, v in prior['comparison']['whole_outputs'].items()) and
            all(v['independent_bit_mismatches'] == v['saved_bit_mismatches'] == 0
                and v['actual_sha256'] == v['independent_sha256'] == v['saved_sha256']
                for v in prior['comparison']['whole_outputs'].values()), 'M16 independent numerical gate incomplete')
    p = prior['comparison']['prefix_outputs']['outputs']
    prefix_widths = dict.fromkeys(('n0', 'qraw', 'qr', 'q'), 1536)
    prefix_widths.update(dict.fromkeys(('kraw', 'kr', 'k', 'vraw', 'v'), 256)); prefix_widths['kv'] = 512
    require(set(p) == set(base.OUTPUTS) and all(v['independent_bit_mismatches'] == 0
            and v['actual_sha256'] == v['independent_sha256'] and v['saved_bit_mismatches'] in (None, 0)
            and v['values'] == 16 * prefix_widths[k]
            for k, v in p.items()), 'M16 raw projection/KV comparison incomplete')
    return dict(path=str(Path(path).resolve()), sha256=digest)


def compare(snapshot, snapshot_path, actual, out, deadline, gate):
    """Independent original full recipe; whole terminal was already accepted."""
    import numpy as np
    require(gate.opened, 'whole comparison before actual public terminal')
    recipe = runtime()[-1]
    arena = snapshot['input_spec']['oracle_arena']
    arena_path = ROOT / arena['path']
    require(arena_path.stat().st_size == arena['bytes'] and file_sha(arena_path) == arena['sha256'],
            'original raw oracle arena changed')
    target = Path(out) / 'independent_original_fullgraph'; target.mkdir()
    timeout = min(600, deadline - time.monotonic())
    require(timeout > 0, 'no remaining original fullgraph oracle budget')
    recipe.execute(ROOT / base.RECIPE / 'generated', arena_path, snapshot['rows'], target, timeout)
    saved = base.checked_json(base.SAVED + '/RESULT.json')
    result = {}
    for i, name in enumerate(recipe.STAGE_NAMES):
        entry = saved['stages'][i]
        require(entry['phase'] == i and entry['name'] == name, 'saved canonical stage order differs')
        raw = actual[name].tobytes()
        direct = (target / ('phase_%d_%s_recipe.f32le' % (i, name))).read_bytes()
        saved_raw = (ROOT / base.SAVED / entry['path']).read_bytes()
        require(sha(saved_raw) == entry['sha256'], 'saved fullgraph producer drift: ' + name)
        saved_raw = saved_raw[:snapshot['rows'] * entry['width'] * 4]
        require(len(raw) == len(direct) == len(saved_raw), 'whole output extent mismatch: ' + name)
        words = [np.frombuffer(v, dtype='<u4') for v in (raw, direct, saved_raw)]
        result[name] = dict(values=len(raw) // 4, actual_sha256=sha(raw), independent_sha256=sha(direct),
            saved_sha256=sha(saved_raw), independent_bit_mismatches=int(np.count_nonzero(words[0] != words[1])),
            saved_bit_mismatches=int(np.count_nonzero(words[0] != words[2])))
    # Reuse the already reviewed independent prefix oracle for the three
    # unbiased projection outputs not exported by the full15-stage recipe.
    prefix = base.compare_after_checkpoint(snapshot, snapshot_path,
        {n: actual[n].tobytes() for n in base.OUTPUTS}, out, deadline, gate)
    require(file_sha(arena_path) == arena['sha256'], 'oracle mutated its original readonly input')
    return dict(whole_outputs=result, prefix_outputs=prefix, original_recipe_stages=15,
                actual_public_pcs_executed=list(range(21)), official_framework_forward=False)


def run(out, path, digest, *, wall_budget=1200, m16=None, m16_sha256=None):
    out, path = Path(out).resolve(), Path(path).resolve()
    require(not out.exists() and 0 < wall_budget <= 1200, 'new output and bounded host budget required')
    s = verify_snapshot(path, digest)
    helper, execution, fixtures, public, prefix, owners, scalar, suffix, physical_adapter, matrix, attention, _ = runtime()
    prior = prerequisite(m16, m16_sha256, s) if s['rows'] == 128 else None
    require(helper.host_tool_identity() == s['host_tool_identity'], 'host tool identity drift')
    out.mkdir(parents=True)
    started, cpu = time.monotonic(), time.process_time(); deadline = started + wall_budget
    report = dict(status='PINNED_BEFORE_EXECUTION', rows=s['rows'], epoch=s['epoch'],
        reviewed_snapshot=str(path), reviewed_snapshot_sha256=digest, source_sha256=s['source_sha256'],
        input_spec=s['input_spec'], binaries=s['binaries'], m16_prerequisite=prior,
        host_tool_identity=s['host_tool_identity'], native_acceptance='NOT_NATIVE_ACCEPTED',
        native_policy='UNCHANGED_FAIL_POLICY_PENDING', rtl_executed=False, scala_executed=False,
        actual_idma=False, hardware_cycles=None, full_wall_mac_utilization=None,
        software_handshake_ticks_are_hardware_cycles=False, old_pass_inherited=False,
        prelaunch_intermediate_payloads=[], official_framework_forward=False)
    def save():
        (out / 'summary.json').write_bytes(encoded(report))
    try:
        with base.frozen_exec(s['source_sha256']) as observed, base.reference_gate(s['input_spec']) as gate:
            f = fixtures.make_qwen2_21_fixture(s['rows'], s['epoch'])
            require(helper.metadata_identity(f) == s['metadata'], 'fullgraph original metadata drift')
            inputs = load_inputs(s['input_spec'], s['rows'])
            require(base.identities(inputs) == s['loaded_inputs'], 'frozen raw inputs changed')
            physical = prefix.PhysicalMemory(f, {n: base.bytes_provider(v) for n, v in inputs.items()})
            memory = physical_adapter.FullGraphMemory(physical)
            r = f.config.regions[3]; n = execution.numeric
            owner = n.model.FfnDrainOwnerModel(n.model.PrefixWorkspace(r.base, r.limit-r.base, s['epoch']+1, 2560),
                enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
            library = matrix.configure_library(C.CDLL(s['binaries']['library']))
            require(library.td_reset() == 0 and library.sf_reset() == 0, 'arithmetic initial environment/reset failed')
            library.sf_vector.argtypes, library.sf_vector.restype = [C.POINTER(C.c_uint32)] * 6, C.c_int
            service = matrix.MatrixService(library); shared_scalar = scalar.ScalarService()
            x = execution.PublicExecution(public.PublicFrontend(physical.metadata_port(), f.config), owner,
                n.CappedTrace(), deadline, host=public.group.HostControl(enabled=True, legacy_prefix=True,
                legacy_attention=True), prefix_owner=owners.PrefixOwner(shared_scalar),
                attention_owner=attention.AttentionOwner(service, shared_scalar), matrix_service=service)
            report.update(metadata=s['metadata'], loaded_inputs=base.identities(inputs)); save()
            (out / 'FROZEN_PINS.json').write_bytes(encoded(report))
            guarded = gate.library(library)
            report['prefix_execution'] = prefix.execute_public_prefix(x, physical, guarded, out)
            report['status'] = 'ACTUAL_PREFIX_COMPLETE_SUFFIX_PENDING'; save()
            actual, report['execution'] = suffix.execute_public_suffix(x, physical, guarded, out, memory=memory)
            require(x.launch_result is not None and x.launch_result['completed'] == 21 and
                    x.counts['result_fire'] == 1 and not x.reset_required(), 'comparison before actual whole terminal')
            require(source_hashes() == s['source_sha256'], 'source drift during fullgraph execution')
            report['status'] = 'WHOLE_TERMINAL_COMPARISON_PENDING'; save()
            gate.opened = True
            report['comparison'] = compare(s, path, actual, out, deadline, gate)
            require(all(v['independent_bit_mismatches'] == v['saved_bit_mismatches'] == 0
                        for v in report['comparison']['whole_outputs'].values()), 'whole output differs from frozen original recipe')
            require(all(v['independent_bit_mismatches'] == 0 and v['saved_bit_mismatches'] in (None, 0)
                        for v in report['comparison']['prefix_outputs']['outputs'].values()), 'prefix/raw projection oracle differs')
            report['source_sha256_after'] = source_hashes()
            require(report['source_sha256_after'] == s['source_sha256'] and
                    binary_identity(s['binaries']['compile_receipt']) == s['binaries'], 'post-execution source/binary drift')
            require(base.identities(inputs) == s['loaded_inputs'], 'readonly inputs changed during execution')
            report.update(status='PASS_PUBLIC21_FULLGRAPH_SOFTWARE_NOT_NATIVE_ACCEPTED',
                imported_python_sha256=s['imported_python_sha256'], executed_imports_observed=sorted(observed),
                host_wall_seconds=time.monotonic()-started, host_cpu_seconds=time.process_time()-cpu,
                host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save(); return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), host_wall_seconds=time.monotonic()-started)
        if 'x' in locals():
            report['failed_host'] = x.report()
        if 'physical' in locals():
            report['failed_memory'] = physical.report()
        save(); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--rows', type=int, choices=(16, 128), default=16)
    parser.add_argument('--compile-receipt', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--expected-snapshot-sha256')
    parser.add_argument('--wall-budget', type=int, default=1200)
    parser.add_argument('--m16-prerequisite', type=Path)
    parser.add_argument('--m16-sha256')
    a = parser.parse_args()
    if a.prepare_only:
        require(a.compile_receipt is not None, 'preparation requires shared library provenance')
        p, s = prepare(a.out, a.compile_receipt, a.rows)
        print(json.dumps(dict(status=s['status'], path=str(p), sha256=file_sha(p))))
    else:
        require(a.snapshot is not None and a.expected_snapshot_sha256 is not None, 'execution needs reviewed snapshot')
        r = run(a.out, a.snapshot, a.expected_snapshot_sha256, wall_budget=a.wall_budget,
                m16=a.m16_prerequisite, m16_sha256=a.m16_sha256)
        print(json.dumps({k: r[k] for k in ('status', 'rows', 'host_wall_seconds')}))
