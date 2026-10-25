"""New default-off public21 orchestration, not a native execution launcher.

The caller must independently admit normal source/module identities, providers,
ELF and runtime mappings, budgets and a unique run identity. This API does not
establish those facts from booleans. Its runtime members are the unchanged
production modules, plus the already configured, exact-pinned native handles.
No old prepare/runtime/build entrypoint is called. This candidate's command
line deliberately has no numerical execution mode.
"""
from pathlib import Path
import json
import hashlib
import time


def need(ok, message):
    if not ok:
        raise ValueError(message)


def run_actual(runtime, providers, profile, out, *, enabled=False,
               admission=None, compare_after_terminal=None, oracle_gate=None):
    """Execute real original prefix/suffix only under a future admitted caller.

    runtime attributes: original, fixtures, public, prefix, scalar, suffix,
    physical_adapter, owner_module, binding, profiles, execution, policy,
    library (configured Matrix), selected (configured SiLU). providers holds
    original readonly allocation names -> byte providers, never references.
    A comparison callback receives actual values only after the real terminal
    and registry seal; callback output is recorded, never promoted to PASS.
    """
    need(type(enabled) is bool and enabled, 'ordered fullgraph is default off')
    need(type(admission) is dict and admission.get('execution_authorized') is True,
         'future independent execution admission required')
    for name in ('source_manifest_sha256', 'profile_sha256', 'elf_sha256',
                 'runtime_manifest_sha256', 'input_manifest_sha256', 'run_id'):
        need(isinstance(admission.get(name), str) and bool(admission[name]),
             'missing independently verified admission identity: ' + name)
    rows = profile['rows']
    need(type(rows) is int and rows == 128 and
         profile.get('profile_id') == 'ordered_fullgraph_m128_terminal_capture_v1',
         'new independently reviewed M128 profile required; this patch grants no execution')
    need(profile['qk_profile'] == 2 and profile['pv_profile'] == 0 and
         profile['raw_kv_transport'] is False, 'QK2 / legacy PV0 profile required')
    need(type(profile['wall_budget']) in (int, float) and
         0 < profile['wall_budget'] <= 1800, 'bounded future wall deadline required')
    need(type(providers) is dict and all(callable(p) for p in providers.values()),
         'original readonly byte providers required')
    need(compare_after_terminal is None or callable(compare_after_terminal),
         'terminal comparison callback must be callable')
    out = Path(out).resolve()
    need(not out.exists(), 'fresh unique output required')
    # Import only our lightweight bridge/registry here. Target module loading and
    # ELF mapping belong to the source-bound caller, not this control API.
    from . import bridge, registry
    from .oracle_path_gate import ExactOraclePathGate
    from .rope_operand_capture.rope_capture import RopeOperandCapture
    need(type(oracle_gate) is ExactOraclePathGate and oracle_gate.installed and
         oracle_gate.state == 'SEALED' and not oracle_gate.comparison_attempted,
         'caller must install exact reviewed oracle-root guard before loading DUT')
    from . import stream
    dispatch, observation = bridge.make_dispatch(profile, enabled=True,
        event_stream_path=out / 'attention_service_events.q2evt')
    out.mkdir(parents=True)
    report = dict(status='PREPARED_NOT_EXECUTED', admission=dict(admission),
                  rows=rows, numeric_acceptance='TEMP', hardware_cycles=None,
                  hardware_acceptance=False, fixed_physical_macs=4096,
                  legacy_pv_upper_bound_percent=63.57, phases=[])

    def save():
        (out / 'orchestration.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')

    def phase(name):
        report['phases'].append(name)
        save()

    retained = False
    terminal_verified = False

    def retain_observation():
        # Private local evidence only. No oracle values, missing-field repair,
        # native-backed properties or public payload publication occurs here.
        nonlocal retained
        if retained:
            return
        folder = out / 'actual_attention_capture'
        folder.mkdir(exist_ok=False)
        evidence = dict(whole_terminal_verified=terminal_verified, fields={}, errors=[])
        capture = observation.get('capture')
        fields = getattr(getattr(capture, 'data', None), 'fields', {})
        for index, (name, field) in enumerate(fields.items()):
            item = dict(name=name)
            try:
                for part in ('words', 'observed', 'frequency'):
                    value = field[part]
                    raw = bytes(value) if isinstance(value, (bytes, bytearray)) else value.tobytes()
                    filename = str(index) + '_' + part + '.bin'
                    (folder / filename).write_bytes(raw)
                    item[part] = dict(file=filename, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                item['shape'] = list(field['shape'])
            except Exception as error:
                item['preservation_error'] = type(error).__name__ + ': ' + str(error)
                evidence['errors'].append(item['preservation_error'])
            evidence['fields'][name] = item
        raw_events = observation.get('service_events_raw')
        if raw_events is None:
            raw_events = observation.get('service_events')
        if raw_events is not None:
            evidence['raw_service_events'] = stream.artifact_evidence(
                raw_events, out / 'attention_service_events.q2evt', evidence_directory=folder)
        (folder / 'EVIDENCE.json').write_text(json.dumps(evidence, sort_keys=True, indent=2) + '\n')
        report['capture_evidence'] = evidence
        retained = True

    started = time.monotonic()
    try:
        with runtime.policy.reference_gate(profile['input_spec']) as gate:
            f = runtime.fixtures.make_qwen2_21_fixture(rows, profile['epoch'])
            physical = runtime.prefix.PhysicalMemory(f, providers)
            memory = runtime.physical_adapter.FullGraphMemory(physical)
            n, region = runtime.original.numeric, f.config.regions[3]
            owner = runtime.owner_module.DenseReductionOwner(
                n.model.PrefixWorkspace(region.base, region.limit - region.base,
                                        profile['epoch'] + 1, 2560),
                enable_dense_drain=True, enable_k_window=True,
                enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
            need(runtime.library.td_reset() == runtime.selected.sf_reset() == 0,
                 'initial arithmetic reset failed')
            service = runtime.binding.ProfiledMatrixService(
                runtime.library, runtime.profiles.QWEN2_QKV_PROFILE)
            shared_scalar = runtime.scalar.ScalarService()
            x = runtime.execution.ReducedPublicExecution(
                runtime.public.PublicFrontend(physical.metadata_port(), f.config),
                owner, n.CappedTrace(), started + profile['wall_budget'], fixture=f,
                host=runtime.public.group.HostControl(enabled=True, legacy_prefix=True,
                                                      legacy_attention=True),
                prefix_owner=runtime.policy.OfficialPrefixOwner(shared_scalar),
                attention_owner=runtime.policy.OfficialAttentionOwner(service, shared_scalar),
                matrix_service=service)
            silu = runtime.policy.ObservedSiluLibrary(runtime.selected, rows)
            guarded = gate.library(silu)
            phase('ORIGINAL_RESOURCES_CONSTRUCTED')
            rope_capture = RopeOperandCapture(owner=x.prefix_owner, fixture=f,
                physical=physical, rows=rows, terminal_type=registry._TerminalEvidence)
            with rope_capture:
                report['prefix_execution'] = runtime.execution.execute_public_prefix(
                    x, physical, guarded, out)
            phase('ORIGINAL_PREFIX_COMPLETE')
            actual, execution_report = runtime.suffix.execute_public_suffix(
                x, physical, guarded, out, memory=memory, attention_dispatch=dispatch)
            # Original legacy label is not a numerical qualification result.
            execution_report = dict(execution_report)
            execution_report['inherited_native_acceptance_label'] = execution_report.get('native_acceptance')
            execution_report['native_acceptance'] = 'NOT_EVALUATED_BY_EXECUTION'
            report['execution'] = execution_report
            phase('ORIGINAL_SUFFIX_RETURNED')
            terminal = registry.terminal_snapshot(x, physical, memory, execution_report)
            terminal_verified = True
            phase('WHOLE_TERMINAL_CONFIRMED')
            retain_observation()
            need(not report['capture_evidence']['errors'], 'actual capture evidence preservation failed')
            need(observation['invocations'] == 1 and observation['capture'] is not None,
                 'actual pc12 ordered dispatch was not observed exactly once')
            need(observation['capture_error'] is None and observation['service_error'] is None
                 and observation['service_events'] is not None,
                 'passive observation failed after real suffix retirement')
            oracle_gate.require_clean()
            sealed_payloads = {}
            report['registry'] = registry.seal_registry(rows=rows, actual=actual,
                execution_report=execution_report, capture_report=observation['capture_report'],
                capture_fields=observation['capture'].data.fields, silu_library=silu,
                terminal=terminal, sealed_payloads=sealed_payloads)
            report['attention_observation'] = observation['capture_report']
            report['service_event_count'] = observation['service_events']['count']
            phase('ACTUAL_REGISTRY_SEALED')
            # Opening the original isolation gate happens only here, not at
            # pc12 completion and not before the original FFN suffix terminal.
            # The original live terminal was consumed by the complete registry.
            # This seal only exports actual observed BF16 half-domain operands.
            rope_report, rope_payloads = rope_capture.seal(
                terminal=terminal, registry=report['registry'])
            report['rope_operand_observation'] = rope_report
            # Read the ORIGINAL readonly x allocation after complete registry seal.
            # Provider provenance and pre/post payload identities belong to the
            # new worker admission; this snapshot alone is not temporal proof.
            input_region = physical.regions['x']
            need(input_region['readonly'] is True and input_region['provider'] is providers['x'],
                 'original readonly x provider identity changed')
            input_x = physical.raw(input_region['base'], input_region['extent'])
            expected_x = profile['input_views']['x']
            need(type(input_x) is bytes and expected_x['shape'] == [rows, 1536] and
                 len(input_x) == expected_x['bytes'] == rows * 1536 * 4 and
                 hashlib.sha256(input_x).hexdigest() == expected_x['sha256'],
                 'terminal original x allocation differs from independently pinned input')
            terminal_values = dict(readonly_x=input_x, sealed_silu=sealed_payloads['silu'],
                x_shape=[rows, 1536], silu_shape=[rows, 8960],
                provenance='ORIGINAL_READONLY_ALLOCATION_AND_ORIGINAL_PHASE4_SEAL',
                rope_operands=rope_payloads, rope_physical_shape=[rows, 64],
                cos_sin_status='ACTUAL_OPERAND_CAPTURE_PENDING_NUMERIC_COMPARISON',
                official29_coverage='TEMP_COVERAGE_LIMITED_NO_SYNTHESIS')
            def verify_live_terminal():
                # Source-pinned original verifier checks real current backing
                # state, not a status boolean and not native-backed properties.
                registry._live_terminal(x, physical, memory, execution_report)
            gate.opened = True
            if compare_after_terminal is not None:
                report['comparison'] = oracle_gate.compare_after_live_terminal(
                    verify_live_terminal, compare_after_terminal,
                    actual, observation, report['registry'], terminal_values=terminal_values)
                phase('TERMINAL_COMPARISON_RETURNED')
            oracle_gate.require_clean()
            report['oracle_isolation'] = oracle_gate.report()
            report['status'] = 'ACTUAL_INVENTORY_COMPLETE_NUMERIC_TEMP'
            save()
            return actual, report
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = type(error).__name__ + ': ' + str(error)
        report['oracle_isolation'] = oracle_gate.report()
        report['attention_observation_error'] = observation.get('capture_error')
        report['service_observation_error'] = observation.get('service_error')
        try:
            retain_observation()
        except Exception as preservation_error:
            report['capture_preservation_error'] = type(preservation_error).__name__ + ': ' + str(preservation_error)
        save()
        raise


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--describe', action='store_true', required=True)
    p.parse_args()
    print(json.dumps(dict(status='PREPARATION_ONLY_NO_NATIVE_LAUNCH', default_enabled=False,
        future_entry='run_actual', full_numeric_status='TEMP_NOT_EXECUTED',
        required_admission='independent source/runtime/input/ELF/profile identity and execution authorization')))


if __name__ == '__main__':
    main()
