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
SIZE = 25044
SHA = '5234e210a012323a44e4d579a16af2dbac52b47f90e974a2716e23c5d9942216'
ENTRY_PIN = (2390, '98b3fa1bddaf0b2b2f998039080ccc750462e34a1f74ab3c0ec1d5cbb6d9838a')
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

# Fixed reviewed source fixture; no native HDL execution.
FIFO_DERIVED_FIXTURE = b'// Copyright 2024 ETH Zurich and University of Bologna.\n// Solderpad Hardware License, Version 0.51, see LICENSE for details.\n// SPDX-License-Identifier: SHL-0.51\n\n// Authors:\n// - Thomas Benz  <tbenz@iis.ee.ethz.ch>\n// - Tobias Senti <tsenti@ethz.ch>\n\n`include "common_cells/assertions.svh"\n`include "common_cells/registers.svh"\n\n/// Stream FIFO that does not cut the timing path. When full; pushing data is allowed if in\n/// the same cycle data is popped. Creates longer timing paths but can use buffer space more\n/// efficiently.\nmodule cc_passthrough_stream_fifo #(\n    /// Depth can be arbitrary from 2 to 2**32\n    parameter int unsigned Depth       = 32\'d8,\n    /// Print information when the simulation launches\n    parameter bit          PrintInfo   = 1\'b0,\n    /// If the FIFO is full, allow reading and writing in the same cycle\n    parameter bit          SameCycleRW = 1\'b1,\n    /// Type of the FIFO\n    parameter type         data_t      = logic\n) (\n    /// Clock\n    input  logic                 clk_i,\n    /// Asynchronous reset active low\n    input  logic                 rst_ni,\n    /// Synchronous clear active high; clears all sequential logic\n    input  logic                 clr_i,\n    /// Fifo flush. Compared to clr_i, this only clears internal pointers.\n    /// Sufficient for most functional purposes.\n    input  logic                 flush_i,\n    /// data to push into the FIFO\n    input  data_t                data_i,\n    /// input data valid\n    input  logic                 valid_i,\n    /// FIFO is not full\n    output logic                 ready_o,\n    /// output data\n    output data_t                data_o,\n    /// FIFO is not empty\n    output logic                 valid_o,\n    /// pop head from FIFO\n    input  logic                 ready_i\n);\n    /// Bit Width of the read and write pointers\n    /// One additional bit to detect overflows\n    localparam int unsigned PointerWidth = $clog2(Depth) + 1;\n\n    // Read and write pointers\n    logic [PointerWidth-1:0]  read_ptr_d,  read_ptr_q;\n    logic [PointerWidth-1:0] write_ptr_d, write_ptr_q;\n\n    // Data\n    data_t [Depth-1:0] data_d, data_q;\n\n    // Enable storage\n    logic load_data;\n\n    assign data_o = data_q[read_ptr_q[PointerWidth-2:0]];\n\n    // Output validity\n    always_comb begin\n        if (flush_i) begin // Flush\n            valid_o     = 1\'b0;\n        end else begin\n            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1\'b1;\n        end\n    end\n\n    // Logic\n    always_comb begin\n        // Default\n        load_data   = 1\'b0;\n        read_ptr_d  = read_ptr_q;\n        write_ptr_d = write_ptr_q;\n        data_d      = data_q;\n\n        if (flush_i) begin // Flush\n            read_ptr_d  = \'0;\n            write_ptr_d = \'0;\n            ready_o     = 1\'b0;\n        end else begin\n            // Read\n            if (ready_i && valid_o) begin\n                if (read_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    read_ptr_d[PointerWidth-2:0] = \'0;\n                    read_ptr_d[PointerWidth-1]   = !read_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment counter\n                    read_ptr_d = read_ptr_q + \'d1;\n                end\n            end\n\n            // Write -> Also able to write if we read in the same cycle\n            ready_o     = (read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? 1\'b1 : write_ptr_q[PointerWidth-2:0] != read_ptr_q[PointerWidth-2:0])\n                || (SameCycleRW && ready_i && valid_o);\n\n            if (valid_i && ready_o) begin\n                load_data = 1\'b1;\n                data_d[write_ptr_q[PointerWidth-2:0]] = data_i;\n\n                if (write_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    write_ptr_d[PointerWidth-2:0] = \'0;\n                    write_ptr_d[PointerWidth-1]   = !write_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment pointer\n                    write_ptr_d = write_ptr_q + \'d1;\n                end\n            end\n        end\n    end\n\n    // Flip Flops\n    `FFARNC( read_ptr_q,  read_ptr_d, clr_i, \'0, clk_i, rst_ni)\n    `FFARNC(write_ptr_q, write_ptr_d, clr_i, \'0, clk_i, rst_ni)\n\n    `FFLARNC(data_q, data_d, load_data, clr_i, \'0, clk_i, rst_ni)\n\nendmodule\n'

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


    def test_18_cluster_selector_and_fixed_two_warning_moves_only(self):
        rows = g.warning_rows(*warnings_fixture())
        new_rows, provenance = g.migrate_fifo_warning_rows(rows, FIFO_DERIVED_FIXTURE)
        hints = INPUTS[g.PROFILE + 'structural_hints.vlt']
        baseline = g.render(FIELDS, hints, rows, '/tmp/relocated-idma')
        derived = g.render(FIELDS, hints, new_rows, '/tmp/relocated-idma', True)
        self.assertEqual(baseline['hierarchy.vlt'],
                         b'`verilator_config\nhier_block -module "qwen2_matrix_command_endpoint"\n')
        self.assertEqual(derived['hierarchy.vlt'],
                         b'`verilator_config\nhier_block -module "bf16_context_lane_cluster16_rev8b_b_candidate"\n')
        for name in ('readonly.vlt', 'dma_hints.vlt'):
            self.assertEqual(baseline[name], derived[name])
        old_lines = baseline['precision_warnings.vlt'].splitlines(keepends=True)
        new_lines = derived['precision_warnings.vlt'].splitlines(keepends=True)
        changes = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
        prefix = b'lint_off -rule WIDTHEXPAND -file "/tmp/relocated-idma/' + g.FIFO_PATH.encode() + b'" -lines '
        self.assertEqual(changes, [(prefix + b'81\n', prefix + b'88\n'),
                                   (prefix + b'100\n', prefix + b'107\n')])
        self.assertEqual(provenance['added_waivers'], 0)
        self.assertEqual([(r['original'], r['derived']) for r in provenance['fixed_line_mapping']],
                         [(81, 88), (100, 107)])
        self.assertEqual(len(new_rows), 21)
        self.assertTrue(provenance['original_warning_inventory_unchanged'])
        self.assertTrue(provenance['original_manifests_unchanged'])
        for invalid in ('true', 1, None):
            with self.assertRaisesRegex(ValueError, 'boolean'):
                g.render(FIELDS, hints, rows, '/tmp/relocated-idma', invalid)

    def test_19_migration_rejects_wrong_rule_line_hash_text_and_missing_extra(self):
        original = g.warning_rows(*warnings_fixture())
        target = next(i for i, row in enumerate(original) if row[0] == g.FIFO_PATH)
        for kind in range(5):
            bad = list(original)
            row = list(bad[target])
            if kind == 0:
                row[2] = 'WIDTHTRUNC'
            elif kind == 1:
                row[1] = 82
            elif kind == 2:
                row[3] = g.FIFO_DERIVED[1]
            elif kind == 3:
                row[0] = 'missing_fifo.sv'
            else:
                bad.append(tuple(row))
            bad[target] = tuple(row)
            with self.assertRaisesRegex(ValueError, 'original rule/line/base SHA'):
                g.migrate_fifo_warning_rows(bad, FIFO_DERIVED_FIXTURE)
        with self.assertRaisesRegex(ValueError, 'derived source identity'):
            g.migrate_fifo_warning_rows(original, b'X' + FIFO_DERIVED_FIXTURE[1:])
        bad_text = FIFO_DERIVED_FIXTURE.replace(b'if (read_ptr_q[PointerWidth-2:0] == (Depth-1))',
                                               b'if (read_ptr_q[PointerWidth-2:0] != (Depth-1))', 1)
        with mock.patch.object(g, 'sha', return_value=g.FIFO_DERIVED[1]):
            with self.assertRaisesRegex(ValueError, 'statement bytes'):
                g.migrate_fifo_warning_rows(original, bad_text)

    def test_20_mock_main_variant_defaults_and_provenance(self):
        warnings, sums, closure = warnings_fixture()
        records = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, idma, sv = root / 'repo', root / 'idma', root / 'same.sv'
            original_rows = g.warning_rows(warnings, sums, closure)
            def read(path, digest, size=None, cap=None):
                if path == sv:
                    return tiny_sv()
                if repo in path.parents:
                    return INPUTS[str(path.relative_to(repo))]
                relative = str(path.relative_to(idma))
                if relative == 'SHA256SUMS.json':
                    return json.dumps(sums).encode()
                if relative == 'SOURCE_CLOSURE.json':
                    return json.dumps(closure).encode()
                if relative == g.FIFO_PATH and digest == g.FIFO_DERIVED[1]:
                    self.assertIn(size, (None, g.FIFO_DERIVED[0]))
                    return FIFO_DERIVED_FIXTURE
                expected = {r[3] for r in original_rows if r[0] == relative}
                self.assertEqual(expected, {digest})
                line = max(r[1] for r in original_rows if r[0] == relative)
                return b'fixture\n' * line
            for option in ([], ['--cluster-boundary']):
                with mock.patch.object(g, 'checked_read', side_effect=read), \
                     mock.patch.object(g.resource, 'setrlimit'), mock.patch.object(g.signal, 'alarm'), \
                     mock.patch.object(g.os, 'sched_getaffinity', return_value={0}), \
                     mock.patch.object(g.os, 'sched_setaffinity'), \
                     mock.patch.object(g, 'write_fresh') as write, mock.patch.object(builtins, 'print'):
                    self.assertEqual(g.main(['--repo', str(repo), '--sv', str(sv), '--idma-root', str(idma),
                                             '--out', str(root / 'out')] + option), 0)
                    records.append(write.call_args.args[1])
        baseline, derived = [json.loads(files['MANIFEST.json']) for files in records]
        self.assertEqual(baseline['hierarchy']['hier_block'], ['qwen2_matrix_command_endpoint'])
        self.assertNotIn('fifo_warning_migration', baseline)
        self.assertEqual(derived['hierarchy']['hier_block'], ['bf16_context_lane_cluster16_rev8b_b_candidate'])
        self.assertEqual(derived['fifo_warning_migration']['added_waivers'], 0)
        self.assertEqual(baseline['idma_manifest_inputs'], derived['idma_manifest_inputs'])
        self.assertEqual(derived['idma_warning_sources'][g.FIFO_PATH]['sha256'], g.FIFO_DERIVED[1])
        self.assertEqual(baseline['idma_warning_sources'][g.FIFO_PATH]['sha256'], g.FIFO_BASE[1])

    def test_21_entry_identity_and_flags_before_source_compile(self):
        entry_raw = (HERE / 'ENTRY.json').read_bytes()
        self.assertEqual((len(entry_raw), hashlib.sha256(entry_raw).hexdigest()), ENTRY_PIN)
        entry = json.loads(entry_raw)
        self.assertEqual(entry['source'], {'name': SOURCE.name, 'bytes': SIZE, 'sha256': SHA})
        code = compile(entry['argv_prefix'][5], '<pinned config loader>', 'exec', dont_inherit=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'generate_4vlt.py'
            for raw in (RAW + b'x', b'X' + RAW[1:]):
                path.write_bytes(raw)
                with mock.patch.object(sys, 'argv', ['-c', str(path)]), \
                     mock.patch.object(builtins, 'compile', side_effect=RuntimeError('must not compile')) as compiler:
                    with self.assertRaisesRegex(SystemExit, 'before compile'):
                        exec(code, {})
                    compiler.assert_not_called()
        with mock.patch.object(sys, 'flags', types.SimpleNamespace(isolated=False)), \
             mock.patch.object(os, 'open', side_effect=RuntimeError('must not read source')) as reader:
            with self.assertRaises(SystemExit):
                exec(code, {})
            reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
