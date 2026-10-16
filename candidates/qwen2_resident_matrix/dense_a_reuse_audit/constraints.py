"""Source audit counts only; no RTL, DMA, arithmetic, or wall-cycle simulation."""
from fractions import Fraction
from math import gcd

JOBS = (('q', 1536, 1536), ('k', 1536, 256), ('v', 1536, 256),
        ('o', 1536, 1536), ('gate', 1536, 8960), ('up', 1536, 8960),
        ('down', 8960, 1536))
USEFUL = 6014828544
MACS = 4096


def groups(n):
    if type(n) is not int or n <= 0 or n % 32:
        raise ValueError('N must be positive N32 geometry')
    return tuple(min(5, n // 32 - first) for first in range(0, n // 32, 5))


def b_address(half, depth, context, nh):
    if half not in (0, 1) or not 0 <= depth < 128 or not 0 <= context < 5 or nh not in (0, 1):
        raise ValueError('B coordinate outside existing allocation')
    linear = half * 1280 + depth * 10 + 2 * context + nh
    return linear % 16, linear // 16


def split_row(first_beat, count, max_beats=16):
    """Legal contiguous descriptors; current selected profile is max_beats=16."""
    if max_beats not in (1, 16, 64) or not 1 <= count <= 5 or first_beat < 0:
        raise ValueError('invalid audited descriptor geometry')
    result = []
    while count:
        take = min(count, max_beats - first_beat % max_beats)
        result.append((first_beat, take))
        first_beat += take
        count -= take
    return tuple(result)


def descriptors(k, n, base_beat=0, max_beats=16):
    if type(k) is not int or k <= 0:
        raise ValueError('K must be positive')
    stride = n // 32
    sizes = groups(n)
    period = max_beats // gcd(stride, max_beats)
    rows = []
    for row in range(period):
        rows.append(sum(len(split_row(base_beat + row * stride + 5 * group, count, max_beats))
                        for group, count in enumerate(sizes)))
    return sum(rows) * (k // period) + sum(rows[:k % period])


def tiled_word_offset(k_size, n_size, k, n):
    """Proposed N160-group/K128 tile format. Index proof only, not a packer."""
    groups(n_size)
    if k_size <= 0 or k_size % 128 or not 0 <= k < k_size or not 0 <= n < n_size:
        raise ValueError('audit supports complete K128 tiles only')
    ng = n // 160 * 160
    cols = min(160, n_size-ng)
    return ng*k_size + k*cols + n-ng


def report():
    jobs = {name: dict(k=k, n=n, contexts=list(groups(n)), matrix_steps=k * (n // 32),
                      reused_a_gathers=k * len(groups(n))) for name, k, n in JOBS}
    steps = sum(j['matrix_steps'] for j in jobs.values())
    gathers = sum(j['reused_a_gathers'] for j in jobs.values())
    # Per-tensor bases may have independent alignments. Report bounds accordingly.
    row_descriptors = {}
    for size in (16, 64):
        per_job = [[descriptors(k, n, offset, size) for offset in range(size)]
                   for _, k, n in JOBS]
        row_descriptors[str(size)] = dict(
            min=sum(map(min, per_job)), max=sum(map(max, per_job)),
            all_bases_boundary_aligned=sum(x[0] for x in per_job))
    ideal = Fraction(USEFUL, MACS)
    return dict(scope='SOURCE_COUNTS_NOT_IMPLEMENTED_CYCLES', jobs=jobs,
                dense_matrix_steps=steps, original_a_gathers=steps,
                reused_a_gathers=gathers, saved_a_gathers=steps-gathers,
                weighted_reuse=str(Fraction(steps, gathers)),
                b_capacity_bytes=16*160*32, b_half_bytes=128*5*32*2,
                fifo_active_payload_before_bytes=4*320,
                fifo_active_payload_after_bytes=3*320+256,
                added_hold_bytes=256, ffn_column_read_events=6*71680,
                combined_a_read_admissions=gathers+6*71680,
                panel_transactions=27648, panel_service_edges=82944,
                selected_bank_bookkeeping=gathers+6*71680+82944,
                weight_bytes=steps*64, weight_beats=steps,
                current_serial_weight_admission_floor=steps*2,
                row_descriptor_counts=row_descriptors,
                proposed_tiled_weight_descriptors=steps//16,
                proposed_tiled_weight_payload_bytes=steps*64,
                current_selected_adapter_max_beats=16,
                matrix_and_panel_floor=steps+71808+82944,
                budget80=str(ideal/Fraction(4,5)), budget90=str(ideal/Fraction(9,10)),
                divider_options0_floor=25*71680,
                notes=['A-read events exclude activation ingress, norms and other clients',
                       'Panel service edges are not a count of A reads',
                       'Bank, Matrix, DMA, SFU bounds are not all additive',
                       'A reuse does not implement FFN overlap or improve W bandwidth'])
