#!/usr/bin/env python3
"""Explicit real Scalar initialization/FENV and five fixed environment probes only."""
import argparse
import ctypes
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_live_attention_model_m128_bounded.v2 import gates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment-only', action='store_true')
    args = parser.parse_args(argv)
    if not args.environment_only:
        print(json.dumps(dict(status='NOT_EXECUTED', scalar_initialized=False, environment_probe_count=0)))
        return 0
    gates.verify_dependencies()
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
    gate = gates.OracleGate(ROOT / 'work/qwen2_live_qkv_inputs_m128/frozen01',
        gates.OUTPUT_ROOT / 'v2_environment_probe_only',
        ROOT / 'work/qwen2_live_attention_reference_m128/frozen01/reference')
    sys.addaudithook(gate.audit)
    rejected = []
    def reject(name, operation):
        try:
            operation()
        except ValueError as error:
            rejected.append(dict(name=name, error=str(error)))
        else:
            raise ValueError('negative control admitted: ' + name)
    reject('arbitrary_direct_current_process', lambda: ctypes.CDLL(None))
    reject('environment_static_call_without_constructor', ScalarService._check_environment)
    reject('unknown_file_library', lambda: ctypes.CDLL('/tmp/not_an_approved_library.so'))
    def _check_environment():
        ctypes.CDLL(None)
    with patch.object(ScalarService, '_check_environment', staticmethod(_check_environment)):
        reject('same_named_monkeypatch_environment', ScalarService)
    # The original constructor is now restored, with unchanged source and code.
    shared = ScalarService()
    gates.require(shared.client is None and dict(shared.calls) == {}, 'environment probe executed service operations')
    gates.require(len([e for e in gate.environment_events if e['event'] == 'ctypes.dlopen']) == 1 and
                  len([e for e in gate.environment_events if e['event'] == 'ctypes.dlsym']) == 1,
                  'expected exactly one source-bound current-process handle and fegetround lookup')
    reject('second_current_process_handle', lambda: ctypes.CDLL(None))
    for role in gates.REFERENCES:
        reject('preseal_oracle_' + role,
               lambda role=role: gate.audit('open', (str(gate.reference / (role + '.f32le')), 'rb', 0)))
    for path in gate.artifacts.values():
        with path.open('rb') as stream:
            stream.read(4)
    reject('native_artifact_write', lambda: gate.audit('open', (str(gate.artifacts['library']), 'wb', 0)))
    reject('unknown_work_native', lambda: gate.audit('open', (str(ROOT / 'work/other/library.so'), 'rb', 0)))
    gates.require(not gate.opened and not gate.reference_reads, 'oracle isolation changed')
    print(json.dumps(dict(status='PASS_REAL_SCALAR_ENVIRONMENT_INITIALIZATION',
        real_audit_hook=True, scalar_initialized=True, numeric_module_imported=True,
        fixed_environment_primitive_probes=5, probe_count_basis='unchanged source-bound constructor completed',
        model_inputs_loaded=False, model_chain_executed=False, scalar_service_op_calls=dict(shared.calls),
        matrix_library_loaded=False, matrix_fma_executed=False, compile_executed=False,
        oracle_opened=False, environment_events=gate.environment_events,
        negative_controls=rejected, source_sha256=gates.pins()['scalar_source_sha256']), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
