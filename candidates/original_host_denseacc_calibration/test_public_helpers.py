"""Synthetic metadata/parser negatives only; zero native/DUT executions."""
from pathlib import Path
import hashlib, tempfile, unittest
from check_calibration_output import check, EXPECTED
from extract_core_input import read_verified_core, identity

class OutputContract(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(check(EXPECTED)['pair_checks'], 401408)
    def test_mutations(self):
        bad = [EXPECTED[:-1], EXPECTED + b'PASS\n', EXPECTED.replace(b'=17 ', b'=18 '),
               EXPECTED.replace(b'=49 ', b'=48 '), EXPECTED.replace(b'=401408', b'=401409'),
               EXPECTED.replace(b'=200704', b'=200705'), EXPECTED.replace(b'randReset0', b'randReset1'),
               EXPECTED.replace(b'no-Host-control', b'full-Host-control'), EXPECTED.replace(b'\n', b'\r\n')]
        for data in bad:
            with self.subTest(data=data[-32:]), self.assertRaises(ValueError):
                check(data)

class Extractor(unittest.TestCase):
    core = b'  module Qwen2ContinuousBlock :\n    input clock : Clock\n'
    def fixture(self, body, core=None):
        return {'parent': identity(body), 'core': identity(self.core if core is None else core)}
    def run_case(self, body, pins):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'high.fir'
            path.write_bytes(body)
            return read_verified_core(path, pins)
    def test_exact(self):
        body = b'FIRRTL version 1.2.0\ncircuit C :\n' + self.core + b'  module After :\n'
        self.assertEqual(self.run_case(body, self.fixture(body)), self.core)
    def test_duplicate(self):
        body = self.core + self.core
        with self.assertRaises(ValueError):
            self.run_case(body, self.fixture(body, body))
    def test_missing(self):
        body = b'  module Other :\n'
        with self.assertRaises(ValueError):
            self.run_case(body, self.fixture(body, b''))
    def test_parent_tamper(self):
        body = self.core
        pins = self.fixture(body)
        pins['parent']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.run_case(body, pins)
    def test_core_tamper(self):
        pins = self.fixture(self.core)
        pins['core']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.run_case(self.core, pins)
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'high.fir'; path.write_bytes(self.core)
            link = Path(tmp) / 'link'; link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_verified_core(link, self.fixture(self.core))

if __name__ == '__main__':
    unittest.main()
