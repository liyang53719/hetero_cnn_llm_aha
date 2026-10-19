"""Independent stdlib tests of the fixed same-buffer cold test loader."""
import contextlib
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
DRIVER_PIN = (5213, '56dc9be913577a43a5ecce0fcb584e8398a9fe114a068d2d65104e1218c72392')
DRIVER_RAW = (HERE / 'run_cold.py').read_bytes()
if (len(DRIVER_RAW), hashlib.sha256(DRIVER_RAW).hexdigest()) != DRIVER_PIN:
    raise ValueError('SOURCE')
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise ValueError('FLAGS')
driver = types.ModuleType('_fixed_cold_driver')
driver.__file__ = str(HERE / 'run_cold.py')
exec(compile(DRIVER_RAW, '<fixed-cold-driver>', 'exec', dont_inherit=True), driver.__dict__)
WORKER_RAW = driver.read_fixed(HERE / 'n0_compare.py', driver.INPUT_PINS['n0_compare.py'])


class LoaderContract(unittest.TestCase):
    def test_load_test_compiles_exact_verified_object_without_reopen(self):
        compiler = compile
        with mock.patch.object(Path, 'open', side_effect=AssertionError('reopen')):
            with mock.patch('builtins.compile', wraps=compiler) as observed:
                module = driver.load_test(WORKER_RAW, driver.INPUT_PINS['n0_compare.py'],
                    HERE / 'n0_compare.py', '_fixed_module_cold')
        self.assertEqual(module.ELEMENTS, 196608)
        selected = [call for call in observed.call_args_list
                    if call.args[1] == '<fixed-_fixed_module_cold>']
        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0].args[0], WORKER_RAW)

    def test_load_test_rejects_length_and_same_size_tamper_before_compile(self):
        for raw in (WORKER_RAW + b' ', bytes([WORKER_RAW[0] ^ 1]) + WORKER_RAW[1:]):
            with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                with self.assertRaisesRegex(ValueError, 'SOURCE'):
                    driver.load_test(raw, driver.INPUT_PINS['n0_compare.py'],
                                     HERE / 'n0_compare.py', '_bad')
                compiler.assert_not_called()

    def test_load_test_rejects_each_missing_isolation_flag(self):
        for missing in ('isolated', 'no_site', 'dont_write_bytecode'):
            flags = dict(isolated=1, no_site=1, dont_write_bytecode=1)
            flags[missing] = 0
            with mock.patch.object(sys, 'flags', types.SimpleNamespace(**flags)):
                with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'FLAGS'):
                        driver.load_test(WORKER_RAW, driver.INPUT_PINS['n0_compare.py'],
                                         HERE / 'n0_compare.py', '_bad')
                    compiler.assert_not_called()

    def test_driver_rejects_worker_mutation_before_any_test_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'n0_compare.py').write_bytes(bytes([WORKER_RAW[0] ^ 1]) + WORKER_RAW[1:])
            with mock.patch.object(driver, '__file__', str(path / 'run_cold.py')):
                with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'SOURCE'):
                        driver.main()
                    compiler.assert_not_called()

    def test_driver_rejects_symlink_before_test_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'n0_compare.py').symlink_to(HERE / 'n0_compare.py')
            with mock.patch.object(driver, '__file__', str(path / 'run_cold.py')):
                with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'PATH'):
                        driver.main()
                    compiler.assert_not_called()

    def test_no_numeric_runtime_imports(self):
        self.assertFalse(any(name.split('.')[0] in ('torch', 'numpy', 'transformers')
                             for name in sys.modules))


if __name__ == '__main__':
    unittest.main()
