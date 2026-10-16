"""Source-derived necessary bounds, never a timed or accepted implementation."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def check_sources():
    pins = json.loads((HERE / 'source_pins.json').read_text())
    if (set(pins) != {'schema', 'scope', 'sources', 'own'} or
            pins['schema'] != 1 or pins['scope'] != 'READ_ONLY_SOURCE_RESOURCE_AUDIT'):
        raise ValueError('audit provenance schema')
    for group in ('sources', 'own'):
        for name, expected in pins[group].items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('noncanonical audit source')
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise ValueError('source changed: ' + name)
    return len(pins['sources'])


def scalar_primitive_trace():
    # At edge 0 idle accepts; edge 1 computes; edge 2 done retires;
    # idle can next accept at edge 3. No backpressure assumed.
    return ('accept', 'normal', 'done')


def scalar_full_exp_trace():
    return ('accept', 'expScale', 'expFloor', 'expFraction',
            *(state for _ in range(7) for state in ('expMul', 'expAdd')),
            'expFinish', 'done')


def raw_k_bank_pair(key, kv_head, stripe):
    if not (type(key) is int and 0 <= key < 128 and
            type(kv_head) is int and 0 <= kv_head < 2 and
            type(stripe) is int and 0 <= stripe < 8):
        raise ValueError('Qwen2 M128 K coordinate')
    line = 16 * key + 8 * kv_head + stripe
    return (2 * (line % 8), 2 * (line % 8) + 1)


def proposed_swizzled_cells(key, kv_head, stripe):
    """Unimplemented bijection proposal; not the existing scratch route."""
    raw_k_bank_pair(key, kv_head, stripe)
    pair = (key + stripe) % 8
    word = (key // 8) * 16 + kv_head * 8 + stripe
    return ((2 * pair, word), (2 * pair + 1, word))


def report():
    tokens, heads, head_dim = 128, 12, 128
    pairs = heads * tokens * (tokens + 1) // 2
    groups = heads * sum((n + 15) // 16 for n in range(1, tokens + 1))
    dense, useful, peak = 1462272, 6014828544, 4096
    attention = 8 * groups + tokens * (tokens + 1)
    ideal = Fraction(useful, peak)
    matrix = dense + attention
    primitive_ii = len(scalar_primitive_trace())
    exp_ii = len(scalar_full_exp_trace())
    folds = 16 * pairs
    vector_fold = 16 * groups
    # Every nonempty finite softmax row has a maximum: exp(0) takes full path.
    guaranteed_full_exp = heads * tokens
    scalar_softmax_min = 2 * pairs * primitive_ii + pairs * 3 + guaranteed_full_exp * (exp_ii - 3)

    def ceiling(cycles):
        return {'minimum_cycles': cycles, 'utilization_ceiling_percent': float(100 * ideal / cycles)}

    return dict(
        schema=1, scope='SOURCE_DERIVED_NECESSARY_BOUNDS_NOT_RTL_PREDICTION',
        tokens=tokens, useful_macs=useful, peak_mac_per_cycle=peak,
        ideal_useful_cycles=int(ideal), dense_issue_count=dense,
        causal_pairs=pairs, qk_groups=groups, packed_attention_issue_count=attention,
        matrix_issue_floor=matrix, fold_adds=folds,
        scalar_add_minimum_request_spacing=primitive_ii,
        full_exp_minimum_request_spacing=exp_ii,
        serial_fold_service_only=ceiling(matrix + folds * primitive_ii),
        serial_original_owner_fold_only=ceiling(matrix + folds * 5),
        scalar_fold_perfect_overlap_unimplementable=ceiling(max(matrix, folds * primitive_ii)),
        hypothetical_vector_fold_only=ceiling(matrix + vector_fold),
        hypothetical_vector_fold_and_scale_only=ceiling(matrix + vector_fold + groups),
        scalar_softmax_subtract_and_sum_minimum=2 * pairs * primitive_ii,
        scalar_softmax_exp_subtract_sum_minimum=scalar_softmax_min,
        guaranteed_full_exp_rows=guaranteed_full_exp,
        serial_vector_fold_scale_existing_softmax=ceiling(matrix + vector_fold + groups + scalar_softmax_min),
        overhead_budget_80=int(ideal * Fraction(5, 4) - matrix),
        overhead_budget_90_exact=str(ideal * Fraction(10, 9) - matrix),
        raw_k_line_reads_without_head_reuse=8 * pairs,
        raw_k_line_reads_if_six_heads_share_each_read=8 * pairs // 6,
        raw_k_same_stripe_distinct_bank_pairs=len({raw_k_bank_pair(k, 0, 0) for k in range(16)}),
        silu_vectors=tokens * 8960 // 16,
        silu_service_minimum_excluding_division=(tokens * 8960 // 16) * (3 + 4 * primitive_ii),
        silu_all_full_exp_service_excluding_division=(tokens * 8960 // 16) * (exp_ii + 4 * primitive_ii),
        extra_mac_units=0, implemented_overlap=False, rtl_executed=False,
        actual_hardware_cycles=None, accepted_80=False, accepted_90=False,
        omitted=('matrix_latency_and_group_bubbles', 'operand_feed', 'DDR_ACKs',
                 'division', 'other_block_operations', 'new_mux_timing', 'backpressure'))


if __name__ == '__main__':
    check_sources()
    print(json.dumps(report(), indent=2, sort_keys=True))
