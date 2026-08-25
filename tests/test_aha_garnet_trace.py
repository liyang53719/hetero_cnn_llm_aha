from heteronpu.aha_garnet_trace import AhaBitstreamEntry, pack_proc_packets


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
