#!/usr/bin/env python3
"""Synthetic source/mock observer tests; no native tools or network.

The /synthetic paths below are invented test inputs, never a reconstruction
of a redacted private path. Existing filename suffix/line/column grammar is
retained. This patch changes only the optional exact top-level signal prefix.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before test project loads')
import hashlib
from pathlib import Path
import tempfile
import types
import unittest

HERE=Path(__file__).absolute().parent

def fixed(path,size,digest):
    raw=path.read_bytes()
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError('fixed same-buffer test input identity')
    return raw

def module(raw,path,name):
    loaded=types.ModuleType(name);loaded.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),loaded.__dict__)
    return loaded

cold_path=HERE/'test_run_cold.py'
cold=module(fixed(cold_path,43065,'a6e4bc55b4cc3919ca28d2ebba4b30604dd07edbe706fa5b85961aff5f3e29cd'),cold_path,'observer_base_cold')
m=cold.m
BARE=fixed(HERE/'fixtures'/'opaque_bare_synthetic.log',390,'62c6b27c70c745905dd987849d8189491f30f757bb25b6013bec831f45fc7afb')

class ObserverCold(unittest.TestCase):
    def test_synthetic_old_rejects_new_accepts(self):
        current=fixed(HERE/'run.py',53278,'235a619fc7d304578ff78a958c173a33cb50d1a860dbf56fe2051fd4396ba3b8')
        patched=b'Example path: (?:host_handshake_micro\\.)?(?:cmd_valid'
        original=b'Example path: host_handshake_micro\\.(?:cmd_valid'
        if current.count(patched)!=1:raise ValueError('unique inverse observer patch')
        prior_raw=current.replace(patched,original)
        if len(prior_raw)!=53273 or hashlib.sha256(prior_raw).hexdigest()!='7dffb2a2fbb108b2bf01926e00372346e5c85e9ef7cef7bbfa03b3b1b45577b0':
            raise ValueError('fixed same-buffer original source identity')
        prior=module(prior_raw,HERE/'synthetic_prior_run.py','observer_prior_cold')
        with self.assertRaisesRegex(ValueError,'fixed opaque combo and atomic handshake path'):
            prior.opaque_observation(BARE,cold.observation(False))
        self.assertEqual(m.opaque_observation(BARE,cold.observation(False)),1)
        self.assertEqual(prior.opaque_observation(cold.OPAQUE,cold.observation(False)),1)
        self.assertEqual(m.opaque_observation(cold.OPAQUE,cold.observation(False)),1)

    def test_finite_signals_bare_and_exact_qualified(self):
        signals=(b'cmd_valid',b'step_valid',b'out_ready',b'completion_ready',b'all_command_ready',b'all_step_ready',b'all_out_valid',b'all_completion')
        for signal in signals:
            for prefix in (b'',b'host_handshake_micro.'):
                with self.subTest(signal=signal,prefix=prefix):
                    raw=BARE.replace(b'Example path: all_command_ready',b'Example path: '+prefix+signal)
                    self.assertEqual(m.opaque_observation(raw,cold.observation(False)),1)

    def test_unknown_prefixes_and_signals_rejected(self):
        for signal in (b'other.all_command_ready',b'TOP.host_handshake_micro.all_command_ready',b'host_handshake_micro.host_handshake_micro.all_command_ready',b'host_handshake_microXall_command_ready',b'host_handshake_micro.arbitrary',b'arbitrary',b'cmd_ready',b'host_handshake_micro.cmd_ready',b'all_command_ready[0]',b'all_command_ready extra'):
            with self.subTest(signal=signal):
                raw=BARE.replace(b'Example path: all_command_ready',b'Example path: '+signal)
                with self.assertRaises(ValueError):m.opaque_observation(raw,cold.observation(False))

    def test_existing_file_suffix_and_location_gates(self):
        variants=(
            BARE.replace(b'host_handshake_micro.sv',b'unrelated.sv'),
            BARE.replace(b'host_handshake_micro.sv',b'host_handshake_micro.v'),
            BARE.replace(b'leaf_opaque_model.sv',b'unrelated.sv'),
            BARE.replace(b'leaf_opaque_model.sv',b'leaf_opaque_model.v'),
            BARE.replace(b'/synthetic/host_handshake_micro.sv',b'[PATH]'),
            BARE.replace(b'/synthetic/leaf_opaque_model.sv',b'[PATH]'),
            BARE.replace(b':18:15:',b':17:15:'),
            BARE.replace(b':18:15:',b':0:15:'),
            BARE.replace(b':18:15:',b':99:15:'),
            BARE.replace(b':18:15:',b':18:0:'),
            BARE.replace(b':18:15:',b':18:-1:'),
            BARE.replace(b':18:15:',b':18:x:'),
            BARE.replace(b':30:3:',b':29:3:'),
            BARE.replace(b':30:3:',b':30:0:'),
        )
        for index,raw in enumerate(variants):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):m.opaque_observation(raw,cold.observation(False))

    def test_fatal_warning_and_error_gates(self):
        variants=(
            BARE.replace(b'UNOPTFLAT',b'WIDTH'),
            BARE.replace(b'%Warning-',b'%Warning '),
            BARE.replace(b'1 warning(s)',b'2 warning(s)'),
            BARE.replace(b'1 warning(s)',b'0 warning(s)'),
            BARE.replace(b'%Error: Exiting due to 1 warning(s)\n',b''),
            BARE.replace(b'%Error: Exiting due to 1 warning(s)',b'%Error: unrelated error'),
            BARE.replace(b'%Error: Exiting',b'%Error: unrelated error\n%Error: Exiting'),
            BARE+b'extra\n',
            BARE+b'%Error: unrelated error\n',
            BARE.replace(b'ALWAYS',b'ASSIGNW'),
            BARE.replace(b'\n',b'\r\n'),
            BARE+b'\x00',
            BARE+b'\xff',
        )
        for index,raw in enumerate(variants):
            with self.subTest(index=index):
                with self.assertRaises((ValueError,UnicodeError)):m.opaque_observation(raw,cold.observation(False))

    def test_same_warning_block_required(self):
        raw=BARE.replace(b'  /synthetic/leaf_opaque_model.sv',b'%Warning-UNOPTFLAT: synthetic second warning\n  /synthetic/leaf_opaque_model.sv').replace(b'1 warning(s)',b'2 warning(s)')
        with self.assertRaises(ValueError):m.opaque_observation(raw,cold.observation(False))

    def test_natural_exit_and_timeout_gates(self):
        mutations=(('exit_code',0),('exit_code',-9),('exit_code',256),('final_reap_signal',9),('receipt_timed_out',True),('cleanup_confirmed',False),('waitid_code',2),('waitid_status',2),('native_record_status','PASS'),('failure_code','LOG_LIMIT'),('failure_boundary','USAGE_OR_POSTFLIGHT'),('kill_attempted',False),('kill_result','UNCONFIRMED'))
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                row=cold.observation(False);row[key]=value
                with self.assertRaises(ValueError):m.opaque_observation(BARE,row)

    def test_bare_full_mock_success_and_failure_boundaries(self):
        with tempfile.TemporaryDirectory(dir=HERE,prefix='observer_tmp_') as directory:
            root=Path(directory);repo=root/'repo';repo.mkdir()
            variants=(('bare',cold.MockRun(opaque=BARE),0),('timeout',cold.MockRun(fail='host_opaque',opaque=BARE,timeout=True),1),('error',cold.MockRun(opaque=BARE+b'%Error: unrelated error\n'),1))
            for name,case,expected in variants:
                with self.subTest(name=name):
                    code,obj,_=case.run(repo,root/name)
                    self.assertEqual(code,expected)
                    summary=obj['summary.json']
                    self.assertEqual(summary['host_pair']['opaque_warning_count'],1 if expected==0 else 0)
                    self.assertEqual(summary['status'],'DIAGNOSTIC_OBSERVED' if expected==0 else 'INCOMPLETE')
                    if name=='timeout':self.assertTrue(obj['stage_exits.json']['stages'][-1]['receipt_timed_out'])
                    if name=='error':self.assertEqual(summary['contract_failure']['boundary'],'OPAQUE_OBSERVATION')

if __name__=='__main__':unittest.main()
