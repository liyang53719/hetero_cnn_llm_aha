"""Source-derived logical beat counts, not DMA cycles or measured bandwidth."""
from fractions import Fraction


def counts(rows):
    if type(rows) is not int or not 1 <= rows <= 128:
        raise ValueError('canonical selected rows 1..128 required')
    pairs = 12 * rows * (rows + 1) // 2
    k = v = 8 * pairs
    unique = 32 * rows
    return dict(scope='SOURCE_PLAN_NOT_EXECUTION', rows=rows, beat_bytes=64,
        words_per_beat=16, container_bits=32, k_extent_bytes=1024 * rows,
        v_extent_bytes=1024 * rows, direct_k_reads=k, direct_v_reads=v,
        direct_kv_reads=k + v, direct_kv_read_bytes=64 * (k + v),
        direct_q_reads=96 * rows, output_write_acks=96 * rows,
        cold_raw_cache_misses=unique, raw_cache_hits=k + v - unique,
        direct_to_cold_cached_kv_read_ratio=Fraction(k + v, unique),
        direct_raw_bank_acquires=0, direct_raw_bank_releases=0,
        installed_bank_geometry=(16, 1376, 256), extra_payload_capacity_bytes=0,
        notes='Original raw cache uses the existing shared banks but adds a different lifetime and traffic schedule.')
