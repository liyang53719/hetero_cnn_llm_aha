"""Stdlib-only PV geometry/capacity screen. Not an executable Attention owner.

No tensors, floating-point operations, C library, RTL or timing model are run.
The transposed route is an existing default-off candidate, not an available
Attention mode. Every report remains BLOCKED until the listed interfaces and
numerical/protocol checks exist. Five contexts never multiply issue capacity.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MACS = 4096
HEADS, KV_HEADS, HEAD_DIM, GQA = 12, 2, 128, 6
COHORT_ROWS = 32
CONTEXTS = 5
A_DEPTH, B_DEPTH, BANKS, WORD_BYTES = 1376, 160, 16, 32
SOURCE_PATHS = (
    'candidates/qwen2_live_attention_model_m128/pv32_owner.py',
    'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/owner_down.patch',
    'candidates/qwen2_resident_matrix/transposed_route/transposed_mode.patch',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala',
    'candidates/qwen2_live_fullblock_model_m128/README.md',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Cohort:
    identity: int
    kv_head: int
    rows: tuple  # (query, query_head); all share the same V vector

    @property
    def keys(self):
        return self.rows[-1][0] + 1


def cohorts(tokens=128):
    require(type(tokens) is int and 1 <= tokens <= 128, 'cold M1..M128 only')
    identity = 0
    for kv in range(KV_HEADS):
        for start in range(0, tokens * GQA, COHORT_ROWS):
            rows = tuple((index // GQA, kv * GQA + index % GQA)
                         for index in range(start, min(start + COHORT_ROWS, tokens * GQA)))
            yield Cohort(identity, kv, rows)
            identity += 1


def physical_cell(row, dimension):
    require(type(row) is int and 0 <= row < 32, 'logical row outside cohort')
    require(type(dimension) is int and 0 <= dimension < 128, 'head dimension')
    # a[r]=p[r], b[128+r]=p[16+r], b[0:128]=V, b[144:256]=0.
    return row % 16, dimension + 128 * (row // 16)


def probability_cell(context, key, row):
    require(type(context) is int and 0 <= context < CONTEXTS, 'five probability cohorts')
    require(type(key) is int and 0 <= key < 128, 'M128 key capacity')
    require(type(row) is int and 0 <= row < 32, 'cohort row')
    return 2 * context + row // 16, key, (row % 16) * 2


def capture_cell(row, dimension):
    physical_cell(row, dimension)
    # One shared 16-KiB capture, not one private buffer per context.
    # All B banks words128..159, disjoint from probability words0..127.
    return dimension // 8, 128 + row, (dimension % 8) * 4


def gather_reads(context, key):
    probability_cell(context, key, 0)
    # V lives in A banks0..7, 16 BF16 dimensions per 256-bit word.
    # K uses words128..255 in these banks and is disjoint from V.
    return [('A', bank, key) for bank in range(8)] + [
        ('B', 2 * context, key), ('B', 2 * context + 1, key)]


def check_port_batch(accesses):
    """Capacity check only; never synthesizes an unconnected read/write route."""
    used = set()
    reads, writes = set(), set()
    for mode, group, bank, word in accesses:
        require(mode in ('read', 'write') and group in ('A', 'B'), 'port kind')
        require(0 <= bank < BANKS and 0 <= word < (A_DEPTH if group == 'A' else B_DEPTH),
                'bank capacity')
        port = mode, group, bank
        require(port not in used, 'second SRAM port requested')
        used.add(port)
        (reads if mode == 'read' else writes).add((group, bank, word))
    require(not reads.intersection(writes), 'same-address read/write is not assumed')


def ratio(value):
    return dict(numerator=value.numerator, denominator=value.denominator,
                fraction=float(value), percent=float(value * 100))


def report(tokens=128):
    tiles = tuple(cohorts(tokens))
    steps, useful, emitted_values, seen = 0, 0, 0, set()
    for tile in tiles:
        for key in range(tile.keys):
            steps += 1
            useful += HEAD_DIM * sum(key <= query for query, _ in tile.rows)
            final = [(query, head) for query, head in tile.rows if key == query]
            emitted_values += bool(final)
            require(not seen.intersection(final), 'duplicate row-final capture')
            seen.update(final)
    pairs = HEADS * tokens * (tokens + 1) // 2
    require(useful == pairs * HEAD_DIM and len(seen) == tokens * HEADS,
            'causal coverage mismatch')
    qk_original_steps = pairs * 8
    pv_original_steps = pairs * 4
    # Seven full dense matrices, no padding benefit or overlapped Matrix unit:
    # Q:1536^2; K,V:1536*256; O:1536^2;
    # gate,up:1536*8960; down:8960*1536.
    dense_useful = tokens * (2 * 1536 * 1536 + 2 * 1536 * 256 + 3 * 1536 * 8960)
    whole_useful = dense_useful + 2 * useful
    require(dense_useful % MACS == 0, 'Dense ideal issue count must be integral')
    dense_ideal_issues = dense_useful // MACS
    floor_pv_free = dense_ideal_issues + qk_original_steps
    floor_candidate_pv = floor_pv_free + steps
    return dict(
        schema='qwen2-pv-gqa-static-screen-v1',
        status='STATIC_ONLY_CANDIDATE_BLOCKED', tokens=tokens,
        scope='geometry/capacity arithmetic only; no owner, numerical, protocol or RTL acceptance',
        actual_model_run=False, actual_rtl_run=False, actual_numeric_run=False,
        hardware_cycles=None, predicted_full_block_cycles=None, hardware_utilization=None,
        candidate=dict(cohorts=len(tiles), matrix_issue_steps=steps,
                       causal_useful_fmas=useful, physical_fmas_if_all_cells_run=steps * MACS,
                       row_final_captures=len(seen), emitted_wide_values_if_row_final_only=emitted_values,
                       useful_over_issued_4096_geometry=ratio(Fraction(useful, steps * MACS)),
                       geometry_is_not_cycle_or_fullblock_utilization=True,
                       contexts_change_issue_capacity=False),
        original=dict(qk_steps=qk_original_steps, pv32_steps=pv_original_steps,
                      attention_steps=qk_original_steps + pv_original_steps),
        fullblock_bound=dict(
            useful_fmas=whole_useful, ideal_dense_issues=dense_ideal_issues,
            all_nonmatrix_work_and_pv_free_cycles_lower_bound=floor_pv_free,
            fixed4096_utilization_upper_bound_pv_free=ratio(Fraction(whole_useful, MACS) / floor_pv_free),
            candidate_pv_and_all_nonmatrix_free_cycles_lower_bound=floor_candidate_pv,
            fixed4096_utilization_upper_bound_with_candidate_pv=ratio(Fraction(whole_useful, MACS) / floor_candidate_pv),
            assumptions=[
                'QK remains the original eight issues per causal query/head/key pair.',
                'The seven Dense operations get ideal full4096 packing and zero setup/drain cost.',
                'One shared Matrix accepts at most one wide issue per cycle; five contexts are storage.',
                'Memory, Scalar, Vector, SiLU, host, ACK and all other costs are zero in this optimistic bound.',
                'The first bound makes PV free; the second adds only candidate PV issued geometry.',
                'No hardware cycle count is inferred from software handshake ticks.',
            ]),
        capacity=dict(A_allocated_bytes=BANKS * A_DEPTH * WORD_BYTES,
                      B_allocated_bytes=BANKS * B_DEPTH * WORD_BYTES,
                      accumulator_bytes=5 * 16 * 256 * 4,
                      K_and_V_one_KV_head_bytes=2 * 128 * 128 * 2,
                      existing_owner_Q_row_bytes=128 * 4,
                      existing_owner_score_and_raw_probability_bytes=2 * 1024 * 4,
                      QK_softmax_preparation='one row at a time using existing owner buffers; no free concurrent Matrix issue',
                      probability_cohorts=5, probability_bytes=5 * 32 * 128 * 2,
                      single_capture_bytes=32 * 128 * 4,
                      B_used_bytes=5 * 32 * 128 * 2 + 32 * 128 * 4,
                      B_probability_words='banks0..9, words0..127; two banks per cohort',
                      B_capture_words='all16 banks, words128..159; one shared capture',
                      metadata_slots=8, wide_result_fifo_entries=2,
                      additional_arithmetic_or_SRAM=0,
                      routing_control_and_valid_bits_costed=False,
                      physical_ports_connected=False),
        blockers=[
            'Current Attention has no Dense bank lease or K/V/P scratch route; explicit ownership and generation fences are required.',
            'Current td_step permits only emit==last and aligned16 group endpoints; arbitrary causal group length and intermediate row-final emits are not implemented.',
            'A returning key/cohort/context identity must drive capture at key==query, before padded suffix updates. A live input counter is insufficient.',
            'Adding zero products after a row ends is not accepted as bit-preserving: signed-zero and original intermediate finite-check behavior remain unresolved.',
            'Existing two-result FIFO and single capture must apply real credits/backpressure; do not allocate five private captures or assume free output ACKs.',
            'Five probability cohorts fit by capacity only. Their loading, bank arbitration, RMW commits, return latency, and capture/store routes are not scheduled.',
            'Original QK/softmax order, BF16 boundaries, numerical faults and exact ACK/publication protocol require small end-to-end numerical/protocol validation.',
            'Keeping original QK excludes fullblock80/90 even with free PV and all other nonmatrix work free.',
        ],
        source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                       for name in SOURCE_PATHS},
    )


if __name__ == '__main__':
    print(json.dumps(report(), indent=2, sort_keys=True))
