"""Source-only contract checker. No compiler, elaboration, simulation or cleanup."""
from pathlib import Path
import hashlib
import importlib.util
import json

C = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ffn_elementwise_checks', C/'tests/test_ffn_elementwise.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.need(hashlib.sha256(m.ORIGINAL.read_bytes()).hexdigest() == m.ORIGINAL_SHA, 'original owner SHA')
m.need(hashlib.sha256(m.BASE.read_bytes()).hexdigest() == m.BASE_SHA, 'frozen runtime base SHA')
m.source_checks(m.LEAF.read_text(), m.PROTOCOL.read_text(), m.BASE.read_text())
def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
print(json.dumps(dict(
    status='PASS_SOURCE_GRAPH_AND_TRANSPORT_CHECKS_NOT_DUT',
    source_members=[pin(m.LEAF), pin(m.PROTOCOL)],
    original_owner=pin(m.ORIGINAL), frozen_runtime_base=pin(m.BASE),
    silu_m128_f3584=m.counts(1, 128, 3584),
    attention_m128_q16=m.counts(2, 128, 4096),
    scope='Original scalar graph + BF16 boundary placement, fixed payload declarations, unchanged transport source and quota contract only; injected-exp numerical model is not hardware/Torch equivalence.',
    resource_delta=dict(new_payload_registers=0, new_fpu=0, new_matrix=0, new_formatter=0, new_bank=0,
                        operation_states_before=6, operation_states_after=7, operation_bits_before=3, operation_bits_after=3,
                        ordinary_scalar_maximum_before=2621440, ordinary_scalar_maximum_after=2752512,
                        physical_area_and_timing_verified=False)), indent=2))
