import json

from heteronpu.aha_garnet_trace import AhaBitstreamEntry, load_control_table, pack_proc_packets


def test_proc_packet_packing_matches_packed_sv_bitstream_entry_order() -> None:
    entries = tuple(AhaBitstreamEntry(0x100 + index, 0xA0 + index) for index in range(9))
    packets = pack_proc_packets(entries, base_address=0x40)
    assert len(packets) == 2
    assert packets[0].address == 0x40
    assert packets[0].data & ((1 << 64) - 1) == 0x0000_0100_0000_00A0
    assert (packets[0].data >> 7 * 64) == 0x0000_0107_0000_00A7
    assert packets[0].byte_enable == (1 << 64) - 1
    assert packets[1].address == 0x80
    assert packets[1].valid_words == 1
    assert packets[1].byte_enable == 0xff


def test_control_table_preserves_axi_limits_and_groups(tmp_path) -> None:
    path = tmp_path / "control.json"
    path.write_text(json.dumps({
        "bitstream_tile": 0, "bitstream_start_address": 0, "bitstream_entries": 9,
        "bs_cfg": [{"address": 0x10, "data": 1}],
        "kernel_cfg": [{"address": 0x20, "data": 2}],
        "pcfg_start": {"address": 0x1C, "data": 1},
        "stream_start": {"address": 0x18, "data": 3},
    }))
    control = load_control_table(path)
    assert (control.bitstream_entries, control.pcfg_start.address, control.stream_start.data) == (9, 0x1C, 3)
