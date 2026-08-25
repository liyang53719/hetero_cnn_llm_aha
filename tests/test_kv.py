import numpy as np

from heteronpu.kv_engine import KVPageEngine


def _tokens(count: int, heads: int = 2, dim: int = 4) -> tuple[np.ndarray, np.ndarray]:
    values = np.arange(count * heads * dim, dtype=np.float32).reshape(count, heads, dim) / 11
    return values, -values


def test_paged_append_and_read_bf16() -> None:
    k, v = _tokens(10)
    kv = KVPageEngine(page_tokens=4, physical_pages=16, kv_heads=2, head_dim=4)
    kv.append(1, 3, k[:5], v[:5])
    kv.append(1, 3, k[5:], v[5:])
    got_k, got_v = kv.read(1, 3)
    assert kv.length(1, 3) == 10
    assert len(kv.block_table(1, 3)) == 3
    np.testing.assert_allclose(got_k, k, rtol=0, atol=0.04)
    np.testing.assert_allclose(got_v, v, rtol=0, atol=0.04)
    kv.check_invariants()


def test_prefix_sharing_and_copy_on_write() -> None:
    k, v = _tokens(9)
    kv = KVPageEngine(page_tokens=4, physical_pages=16, kv_heads=2, head_dim=4)
    kv.append(10, 0, k[:8], v[:8])
    kv.share_prefix(10, 20, 0, tokens=8)
    assert kv.block_table(10, 0) == kv.block_table(20, 0)
    before = kv.pages_in_use
    kv.append(20, 0, k[8], v[8])
    # A new logical page is allocated; full shared pages remain shared.
    assert kv.pages_in_use == before + 1
    kv.check_invariants()
    src_k, _ = kv.read(10, 0)
    dst_k, _ = kv.read(20, 0)
    assert src_k.shape[0] == 8
    assert dst_k.shape[0] == 9


def test_partial_prefix_is_copied_and_int8_format_works() -> None:
    k, v = _tokens(7)
    kv = KVPageEngine(
        page_tokens=4,
        physical_pages=16,
        kv_heads=2,
        head_dim=4,
        storage_format="int8",
    )
    kv.append(0, 0, k, v)
    kv.share_prefix(0, 1, 0, tokens=6)
    got_k, got_v = kv.read(1, 0)
    assert got_k.shape[0] == 6
    np.testing.assert_allclose(got_k, k[:6], rtol=0.02, atol=0.04)
    np.testing.assert_allclose(got_v, v[:6], rtol=0.02, atol=0.04)
    kv.free_sequence(0)
    kv.free_sequence(1)
    assert kv.pages_in_use == 0
    kv.check_invariants()


def test_forked_partial_page_uses_copy_on_write() -> None:
    k, v = _tokens(7)
    extra_k, extra_v = _tokens(1)
    kv = KVPageEngine(page_tokens=4, physical_pages=16, kv_heads=2, head_dim=4)
    kv.append(0, 0, k, v)
    kv.fork_sequence(0, 1, 0)
    shared_tail = kv.block_table(0, 0)[-1]
    assert kv.block_table(1, 0)[-1] == shared_tail
    source_before, _ = kv.read(0, 0)
    kv.append(1, 0, extra_k + 99, extra_v - 99)
    assert kv.cow_copies == 1
    assert kv.block_table(1, 0)[-1] != shared_tail
    source_after, _ = kv.read(0, 0)
    np.testing.assert_array_equal(source_after, source_before)
    kv.check_invariants()
