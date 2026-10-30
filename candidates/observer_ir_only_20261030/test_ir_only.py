import ast, copy, hashlib, importlib.util, json, pathlib, tempfile, unittest
from types import SimpleNamespace

D = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ir_entry', D / 'run_ir_only.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestIRScope(unittest.TestCase):
    def test_fixed_names(self):
        self.assertEqual(len(m.EXPECTED_NAMES), 8)
        overlay = json.loads((D / 'OVERLAY.json').read_text())
        self.assertEqual({r['name'] for r in overlay['files']}, m.EXPECTED_NAMES)
        self.assertEqual(overlay['source_count'], 155)
        self.assertEqual(overlay['expected_low_ports'], 122)

    def test_exact_selection_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            originals = []
            for name in sorted(m.EXPECTED_NAMES) + ['Other%d.scala' % i for i in range(147)]:
                p = root / 'original' / name
                p.parent.mkdir(exist_ok=True)
                p.write_text('original')
                originals.append(p)
            rows = []
            for name in sorted(m.EXPECTED_NAMES):
                p = root / 'candidate' / name
                p.parent.mkdir(exist_ok=True)
                p.write_text('candidate')
                rows.append(dict(name=name, path=str(p.relative_to(root)), bytes=9, sha256=m.sha(p)))
            overlay = dict(schema='FIXED155_OBSERVER_OVERLAY8_V1', source_count=155, files=rows)
            fixed = SimpleNamespace(checked_paths=lambda *args: originals)
            result = m.selected_sources(root, {}, overlay, fixed)
            self.assertEqual(len(result), 155)
            self.assertEqual(sum(a != b for a, b in zip(result, originals)), 8)
            (root / rows[0]['path']).write_text('tampered!')
            with self.assertRaises(ValueError):
                m.selected_sources(root, {}, overlay, fixed)

    def test_missing_duplicate_and_traversal_overlay(self):
        fixed = SimpleNamespace(checked_paths=lambda *args: [])
        overlay = json.loads((D / 'OVERLAY.json').read_text())
        for rows in (overlay['files'][:-1], overlay['files'][:-1] + [overlay['files'][0]]):
            bad = dict(overlay, files=rows)
            with self.assertRaises(ValueError):
                m.selected_sources(pathlib.Path('/unused'), {}, bad, fixed)
        bad = copy.deepcopy(overlay)
        bad['files'][0]['path'] = '../' + bad['files'][0]['name']
        with self.assertRaises(ValueError):
            m.selected_sources(pathlib.Path('/unused'), {}, bad, fixed)

    def test_complete_requires_native_cleanup_and_log(self):
        good = dict(native_exit=0, errors=[], cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'), log_capture=dict(pipe_eof_observed=True, gzip_finalized=True))
        self.assertTrue(m.completed(good))
        for key, value in [('native_exit', None), ('native_exit', 1), ('errors', ['failure']), ('cleanup_proof', {}), ('log_capture', {'pipe_eof_observed': True})]:
            self.assertFalse(m.completed(dict(good, **{key: value})))

    def test_java_fixed_helper_empty_args(self):
        argv = m.java_command('/jdk/bin/java', '4g', '/classes:/jars', 'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5')
        self.assertEqual(argv[-1], 'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5')
        self.assertIn('-XX:ActiveProcessorCount=1', argv)
        self.assertIn('-Xmx4g', argv)

    def test_only_reviewed_stages_and_caps(self):
        tree = ast.parse((D / 'run_ir_only.py').read_text())
        calls = [x for x in ast.walk(tree) if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == 'stage']
        names = [x.args[0].value for x in calls]
        self.assertEqual(names, ['jdk', 'compile_tools', 'jars', 'verilator_bytes', 'runtime_identity', 'compile155', 'original_ir'])
        ir = calls[-1]
        values = {k.arg: ast.literal_eval(k.value) for k in ir.keywords if not isinstance(k.value, ast.BinOp)}
        self.assertEqual(values, dict(wall=480, rss=5, heap_as=12, cpu=420, ir_specific=True))
        self.assertEqual(m.JOB_SECONDS, 3600)
        self.assertEqual(m.TREE, 12_081_306_272)

    def test_no_backend_or_payload_calls(self):
        text = (D / 'run_ir_only.py').read_text()
        for forbidden in ('one_job_build_only.py', 'run_frontend_serial', 'acquire_idma_artifact.py', 'recover_matrix_portable.py', 'reference_job.py', 'PortableHostHighSimulationEmitter', 'EmitPhysicalFmaStageLibrary', '--cc', '--binary'):
            self.assertNotIn(forbidden, text)
        self.assertIn("'--download-jars'", text)
        self.assertIn("'--execute-reviewed-acquisition'", text)
        self.assertNotIn('GH_TOKEN', text)

    def test_original_inventory_not_reimplemented(self):
        text = (D / 'inventory_host.py').read_text()
        self.assertIn('fresh_host.inventory(contract, a.java_home, a.verilator_root)', text)
        self.assertIn('fresh_host.validate_compile_inventory', text)
        self.assertNotIn('dependency_paths', text)

    def test_summary_scope_never_numeric(self):
        text = (D / 'run_ir_only.py').read_text()
        self.assertIn('numerical_pass=False', text)
        self.assertIn("len(raw.encode()) <= 65536", text)
        self.assertIn('FAILED_OR_INCOMPLETE', text)
        self.assertIn("'cleanup_proof'", text)

    def test_failure_does_not_mutate_preexisting_or_unowned_root(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            before = list(root.iterdir())
            self.assertFalse(m.write_failure_summary(root, {}, ValueError('rejected old root')))
            self.assertEqual(list(root.iterdir()), before)
            st = root.stat()
            bad = dict(path=str(root), dev=st.st_dev, ino=st.st_ino + 1)
            self.assertFalse(m.write_failure_summary(root, bad, ValueError('replaced root')))
            self.assertEqual(list(root.iterdir()), before)

    def test_failure_owned_root_summary_once_only(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t) / 'owned'
            root.mkdir()
            st = root.stat()
            owner = dict(path=str(root), dev=st.st_dev, ino=st.st_ino)
            self.assertTrue(m.write_failure_summary(root, owner, ValueError('not exported')))
            p = root / 'IR_SUMMARY.json'
            before = p.read_bytes()
            self.assertFalse(m.write_failure_summary(root, owner, RuntimeError('second')))
            self.assertEqual(p.read_bytes(), before)
            self.assertNotIn(b'not exported', before)

    def test_failure_symlink_root_does_not_write(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            target = root / 'target'
            target.mkdir()
            alias = root / 'alias'
            alias.symlink_to(target, target_is_directory=True)
            st = target.stat()
            self.assertFalse(m.write_failure_summary(alias, dict(path=str(alias), dev=st.st_dev, ino=st.st_ino), ValueError()))
            self.assertEqual(list(target.iterdir()), [])

    def test_ir_check_requires_new_ports(self):
        text = (D / 'check_ir.py').read_text()
        self.assertIn("measured_ports['low'] != 122", text)
        self.assertIn("('kind','rank','last')", text)
        self.assertIn('old_canonical_identity_compared=False', text)
        self.assertIn('block_numerical_pass=False', text)

if __name__ == '__main__':
    unittest.main()
