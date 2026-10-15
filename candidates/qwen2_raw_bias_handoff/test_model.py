from dataclasses import replace

import pytest

from candidates.qwen2_raw_bias_handoff.model import (
    Handoff, Pair, SharedDMA, bias_packet, bf16_container, ledger)


def setup(*, tensor='K', debug=None):
    p = Pair(7, 11, 12, tensor, 256 if tensor == 'K' else 1536,
             0x100000, 0x400000, 0x800000)
    dma = SharedDMA(p.epoch)
    return Handoff(p, dma, enabled=True, old_owners_idle=True, debug_sink=debug)


def prime(e, panel=0, value=0x3f808000):
    tag = e.reserve(panel)
    e.emit(tag, (value,)*4096)
    for half in range(2):
        req = e.poll_request()
        assert req.identity == (tag, half)
        assert req.address == e.pair.bias_base+(panel*32+half*16)*4
        e.complete(req, words=(0x34000000,)*16)
    return tag


def test_post_add_only_bf16_rounding_signed_zero_and_finite_boundary():
    raw, small = 0x3f808000, 0x34000000
    assert bias_packet((raw,)*16, (small,)*16) == (0x3f810000,)*16
    assert bias_packet((bf16_container(raw),)*16, (small,)*16) == (0x3f800000,)*16
    assert bias_packet((0x80000000,)*16, (0x80000000,)*16) == (0x80000000,)*16
    assert bias_packet((0x3f800000,)*16, (0xbf800000,)*16) == (0,)*16
    with pytest.raises(ValueError, match='overflow'):
        bf16_container(0x7f7fffff)


def test_default_off_mode_pair_span_and_epoch_gates():
    e = setup()
    with pytest.raises(ValueError, match='mode'):
        Handoff(e.pair, SharedDMA(7))
    for p in (replace(e.pair, width=1536), replace(e.pair, dst_base=e.pair.raw_base),
              replace(e.pair, bias_base=e.pair.bias_base+4), replace(e.pair, epoch=8)):
        with pytest.raises(ValueError):
            Handoff(p, SharedDMA(7), enabled=True, old_owners_idle=True)


def test_three_output_credits_no_frontier_overflow_duplicate_or_reorder():
    e = setup()
    tags = [e.reserve(i) for i in range(3)]
    with pytest.raises(ValueError, match='credits'):
        e.reserve(3)
    with pytest.raises(ValueError, match='monotonic'):
        e.reserve(1)
    e.emit(tags[1], (0,)*4096)
    assert e.poll_request() is None  # later completed tile cannot bypass head
    assert e.peak_tiles == 3 and len(e.tiles) == 3
    with pytest.raises(ValueError, match='duplicate'):
        e.emit(tags[1], (0,)*4096)
    assert e.poisoned and e.producer_pending == {tags[0], tags[2]}


def test_bias_identity_and_raw_backpressure_hold_actual_payload():
    observed = []
    e = setup(debug=lambda identity, raw: observed.append((identity, raw)))
    tag = prime(e)
    identity = e.accept_raw()
    assert identity.tile == tag and identity.packet == 0
    assert observed == [(identity, (0x3f808000,)*16)]
    assert e.output[1] == (0x3f810000,)*16
    req = e.poll_request()
    held = e.output
    for _ in range(50):
        assert e.accept_raw() is None and e.poll_request() is None
        assert e.output == held and e.dma.pending == req
    assert e.write_acks == 0 and not e.done
    e.complete(req)
    assert e.accept_raw().packet == 1


def test_shared_w_transfer_blocks_bias_request_without_extra_bus():
    e = setup()
    tag = e.reserve(0)
    e.emit(tag, (0,)*4096)
    w = e.dma.issue('w_read', ('K', 0, 32, 3), ((64*3+32)*256)*2)
    assert e.poll_request() is None and e.accept_raw() is None
    with pytest.raises(ValueError, match='credit'):
        e.dma.issue('x_read', ('n0', 0), 0)
    e.dma.complete(w)
    assert e.poll_request().kind == 'bias_read'


def test_wrong_ack_poison_preserves_original_request_until_drain():
    e = setup()
    prime(e)
    e.accept_raw()
    req = e.poll_request()
    with pytest.raises(ValueError, match='identity'):
        e.complete(replace(req, epoch=req.epoch+1))
    assert e.poisoned and e.dma.pending == req and not e.drained
    e.complete(req)
    assert e.drained and not e.done and not e.producer_done
    with pytest.raises(ValueError, match='poison'):
        e.reserve(1)


