"""Positive and mutation-negative source contracts. No mock VHost/model types."""
import argparse
import hashlib
import marshal
import struct
import sys
import tempfile
import types
import unittest
from importlib.util import MAGIC_NUMBER
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER_SHA256 = '0edeacc9ae2651d97f8e06a20c86696be064b99c367f365edcebf8bc3dcd6a40'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, required=True)
args, remaining = parser.parse_known_args()
REPO = args.repo


def module(name, path):
    # Same-byte pattern from the published test_recovery.py. No bytecode lookup.
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CHECKER_SHA256:
        raise ValueError('project source bytes differ before execution: cold_check.py')
    result = types.ModuleType(name)
    result.__file__ = str(path.resolve())
    sys.modules[name] = result
    exec(compile(raw, 'cold_check.py', 'exec', dont_inherit=True), result.__dict__)
    return result


c = module('host_ports_cold_check_v2', HERE / 'cold_check.py')


class HostPinsSourceTests(unittest.TestCase):
    def setUp(self):
        self.header = (c.HERE / 'host_ports.hpp').read_text()

    def rejected(self, old, new):
        self.assertIn(old, self.header)
        with self.assertRaises(ValueError):
            c.check(self.header.replace(old, new, 1), repo=REPO)

    def test_exact_published_contract(self):
        self.assertEqual(c.check(repo=REPO), dict(input_slots=54, result_fields=4, hub_counters=4, compiled=False, model_executed=False))

    def test_missing_r_word_rejected(self):
        self.rejected('    d.io_axi_r_bits_data[15]=0;\n', '')

    def test_duplicate_input_rejected(self):
        self.rejected('d.io_axi_r_bits_data[15]=0;', 'd.io_axi_r_bits_data[14]=0;')

    def test_nonzero_initialization_rejected(self):
        self.rejected('d.io_launch_valid=0;', 'd.io_launch_valid=1;')

    def test_output_write_rejected(self):
        self.rejected('d.io_axi_w_ready=0;', 'd.io_axi_w_valid=0;')

    def test_result_swap_rejected(self):
        self.rejected('value.failedPc = d.io_result_bits_failedPc;', 'value.failedPc = d.io_result_bits_epoch;')

    def test_result_narrowing_rejected(self):
        self.rejected('std::uint16_t completed', 'std::uint8_t completed')

    def test_hub_index_swap_rejected(self):
        self.rejected('value.accepted[1] = d.io_memoryAccepted_1;', 'value.accepted[1] = d.io_memoryAccepted_0;')

    def test_hub_counter_narrowing_rejected(self):
        self.rejected('std::array<std::uint64_t, 2>', 'std::array<std::uint32_t, 2>')

    def test_counter_fabrication_rejected(self):
        self.rejected('value.returned[0] = d.io_memoryReturned_0;', 'value.returned[0] = 0;')

    def test_arithmetic_in_getter_rejected(self):
        self.rejected('value.status = d.io_result_bits_status;', 'value.status = d.io_result_bits_status + 1;')

    def test_eval_side_effect_rejected(self):
        self.rejected('d.clock=0;', 'd.clock=0;\n    d.eval();')

    def test_launch_stub_rejected(self):
        self.rejected('template<class Model> struct HostPins {', 'template<class Model> struct HostPins {\n    static void launch_payload(Model&) {}')

    def test_changed_checker_source_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'cold_check.py'
            source.write_bytes((HERE / 'cold_check.py').read_bytes() + b'\n# changed\n')
            with self.assertRaisesRegex(ValueError, 'source bytes differ before execution'):
                module('host_ports_changed_checker', source)

    def test_valid_timestamp_poisoned_pyc_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'cold_check.py'
            source.write_bytes((HERE / 'cold_check.py').read_bytes())
            stat = source.stat()
            suffix = '.opt-' + str(sys.flags.optimize) if sys.flags.optimize else ''
            cache = source.parent / '__pycache__' / ('cold_check.' + sys.implementation.cache_tag + suffix + '.pyc')
            cache.parent.mkdir()
            poisoned = compile('POISON_EXECUTED = True\nraise RuntimeError("poisoned pyc executed")\n', str(source), 'exec')
            header = MAGIC_NUMBER + struct.pack('<III', 0, int(stat.st_mtime) & 0xffffffff, stat.st_size)
            cache.write_bytes(header + marshal.dumps(poisoned))
            self.assertEqual(cache.read_bytes()[:16], header)
            self.assertEqual(marshal.loads(cache.read_bytes()[16:]).co_code, poisoned.co_code)
            loaded = module('host_ports_poison_cache_check', source)
            self.assertFalse(hasattr(loaded, 'POISON_EXECUTED'))
            self.assertTrue(callable(loaded.check))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + remaining)
