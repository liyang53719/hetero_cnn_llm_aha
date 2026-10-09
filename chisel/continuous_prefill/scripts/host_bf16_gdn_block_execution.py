#!/usr/bin/env python3
"""Full-block profile of the shared physical DDR/ACK replay and DUT binding.

Native failure never erases a genuine canonical execution. It is preserved as
FAIL in overall acceptance, with its original thresholds, in the same report.
"""
from pathlib import Path
import json
import subprocess
import sys
import numpy as np

import host_bf16_gdn_core_execution as core
from host_bf16_gdn_execution import _build_identity, verify_all_build_sources
from host_bf16_qkv_execution import require, sha
from pack_host_bf16_gdn_block_fixture import (ROOT, KINDS, GdnBlockFixtureSession,
    ACTUAL_DENSE_MACS, build_layout, _write_launch, native_full_block_metrics,
    frozen_operator_metrics)

PREFIX = 'HOST_BF16_GDN_BLOCK_'
SCOPE = 'FULL_LAYER0_GDN_BLOCK_RAW_HIDDEN_TO_RESIDUAL2_AND_BOTH_STATES'
SCHEMA = core.SCHEMA
_events = lambda log: core._events(log, prefix=PREFIX)
_initial = core._initial
_native_metrics = core._native_metrics


def _frozen_gates(fixture, manifest):
    """Recompute frozen gates; preserve FAIL while the hardware chain executes."""
    fixture = Path(fixture)
    arrays = {}
    for prefix in ('expected', 'native', 'conditioned'):
        roles = ('conv', 'conv_before_silu') if prefix == 'conditioned' else KINDS[:-1] + ('history', 'state', 'conv_before_silu')
        rows = []
        for token in range(2):
            row = {}
            for role in roles:
                fp32 = role in ('prep', 'state')
                value = np.fromfile(fixture/f'{prefix}_{role}{token}.{"f32le" if fp32 else "bf16le"}', dtype='<f4' if fp32 else '<u2')
                # Preserve the original audit's state geometry.
                row[role] = value.reshape(16,128,128) if role == 'state' else value
            rows.append(row)
        arrays[prefix] = rows
    fixed = frozen_operator_metrics(arrays['expected'], arrays['native'], arrays['conditioned'])
    block = native_full_block_metrics(arrays['expected'], arrays['native'])
    require(fixed == manifest['frozen_operator_metrics'], 'frozen operator metrics changed')
    require(block == manifest['native_full_block_metrics'], 'frozen native full-block metrics changed')
    operator_pass = all(x['passed'] for x in fixed)
    native_pass = operator_pass and all(x['passed'] for x in block)
    require(manifest['native_operator_gate_pass'] is operator_pass and manifest['native_full_block_gate_pass'] is native_pass,
            'native gate result/threshold drift')
    require(manifest['native_full_block_status'] == ('PASS' if native_pass else 'FAIL'), 'native gate status drift')
    return fixed


def audit_artifacts(fixture, output, log, *, session):
    result = core.audit_artifacts(fixture, output, log, session=session, _profile=sys.modules[__name__])
    manifest = session.verify(fixture)
    native_pass = manifest['native_full_block_gate_pass']
    for run in result['runs']:
        checks = manifest['native_full_block_metrics'][run['token']]['checks']
        for name, metric in run['native_diagnostics'].items():
            if name in checks:
                metric['frozen_full_block_check'] = checks[name]
                metric['acceptance'] = ('FROZEN_FP32_STATE_ABS_REL' if name == 'state' else
                    'FROZEN_BF16_BLOCK_OUTPUT' if name == 'residual2' else 'FROZEN_BF16_OPERATOR')
    result.update(status='PASS_HOST_GDN_BLOCK_ARTIFACT_CHECK_ONLY' if native_pass else 'FAIL_HOST_GDN_BLOCK_NATIVE_ACCEPTANCE',
        scope=SCOPE, canonical_block_pass=True, canonical_core_pass=True,
        native_operator_gate_pass=manifest['native_operator_gate_pass'],
        native_full_block_gate_pass=native_pass, native_full_block_status='PASS' if native_pass else 'FAIL',
        native_full_block_metrics=manifest['native_full_block_metrics'], overall_pass=False,
        full_block_supported=True, input_norm_dut=True, o_projection_dut=True, residual_dut=True, ffn_dut=True,
        fault_restore_supported=False)
    return result


def run_case(build, fixture, *, session, label='block_cold_carried', source_root=ROOT, timeout_seconds=21600):
    """Execute the existing production full-block ELF once, on one live DUT.

    Return an explicit failing overall result when native gates fail; callers
    must gate their exit status on overall_pass, not canonical_block_pass.
    """
    build, fixture = Path(build).resolve(), Path(fixture).resolve()
    require(type(session) is GdnBlockFixtureSession, 'live GdnBlockFixtureSession required')
    require(type(timeout_seconds) is int and 0 < timeout_seconds <= 21600, 'bounded actual runtime required')
    require(type(label) is str and label and all(c.isalnum() or c in '_-' for c in label), 'invalid output label')
    manifest = session.verify(fixture); _frozen_gates(fixture, manifest)
    identity = _build_identity(build, profile='block')
    verify_all_build_sources(build, label+'_initial_source_verify.log', source_root=source_root)
    output, log = build/label, build/(label+'.log')
    require(not output.exists() and not output.is_symlink() and not log.exists() and not log.is_symlink(), 'fresh evidence paths required')
    with log.open('w') as stream:
        process = subprocess.run([str(build/'obj/VHostBlockTop'), str(fixture), str(output)], stdout=stream,
                                 stderr=subprocess.STDOUT, timeout=timeout_seconds)
    (build/(label+'.exit')).write_text(str(process.returncode)+'\n')
    require(_build_identity(build, profile='block') == identity, 'DUT identity changed during execution')
    verify_all_build_sources(build, label+'_final_source_verify.log', source_root=source_root)
    session.verify(fixture)
    require(process.returncode == 0, 'production Host GDN block execution failed; no canonical acceptance')
    result = audit_artifacts(fixture, output, log, session=session)
    passed = result['native_full_block_gate_pass']
    result.update(status='PASS_PRODUCTION_HOST_GDN_BLOCK' if passed else 'FAIL_PRODUCTION_HOST_GDN_BLOCK_NATIVE_ACCEPTANCE',
        overall_pass=passed, actual_dut_identity_verified=True, source_immutability_verified=True,
        binary_sha256=identity[str(build/'obj/VHostBlockTop')], rtl_sha256=identity[str(build/'generated/HostBlockTop.sv')],
        build_ready_sha256=identity[str(build/'build_ready.json')])
    (build/(label+'.result.json')).write_text(json.dumps(result, indent=2)+'\n')
    return result