def test_bad_bias_payload_poison_drain_and_abort_with_queued_tiles():
    e = setup()
    for i in range(3):
        e.emit(e.reserve(i), (0,)*4096)
    req = e.poll_request()
    with pytest.raises(ValueError, match='length'):
        e.complete(req, words=(0,))
    assert e.poisoned and e.request == req and len(e.tiles) == 0
    e.complete(req)
    assert e.drained and not e.done


def test_all_same_stimulus_raw_observed_and_final_ack_is_separate():
    seen, writes = {}, set()
    e = setup(debug=lambda tag, raw: seen.__setitem__((tag.tile.panel, tag.packet), raw))
    for panel in range(8):
        # Actual distinct finite words identify every coordinate; no golden input.
        raw = tuple(0x3f800000+panel*4096+i for i in range(4096))
        e.emit(e.reserve(panel), raw)
        for half in range(2):
            e.complete(e.poll_request(), words=(0,)*16)
        for packet in range(256):
            identity = e.accept_raw()
            assert seen[(panel, packet)] == raw[packet*16:(packet+1)*16]
            row, half = divmod(packet, 2)
            expected = e.pair.dst_base+(row*256+32*panel+16*half)*4
            assert identity.address == expected and expected not in writes
            writes.add(expected)
            req = e.poll_request()
            if panel == 7 and packet == 255:
                assert e.producer_done and not e.done and e.dma.pending == req
            e.complete(req)
    assert e.done and len(seen) == len(writes) == 2048
    assert writes == set(range(e.pair.dst_base, e.pair.dst_base+128*256*4, 64))
    assert e.dma.stats['acked:bias_read'] == 16
    assert e.dma.stats['acked:bias_write'] == 2048


def test_memory_error_and_lost_ack_never_publish():
    e = setup()
    prime(e)
    e.accept_raw()
    req = e.poll_request()
    assert not e.done and e.write_acks == 0
    e.complete(req, error=True)
    assert e.poisoned and e.drained and not e.done and e.write_acks == 0


def test_wrong_producer_epoch_poison_retains_root_return_obligation():
    e = setup()
    tag = e.reserve(0)
    bad = replace(tag, pair=replace(tag.pair, epoch=tag.pair.epoch+1))
    with pytest.raises(ValueError, match='producer return'):
        e.emit(bad, (0,)*4096)
    assert e.poisoned and not e.drained and e.producer_pending == {tag}
    e.emit(tag, (0,)*4096)
    assert e.drained and not e.done and e.raw_packets == 0


def test_abort_retains_all_accepted_roots_and_no_new_admission():
    e = setup()
    tags = [e.reserve(i) for i in range(3)]
    e.emit(tags[1], (0,)*4096)
    e.abort()
    assert e.producer_pending == {tags[0], tags[2]} and not e.drained
    e.emit(tags[2], ())  # poisoned valid-tag return is drain-only
    assert not e.drained
    e.emit(tags[0], (), error=True)
    assert e.drained and not e.producer_done
    with pytest.raises(ValueError, match='poison'):
        e.reserve(3)


def test_nonfinite_producer_return_consumes_tag_but_never_publishes():
    e = setup()
    tag = e.reserve(0)
    with pytest.raises(ValueError, match='nonfinite'):
        e.emit(tag, (0x7f800000,)*4096)
    assert e.poisoned and e.drained and e.raw_packets == 0
    with pytest.raises(ValueError, match='poison'):
        e.reserve(1)


def test_debug_observer_exception_fails_closed_without_losing_returns():
    def failing_sink(tag, raw):
        raise RuntimeError('observer failed')
    e = setup(debug=failing_sink)
    prime(e)
    pending = e.reserve(1)
    with pytest.raises(RuntimeError, match='observer'):
        e.accept_raw()
    assert e.poisoned and e.raw_packets == 1 and not e.done and not e.drained
    e.emit(pending, ())
    assert e.drained and not e.done


def test_full_qk_cold_bus_floors_and_savings_counted_once():
    d, shared = ledger(), ledger(shared_x_lease=True)
    assert d['x_read_beats'] == 24576
    assert shared['standalone_projection_raw_ddr_floor'] == 112640
    assert shared['fused_through_final_bias_ack_floor'] == 112752
    assert shared['saved_raw_write_and_bias_read_beats'] == 28672
    assert shared['net_saved_beats'] == 28672
    assert d['fused_through_final_bias_ack_ceiling'] < shared['fused_through_final_bias_ack_ceiling'] < .8
    exported = ledger(shared_x_lease=True, debug_raw_ddr=True)
    assert exported['fused_through_final_bias_ack_floor'] == 112752+14336
    assert exported['net_saved_beats'] == 14336
    assert exported['hardware_cycles'] is None and exported['hardware_utilization'] is None
