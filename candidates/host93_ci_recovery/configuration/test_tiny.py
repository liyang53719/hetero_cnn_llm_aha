"""Pure Python source and tiny synthetic fixture tests. No real SV/main execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B.')
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent
SOURCE = HERE / 'generate_4vlt.py'
SIZE = 21954
SHA = 'b29a17b9cc39e5a93473df922ed4c87489e1e346fafb830c1fbb721e1931b81f'
RAW = SOURCE.read_bytes()

def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('source identity before compile')
    module = types.ModuleType('verified_host_config_tiny')
    module.__file__ = str(SOURCE)
    module.__verified_source_pin__ = {'bytes': SIZE, 'sha256': SHA}
    exec(compile(raw, str(SOURCE), 'exec', dont_inherit=True), module.__dict__)
    return module

g = load(RAW)
if len(sys.argv) < 3 or sys.argv[1] != '--repo':
    raise SystemExit('Supply --repo ABSOLUTE_REPO; only five pinned small data files are read.')
REPO = g.absolute(sys.argv[2])
del sys.argv[1:3]
INPUTS = {p: g.checked_read(REPO / p, digest, size) for p, (size, digest) in g.PINS.items()}
BINDING = INPUTS[g.BRIDGE + 'generated_binding.hpp']
N0 = INPUTS[g.BRIDGE + 'n0_fields.hpp']
CONTRACT = g.unique_json(INPUTS['development_snapshots/canonical_host93_same_sv_source_20261018/checker/CONTRACT.json'])
WARNINGS = g.unique_json(INPUTS[g.PROFILE + 'WARNINGS.json'])
FIELDS, ORIGINS = g.derive_fields(BINDING, N0, CONTRACT)

def tiny_sv(fields=None, paths=None):
    fields = FIELDS if fields is None else fields
    paths = g.PATHS if paths is None else paths
    lines = []
    for module in sorted(set(paths.values())):
        lines += ['module ' + module + '(', '  input clock,', '        reset', ');']
        for (owner, name), width in sorted(fields.items()):
            if owner == module and name not in ('clock', 'reset'):
                lines.append('  wire ' + ('[' + str(width - 1) + ':0] ' if width > 1 else '') + name + ';')
        for parent, name, child in sorted(g.expected_edges(paths)):
            if parent == module:
                lines += ['  ' + child + ' ' + name + ' (', '  );']
        lines += ['endmodule']
    return ('\n'.join(lines) + '\n').encode()

def warnings_fixture():
    sums = {e['file'][len(g.WARNING_PREFIX):]: e['source_sha256'] for e in WARNINGS['warnings']}
    return copy.deepcopy(WARNINGS), sums, {'admitted_input_hashes': dict(sums)}

class Tiny(unittest.TestCase):
    def test_01_source_identity_before_compile(self):
        for raw in (RAW + b'x', b'X' + RAW[1:]):
            with mock.patch.object(builtins, 'compile', side_effect=RuntimeError('must not compile')) as compiler:
                with self.assertRaisesRegex(ValueError, 'before compile'):
                    load(raw)
                compiler.assert_not_called()

    def test_02_no_execution_network_dynamic_loader_or_assert(self):
        tree = ast.parse(RAW)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        self.assertFalse(imports & {'subprocess', 'socket', 'requests', 'urllib', 'importlib'})
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        self.assertNotIn(b'exec(', RAW)

    def test_03_exact_field_union_and_overlap(self):
        self.assertEqual(len(FIELDS), 610)
        self.assertEqual(sum('binding' in o for o in ORIGINS.values()), 468)
        self.assertEqual(sum('n0' in o for o in ORIGINS.values()), 81)
        self.assertEqual(sum('same_sv_contract' in o for o in ORIGINS.values()), 75)
        self.assertEqual(sum('matrix_nine' in o for o in ORIGINS.values()), 9)
        self.assertEqual(FIELDS['MatrixPipelineService', 'steps'], 64)
        self.assertEqual(FIELDS['Qwen2ContinuousBlock', 'canonicalCosTap_value'], 512)

    def test_04_binding_missing_extra_and_scope_mismatch(self):
        marker = b'registered(s.__Vscopep_HostBlockTop,"clock",&r.HostBlockTop__DOT__clock,1,VLVT_UINT8,syms_);'
        for bad in (BINDING.replace(marker, b'', 1), BINDING + marker,
                    BINDING.replace(b'&r.HostBlockTop__DOT__clock,1', b'&r.HostBlockTop__DOT__wrong,1', 1)):
            with self.assertRaises(ValueError):
                g.derive_fields(bad, N0, CONTRACT)

    def test_05_n0_unknown_path_and_tap_unknown_extra(self):
        with self.assertRaisesRegex(ValueError, 'unknown logical path'):
            g.derive_fields(BINDING, N0.replace(b'__dma__DOT__stream', b'__unknown__DOT__stream', 1), CONTRACT)
        bad = copy.deepcopy(CONTRACT)
        bad['TAPS']['UnknownModule'] = {'canonicalExtra': 1}
        with self.assertRaises(ValueError):
            g.derive_fields(BINDING, N0, bad)
        bad = copy.deepcopy(CONTRACT)
        bad['TAPS']['SiluVectorUnit']['canonicalUnknown'] = 1
        with self.assertRaises(ValueError):
            g.derive_fields(BINDING, N0, bad)

    def test_06_tiny_610_declarations_and_paths(self):
        sv = tiny_sv()
        self.assertLess(len(sv), 40000)
        self.assertEqual(len(g.scan_declarations(sv, FIELDS, g.PATHS)), 610)

    def test_07_missing_wrong_width_and_duplicate(self):
        sv = tiny_sv()
        for bad in (sv.replace(b'  wire [63:0] steps;\n', b'', 1),
                    sv.replace(b'  wire [63:0] steps;', b'  wire [62:0] steps;', 1),
                    sv.replace(b'  wire [63:0] steps;', b'  wire [63:0] steps;\n  wire [63:0] steps;', 1)):
            with self.assertRaises(ValueError):
                g.scan_declarations(bad, FIELDS, g.PATHS)

    def test_08_hierarchy_missing_unknown_extra_wrong_type(self):
        sv = tiny_sv()
        for bad in (sv.replace(b'  MatrixPipelineService matrix (', b'  OtherModule matrix (', 1),
                    sv.replace(b'  MatrixPipelineService matrix (', b'  MatrixPipelineService unknown (', 1),
                    sv.replace(b'  MatrixPipelineService matrix (', b'  MatrixPipelineService matrix (\n  MatrixPipelineService matrix (', 1)):
            with self.assertRaises(ValueError):
                g.scan_declarations(bad, FIELDS, g.PATHS)

    def test_09_comment_string_decoys_and_declaration_shapes(self):
        sv = tiny_sv()
        for replacement in (b'// wire [63:0] steps;', b'/* wire [63:0] steps; */',
                            b'$display("wire [63:0] steps;");', b'wire [0:63] steps;',
                            b'wire [63:0] steps [0:1];'):
            with self.assertRaises(ValueError):
                g.scan_declarations(sv.replace(b'wire [63:0] steps;', replacement, 1), FIELDS, g.PATHS)
        with self.assertRaises(ValueError):
            g.scan_declarations(sv + b'/*', FIELDS, g.PATHS)

    def test_10_inherited_ansi_width(self):
        fields = {('HostBlockTop', 'a'): 32, ('HostBlockTop', 'b'): 32, ('HostBlockTop', 'c'): 1}
        sv = b'module HostBlockTop(\ninput [31:0] a,\nb,\noutput c\n);\nendmodule\n'
        self.assertEqual(len(g.scan_declarations(sv, fields, {'': 'HostBlockTop'})), 3)
        with self.assertRaises(ValueError):
            g.scan_declarations(sv.replace(b'input [31:0]', b'input [30:0]'), fields, {'': 'HostBlockTop'})

    def test_11_exact_warning_dedup_and_manifest_match(self):
        w, sums, closure = warnings_fixture()
        rows = g.warning_rows(w, sums, closure)
        self.assertEqual(len(rows), 21)
        self.assertTrue(all(r[2].startswith('WIDTH') for r in rows))
        self.assertEqual(len({r[0] for r in rows}), 6)

    def test_12_warning_digest_mismatch_unknownextra_line_traversal(self):
        for kind in range(5):
            w, sums, closure = warnings_fixture()
            if kind == 0:
                sums[next(iter(sums))] = '0' * 64
            elif kind == 1:
                w['warnings'][0]['rule'] = 'LATCH'
            elif kind == 2:
                w['warnings'][1]['line'] = 0
            elif kind == 3:
                w['warnings'][1]['file'] = g.WARNING_PREFIX + '../escape'
            else:
                w['warnings'].append(copy.deepcopy(w['warnings'][1]))
            with self.assertRaises(ValueError):
                g.warning_rows(w, sums, closure)

    def test_13_render_is_exact_scope(self):
        files = g.render(FIELDS, INPUTS[g.PROFILE + 'structural_hints.vlt'], g.warning_rows(*warnings_fixture()), '/tmp/relocated-idma')
        self.assertEqual(set(files), set(g.CONFIG_NAMES))
        self.assertEqual(files['readonly.vlt'].count(b'public_flat_rd '), 610)
        self.assertNotIn(b'*', files['readonly.vlt'])
        self.assertNotIn(b'public_flat_rw', files['readonly.vlt'])
        self.assertEqual(files['hierarchy.vlt'].count(b'hier_block '), 1)
        self.assertEqual(files['dma_hints.vlt'], INPUTS[g.PROFILE + 'structural_hints.vlt'])
        self.assertEqual(files['precision_warnings.vlt'].count(b'lint_off '), 21)
        self.assertNotIn(b'PINMISSING', files['precision_warnings.vlt'])
        self.assertIn(b'/tmp/relocated-idma/', files['precision_warnings.vlt'])

    def test_14_read_same_buffer_and_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'file'; p.write_bytes(b'abc')
            self.assertEqual(g.checked_read(p, g.sha(b'abc'), 3), b'abc')
            for size, digest in ((4, g.sha(b'abc')), (3, '0' * 64)):
                with self.assertRaises(ValueError):
                    g.checked_read(p, digest, size)
            link = Path(td) / 'link'; link.symlink_to(p)
            with self.assertRaises(OSError):
                g.checked_read(link, g.sha(b'abc'), 3)
            directory = Path(td) / 'alias'; directory.symlink_to(td)
            with self.assertRaises(OSError):
                g.checked_read(directory / 'file', g.sha(b'abc'), 3)

    def test_15_fresh_output_only_and_readback(self):
        files = {name: b'tiny\n' for name in g.CONFIG_NAMES}
        files['MANIFEST.json'] = b'{}\n'
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'out'
            g.write_fresh(out, files)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, files)
            with self.assertRaises(FileExistsError):
                g.write_fresh(out, files)
            with self.assertRaises(ValueError):
                g.write_fresh(Path(td) / 'other', dict(files, extra=b'x'))

    def test_16_duplicate_json_and_unsafe_output_paths(self):
        with self.assertRaises(ValueError):
            g.unique_json(b'{"key":1,"key":2}')
        for path in ('relative', '/tmp/../escape', '/tmp/a*', '/tmp/a"', '/tmp/with\nline'):
            with self.assertRaises(ValueError):
                g.absolute(path)

    def test_17_main_never_reads_real_sv_in_tiny(self):
        with mock.patch.object(g, 'checked_read', side_effect=RuntimeError('tiny never reads real SV')) as reader:
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                g.main(['--repo', '/tmp/repo', '--sv', '/tmp/same.sv', '--idma-root', '/tmp/idma', '--out', '/tmp/repo/out'])
            reader.assert_not_called()

if __name__ == '__main__':
    unittest.main()
