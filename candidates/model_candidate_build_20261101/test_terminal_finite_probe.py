import unittest
import terminal_finite_probe as p

def header():
    text='#ifndef VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_\n#define VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_\nclass alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root final : public VerilatedModule {\npublic:\n    VL_OUT8(io_resetRequired,0,0);\n'
    text+=''.join('    IData/*31:0*/ '+p.MEMBER_PREFIX+str(r)+'_'+str(c)+';\n' for r in range(16) for c in range(256))
    return (text+'\n};\n#endif\n').encode()
class Tests(unittest.TestCase):
    def test_full(self):
        m=p.match_header(header());a=p.accessor_bytes(m);self.assertEqual(len(m),4096);self.assertEqual(a.count(b'case '),4096);self.assertIn(b'default: std::abort()',a)
    def test_config(self):
        b=p.config_bytes();self.assertEqual(b.count(b'public_flat_rd'),4096);self.assertNotIn(b'*',b)
    def test_missing(self):
        with self.assertRaises(ValueError):p.match_header(header().replace(('    IData/*31:0*/ '+p.MEMBER_PREFIX+'0_0;\n').encode(),b''))
    def test_width(self):
        with self.assertRaises(ValueError):p.match_header(header().replace(b'IData/*31:0*/',b'IData/*30:0*/',1))
    def test_duplicate(self):
        with self.assertRaises(ValueError):p.match_header(header().replace(b'\n};',('\n IData/*31:0*/ '+p.MEMBER_PREFIX+'0_0;\n};').encode()))
    def test_commented(self):
        with self.assertRaises(ValueError):p.match_header(header().replace(('IData/*31:0*/ '+p.MEMBER_PREFIX+'0_0;').encode(),('//IData/*31:0*/ '+p.MEMBER_PREFIX+'0_0;').encode()))
    def test_preprocessor(self):
        with self.assertRaises(ValueError):p.match_header(header().replace(b'public:',b'#if 0\npublic:\n#endif'))
    def test_reorder_accessor(self):
        m=p.match_header(header());m[0],m[1]=m[1],m[0]
        with self.assertRaises(ValueError):p.accessor_bytes(m)
if __name__=='__main__':unittest.main()
