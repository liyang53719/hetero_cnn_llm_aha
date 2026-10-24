"""Synthetic-only failure tests; no running/original artifacts are opened."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
SOURCE_COMMIT = '1' * 40
FULL_DRIVER_SHA = '5' * 64

spec = importlib.util.spec_from_file_location('terminal_gate', Path(__file__).with_name('terminal_gate.py'))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


def fixture():
    owner = dict(pid=5, ppid=2, group=5, start=123)
    row = dict(owner, session=5, state='Z')
    boot = 'a015bb85-7341-467e-9d31-616e413f7d75'
    start = dict(row, boot_id=boot, work_stop_monotonic=10900)
    scans = []
    for a, b in ((101., 102.), (103., 104.)):
        scans.append(dict(started=a, finished=b, complete=True, captured={'5': row}, members=[row],
            identities=[dict(original=row, observed=row, classification='defunct_present_unreaped')]*2,
            nonleader_present=False, live_nonleader_present=False, leader_exited_retained=True))
    proof = dict(schema=1, status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP', scope=g.SCOPE,
        source_sha256=g.CLEANUP_SHA, parent_pid=2, boot_id=boot, owner_identity=owner, session=5,
        stop=10930, started=100., signal_at=100.5, barrier_at=104., reap_started_at=105.,
        reaped_at=106., completed_at=107., empty_complete_scans=2,
        no_nonleader_identities_at_barrier=True, direct_leader_reaped=True, direct_exit_code=-9,
        no_post_reap_signals=True, grandchildren_reaped_by_this_helper=False,
        complete_scan_bounds=[[101., 102.], [103., 104.]], scan_evidence_sha256=g.digest(g.canonical(scans)))
    cleanup = dict(proof=proof, cleanup_complete=True, leader_reaped=True, authority_released=True,
        scope=g.SCOPE, source_sha256=g.CLEANUP_SHA, stop=10930, started=100., leader=row, scans=scans,
        signals=[dict(at=100.5, pid=5, kind='SIGKILL', leader_retained=True)])
    launch = dict(status='FAILED', actual_complete_uncompared=False, cleanup_confirmed=True,
        returncode=-9, supervisor_pid=2, child_identity=row, boot_id=boot, cleanup_proof=proof,
        original_stop_monotonic=11500, source_commit=SOURCE_COMMIT)
    return start, launch, cleanup


def config_fixture(root):
    """Structurally valid synthetic-only configuration, never real evidence."""
    root = Path(root)
    return dict(schema=1,scope='REVIEWED_POST_TERMINAL_COLD128_CONFIGURATION',
        source_commit=SOURCE_COMMIT,full_driver_sha256=FULL_DRIVER_SHA,
        paths=dict(repository=str(REPOSITORY),harness=str(root),run_directory=str(root/'run'),
                   fixture=str(root/'unused_fixture'),numpy_site=str(root/'numpy_site')),
        files={name:dict(path=str(root/path),bytes=1,sha256=char*64) for name,path,char in (
            ('plan','PLAN.json','2'),('terminal_manifest','handoff.json','3'),
            ('reference_freeze','REFERENCE_FREEZE.json','4'),('native_manifest','reference/native/manifest.json','6'))},
        terminal=dict(retained_exec_session=7,executor_exit_code=1,owner_identity=dict(pid=5,ppid=2,group=5,start=123,session=5),
            boot_id='a015bb85-7341-467e-9d31-616e413f7d75',work_start_monotonic=100.))


class ReviewedConfigurationTests(unittest.TestCase):
    def load(self, root, mutate=None, *, raw=None):
        data=config_fixture(root)
        if mutate: mutate(data)
        path=Path(root)/'config.json'
        path.write_bytes(raw if raw is not None else json.dumps(data).encode())
        return g.load_reviewed_config(path,g.digest(path.read_bytes()))

    def test_complete_config_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            loaded=self.load(d)
            self.assertEqual(loaded['terminal']['retained_exec_session'],7)
            self.assertFalse(Path(loaded['files']['native_manifest']['path']).exists())

    def test_relative_paths_resolve_only_at_config_parent(self):
        with tempfile.TemporaryDirectory() as d:
            def relative(data):
                data['paths']=dict(repository='source',harness='evidence',run_directory='evidence/run',fixture='fixture',numpy_site='site')
                for key,name in (('plan','evidence/PLAN.json'),('reference_freeze','evidence/REFERENCE_FREEZE.json'),
                                 ('terminal_manifest','handoff.json'),('native_manifest','reference/native/manifest.json')):
                    data['files'][key]['path']=name
            loaded=self.load(d,relative)
            self.assertEqual(loaded['paths']['repository'],Path(d)/'source')
            self.assertEqual(loaded['files']['plan']['path'],str(Path(d)/'evidence/PLAN.json'))

    def test_missing_config_has_no_default(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):g.load_reviewed_config(Path(d)/'missing','0'*64)
            with self.assertRaises(TypeError):g.admit_terminal_manifest('unused','0'*64)

    def test_malformed_and_duplicate_json_fail_closed(self):
        for raw in (b'{',b'[]',b'{"schema":1,"schema":1}',b'{"schema":NaN}'):
            with self.subTest(raw=raw),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):self.load(d,raw=raw)

    def test_missing_extra_bad_types_and_weakened_terminal_rejected(self):
        mutations=(lambda c:c.pop('source_commit'),lambda c:c.update(extra=True),lambda c:c.update(schema=True),
            lambda c:c.update(source_commit='not-a-commit'),lambda c:c.update(full_driver_sha256='0'*63),
            lambda c:c['paths'].pop('repository'),lambda c:c['files'].pop('native_manifest'),
            lambda c:c['files']['plan'].update(bytes=True),lambda c:c['files']['plan'].update(sha256='z'*64),
            lambda c:c['terminal'].update(retained_exec_session=True),lambda c:c['terminal'].update(executor_exit_code=0),
            lambda c:c['terminal']['owner_identity'].update(start=True),lambda c:c['terminal']['owner_identity'].update(session=9),
            lambda c:c['terminal'].update(boot_id='0'*36),lambda c:c['terminal'].update(work_start_monotonic=-1),
            lambda c:c['files']['reference_freeze'].update(path=c['files']['plan']['path']))
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):self.load(d,mutate)

    def test_path_spelling_and_symlink_aliases_rejected(self):
        for spelling in ('source/../source','source//child','./source','source/',r'source\\child'):
            with self.subTest(spelling=spelling),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):self.load(d,lambda c:c['paths'].update(repository=spelling))
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'source';target.mkdir();alias=Path(d)/'alias';alias.symlink_to(target)
            with self.assertRaises(ValueError):self.load(d,lambda c:c['paths'].update(repository='alias'))
            with self.assertRaises(ValueError):self.load(d,lambda c:c['paths'].update(repository='alias/missing'))
            self.load(d)
            config_alias=Path(d)/'config_alias.json';config_alias.symlink_to(Path(d)/'config.json')
            with self.assertRaises(ValueError):g.load_reviewed_config(config_alias,g.digest((Path(d)/'config.json').read_bytes()))

    def test_reviewed_pin_and_later_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            loaded=self.load(d);path=Path(d)/'config.json'
            with self.assertRaisesRegex(ValueError,'receipt hash'):g.load_reviewed_config(path,'f'*64)
            path.write_bytes(b'{}')
            with self.assertRaises(ValueError):g.recheck_config(loaded)

    def test_unmodified_repository_source_pins(self):
        for name in g.SOURCE_FILES:
            path,raw=g.read_source(REPOSITORY,name)
            self.assertEqual(g.digest(raw),g.SOURCE_FILES[name][1])
            self.assertEqual(path,REPOSITORY/g.SOURCE_FILES[name][0])

    def test_helper_hash_mismatch_and_alias_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/g.SOURCE_FILES['strict_cleanup'][0];path.parent.mkdir(parents=True)
            path.write_bytes(b'SYNTHETIC WRONG SOURCE')
            with self.assertRaisesRegex(ValueError,'receipt hash'):g.original_scan_classifier(d)
            path.unlink();path.symlink_to(REPOSITORY/g.SOURCE_FILES['strict_cleanup'][0])
            with self.assertRaisesRegex(ValueError,'aliases'):g.original_scan_classifier(d)


class DurableProofTests(unittest.TestCase):
    def check_bad(self, mutate):
        s, l, c = copy.deepcopy(fixture()); mutate(s, l, c)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            g.validate_durable_cleanup(s, l, c, 100., repository=REPOSITORY)

    def test_valid_durable_proof(self):
        g.validate_durable_cleanup(*fixture(), 100., repository=REPOSITORY)

    def test_running_rejected(self):
        self.check_bad(lambda s,l,c:l.update(status='RUNNING'))

    def test_unknown_cleanup_rejected(self):
        self.check_bad(lambda s,l,c:l.update(cleanup_confirmed=False))

    def test_wrong_owner_start_rejected(self):
        self.check_bad(lambda s,l,c:s.update(start=124))

    def test_wrong_boot_rejected(self):
        self.check_bad(lambda s,l,c:s.update(boot_id='0'*36))

    def test_reap_before_barrier_rejected(self):
        self.check_bad(lambda s,l,c:c['proof'].update(reap_started_at=103.))

    def test_deadline_extension_rejected(self):
        self.check_bad(lambda s,l,c:c['proof'].update(stop=20000))

    def test_changed_scan_rejected(self):
        self.check_bad(lambda s,l,c:c['scans'][-1].update(complete=False))

    def test_nonleader_not_hidden_by_false_flags(self):
        def mutate(s,l,c):
            c['scans'][-1]['members'].append(dict(pid=7,ppid=5,group=5,start=125,session=5,state='Z'))
            c['proof']['scan_evidence_sha256']=g.digest(g.canonical(c['scans']))
        self.check_bad(mutate)

    def test_post_reap_signal_rejected(self):
        self.check_bad(lambda s,l,c:c['signals'].append(dict(at=106.,pid=5,kind='SIGKILL',leader_retained=True)))

    def test_wrong_direct_exit_rejected(self):
        self.check_bad(lambda s,l,c:l.update(returncode=0))

    def test_missing_tracked_identity_rejected(self):
        def mutate(s,l,c):
            c['scans'][-1]['captured']['7']=None
            c['proof']['scan_evidence_sha256']=g.digest(g.canonical(c['scans']))
        self.check_bad(mutate)

    def test_explicit_integrity_failure_rejected(self):
        self.check_bad(lambda s,l,c:l.update(all_frozen_actual_inputs_unchanged=False))

    def test_first_signal_time_mismatch_rejected(self):
        self.check_bad(lambda s,l,c:c['signals'][0].update(at=100.75))

    def test_cleanup_start_mismatch_rejected(self):
        self.check_bad(lambda s,l,c:c.update(started=99.))

    def test_error_evidence_rejected(self):
        self.check_bad(lambda s,l,c:c.update(error='original cleanup failure'))

    def test_escaped_tracked_identity_not_hidden(self):
        def mutate(s,l,c):
            original=dict(pid=7,ppid=5,group=5,start=125,session=5,state='R')
            escaped=dict(original,group=9,session=9)
            c['scans'][-1]['captured']['7']=escaped
            c['scans'][-1]['members'].append(escaped)
            c['scans'][-1]['identities'].append(dict(original=original,observed=None,classification='identity_disappeared'))
            c['proof']['scan_evidence_sha256']=g.digest(g.canonical(c['scans']))
        self.check_bad(mutate)

    def test_earlier_scan_error_not_hidden(self):
        def mutate(s,l,c):
            prior=copy.deepcopy(c['scans'][0]);prior.update(started=100.6,finished=100.7,error='denied proc entry')
            c['scans'].insert(0,prior)
        self.check_bad(mutate)

    def test_earlier_incomplete_scan_not_hidden(self):
        def mutate(s,l,c):
            prior=copy.deepcopy(c['scans'][0]);prior.update(started=100.6,finished=100.7,complete=False)
            c['scans'].insert(0,prior)
        self.check_bad(mutate)


class AdmissionOrderingTests(unittest.TestCase):
    def create(self, directory, *, running=False, terminal_observed=True):
        root=Path(directory); run=root/'run'; run.mkdir(); (run/'actual').mkdir()
        plan=dict(source_commit=SOURCE_COMMIT,run_directory=str(run),
            comparison={'native_manifest':str(root/'reference/native/manifest.json')},driver_api={'fixture':str(root/'unused_fixture')},
            repository=str(REPOSITORY),numpy_site=str(root/'numpy_site'),
            inputs={str(root/'REFERENCE_FREEZE.json'):dict(bytes=1,sha256='4'*64,resolved=str(root/'REFERENCE_FREEZE.json'))})
        planpath=root/'PLAN.json'; planpath.write_text(json.dumps(plan)); psha=g.digest(planpath.read_bytes())
        s,l,c=fixture(); s['plan_sha256']=l['plan_sha256']=psha
        if running:l['status']='RUNNING'
        paths=dict(start=str(run/'START.json'),launch=str(run/'LAUNCH.json'),cleanup=str(run/'CLEANUP.json'),
            identity=str(run/'actual/identity.json'),evidence=str(run/'actual/summary.json'))
        for key,value in (('start',s),('launch',l),('cleanup',c)):
            Path(paths[key]).write_text(json.dumps(value))
        # Identity/evidence deliberately do not exist. A good gate returns paths,
        # and the adapter must separately authenticate these after admission.
        pins={p:dict(bytes=Path(p).stat().st_size,sha256=g.digest(Path(p).read_bytes()))
              if Path(p).exists() else dict(bytes=5,sha256='0'*64) for p in paths.values()}
        manifest=dict(schema=1,scope='ROOT_REVIEWED_TERMINAL_COLD_DIAGNOSTIC_HANDOFF',retained_exec_session=7,
            retained_handle_terminal_observed=terminal_observed,executor_exit_code=1,overall_status='INCOMPLETE',
            combined_full_run_acceptance=False,source_commit=SOURCE_COMMIT,
            plan=dict(path=str(planpath),bytes=planpath.stat().st_size,sha256=psha),run_directory=str(run),
            metadata=paths,inputs=pins)
        m=root/'handoff.json';m.write_text(json.dumps(manifest))
        config = config_fixture(root)
        config['files']['plan'] = dict(path=str(planpath),bytes=planpath.stat().st_size,sha256=psha)
        config['files']['terminal_manifest'] = dict(path=str(m),bytes=m.stat().st_size,sha256=g.digest(m.read_bytes()))
        cp = root/'reviewed_config.json'; cp.write_text(json.dumps(config))
        return m,g.digest(m.read_bytes()),cp,g.digest(cp.read_bytes())

    def test_valid_gate_never_reads_actual_payload(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.create(d);seen=[];original=g.read_pinned
            def spy(path,*args,**kwargs):seen.append(str(path));return original(path,*args,**kwargs)
            with patch.object(g,'read_pinned',spy):
                gate=g.admit_terminal(*args)
                g.recheck_terminal_manifest(gate)
            self.assertFalse(any('/actual/' in p for p in seen))
            self.assertEqual(gate['whole_run_status'],'INCOMPLETE')

    def test_running_gate_denies_before_actual_reads(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'known incomplete terminal'):
                g.admit_terminal(*self.create(d,running=True))

    def test_missing_root_terminal_observation_denied(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'known-terminal parent'):
                g.admit_terminal(*self.create(d,terminal_observed=False))

    def test_wrong_reviewed_sha_denied(self):
        with tempfile.TemporaryDirectory() as d:
            m,sha,p,psha=self.create(d)
            with self.assertRaisesRegex(ValueError,'terminal manifest binding'):
                g.admit_terminal(m,'f'*64,p,psha)

    def test_post_gate_receipt_drift_denied(self):
        with tempfile.TemporaryDirectory() as d:
            gate=g.admit_terminal(*self.create(d))
            Path(gate['metadata_paths']['launch']).write_text('{}')
            with self.assertRaises(ValueError):g.recheck_terminal_manifest(gate)

    def test_frozen_identity_config_mismatches_rejected(self):
        mutations=(lambda c:c['terminal'].update(retained_exec_session=8),
            lambda c:c['terminal']['owner_identity'].update(start=124),
            lambda c:c['terminal'].update(work_start_monotonic=101.),
            lambda c:c['terminal'].update(boot_id='b015bb85-7341-467e-9d31-616e413f7d75'),
            lambda c:c.update(source_commit='f'*40),lambda c:c['files']['plan'].update(sha256='f'*64))
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i),tempfile.TemporaryDirectory() as d:
                m,ms,cp,cs=self.create(d);data=json.loads(cp.read_bytes());mutate(data);cp.write_text(json.dumps(data))
                with self.assertRaises(ValueError):g.admit_terminal(m,ms,cp,g.digest(cp.read_bytes()))

    def test_manifest_alias_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            m,ms,cp,cs=self.create(d);alias=Path(d)/'alias.json';alias.symlink_to(m)
            with self.assertRaises(ValueError):g.admit_terminal(alias,ms,cp,cs)

    def test_config_drift_after_gate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.create(d);gate=g.admit_terminal(*args);args[2].write_text('{}')
            with self.assertRaises(ValueError):g.recheck_terminal_manifest(gate)

    def test_example_is_synthetic_structural_input_not_evidence(self):
        path=HERE/'REVIEWED_CONFIG.synthetic.example.json'
        config=g.load_reviewed_config(path,g.digest(path.read_bytes()))
        example=json.loads(path.read_bytes())
        self.assertTrue(all(not Path(value).is_absolute() for value in example['paths'].values()))
        self.assertTrue(all(not Path(value['path']).is_absolute() for value in example['files'].values()))
        self.assertFalse(Path(config['files']['terminal_manifest']['path']).exists())
        with self.assertRaises(FileNotFoundError):
            g.admit_terminal(config['files']['terminal_manifest']['path'],config['files']['terminal_manifest']['sha256'],
                path,g.digest(path.read_bytes()))


if __name__ == '__main__':
    unittest.main()
