"""Synthetic ZIP and semantic-contract tests only; no real archive or native tools."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B test_tiny.py.')
import ast
import builtins
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
import types
import unittest
from unittest import mock
import warnings
import zipfile

HERE = Path(__file__).absolute().parent
SOURCE = HERE / 'extract_idma.py'
RAW = SOURCE.read_bytes()
SIZE = 22764
SHA = '2efd8b77e61ce68d01af2217e8e7a772da5ad46336531f5c21107cd0a7e2b532'


def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('source identity before compile')
    module = types.ModuleType('verified_tiny_idma')
    module.__file__ = str(SOURCE)
    module.__verified_source_pin__ = {'bytes': SIZE, 'sha256': SHA}
    exec(compile(raw, str(SOURCE), 'exec', dont_inherit=True), module.__dict__)
    return module


g = load(RAW)


def zipped(rows=None):
    if rows is None:
        rows = [('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644)]
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as z:
            for name, data, mode in rows:
                i = zipfile.ZipInfo(name)
                i.create_system = 3
                i.external_attr = mode << 16
                z.writestr(i, data)
    return buffer.getvalue()


def inspect(raw, count=1, size=3, digest=None):
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as z:
        index = g.index_zip(z, count)
        return g.member(z, index, 'idma_export/a.sv', size, digest or g.sha(b'abc'))


def contract_fixture():
    sources = ['idma/s' + str(i) + '.sv' for i in range(294)]
    headers = ['idma/h' + str(i) + '.svh' for i in range(18)]
    admitted = {name: g.sha(b'abc') for name in sources + headers}
    manifest = dict(admitted)
    for name in set(g.EXTRAS) - {'SHA256SUMS.json'} | {g.CLOCK}:
        manifest[name] = g.sha(b'abc')
    for i in range(927 - len(manifest)):
        manifest['extra' + str(i)] = g.sha(b'x')
    closure = {'schema': 2, 'source_files': 294, 'include_directories': 8,
               'initial_filelist_defines': dict(g.DEFINES), 'admitted_input_hashes': admitted}
    lines = ['+define+' + name for name in g.DEFINES]
    lines += ['+incdir+@ROOT@/inc' + str(i) for i in range(8)]
    lines += ['@ROOT@/' + name for name in sources]
    return manifest, closure, ('\n'.join(lines) + '\n').encode()


# Fixed reviewed source fixture, not a live archive or repository input.
FIFO_BASE_FIXTURE = b'// Copyright 2024 ETH Zurich and University of Bologna.\n// Solderpad Hardware License, Version 0.51, see LICENSE for details.\n// SPDX-License-Identifier: SHL-0.51\n\n// Authors:\n// - Thomas Benz  <tbenz@iis.ee.ethz.ch>\n// - Tobias Senti <tsenti@ethz.ch>\n\n`include "common_cells/assertions.svh"\n`include "common_cells/registers.svh"\n\n/// Stream FIFO that does not cut the timing path. When full; pushing data is allowed if in\n/// the same cycle data is popped. Creates longer timing paths but can use buffer space more\n/// efficiently.\nmodule cc_passthrough_stream_fifo #(\n    /// Depth can be arbitrary from 2 to 2**32\n    parameter int unsigned Depth       = 32\'d8,\n    /// Print information when the simulation launches\n    parameter bit          PrintInfo   = 1\'b0,\n    /// If the FIFO is full, allow reading and writing in the same cycle\n    parameter bit          SameCycleRW = 1\'b1,\n    /// Type of the FIFO\n    parameter type         data_t      = logic\n) (\n    /// Clock\n    input  logic                 clk_i,\n    /// Asynchronous reset active low\n    input  logic                 rst_ni,\n    /// Synchronous clear active high; clears all sequential logic\n    input  logic                 clr_i,\n    /// Fifo flush. Compared to clr_i, this only clears internal pointers.\n    /// Sufficient for most functional purposes.\n    input  logic                 flush_i,\n    /// data to push into the FIFO\n    input  data_t                data_i,\n    /// input data valid\n    input  logic                 valid_i,\n    /// FIFO is not full\n    output logic                 ready_o,\n    /// output data\n    output data_t                data_o,\n    /// FIFO is not empty\n    output logic                 valid_o,\n    /// pop head from FIFO\n    input  logic                 ready_i\n);\n    /// Bit Width of the read and write pointers\n    /// One additional bit to detect overflows\n    localparam int unsigned PointerWidth = $clog2(Depth) + 1;\n\n    // Read and write pointers\n    logic [PointerWidth-1:0]  read_ptr_d,  read_ptr_q;\n    logic [PointerWidth-1:0] write_ptr_d, write_ptr_q;\n\n    // Data\n    data_t [Depth-1:0] data_d, data_q;\n\n    // Enable storage\n    logic load_data;\n\n    assign data_o = data_q[read_ptr_q[PointerWidth-2:0]];\n\n    // Logic\n    always_comb begin\n        // Default\n        load_data   = 1\'b0;\n        read_ptr_d  = read_ptr_q;\n        write_ptr_d = write_ptr_q;\n        data_d      = data_q;\n\n        if (flush_i) begin // Flush\n            read_ptr_d  = \'0;\n            write_ptr_d = \'0;\n            valid_o     = 1\'b0;\n            ready_o     = 1\'b0;\n        end else begin\n            // Read\n            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1\'b1;\n            if (ready_i && valid_o) begin\n                if (read_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    read_ptr_d[PointerWidth-2:0] = \'0;\n                    read_ptr_d[PointerWidth-1]   = !read_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment counter\n                    read_ptr_d = read_ptr_q + \'d1;\n                end\n            end\n\n            // Write -> Also able to write if we read in the same cycle\n            ready_o     = (read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? 1\'b1 : write_ptr_q[PointerWidth-2:0] != read_ptr_q[PointerWidth-2:0])\n                || (SameCycleRW && ready_i && valid_o);\n\n            if (valid_i && ready_o) begin\n                load_data = 1\'b1;\n                data_d[write_ptr_q[PointerWidth-2:0]] = data_i;\n\n                if (write_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    write_ptr_d[PointerWidth-2:0] = \'0;\n                    write_ptr_d[PointerWidth-1]   = !write_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment pointer\n                    write_ptr_d = write_ptr_q + \'d1;\n                end\n            end\n        end\n    end\n\n    // Flip Flops\n    `FFARNC( read_ptr_q,  read_ptr_d, clr_i, \'0, clk_i, rst_ni)\n    `FFARNC(write_ptr_q, write_ptr_d, clr_i, \'0, clk_i, rst_ni)\n\n    `FFLARNC(data_q, data_d, load_data, clr_i, \'0, clk_i, rst_ni)\n\nendmodule\n'


FIFO_DERIVED_FIXTURE = b'// Copyright 2024 ETH Zurich and University of Bologna.\n// Solderpad Hardware License, Version 0.51, see LICENSE for details.\n// SPDX-License-Identifier: SHL-0.51\n\n// Authors:\n// - Thomas Benz  <tbenz@iis.ee.ethz.ch>\n// - Tobias Senti <tsenti@ethz.ch>\n\n`include "common_cells/assertions.svh"\n`include "common_cells/registers.svh"\n\n/// Stream FIFO that does not cut the timing path. When full; pushing data is allowed if in\n/// the same cycle data is popped. Creates longer timing paths but can use buffer space more\n/// efficiently.\nmodule cc_passthrough_stream_fifo #(\n    /// Depth can be arbitrary from 2 to 2**32\n    parameter int unsigned Depth       = 32\'d8,\n    /// Print information when the simulation launches\n    parameter bit          PrintInfo   = 1\'b0,\n    /// If the FIFO is full, allow reading and writing in the same cycle\n    parameter bit          SameCycleRW = 1\'b1,\n    /// Type of the FIFO\n    parameter type         data_t      = logic\n) (\n    /// Clock\n    input  logic                 clk_i,\n    /// Asynchronous reset active low\n    input  logic                 rst_ni,\n    /// Synchronous clear active high; clears all sequential logic\n    input  logic                 clr_i,\n    /// Fifo flush. Compared to clr_i, this only clears internal pointers.\n    /// Sufficient for most functional purposes.\n    input  logic                 flush_i,\n    /// data to push into the FIFO\n    input  data_t                data_i,\n    /// input data valid\n    input  logic                 valid_i,\n    /// FIFO is not full\n    output logic                 ready_o,\n    /// output data\n    output data_t                data_o,\n    /// FIFO is not empty\n    output logic                 valid_o,\n    /// pop head from FIFO\n    input  logic                 ready_i\n);\n    /// Bit Width of the read and write pointers\n    /// One additional bit to detect overflows\n    localparam int unsigned PointerWidth = $clog2(Depth) + 1;\n\n    // Read and write pointers\n    logic [PointerWidth-1:0]  read_ptr_d,  read_ptr_q;\n    logic [PointerWidth-1:0] write_ptr_d, write_ptr_q;\n\n    // Data\n    data_t [Depth-1:0] data_d, data_q;\n\n    // Enable storage\n    logic load_data;\n\n    assign data_o = data_q[read_ptr_q[PointerWidth-2:0]];\n\n    // Output validity\n    always_comb begin\n        if (flush_i) begin // Flush\n            valid_o     = 1\'b0;\n        end else begin\n            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1\'b1;\n        end\n    end\n\n    // Output readiness\n    always_comb begin\n        if (flush_i) begin // Flush\n            ready_o     = 1\'b0;\n        end else begin\n            ready_o     = (read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n                ? 1\'b1 : write_ptr_q[PointerWidth-2:0] != read_ptr_q[PointerWidth-2:0])\n                || (SameCycleRW && ready_i && valid_o);\n        end\n    end\n\n    // Logic\n    always_comb begin\n        // Default\n        load_data   = 1\'b0;\n        read_ptr_d  = read_ptr_q;\n        write_ptr_d = write_ptr_q;\n        data_d      = data_q;\n\n        if (flush_i) begin // Flush\n            read_ptr_d  = \'0;\n            write_ptr_d = \'0;\n        end else begin\n            // Read\n            if (ready_i && valid_o) begin\n                if (read_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    read_ptr_d[PointerWidth-2:0] = \'0;\n                    read_ptr_d[PointerWidth-1]   = !read_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment counter\n                    read_ptr_d = read_ptr_q + \'d1;\n                end\n            end\n\n            // Write -> Also able to write if we read in the same cycle\n\n            if (valid_i && ready_o) begin\n                load_data = 1\'b1;\n                data_d[write_ptr_q[PointerWidth-2:0]] = data_i;\n\n                if (write_ptr_q[PointerWidth-2:0] == (Depth-1)) begin\n                    // On overflow reset pointer to zero and flip imaginary bit\n                    write_ptr_d[PointerWidth-2:0] = \'0;\n                    write_ptr_d[PointerWidth-1]   = !write_ptr_q[PointerWidth-1];\n                end else begin\n                    // Increment pointer\n                    write_ptr_d = write_ptr_q + \'d1;\n                end\n            end\n        end\n    end\n\n    // Flip Flops\n    `FFARNC( read_ptr_q,  read_ptr_d, clr_i, \'0, clk_i, rst_ni)\n    `FFARNC(write_ptr_q, write_ptr_d, clr_i, \'0, clk_i, rst_ni)\n\n    `FFLARNC(data_q, data_d, load_data, clr_i, \'0, clk_i, rst_ni)\n\nendmodule\n'

def fifo_selection_fixture():
    names = [g.FIFO_PATH, 'SHA256SUMS.json', 'SOURCE_CLOSURE.json'] + [
        'synthetic/source' + str(i) + '.sv' for i in range(316)]
    remaining = 3072200 - len(FIFO_BASE_FIXTURE)
    contents = [FIFO_BASE_FIXTURE] + [b'x' * (remaining // 318) for i in range(317)]
    contents.append(b'x' * (remaining - sum(map(len, contents[1:]))))
    return [({'zip_member': g.PREFIX + name, 'relative_destination': name,
              'bytes': len(raw), 'sha256': g.sha(raw)}, raw)
            for name, raw in zip(names, contents)]


class Tiny(unittest.TestCase):
    def test_01_source_bad_size_same_length_sha_precompile(self):
        for raw in (RAW + b'x', b'X' + RAW[1:]):
            with mock.patch.object(builtins, 'compile', side_effect=RuntimeError('no compile')) as compiler:
                with self.assertRaisesRegex(ValueError, 'before compile'):
                    load(raw)
                compiler.assert_not_called()

    def test_02_no_bare_assert_importlib_network_subprocess(self):
        nodes = list(ast.walk(ast.parse(RAW)))
        self.assertFalse(any(isinstance(node, ast.Assert) for node in nodes))
        imports = {a.name for n in nodes if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {'subprocess', 'requests', 'socket', 'urllib', 'importlib'})
        self.assertNotIn(b'exec(', RAW)
        self.assertNotIn(b'.extractall(', RAW)

    def test_03_tiny_good_crc_size_hash(self):
        self.assertEqual(inspect(zipped()), b'abc')

    def test_04_unselected_unsafe_paths_rejected(self):
        for name in ['/abs', '../up', 'a/../up', 'a\\back', './dot', 'a//empty', 'C:/drive', 'dir/']:
            raw = zipped([('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644),
                          (name, b'x', stat.S_IFREG | 0o644)])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe'):
                inspect(raw, 2)

    def test_05_duplicate_and_nonregular(self):
        rows = [('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644)] * 2
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect(zipped(rows), 2)
        for mode in [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o700, stat.S_IFIFO | 0o600, 0o644]:
            raw = zipped([('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644), ('unselected', b'x', mode)])
            with self.assertRaisesRegex(ValueError, 'nonregular'):
                inspect(raw, 2)

    def test_06_encrypted_metadata(self):
        for bit in [1, 0x40, 0x2000]:
            raw = bytearray(zipped())
            struct.pack_into('<H', raw, raw.index(b'PK\x01\x02') + 8, bit)
            with self.assertRaisesRegex(ValueError, 'encryption'):
                inspect(bytes(raw))

    def test_07_crc_size_and_sha_failures(self):
        raw = bytearray(zipped())
        struct.pack_into('<I', raw, raw.index(b'PK\x01\x02') + 16, 0)
        with self.assertRaises(zipfile.BadZipFile):
            inspect(bytes(raw))
        with self.assertRaisesRegex(ValueError, 'metadata size'):
            inspect(zipped(), size=4)
        with self.assertRaisesRegex(ValueError, 'SHA'):
            inspect(zipped(), digest='0' * 64)

    def test_08_semantic_319_contract(self):
        manifest, closure, filelist = contract_fixture()
        selected, basis = g.derive_selection(manifest, closure, filelist)
        self.assertEqual(len(selected), 319)
        self.assertEqual(len(basis['ordered_sources']), 294)
        self.assertEqual(len(basis['headers']), 18)
        self.assertIn(g.CLOCK, selected)
        self.assertTrue(set(g.EXTRAS) <= set(selected))
        self.assertNotIn('SAFE_IDENTITY.json', selected)

    def test_09_semantic_disagreement_and_counts_rejected(self):
        m, c, f = contract_fixture()
        bad = copy.deepcopy(c)
        bad['admitted_input_hashes']['idma/s0.sv'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'disagreement'):
            g.derive_selection(m, bad, f)
        with self.assertRaisesRegex(ValueError, 'token'):
            g.derive_selection(m, c, f + b'-f /escape\n')
        with self.assertRaisesRegex(ValueError, 'counts'):
            g.derive_selection(m, c, f + b'@ROOT@/idma/s0.sv\n')
        with self.assertRaisesRegex(ValueError, 'define'):
            g.derive_selection(m, c, f + b'+define+UVM\n')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            g.unique_json(b'{"same":1,"same":2}')

    def test_10_archive_identity_before_zip_parse(self):
        with mock.patch.object(g.zipfile, 'ZipFile', side_effect=RuntimeError('no parsing')) as parser:
            with self.assertRaisesRegex(ValueError, 'before ZIP parse'):
                g.prepare(b'not-the-real-archive')
            parser.assert_not_called()

    def test_11_fresh_output_modes_overwrite_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'fresh'
            fd = g.fresh(out)
            try:
                g.write(fd, 'sources/a.sv', b'abc')
                self.assertEqual(g.tree(fd), (['sources/a.sv'], 3))
                self.assertEqual((out / 'sources/a.sv').read_bytes(), b'abc')
                self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((out / 'sources/a.sv').stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError):
                    g.write(fd, 'sources/a.sv', b'new')
                (out / 'link').symlink_to(Path(td))
                with self.assertRaises(OSError):
                    g.write(fd, 'link/escape', b'x')
            finally:
                os.close(fd)
            with self.assertRaises(FileExistsError):
                g.fresh(out)
            self.assertFalse((Path(td) / 'escape').exists())

    def test_12_checked_read_type_size_sha_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'tiny'
            p.write_bytes(b'abc')
            self.assertEqual(g.checked_read(p, 3, g.sha(b'abc'))[0], b'abc')
            with self.assertRaisesRegex(ValueError, 'size'):
                g.checked_read(p, 4, g.sha(b'abc'))
            with self.assertRaisesRegex(ValueError, 'identity'):
                g.checked_read(p, 3, '0' * 64)
            alias = Path(td) / 'link'
            alias.symlink_to(p)
            with self.assertRaises(OSError):
                g.checked_read(alias, 3, g.sha(b'abc'))

    def test_13_current_process_resource_limits_mocked(self):
        with mock.patch.object(g.resource, 'getrlimit', return_value=(-1, -1)), \
             mock.patch.object(g.resource, 'setrlimit') as resource_limits, \
             mock.patch.object(g.os, 'sched_getaffinity', side_effect=[{3, 4}, {3}]), \
             mock.patch.object(g.os, 'sched_setaffinity') as affinity, mock.patch.object(g, 'arm') as arm:
            g.limits(10.0)
            self.assertEqual(resource_limits.call_args_list, [mock.call(g.resource.RLIMIT_CPU, (40, 40)),
                             mock.call(g.resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2)),
                             mock.call(g.resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))])
            affinity.assert_called_once_with(0, {3})
            arm.assert_called_once_with(65.0)

    def test_14_failure_report_preserved_without_archive(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'failed'
            with mock.patch.object(g, 'limits'), mock.patch.object(g, 'arm'), \
                 mock.patch.object(g, 'checked_read', side_effect=ValueError('synthetic read failure')):
                with self.assertRaisesRegex(ValueError, 'synthetic read failure'):
                    g.extract('/unused/archive', out, time.monotonic())
            report = json.loads((out / 'EXTRACTION_REPORT.json').read_bytes())
            self.assertFalse(report['complete'])
            self.assertFalse(report['native_executed'])
            self.assertEqual(report['subset_inventory'], [])

    def test_15_default_entry_data_only(self):
        with mock.patch.object(sys, 'argv', ['extract_idma.py']), \
             mock.patch.object(g, 'extract', side_effect=RuntimeError('no extraction')) as run, \
             mock.patch.object(builtins, 'print') as output:
            g.main()
            run.assert_not_called()
            self.assertEqual(json.loads(output.call_args.args[0])['status'], 'SOURCE_ONLY_NO_ARCHIVE_READ_NO_EXTRACTION')

    def test_16_actual_loader_bad_size_same_length_sha_precompile(self):
        raw = (HERE / 'ENTRY.json').read_bytes()
        self.assertEqual(len(raw), 5451)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '9542df5b0728ebb2f590a7eaebc7315945809cc2d7dc963fd6220b4cb04d21da')
        code = compile(json.loads(raw)['bootstrap'], '<pinned actual loader>', 'exec', dont_inherit=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'extract_idma.py'
            for content in (RAW + b'x', b'X' + RAW[1:]):
                path.write_bytes(content)
                with mock.patch.object(sys, 'argv', ['-c', str(path)]), \
                     mock.patch.object(builtins, 'compile', side_effect=RuntimeError('no compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'before compile'):
                        exec(code, {})
                    compiler.assert_not_called()

    def test_17_actual_loader_source_only_and_isolation_guard(self):
        raw = (HERE / 'ENTRY.json').read_bytes()
        self.assertEqual(len(raw), 5451)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '9542df5b0728ebb2f590a7eaebc7315945809cc2d7dc963fd6220b4cb04d21da')
        code = compile(json.loads(raw)['bootstrap'], '<pinned actual loader>', 'exec', dont_inherit=True)
        with mock.patch.object(sys, 'argv', ['-c', str(SOURCE)]), \
             mock.patch.object(builtins, 'print') as output:
            exec(code, {})
        self.assertEqual(json.loads(output.call_args.args[0])['status'], 'SOURCE_ONLY_NO_ARCHIVE_READ_NO_EXTRACTION')
        with mock.patch.object(sys, 'flags', types.SimpleNamespace(isolated=False)), \
             mock.patch.object(os, 'open', side_effect=RuntimeError('must not read local code')) as read:
            with self.assertRaises(SystemExit):
                exec(code, {})
            read.assert_not_called()


    def test_18_exact_fifo_delta_and_original_selection_unchanged(self):
        original = fifo_selection_fixture()
        snapshot = copy.deepcopy(original)
        result, provenance = g.derive_fifo_valid_split(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(len(result), 319)
        self.assertEqual([r['relative_destination'] for r, b in result],
                         [r['relative_destination'] for r, b in original])
        changed = [(a, b) for a, b in zip(original, result) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertEqual((len(result[0][1]), g.sha(result[0][1])), g.FIFO_DERIVED)
        self.assertEqual(result[0][1], FIFO_DERIVED_FIXTURE)
        self.assertEqual(provenance['intermediate'], {'bytes': 4536, 'sha256': g.FIFO_VALID_SPLIT[1]})
        self.assertEqual(sum(r['bytes'] for r, b in result), 3072451)
        self.assertEqual(provenance['original'], {'bytes': 4411, 'sha256': g.FIFO_BASE[1]})
        self.assertEqual(provenance['derived'], {'bytes': 4662, 'sha256': g.FIFO_DERIVED[1]})
        self.assertTrue(provenance['original_manifest_unchanged'])
        self.assertEqual(provenance['selected_bytes_delta'], 251)

    def test_19_fifo_wrong_base_hash_extra_missing_and_duplicate_rejected(self):
        original = fifo_selection_fixture()
        for kind in range(7):
            bad = copy.deepcopy(original)
            if kind == 0:
                row, raw = bad[0]
                raw = b'X' + raw[1:]
                bad[0] = (dict(row, sha256=g.sha(raw)), raw)
            elif kind == 1:
                bad[0][0]['sha256'] = '0' * 64
            elif kind == 2:
                bad.append(copy.deepcopy(bad[1]))
            elif kind == 3:
                bad[0][0]['relative_destination'] = 'synthetic/other.sv'
                bad[0][0]['zip_member'] = g.PREFIX + 'synthetic/other.sv'
            elif kind == 4:
                bad[1] = copy.deepcopy(bad[0])
            elif kind == 5:
                bad.pop()
            else:
                row, raw = bad[1]
                bad[1] = (row, b'Y' + raw[1:])
            with self.assertRaises(ValueError):
                g.derive_fifo_valid_split(bad)
        with mock.patch.object(g, 'FIFO_DERIVED', (4662, '0' * 64)):
            with self.assertRaisesRegex(ValueError, 'derived identity'):
                g.derive_fifo_valid_split(original)

    def test_20_cli_split_is_explicit_default_false(self):
        for option, enabled in (([], False), (['--fifo-valid-split'], True)):
            result = {'status': 'mock', 'selected_files': 319, 'selected_bytes': 3072451 if enabled else 3072200,
                      'archive_unchanged': True, 'native_executed': False}
            with mock.patch.object(sys, 'argv', ['extract_idma.py', '--archive', '/tmp/archive',
                                               '--out', '/tmp/output'] + option), \
                 mock.patch.object(g, '__entry_monotonic__', 12.0, create=True), \
                 mock.patch.object(g, 'extract', return_value=result) as run, \
                 mock.patch.object(builtins, 'print'):
                g.main()
                run.assert_called_once_with('/tmp/archive', '/tmp/output', 12.0, enabled)

    def test_21_original_prepare_failure_prevents_derivation(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(g, 'limits'), mock.patch.object(g, 'arm'), \
                 mock.patch.object(g, 'checked_read', return_value=(b'mock archive', {'bytes': 12})), \
                 mock.patch.object(g, 'prepare', side_effect=ValueError('original 319 not verified')), \
                 mock.patch.object(g, 'derive_fifo_valid_split') as derive:
                with self.assertRaisesRegex(ValueError, 'original 319'):
                    g.extract('/unused/archive', Path(td) / 'failed', time.monotonic(), True)
                derive.assert_not_called()



    def test_22_mock_archive_extracts_exact_baseline_or_single_derived_source(self):
        original = fifo_selection_fixture()
        read_source = g.checked_read
        archive = '/unused/fixed-archive'
        def read(path, size, digest):
            if str(path) == archive:
                self.assertEqual((size, digest), (g.ARCHIVE_SIZE, g.ARCHIVE_SHA))
                return b'mock archive', {'bytes': g.ARCHIVE_SIZE, 'sha256': g.ARCHIVE_SHA}
            return read_source(path, size, digest)
        with tempfile.TemporaryDirectory() as td:
            reports = []
            outputs = []
            for enabled in (False, True):
                out = Path(td) / ('derived' if enabled else 'baseline')
                with mock.patch.object(g, 'limits'), mock.patch.object(g, 'arm'), \
                     mock.patch.object(g, 'checked_read', side_effect=read), \
                     mock.patch.object(g, 'prepare', return_value=(original, {'mock': True})) as prepare, \
                     mock.patch.object(g, 'derive_fifo_valid_split', wraps=g.derive_fifo_valid_split) as derive:
                    report = g.extract(archive, out, time.monotonic(), enabled)
                    prepare.assert_called_once_with(b'mock archive')
                    self.assertEqual(derive.call_count, int(enabled))
                    self.assertEqual(report['selected_files'], 319)
                    self.assertEqual(report['selected_bytes'], 3072451 if enabled else 3072200)
                    self.assertTrue(report['complete'])
                    self.assertTrue(report['archive_unchanged'])
                    self.assertFalse(report['native_executed'])
                reports.append(report)
                outputs.append({str(p.relative_to(out / 'sources')): p.read_bytes()
                                for p in (out / 'sources').rglob('*') if p.is_file()})
            self.assertEqual(outputs[0], {row['relative_destination']: raw for row, raw in original})
            self.assertEqual(set(outputs[0]), set(outputs[1]))
            self.assertEqual([name for name in outputs[0] if outputs[0][name] != outputs[1][name]],
                             [g.FIFO_PATH])
            self.assertNotIn('source_derivations', reports[0])
            self.assertEqual(len(reports[1]['source_derivations']), 1)
            for name in ('SHA256SUMS.json', 'SOURCE_CLOSURE.json'):
                self.assertEqual(outputs[0][name], outputs[1][name])



    def test_23_ready_split_exact_anchor_rejects_same_length_mutations(self):
        original = fifo_selection_fixture()
        mutations = [
            (b"ready_o     = 1'b0;", b"ready_o    =  1'b0;"),
            (b"|| (SameCycleRW && ready_i && valid_o);", b"|| (SameCycleRZ && ready_i && valid_o);")]
        real_sha = g.sha
        for before, after in mutations:
            bad = copy.deepcopy(original)
            row, raw = bad[0]
            changed = raw.replace(before, after, 1)
            self.assertNotEqual(changed, raw)
            self.assertEqual(len(changed), len(raw))
            bad[0] = (row, changed)
            def mocked_sha(data):
                if len(data) == g.FIFO_BASE[0]:
                    return g.FIFO_BASE[1]
                if len(data) == g.FIFO_VALID_SPLIT[0]:
                    return g.FIFO_VALID_SPLIT[1]
                return real_sha(data)
            with mock.patch.object(g, 'sha', side_effect=mocked_sha):
                with self.assertRaisesRegex(ValueError, 'ready split exact unique transformation anchors'):
                    g.derive_fifo_valid_split(bad)

    def test_24_valid_only_intermediate_identity_must_pass_before_ready_split(self):
        with mock.patch.object(g, 'FIFO_VALID_SPLIT', (4536, '0' * 64)):
            with self.assertRaisesRegex(ValueError, 'valid-only intermediate identity'):
                g.derive_fifo_valid_split(fifo_selection_fixture())


if __name__ == '__main__':
    unittest.main(verbosity=2)
