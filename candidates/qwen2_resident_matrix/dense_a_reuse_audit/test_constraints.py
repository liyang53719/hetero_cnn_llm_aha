import hashlib
import json
import os
from pathlib import Path

import pytest

from candidates.qwen2_resident_matrix.dense_a_reuse_audit.constraints import (
    JOBS, b_address, descriptors, groups, report, split_row, tiled_word_offset)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def source(path):
    primary = ROOT / path
    if primary.is_file():
        return primary
    alternate = os.environ.get('HETERO_AUDIT_BASE_SOURCE')
    if alternate:
        return Path(alternate) / path
    raise FileNotFoundError(f'{path}: use full repo or explicit HETERO_AUDIT_BASE_SOURCE')


def test_all_sources_pinned():
    pins = json.loads((HERE/'source_pins.json').read_text())['sources']
    for path, digest in pins.items():
        assert hashlib.sha256(source(path).read_bytes()).hexdigest() == digest, path


def test_existing_loop_and_capacity_source():
    s = source('candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala').read_text()
    assert 'new Queue(new MatrixStreamStep,4,pipe=true)' in s
    assert 'when(readContext+1.U===contexts)' in s
    assert 'readContext:=0.U;readK:=readK+1.U' in s
    b = source('candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseBanks.scala').read_text()
    assert 'Seq.fill(16)(SyncReadMem(160,UInt(256.W)))' in b
    assert 'depth.pad(12)*10.U+group.pad(12)' in b


def test_b_allocation_bijection():
    seen = {b_address(h, k, c, nh) for h in range(2) for k in range(128)
            for c in range(5) for nh in range(2)}
    assert seen == {(bank, word) for bank in range(16) for word in range(160)}


def test_real_shapes_and_tails():
    r = report()
    assert r['dense_matrix_steps'] == 1462272
    assert r['reused_a_gathers'] == 298496
    assert r['saved_a_gathers'] == 1163776
    assert groups(1536) == (5,)*9 + (3,)
    assert groups(256) == (5, 3)
    assert groups(8960) == (5,)*56


def test_reuse_preserves_per_output_k_sequence():
    for n in (32, 96, 160, 256, 1536):
        for count in groups(n):
            events = [(k, c) for k in range(17) for c in range(count)]
            for c in range(count):
                assert [k for k, context in events if context == c] == list(range(17))
            assert len({k for k, _ in events}) == 17


def test_fifo_repartition_uses_active_payload_not_dead_zero_lanes():
    r = report()
    assert 128*2 + 32*2 == 320
    assert r['fifo_active_payload_before_bytes'] == 1280
    assert r['fifo_active_payload_after_bytes'] == 1216
    assert 3*320+256 < 4*320
    assert (16+256)*2 == 544  # Nominal bundle, not retained payload claim.


def test_boundary_split_all_offsets():
    for size in (1,16,64):
        for start in range(size*2):
            for count in range(1,6):
                pieces = split_row(start,count,size)
                assert [b for first,n in pieces for b in range(first,first+n)] == list(range(start,start+count))
                assert all(first//size == (first+n-1)//size for first,n in pieces)


def test_descriptor_period_count_matches_direct_enumeration():
    for size in (16,64):
        for k,n in ((1,256),(17,1536),(67,8960)):
            for offset in (0,1,size-1):
                direct = sum(len(split_row(offset+row*(n//32)+5*g,c,size))
                             for row in range(k) for g,c in enumerate(groups(n)))
                assert descriptors(k,n,offset,size) == direct


def test_current_profile_and_serial_fences_remain_explicit():
    host = source('candidates/qwen2_resident_matrix/transposed_host/host_workspace.patch').read_text()
    assert 'pipelined && weightReadBeats==16' in host
    adapter = source('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala').read_text()
    assert 'io.streamRequest.get.ready := state === idle' in adapter
    assert 'x.address(boundaryBits-1,0).pad(16)+(newStream.beats.pad(16)<<6)>(maxBeats*64).U' in adapter
    wrapper = source('rtl/integration/idma_backend_rw_axi_flat_wrap.sv').read_text()
    assert 'req_ready_o=backend_req_ready&&!active_q&&!axi_fault_q' in wrapper
    assert 'if(rsp_valid_o&&rsp_ready_i)begin active_q<=0;response_pending_q<=0;end' in wrapper


def test_component_bounds_are_not_free_overlap():
    r = report()
    assert r['combined_a_read_admissions'] == 728576
    assert r['selected_bank_bookkeeping'] == 811520
    assert r['current_serial_weight_admission_floor'] == 2924544
    assert r['matrix_and_panel_floor'] == 1617024
    assert r['divider_options0_floor'] == 1792000
    assert r['row_descriptor_counts']['16']['min'] == 365568


def test_saved_report_exact():
    assert json.loads((HERE/'M128_COUNTS.json').read_text()) == report()


def test_bad_coordinates_fail_closed():
    for n in (0,-32,31,True):
        with pytest.raises(ValueError): groups(n)
    with pytest.raises(ValueError): b_address(0,128,0,0)
    with pytest.raises(ValueError): split_row(0,6)


def test_tiled_mapping_bijective_and_preserves_logical_weights():
    k_size,n_size = 256,256
    packed = [None]*(k_size*n_size)
    for k in range(k_size):
        for n in range(n_size):
            p = tiled_word_offset(k_size,n_size,k,n)
            assert packed[p] is None
            packed[p] = (k,n)  # Addresses/identities only; no model weights.
    assert None not in packed
    for ng in (0,160):
        cols = min(160,n_size-ng)
        for kb in (0,128):
            start = tiled_word_offset(k_size,n_size,kb,ng)
            expected = [(k,n) for k in range(kb,kb+128) for n in range(ng,ng+cols)]
            assert packed[start:start+128*cols] == expected
            assert start*2 % 1024 == 0
            assert 128*cols*2 % 1024 == 0


def test_full_shape_tiled_burst_count_and_capacity():
    count = 0
    for _,k,n in JOBS:
        for g,c in enumerate(groups(n)):
            for kb in range(0,k,128):
                first = tiled_word_offset(k,n,kb,g*160)*2
                size = 128*c*32*2
                assert first % 1024 == 0 and size % 1024 == 0
                assert size <= 40960
                count += size//1024
    assert count == report()['proposed_tiled_weight_descriptors'] == 91392
    assert count*1024 == report()['weight_bytes']


def test_existing_packer_does_not_claim_tiled_physical_layout():
    packer = source('src/heteronpu/weight_packing.py').read_text()
    assert 'DO NOT change' in packer
    assert "format='row_major_kn_bf16le'" in packer
    assert 'f.seek(((r0+row)*pn+c0)*2)' in packer
