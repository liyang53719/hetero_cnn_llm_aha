#!/usr/bin/env python3
"""Live fresh-source admission and actual-DUT binding for the Attention block.

Saved fixture/trace/DDR consistency is insufficient. Only this factory can issue
an in-process block authority; only run_case binds it to one newly run actual ELF.
The two launches in each process retain actual prior cache writes without reset.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import os
import subprocess
import sys
import weakref

# Use the public descriptor and reference modules; no candidate path overlays.
import host_bf16_attention_block_fixture as fixture
import host_bf16_attention_block_execution as execution
import host_bf16_attention_block_reference as reference
from pack_host_bf16_v_fixture import CaptureSession
from host_bf16_qkv_execution import verify_all_build_sources

ROOT = fixture.ROOT
require, sha = fixture.require, fixture.file_sha
BUILD_STATUS = 'BUILT_HOST_ATTENTION_BLOCK_NOT_NUMERICAL_PASS'
CASE_STATUS = 'PASS_PRODUCTION_HOST_ATTENTION_BLOCK_PAIR_FROZEN_RECIPE'
MODES = execution.MODES
SCOPE = 'QWEN35_LAYER3_ATTENTION_BLOCK_M1'


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


@dataclass(frozen=True)
class _Authority:
    session: CaptureSession
    projection_session: object
    attention_session: object
    full_block_reference: object
    dense_tools: object
    directory: Path
    receipt_bytes: bytes
    projection_receipt_sha256: str
    attention_receipt_sha256: str
    source_sha256: dict


_ISSUED = weakref.WeakKeyDictionary()


class FreshAttentionBlockSession:
    """Opaque live authority. There is no saved-receipt/digest constructor."""
    __slots__ = ('__weakref__',)

    def __init__(self, *args, **kwargs):
        raise TypeError('use generate_block_reference with live same-invocation authorities')

    def _authority(self):
        value = _ISSUED.get(self)
        require(value is not None, 'unissued or expired live Attention block authority')
        return value

    @property
    def directory(self):
        return self._authority().directory

    @property
    def receipt_sha256(self):
        return fixture.sha(self._authority().receipt_bytes)

    def verify(self, *, session, projection_session, attention_session):
        a = self._authority()
        require(type(session) is CaptureSession and session is a.session and session.fresh is True,
                'same live fresh capture required')
        require(type(projection_session) is reference.projection.FreshProjectionReferenceSession and
                projection_session is a.projection_session and
                type(attention_session) is reference.norm_rope.FreshAttentionReferenceSession and
                attention_session is a.attention_session, 'same live independent reference authorities required')
        projection_session.verify(session=session)
        attention_session.verify(session=session, projection_reference_session=projection_session)
        require(type(a.full_block_reference) is reference.FullBlockReferenceSession and
                type(a.dense_tools) is reference.FullBlockDenseTools,'live raw-hidden full-block graph authority')
        _, _, live_receipt = a.full_block_reference.select(session=session)
        a.dense_tools.verify()
        require(projection_session.receipt_sha256 == a.projection_receipt_sha256 and
                attention_session.receipt_sha256 == a.attention_receipt_sha256, 'upstream live reference changed')
        require(fixture.source_identity() == a.source_sha256, 'block source closure changed')
        receipt = json.loads(a.receipt_bytes)
        require(encoded(live_receipt)==a.receipt_bytes,'full-block graph differs from live factory')
        require(receipt['official_manifest_sha256'] == session.manifest_sha256, 'fresh capture identity changed')
        require(encoded(json.loads(fixture.safe_file(a.directory, 'reference_receipt.json').read_bytes())) ==
                a.receipt_bytes, 'block receipt differs from live factory')
        fixture.validate_reference_receipt(a.directory, receipt)
        require({str(p.relative_to(a.directory)) for p in a.directory.rglob('*') if p.is_file()} ==
                set(fixture.reference_inventory(receipt)) | {'reference_receipt.json'}, 'block bundle file inventory')
        require(all(not p.is_symlink() for p in a.directory.rglob('*')), 'symlink block bundle')
        return receipt


def generate_block_reference(session, projection_session, attention_session, output):
    """Compute block expectations once from live factories; do not touch DUT DDR."""
    require(type(session) is CaptureSession and session.fresh is True, 'live fresh capture required')
    require(type(projection_session) is reference.projection.FreshProjectionReferenceSession and
            type(attention_session) is reference.norm_rope.FreshAttentionReferenceSession,
            'live independent projection and Norm/RoPE authorities required')
    projection_receipt=projection_session.verify(session=session)
    attention_receipt=attention_session.verify(session=session,projection_reference_session=projection_session)
    require(projection_receipt['native_operator_gate_pass'] is True and attention_receipt['original_operator_gate_pass'] is True,
            'original component gates must pass before dense tool preparation')
    output = Path(output)
    require(not output.is_symlink(), 'block reference output symlink')
    output = output.resolve()
    require(output.is_relative_to(ROOT/'work') and output != ROOT/'work' and not output.exists(),
            'fresh reference output beneath ignored work required')
    sources = fixture.source_identity()
    # The surrounding supervised fresh runner owns the compiler slot and total
    # budget. This explicit factory is dormant during import and control tests.
    dense_tools = reference.compile_full_block_dense_tools(output.with_name(output.name+'_dense_tools'))
    graph = reference.prepare_full_block_reference(session, projection_session, attention_session,
        dense_tools, variant='baseline', launch_counts=(1,1))
    inputs, expected, receipt = graph.select(session=session)
    require(receipt['original_projection_gate_pass'] is True and receipt['original_norm_rope_gate_pass'] is True,
            'unchanged original projection/Norm/RoPE operator gates required')
    fixture.write_reference_bundle(inputs, expected, receipt, output)
    require(fixture.source_identity() == sources, 'source changed during block reference creation')
    result = object.__new__(FreshAttentionBlockSession)
    _ISSUED[result] = _Authority(session, projection_session, attention_session, graph, dense_tools, output,
        encoded(receipt), projection_session.receipt_sha256, attention_session.receipt_sha256, sources)
    result.verify(session=session, projection_session=projection_session, attention_session=attention_session)
    return result


def admit_fixture(path, *, block_session, session, projection_session, attention_session):
    require(type(block_session) is FreshAttentionBlockSession, 'live block factory authority required')
    receipt = block_session.verify(session=session, projection_session=projection_session, attention_session=attention_session)
    admitted = fixture.verify(path)
    saved = json.loads(fixture.safe_file(path, 'reference_receipt.json').read_bytes())
    require(encoded(saved) == encoded(receipt), 'fixture receipt differs from live block authority')
    # fixture.verify checks each expected/input file against this exact receipt.
    return dict(admitted, live_authorities_verified=True, block_reference_receipt_sha256=block_session.receipt_sha256,
                input_sha256={name:record['sha256'] for name,record in receipt['inputs'].items()},
                original_operator_gate_pass=receipt['original_norm_rope_gate_pass'],
                projection_native_operator_gate_pass=receipt['original_projection_gate_pass'],
                native_full_block_acceptance=False, original_native_full_block_failures=receipt['original_native_full_block_failures'])


def pack_fixture(output, *, block_session, session, projection_session, attention_session):
    require(type(block_session) is FreshAttentionBlockSession, 'live block factory authority required')
    block_session.verify(session=session, projection_session=projection_session, attention_session=attention_session)
    fixture.pack(block_session.directory, output)
    return admit_fixture(output, block_session=block_session, session=session,
                         projection_session=projection_session, attention_session=attention_session)


def _verify_tool_files(build, toolchain):
    require({'verilator_launcher','verilator_backend','firtool','java','cxx'} <= set(toolchain['tools']),
            'actual build tool inventory missing')
    for record in toolchain['tools'].values():
        path = Path(record['path'])
        require(path.is_absolute() and path.is_file() and sha(path) == record['sha256'], 'build tool changed')
    jar_root = Path(os.environ['OFFLINE_TOOLS'])/'jars' if os.environ.get('OFFLINE_TOOLS') else build/'maven'
    for name,digest in toolchain['compiler_jars_sha256'].items():
        require(sha(fixture.safe_file(jar_root, name)) == digest, 'compiler dependency changed')
    require(toolchain['compiler_jars_verified_after_build'] is True and toolchain['compiler_jars_sha256'],
            'compiler dependency identity missing')
    export = os.environ.get('IDMA_EXPORT')
    require(export and toolchain['idma_export_source_sha256'], 'pinned iDMA source identity missing')
    for name,digest in toolchain['idma_export_source_sha256'].items():
        require(sha(fixture.safe_file(Path(export), name)) == digest, 'iDMA export changed')


def build_identity(build, required_sources):
    build = Path(build)
    require(build.is_dir() and not build.is_symlink(), 'build evidence path')
    ready = json.loads(fixture.safe_file(build, 'build_ready.json').read_bytes())
    require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False and
            ready['initial_verilation_exit'] == 0, 'Attention block build-only receipt required')
    names = {'obj/VHostBlockTop':'binary_sha256', 'generated/HostBlockTop.sv':'rtl_sha256',
             'sources.sha256.json':'source_manifest_sha256', 'generated/SCOPE.json':'scope_sha256',
             'toolchain.json':'toolchain_sha256', 'actual_verilator_after.json':'actual_verilator_sha256',
             'compiler_jars.sha256.json':'compiler_jars_sha256', 'hardfloat.sha256.json':'hardfloat_manifest_sha256'}
    values = {name:sha(fixture.safe_file(build, name)) for name in names}
    require(all(values[name] == ready[key] for name,key in names.items()), 'DUT/build/tool receipt drift')
    with fixture.safe_file(build, 'obj/VHostBlockTop').open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'actual compiled ELF required')
    scope = json.loads((build/'generated/SCOPE.json').read_bytes())
    require(scope['scope'] == SCOPE and scope['attention_block_policy_version'] == 3 and scope['default_enabled'] is False,
            'wrong production Attention block profile')
    for field in ('input_norm_dut','sigmoid_gate_dut','output_projection_dut','ffn_supported','full_block_supported'):
        require(scope[field] is True, 'missing full-block owner: '+field)
    for field in ('numerical_acceptance','fault_restore_supported','full_m128_supported'):
        require(scope[field] is False, 'scope inflation: '+field)
    require((scope['max_declared_rows'],scope['active_tokens_supported'],scope['max_cache_tokens'])==(128,1,256), 'M1-only full-block scope')
    require((scope['logical_matrix_engines'],scope['physical_matrix_slices'],scope['pinned_idma_instances']) == (1,8,1)
            and scope['scalar_service_shared'] is True, 'physical resource contract')
    sources = json.loads((build/'sources.sha256.json').read_bytes())
    require(required_sources and all(sources.get(name) == digest == sha(fixture.safe_file(ROOT,name))
                                    for name,digest in required_sources.items()), 'built/live source closure mismatch')
    toolchain = json.loads((build/'toolchain.json').read_bytes())
    require(json.loads((build/'actual_verilator_after.json').read_bytes()) == ready['actual_verilator'],
            'actual Verilator ELF identity changed')
    _verify_tool_files(build, toolchain)
    values['build_ready.json'] = sha(build/'build_ready.json')
    return values


def execution_identity(output, log):
    output, log = Path(output), Path(log)
    require(output.is_dir() and not output.is_symlink() and log.is_file() and not log.is_symlink(),
            'actual execution evidence path')
    paths = list(output.rglob('*'))
    require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in paths), 'actual evidence symlink/type')
    files = {str(p.relative_to(output)):sha(p) for p in sorted(paths) if p.is_file()}
    require(files, 'actual execution artifact inventory empty')
    return dict(log_sha256=sha(log), files_sha256=files)


def verify_case_outputs(build, result):
    require(result['mode'] in MODES, 'unknown final case mode')
    label = result['mode'].replace('-', '_')
    require(execution_identity(Path(build)/label, Path(build)/(label+'.log')) == result['execution_identity'],
            'actual execution evidence changed after audit')


def run_case(build, path, mode, *, block_session, session, projection_session, attention_session, timeout_seconds=3600):
    require(mode in MODES, 'unsupported actual mode')
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 10800, 'bounded actual timeout required')
    build, path = Path(build), Path(path)
    authorities = dict(block_session=block_session, session=session, projection_session=projection_session, attention_session=attention_session)
    admitted = admit_fixture(path, **authorities)
    identity = build_identity(build, admitted['source_sha256'])
    label = mode.replace('-', '_')
    verify_all_build_sources(build, label+'_initial_source_verify.log')
    output, log = build/label, build/(label+'.log')
    require(not output.exists() and not log.exists(), 'fresh actual execution evidence required')
    try:
        with log.open('w') as stream:
            result = subprocess.run([str(build/'obj/VHostBlockTop'),str(path),str(output),mode],
                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        (build/(label+'.exit')).write_text('TIMEOUT\n')
        raise ValueError('actual two-launch Attention block timeout: '+mode) from error
    (build/(label+'.exit')).write_text(str(result.returncode)+'\n')
    require(result.returncode == 0, 'actual two-launch Attention block execution failed: '+mode)
    actual_identity = execution_identity(output, log)
    audit = execution.audit(path, output, log, mode)
    require(audit['log_sha256'] == actual_identity['log_sha256'], 'actual log changed during audit')
    require(audit['status'] == 'CONSISTENT_ATTENTION_BLOCK_ARTIFACTS_ONLY' and
            audit['actual_dut_identity_verified'] is False and audit['numerical_acceptance_eligible'] is False,
            'generic auditor cannot award numerical authority')
    require(admit_fixture(path, **authorities) == admitted, 'live admission changed during actual execution')
    require(build_identity(build, admitted['source_sha256']) == identity, 'DUT identity changed during execution')
    verify_all_build_sources(build, label+'_final_source_verify.log')
    require(len(audit['runs']) == 2 and [r['phase'] for r in audit['runs']] == list(fixture.PHASES), 'pair inventory')
    require(execution_identity(output,log) == actual_identity, 'actual execution evidence changed during audit')
    outputs = {phase:{name:actual_identity['files_sha256'][phase+'/actual_'+name+'.bf16le']
                      for name in fixture.NAMES} for phase in fixture.PHASES}
    result = dict(audit, status=CASE_STATUS, actual_dut_identity_verified=True,
        numerical_acceptance_eligible=mode == 'pass', source_immutability_verified=True,
        live_authorities_verified=True, same_dut_launches=2, resets_between_launches=0,
        intermediate_preload=False, prior_cache_preload=False, native_context_acceptance=False,
        frozen_recipe_block_acceptance=mode=='pass',full_block_m1_executed=True,
        full_block_supported=True,native_full_block_acceptance=False,overall_pass=False,
        binary_sha256=identity['obj/VHostBlockTop'], rtl_sha256=identity['generated/HostBlockTop.sv'],
        build_ready_sha256=identity['build_ready.json'], block_reference_receipt_sha256=block_session.receipt_sha256,
        actual_sha256=outputs, input_sha256=admitted['input_sha256'], execution_identity=actual_identity)
    (build/(label+'.result.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result
