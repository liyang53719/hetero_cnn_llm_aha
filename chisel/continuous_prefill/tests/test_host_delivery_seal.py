"""Small descriptor fixtures only: never hardware numerical evidence."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from seal_host_command_delivery import decode_tables, header_value

BASE = 0x100000000
NULL = 0xffffff

def fixture():
    words = []
    cmds = []
    def record(kind, nxt, payload): return kind | (nxt << 32) | (payload << 56)
    def tensor(addr, root, tail):
        base = (addr & ((1 << 48) - 1)) | (7 << 52) | (2 << 60) | ((addr >> 48) << 64)
        return [record(1, root + 1, base), record(2, root + 2, 16 | (1536 << 18) | (1 << 36) | (1 << 54)),
                record(3, tail, 1536 | (1 << 24) | (1 << 48))]
    for pc in range(3):
        r = pc * 10
        cmds.append(0x330 | (pc << 24) | ((pc + 1) << 40) | (r << 56) | ((r + 4) << 80) | ((r + 7) << 104))
        src = BASE if pc == 0 else BASE + 0x40000 + (pc - 1) * 98304
        words += tensor(src, r, r + 3)
        words += [record(0x20, NULL, 0x30 | (2 << 16) | (1 << 24) | (7 << 32) | (7 << 36) | (16 << 40))]
        words += tensor(BASE + 0x20000, r + 4, NULL)
        words += tensor(BASE + 0x40000 + pc * 98304, r + 7, NULL)
    cmd = b''.join(x.to_bytes(16, 'little') for x in cmds).ljust(64, b'\0')
    desc = b''.join(x.to_bytes(16, 'little') for x in words).ljust(512, b'\0')
    return cmd, desc

def verify(cmd, desc):
    return decode_tables(cmd, desc, tokens=16, hidden=1536,
                         source_y=BASE, source_x=BASE + 0x20000, output=BASE + 0x40000)

class HostDeliverySealTest(unittest.TestCase):
    def test_every_descriptor_is_decoded(self):
        rows = verify(*fixture())
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]['a'], rows[0]['dst'])
        self.assertEqual(rows[2]['a'], rows[1]['dst'])
    def test_every_payload_bit_is_bound(self):
        cmd, desc = fixture()
        # All 30 public records: changing ANY bit must fail this fixed contract.
        for bit in range(30 * 128):
            with self.subTest(bit=bit):
                bad = bytearray(desc); bad[bit // 8] ^= 1 << (bit % 8)
                with self.assertRaises(ValueError): verify(cmd, bytes(bad))
    def test_all_command_bits_are_bound(self):
        cmd, desc = fixture()
        for bit in range(3 * 128):
            with self.subTest(bit=bit):
                bad = bytearray(cmd); bad[bit // 8] ^= 1 << (bit % 8)
                with self.assertRaises(ValueError): verify(bytes(bad), desc)
    def test_truncation_is_rejected(self):
        cmd, desc = fixture()
        for a, b in [(cmd[:-1], desc), (cmd, desc[:-16])]:
            with self.assertRaises(ValueError): verify(a, b)
    def test_header_identity(self):
        self.assertEqual(header_value('static constexpr int H=1536;\n', 'H'), 1536)
        for text in ['// no geometry', 'H=1536; H=64;']:
            with self.assertRaises(ValueError): header_value(text, 'H')

if __name__ == '__main__': unittest.main()
