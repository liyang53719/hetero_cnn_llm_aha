"""Synthetic clock/control tests only; no model, native kernel or payload reads."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from . import stage_log as S

LIMITS=dict(cpu_seconds=1200,wall_seconds=1260,address_space_bytes=4<<30,output_bytes=96<<20)


def counts(**updates):
    result={key:0 for key in S.COUNTER_LIMITS};result.update(updates);return result


class StageLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'STAGES.jsonl'

    def rows(self):return [json.loads(line) for line in self.path.read_text().splitlines()]

    def sample(self):
        log=S.StageLog(self.path,LIMITS);log.begin('PC0_NORM',counters=counts())
        log.end('PC0_NORM',counters=counts(completed=1,jobs=1))
        return self.rows()[-1]

    def test_begin_end_real_clock_differences_and_durable_each_record(self):
        wall=[100.];cpu=[20.];calls=[];real_fsync=S.os.fsync
        def fsync(fd):calls.append(fd);real_fsync(fd)
        with patch.object(S.time,'monotonic',side_effect=lambda:wall[0]),patch.object(S.time,'process_time',side_effect=lambda:cpu[0]),patch.object(S.os,'fsync',side_effect=fsync):
            log=S.StageLog(self.path,LIMITS)
            wall[0]=101.;cpu[0]=20.5;log.begin('PC0_NORM',counters=counts())
            first=S.safe_last(self.path);self.assertEqual(first['record']['event'],'BEGIN')
            self.assertEqual(first['record']['stage_wall_seconds'],0.)
            wall[0]=104.;cpu[0]=22.;log.end('PC0_NORM',counters=counts(completed=1,jobs=1))
        last=S.safe_last(self.path)['record']
        self.assertEqual((last['wall_seconds'],last['cpu_seconds'],last['stage_wall_seconds'],last['stage_cpu_seconds']),(4.,2.,3.,1.5))
        self.assertEqual(len(calls),3)  # fresh file, BEGIN, END
        self.assertEqual([r['sequence'] for r in self.rows()],[1,2])
        self.assertIs(last['snapshot_is_acceptance'],False);self.assertIsNone(last['hardware_cycles'])

    def test_exact_fused_groups_are_not_21_additive_owner_intervals(self):
        self.assertEqual(len(S.OWNER_STAGES),17)
        self.assertIn('PC10_12_ATTENTION',S.OWNER_STAGES);self.assertIn('PC16_18_FFN',S.OWNER_STAGES)
        for label in ('PC10','PC11','PC12','PC16','PC17','PC18'):
            self.assertNotIn(label,S.STAGES)
        log=S.StageLog(self.path,LIMITS)
        for label in S.OWNER_STAGES:log.transition(label,counters=counts())
        log.finish(counters=counts(completed=21,jobs=17,accepted_results=1))
        rows=self.rows();self.assertEqual(len(rows),34)
        self.assertEqual([r['stage'] for r in rows[::2]],list(S.OWNER_STAGES))
        self.assertEqual(rows[-1]['counters']['completed'],21)
        self.assertEqual(rows[-1]['stage_kind'],'OWNER_GROUP')

    def test_auxiliary_stage_not_owner_group(self):
        log=S.StageLog(self.path,LIMITS);log.transition('SETUP',counters=counts());log.finish(counters=counts())
        self.assertTrue(all(r['stage_kind']=='AUXILIARY' for r in self.rows()))
        reference=dict(LIMITS,cpu_seconds=60,wall_seconds=90)
        log=S.StageLog(Path(self.tmp.name)/'reference.jsonl',reference)
        log.begin('REFERENCE',counters=counts());log.finish(counters=counts())

    def test_failure_enum_is_durable_without_business_error_body(self):
        log=S.StageLog(self.path,LIMITS);log.begin('PC1_Q',counters=counts(completed=1,jobs=1))
        self.assertTrue(log.failure('PC1_Q','TIMEOUT',counters=counts(completed=1,jobs=2)))
        last=S.safe_last(self.path)['record']
        self.assertEqual((last['event'],last['status'],last['error_enum']),('FAIL','FAILED','TIMEOUT'))
        self.assertTrue(log.closed);self.assertTrue(log.healthy)
        with self.assertRaises(ValueError):log.begin('PC4_K',counters=counts())

    def test_logging_failure_never_masks_original_business_exception(self):
        log=S.StageLog(self.path,LIMITS);log.begin('PC1_Q',counters=counts())
        original=RuntimeError('PRIVATE_BUSINESS_DETAIL')
        try:
            try:raise original
            except BaseException:
                with patch.object(log,'_write',side_effect=OSError('PRIVATE_WRITE_DETAIL')):
                    self.assertFalse(log.failure('PC1_Q','INTERNAL',counters=counts()))
                raise
        except BaseException as caught:self.assertIs(caught,original)
        self.assertFalse(log.healthy)
        self.assertEqual(S.safe_last(self.path)['record']['event'],'BEGIN')
        self.assertNotIn('PRIVATE',self.path.read_text())

    def test_begin_write_failure_prevents_stage_start(self):
        log=S.StageLog(self.path,LIMITS)
        with patch.object(log,'_write',side_effect=OSError('PRIVATE_WRITE_DETAIL')):
            with self.assertRaises(OSError):log.begin('PC0_NORM',counters=counts())
        self.assertIsNone(log.active);self.assertFalse(log.healthy)
        self.assertEqual(S.safe_last(self.path)['status'],'UNAVAILABLE')

    def test_no_repeated_nested_unknown_or_mismatched_stage(self):
        log=S.StageLog(self.path,LIMITS)
        for bad in ('PRIVATE_STAGE',True,{},None):
            with self.assertRaises(ValueError):log.begin(bad,counters=counts())
        log.begin('PC0_NORM',counters=counts())
        with self.assertRaises(ValueError):log.begin('PC1_Q',counters=counts())
        with self.assertRaises(ValueError):log.end('PC1_Q',counters=counts())
        with self.assertRaises(ValueError):log.end('PC0_NORM',counters=counts(),status='PRIVATE_STATUS')
        log.end('PC0_NORM',counters=counts())
        with self.assertRaises(ValueError):log.transition('PC0_NORM',counters=counts())

    def test_fixed_native_counters_and_monotonic_observations(self):
        for key,limit in S.COUNTER_LIMITS.items():
            for bad in (True,-1,limit+1,0.,None,'PRIVATE_VALUE',{},[]):
                with self.assertRaises(ValueError):S.counters(counts(**{key:bad}))
        for row in ({},dict(counts(),private=7)):
            with self.assertRaises(ValueError):S.counters(row)
        log=S.StageLog(self.path,LIMITS);log.begin('PC1_Q',counters=counts(completed=1))
        with self.assertRaises(ValueError):log.end('PC1_Q',counters=counts())

    def test_limits_explicit_canonical_and_fresh_file(self):
        for field in LIMITS:
            for value in (None,True,0,-1,'PRIVATE_VALUE',LIMITS[field]+1):
                bad=dict(LIMITS);bad[field]=value
                with self.assertRaises(ValueError):S.StageLog(self.path,bad)
        log=S.StageLog(self.path,LIMITS)
        with self.assertRaises(FileExistsError):S.StageLog(self.path,LIMITS)
        self.assertEqual(log.sequence,0)

    def test_last_complete_record_survives_truncated_tail_only(self):
        record=self.sample();raw=self.path.read_bytes()
        self.path.write_bytes(raw+b'{"private":"partial')
        self.assertEqual(S.safe_last(self.path)['record'],record)
        self.path.write_bytes(b'{"private":"partial')
        self.assertEqual(S.safe_last(self.path)['status'],'UNAVAILABLE')
        self.path.write_bytes(raw+b'{"schema":1,"schema":1}\n')
        self.assertEqual(S.safe_last(self.path)['status'],'UNAVAILABLE')
        self.path.write_bytes(raw+json.dumps(dict(private='PRIVATE_VALUE'*7000)).encode()+b'\n')
        self.assertEqual(S.safe_last(self.path)['status'],'UNAVAILABLE')

    def test_record_unknown_fields_types_times_and_enums_rejected(self):
        record=self.sample()
        changes=[('private','PRIVATE_VALUE'),('stage','PRIVATE_VALUE'),('error_enum','PRIVATE_VALUE'),
            ('event','PRIVATE_VALUE'),('status','PRIVATE_VALUE'),('sequence',True),('sequence',1),('schema',True),
            ('hardware_cycles',1),('snapshot_is_acceptance',True),('stage_kind','AUXILIARY')]
        for key in ('wall_seconds','cpu_seconds','stage_wall_seconds','stage_cpu_seconds'):
            changes.extend((key,bad) for bad in (True,-1,1801,10**400,float('nan'),float('inf'),'PRIVATE_VALUE'))
        for key,value in changes:
            changed=copy.deepcopy(record);changed[key]=value
            self.path.write_text(json.dumps(changed)+'\n')
            result=S.safe_last(self.path)
            self.assertEqual(result['status'],'UNAVAILABLE',(key,value))
            self.assertNotIn('PRIVATE_VALUE',json.dumps(result))

    def test_alias_replaced_file_and_missing_path_rejected(self):
        log=S.StageLog(self.path,LIMITS);log.begin('PC0_NORM',counters=counts())
        alias=Path(self.tmp.name)/'alias.jsonl';alias.symlink_to(self.path)
        self.assertEqual(S.safe_last(alias)['status'],'UNAVAILABLE')
        with self.assertRaises(ValueError):S.StageLog(alias,LIMITS)
        replacement=Path(self.tmp.name)/'replacement';replacement.write_bytes(self.path.read_bytes());replacement.replace(self.path)
        with self.assertRaises(ValueError):log.end('PC0_NORM',counters=counts())
        self.assertEqual(S.safe_last(Path(self.tmp.name)/'missing')['status'],'UNAVAILABLE')

    def test_failure_with_unknown_enum_or_bad_counters_returns_false(self):
        log=S.StageLog(self.path,LIMITS);log.begin('PC0_NORM',counters=counts())
        self.assertFalse(log.failure('PC0_NORM','PRIVATE_ERROR',counters=counts()))
        self.assertNotIn('PRIVATE_ERROR',self.path.read_text())
        self.assertEqual(S.safe_last(self.path)['record']['event'],'BEGIN')

    def test_import_is_cold_and_no_signal_finalization_promised(self):
        code='from candidates.qwen2_m16_stage_diagnostic import stage_log; import sys; assert not any(n.split(".")[0] in ("torch","numpy","transformers") for n in sys.modules)'
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(S.__file__).resolve().parents[2],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('no SIGKILL finalizer',S.__doc__)


if __name__=='__main__':unittest.main()
