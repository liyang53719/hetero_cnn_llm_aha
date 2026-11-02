"""Synthetic generated-header tests only; no EDA/native execution."""
import copy
import json
import pathlib
import tempfile
import unittest
import first_fault_probe as m

D=pathlib.Path(__file__).resolve().parent
SCHEMA=D/'FIXED_NONHIER_SCHEMA.json'

def synthetic_header(doc):
    lines=['#ifndef VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_', '#define VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_  // guard', '#include "verilated.h"', 'class alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root final : public VerilatedModule {', '  public:']
    for r in doc['signals']:
        name,port=m.expected_member(r);w=r['width_bits']
        if port: lines.append('    VL_OUT8('+name+','+str(w-1)+',0);')
        else:
            t='CData' if w<=8 else 'SData' if w<=16 else 'IData' if w<=32 else 'QData'
            lines.append('    '+t+'/*'+str(w-1)+':0*/ '+name+';')
    return ('\n'.join(lines)+'\n};\n#endif  // guard\n').encode()

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.w=pathlib.Path(self.tmp.name).resolve()
        self.doc,_=m.load_schema(SCHEMA);self.raw=synthetic_header(self.doc)
        self.root=self.w/'VHostBlockTopV4___024root.h';self.root.write_bytes(self.raw)
        self.config=self.w/'readonly.vlt';m.write_config(SCHEMA,self.config)
        self.access=self.w/'readonly_first_fault_access.hpp';self.evidence=self.w/'evidence.json'
    def generate(self):return m.generate(SCHEMA,self.config,self.root,self.access,self.evidence)
    def test_exact_positive(self):
        e=self.generate();self.assertEqual(len(e['mappings']),114);self.assertEqual(e['root_header']['sha256'],m.digest(self.raw));self.assertEqual(self.root.read_bytes(),self.raw)
        text=self.access.read_text();self.assertIn('const VHostBlockTopV4___024root* const root = dut.rootp;',text)
        self.assertEqual(text.count('static_cast<std::uint64_t>(root->'),114)
        self.assertNotIn('eval(',text);self.assertNotIn('reinterpret_cast',text)
        self.assertEqual(self.config.read_bytes(),m.config_bytes(self.doc))
        self.assertEqual(len(self.config.read_text().splitlines()),115)
        self.assertEqual(e['accessor']['text'].encode(),self.access.read_bytes())
        self.assertLess(self.evidence.stat().st_size,128<<10)
    def test_missing(self):
        self.root.write_bytes(self.raw.replace(b'    VL_OUT8(io_resetRequired,0,0);\n',b''))
        with self.assertRaises(ValueError):self.generate()
    def test_duplicate(self):
        self.root.write_bytes(self.raw.replace(b'    VL_OUT8(io_resetRequired,0,0);',b'    VL_OUT8(io_resetRequired,0,0);\n    VL_OUT8(io_resetRequired,0,0);'))
        with self.assertRaises(ValueError):self.generate()
    def test_wrong_width(self):
        self.root.write_bytes(self.raw.replace(b'VL_OUT8(io_resetRequired,0,0)',b'VL_OUT8(io_resetRequired,1,0)'))
        with self.assertRaises(ValueError):self.generate()
    def test_wrong_storage(self):
        self.root.write_bytes(self.raw.replace(b'CData/*0:0*/',b'QData/*0:0*/',1))
        with self.assertRaises(ValueError):self.generate()
    def test_comment_hidden_decl(self):
        self.root.write_bytes(self.raw.replace(b'VL_OUT8(io_resetRequired,0,0);',b'/* VL_OUT8(io_resetRequired,0,0); */'))
        with self.assertRaises(ValueError):self.generate()
    def test_branch_injection(self):
        self.root.write_bytes(self.raw.replace(b'    VL_OUT8(io_resetRequired,0,0);',b'#if 0\n    VL_OUT8(io_resetRequired,0,0);\n#endif'))
        with self.assertRaises(ValueError):self.generate()
    def test_comment_fake_second_decl_ignored(self):
        self.root.write_bytes(self.raw.replace(b'  public:',b'  public:\n/*\n    VL_OUT8(io_resetRequired,0,0);\n*/'))
        self.generate()
    def test_schema_tamper(self):
        path=self.w/'schema.json';path.write_bytes(SCHEMA.read_bytes()+b' ')
        with self.assertRaises(ValueError):m.write_config(path,self.w/'out.vlt')
    def test_unknown_module_schema(self):
        doc=copy.deepcopy(self.doc);doc['signals'][0]['module']='TransposedDenseDownOwner'
        path=self.w/'schema.json';path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):m.write_config(path,self.w/'out.vlt')
    def test_wildcard_extra_config(self):
        self.config.write_bytes(self.config.read_bytes()+b'public_flat_rd -module "*" -var "*"\n')
        with self.assertRaises(ValueError):self.generate()
    def test_reordered_config(self):
        ls=self.config.read_text().splitlines();ls[1],ls[2]=ls[2],ls[1];self.config.write_text('\n'.join(ls)+'\n')
        with self.assertRaises(ValueError):self.generate()
    def test_input_symlink(self):
        actual=self.w/'actual.h';self.root.rename(actual);self.root.symlink_to(actual)
        with self.assertRaises(ValueError):self.generate()
    def test_output_symlink(self):
        target=self.w/'target';target.write_text('preserve');self.access.symlink_to(target)
        with self.assertRaises(ValueError):self.generate()
        self.assertEqual(target.read_text(),'preserve')
    def test_no_overwrite(self):
        self.generate()
        with self.assertRaises(ValueError):self.generate()
    def test_bad_scope(self):
        self.root.write_bytes(self.raw.replace(b'class alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root',b'class alignas(VL_CACHE_LINE_BYTES) OtherRoot'))
        with self.assertRaises(ValueError):self.generate()
    def test_wrong_path_no_alternative(self):
        self.root.write_bytes(self.raw.replace(b'HostBlockTopV4__DOT__owner__DOT__matrix__DOT__',b'HostBlockTopV4__DOT__other__DOT__matrix__DOT__'))
        with self.assertRaises(ValueError):self.generate()
    def test_empty_and_non_ascii(self):
        for raw in (b'',self.raw+b'\xff'):
            self.root.write_bytes(raw)
            with self.assertRaises((ValueError,UnicodeDecodeError)):self.generate()
    def test_no_target_in_methods(self):
        self.root.write_bytes(self.raw.replace(b'\n};',b'\n void injected(){io_resetRequired=0;}\n};'))
        with self.assertRaises(ValueError):self.generate()

if __name__=='__main__':unittest.main()
