#!/usr/bin/env python3
"""Unit tests for receipt parsing only, not fake hardware evidence."""
from pathlib import Path
import importlib.util
import os
import unittest
P=Path(os.environ.get('OWNER_FAULT_SCRIPT',str(Path(__file__).resolve().parents[1]/'scripts/run_host_owner_faults.py')))
spec=importlib.util.spec_from_file_location('owner_faults',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def log(mode):
    pc,prior=m.CASES[mode]
    return ''.join(f'OWNER_COMPLETION pc={i} owner=3 signal={i+1}\n' for i in range(prior))+f'EXPECTED_ERROR pc={pc} status=3\nHOST_BLOCK_FAULT_PASS mode={mode} pc={pc} prior_completions={prior} next_owner_not_started=1\n'

class FaultReceipts(unittest.TestCase):
    def test_all_eight_exact_receipts(self):
        for mode in m.CASES:
            with self.subTest(mode=mode):self.assertEqual(m.check_log(mode,log(mode),0)['mode'],mode)
    def test_unknown_mode(self):
        with self.assertRaises(ValueError):m.check_log('unknown-op',log('bad-first-op'),0)
    def test_regular_numeric_pass_is_not_fault_pass(self):
        with self.assertRaises(ValueError):m.check_log('bad-first-op',log('bad-first-op')+'HOST_BLOCK_ALL_OWNERS_PASS\n',0)
    def test_wrong_error_pc(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error').replace('EXPECTED_ERROR pc=1','EXPECTED_ERROR pc=2'),0)
    def test_zero_error_status(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error').replace('status=3','status=0'),0)
    def test_nonzero_exit(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error'),1)
    def test_missing_fault_receipt(self):
        with self.assertRaises(ValueError):m.check_log('read-error','EXPECTED_ERROR pc=1 status=3\n',0)
    def test_duplicated_receipt(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error')*2,0)
    def test_consumer_completion(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error')+'OWNER_COMPLETION pc=1 owner=2\n',0)
    def test_fatal(self):
        with self.assertRaises(ValueError):m.check_log('read-error',log('read-error')+'Fatal\n',0)

if __name__=='__main__':unittest.main()
