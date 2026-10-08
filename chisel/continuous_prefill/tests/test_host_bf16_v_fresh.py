# SPDX-License-Identifier: Apache-2.0
"""Lightweight mocked-source tests only. Never capture Torch or compile RTL."""
from pathlib import Path
import contextlib,hashlib,io,json,os,sys,tempfile,unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pack_host_bf16_v_fixture as pack
import verify_host_bf16_v_fixture as admission
import run_host_bf16_v_fresh_gate as fresh
import run_host_bf16_v_replays as replay
import host_bf16_v_toolchain as toolchain

class FreshHostVTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='.host_v_fresh_unit_',dir=pack.ROOT/'work')
        self.base=Path(self.tmp.name);self.capture_dir=self.base/'official';self.capture_dir.mkdir()
        self.payloads=[self.base/x for x in ('payload0','payload3','extra')]
        self.records={'layer0':{'sha256':'0'*64},'layer3':{'sha256':'3'*64},'additional_prefix':{'sha256':'4'*64}}
        self.official={'payload_manifests':self.records,'corpora':{},'source_sha256':{'unit-only/native.py':'a'*64}}
        a=np.broadcast_to(np.arange(1,129,dtype='<f4').reshape(1,128,1),(1,128,1024)).copy()
        y=np.full((1,128,512),2,dtype='<f4')
        for variant in ('baseline','avx2'):
            d=self.capture_dir/variant/'native';d.mkdir(parents=True)
            np.savez(d/'all_bf16_producers.npz',**{p+'_m128_native_producer_'+i:arr for p in ('cold','carried') for i,arr in (('07',a),('26',y))})
            report={'status':'BLOCKED_BF16_PRODUCER_GATE','gate_pass':False,
                'failed_producers':[{'producer':'unit-only failure','pass':False}],
                'thresholds':{'operator':{'max_abs':0.03125,'mean_abs':0.005}},'softmax_invariants':[]}
            (d/'result.json').write_text(json.dumps(report))
            self.official['corpora'][variant]={'native_audit_gate_pass':False,'native_audit_status':report['status'],
                'native_failed_comparisons':1,'fresh_audit_arrays':pack.capture._record(d/'all_bf16_producers.npz'),
                'fresh_audit_report':pack.capture._record(d/'result.json')}
        (self.capture_dir/'provenance.json').write_text(json.dumps(self.official))
        self.digest=fresh.sha(self.capture_dir/'provenance.json')
        self.loads=[]
        def load(root,directory,*,trusted_manifest_sha256):
            self.loads.append(trusted_manifest_sha256)
            if trusted_manifest_sha256!=self.digest or fresh.sha(Path(directory)/'provenance.json')!=trusted_manifest_sha256:
                raise ValueError('untrusted materialized manifest digest')
            return {}
        self.stack=contextlib.ExitStack()
        self.stack.enter_context(patch.object(pack.capture,'load_materialized',side_effect=load))
        self.stack.enter_context(patch.object(pack.capture,'_payload_inputs',return_value=(self.records,{})))
        self.stack.enter_context(patch.object(pack,'load_payload',return_value=({'revision':'unit-test-only'},
            {'self_attn.v_proj.weight':np.full(512*1024,0x3f80,dtype='<u2').tobytes()})))
        self.session=pack.CaptureSession(self.capture_dir,self.digest,*self.payloads,True)
    def tearDown(self):self.stack.close();self.tmp.cleanup()

    def test_rebuild_return_digest_retained_and_disk_cannot_replace_it(self):
        with patch.object(pack.capture,'rebuild',return_value=({},self.digest)) as rebuild:
            session=pack.rebuild_session(self.capture_dir,*self.payloads)
        self.assertEqual(rebuild.call_args.args,(pack.ROOT,*self.payloads,self.capture_dir))
        self.assertEqual(session.manifest_sha256,self.digest)
        raw=json.loads((self.capture_dir/'provenance.json').read_text());raw['caller_digest']='f'*64
        (self.capture_dir/'provenance.json').write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'untrusted'):session.verify()
        self.assertEqual(set(self.loads),{self.digest})

    def test_fresh_pack_and_verify_source_bytes_and_counts(self):
        fixture=self.base/'fixture'
        m=pack.pack_fixture(fixture,variant='avx2',phase='carried',token_base=47,token_count=81,session=self.session)
        self.assertEqual((m['fresh_official_executions'],m['reused_official_executions']),(2,0))
        self.assertIs(m['cross_host_byte_equivalence_claimed'],False)
        self.assertEqual(m['native_full_block_gate_pass'],{'baseline':False,'avx2':False})
        result=admission.verify(fixture,session=self.session)
        self.assertEqual(result['input_sha256'],pack.fixture_input_hashes(fixture,m))
        self.assertEqual(result['input_sha256']['activation_window'],hashlib.sha256((fixture/'activation.bf16le').read_bytes()[47*2048:128*2048]).hexdigest())
        # Standalone verifier cannot resurrect a saved fresh session or trust its SHA.
        with self.assertRaisesRegex(ValueError,'live same-invocation'):admission.verify(fixture)
        p=fixture/'activation.bf16le';raw=bytearray(p.read_bytes());raw[0]^=1;p.write_bytes(raw)
        with self.assertRaises(ValueError):admission.verify(fixture,session=self.session)

    def test_legacy_code_pinned_capture_format_stays_supported(self):
        old=pack.CaptureSession(self.capture_dir,self.digest,*self.payloads,False)
        fixture=self.base/'old_fixture';m=pack.pack_fixture(fixture,session=old)
        self.assertNotIn('capture_mode',m);self.assertEqual((m['fresh_official_executions'],m['reused_official_executions']),(0,2))
        m['sources']=pack.LEGACY_PINNED_SOURCES
        (fixture/'manifest.json').write_text(json.dumps(m))
        with patch.object(admission,'pinned_session',return_value=old):
            self.assertEqual(admission.verify(fixture)['status'],'PASS_CODE_PINNED_HOST_V_FIXTURE')
        m['sources']=dict(pack.LEGACY_PINNED_SOURCES);m['sources'][next(iter(m['sources']))]='f'*64
        (fixture/'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError):admission.verify(fixture,session=old)

    def test_no_caller_capture_npz_or_trust_digest_cli(self):
        for flag in ('--capture','--npz','--source','--trusted-manifest-sha256','--expected-output','--reuse-capture'):
            with self.subTest(flag=flag),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                fresh.parser().parse_args(['--output',str(self.base/'out'),flag,'untrusted'])

    def test_cli_defaults_and_hash_only_upload_allowlist(self):
        args=fresh.parser().parse_args(['--output',str(self.base/'out'),'--full128'])
        self.assertEqual(args.burst,'0');self.assertEqual(args.payload_layer3,pack.ROOT/'work/qwen35_layer3_payload')
        out=self.base/'compact_test';out.mkdir()
        fresh._write_compact(out,{'status':'UNIT_TEST_ONLY'},{'source_sha256':{'test':'a'*64}})
        self.assertEqual({p.name for p in (out/'compact').iterdir()},fresh.COMPACT_FILES)
        (out/'compact/weights.npz').write_bytes(b'not an uploadable artifact')
        with self.assertRaisesRegex(ValueError,'non-allowlisted'):fresh._write_compact(out,{}, {})

    def test_preflight_failure_writes_only_compact_json_without_capture(self):
        out=self.base/'preflight_failed';args=fresh.parser().parse_args(['--output',str(out)])
        with patch.dict(os.environ,{'IDMA_EXPORT':''},clear=False),patch.object(fresh,'rebuild_session') as rebuild:
            result,code=fresh.run(args)
        self.assertEqual(code,1);self.assertEqual(result['stage'],'preflight');rebuild.assert_not_called()
        self.assertFalse(result['capture_verification_succeeded']);self.assertIsNone(result['fresh_official_executions'])
        self.assertEqual({p.name for p in (out/'compact').iterdir()},fresh.COMPACT_FILES)

    def test_full_flow_retains_one_session_and_build_only_is_not_acceptance(self):
        out=self.base/'flow';args=fresh.parser().parse_args(['--output',str(out),'--full128'])
        idma=self.base/'idma';idma.mkdir();(idma/'idma.f.in').write_text('unit stub, never compiled')
        events=[]
        def build(command,**kwargs):
            events.append('build');self.assertEqual(command[2],'--build-only')
            self.assertNotIn(self.digest,' '.join(command));self.assertEqual(kwargs['env']['BUILD_JOBS'],'1')
            directory=Path(command[3]);directory.mkdir();(directory/'sources.sha256.json').write_text('{}');(directory/'toolchain.json').write_text(json.dumps({'compiler_jars_sha256':{'unit.jar':'f'*64},'hardfloat_source_sha256':{'unit.scala':'e'*64}}))
        def representative(directory,fixture,session):
            events.append('representative');self.assertIs(session,self.session)
            return {'status':'UNIT_TEST_ONLY','actual_sha256':'a'*64,'binary_sha256':'b'*64,'rtl_sha256':'c'*64}
        def replays(directory,destination,**kwargs):
            events.append('full128');self.assertIs(kwargs['session'],self.session)
            self.assertTrue(kwargs['only_full128']);self.assertTrue(kwargs['full128'])
            return {'cases':[{'name':v+'_'+p,'input_sha256':{'activation_window':'d'*64},'actual_sha256':'e'*64}
                for v in ('baseline','avx2') for p in ('cold','carried')]}
        with patch.dict(os.environ,{'IDMA_EXPORT':str(idma),'BUILD_JOBS':'1','GITHUB_SHA':'0'*40},clear=False),\
             patch.object(fresh,'rebuild_session',return_value=self.session) as rebuild,\
             patch.object(fresh,'_git_head',return_value='0'*40),\
             patch.object(fresh,'verify_idma_export',return_value={'commits':{'idma':'unit stub'}}),\
             patch.object(fresh.subprocess,'run',side_effect=build),\
             patch.object(fresh,'run_representative',side_effect=representative),\
             patch.object(fresh,'verify_all_build_sources',side_effect=lambda *a: events.append('final_sources')),\
             patch.object(fresh,'run_replays',side_effect=replays):
            result,code=fresh.run(args)
        self.assertEqual(code,0);rebuild.assert_called_once();self.assertEqual(events,['build','representative','full128','final_sources'])
        self.assertEqual((result['fresh_official_executions'],result['reused_official_executions']),(2,0))
        self.assertEqual(len(result['full128_cases']),4);self.assertIs(result['cross_host_byte_equivalence_claimed'],False)
        self.assertEqual(result['native_full_block_failures']['baseline']['failed_producers'][0]['pass'],False)
        hashes=json.loads((out/'compact/source_input_hashes.json').read_text())
        self.assertEqual(hashes['official_capture_manifest_sha256'],self.digest)
        self.assertEqual(len(hashes['input_sha256']),5)
        self.assertEqual(result['git_head'],'0'*40);self.assertTrue(result['git_head_verified_unchanged'])
        self.assertIn('unit-only/native.py',hashes['source_sha256'])
        self.assertEqual(result['toolchain']['compiler_jars_sha256'],{'unit.jar':'f'*64})
        self.assertEqual(set(self.loads),{self.digest})

    def test_capture_drift_after_build_cannot_become_pass(self):
        out=self.base/'drift';args=fresh.parser().parse_args(['--output',str(out)])
        def bad_build(command,**kwargs):
            directory=Path(command[3]);directory.mkdir();(directory/'toolchain.json').write_text('{}')
            (self.capture_dir/'provenance.json').write_text('{}')
        with patch.dict(os.environ,{'GITHUB_SHA':'0'*40},clear=False),patch.object(fresh,'_preflight',return_value={}),patch.object(fresh,'_git_head',return_value='0'*40),patch.object(fresh,'rebuild_session',return_value=self.session),\
             patch.object(fresh.subprocess,'run',side_effect=bad_build):
            result,code=fresh.run(args)
        self.assertEqual(code,1);self.assertEqual(result['status'],'FAIL_FRESH_PRODUCTION_HOST_V_ONLY')
        self.assertFalse(result['capture_verification_succeeded'])
        self.assertIn('final_capture_verification_error',result)
        self.assertEqual(set(self.loads),{self.digest})

    def test_idma_preflight_calls_fixed_export_verifier_before_capture(self):
        export=self.base/'export';export.mkdir();(export/'idma.f.in').write_text('not trusted by itself')
        with patch.object(fresh,'verify_idma_export',side_effect=ValueError('iDMA revision drift')) as check:
            with self.assertRaisesRegex(ValueError,'revision drift'):
                fresh._preflight({'IDMA_EXPORT':str(export),'BUILD_JOBS':'1'},self.base)
        check.assert_called_once_with(export,self.base/'idma_preflight')

    def test_replay_end_guard_rejects_compiled_and_hardfloat_drift(self):
        root=self.base/'mock_checkout';build=self.base/'mock_build';build.mkdir()
        relative='chisel/continuous_prefill/src/main/StreamingDense.scala'
        src=root/relative;src.parent.mkdir(parents=True);src.write_text('unit-only source')
        hf=self.base/'hf';hfs=hf/'hardfloat/src/main/scala';hfs.mkdir(parents=True)
        file=hfs/'Unit.scala';file.write_text('unit-only HardFloat')
        (build/'sources.sha256.json').write_text(json.dumps({relative:fresh.sha(src)}))
        (build/'hardfloat.sha256.json').write_text(json.dumps({'hardfloat/src/main/scala/Unit.scala':fresh.sha(file)}))
        (build/'build_ready.json').write_text(json.dumps({'hardfloat_source':str(hf)}))
        with patch.object(replay,'ROOT',root):
            replay.verify_compiled_sources(build)
            src.write_text('changed during final replay')
            with self.assertRaisesRegex(ValueError,'compiled source changed'):replay.verify_compiled_sources(build)
            src.write_text('unit-only source');file.write_text('changed HardFloat')
            with self.assertRaisesRegex(ValueError,'HardFloat source changed'):replay.verify_compiled_sources(build)
        body=(fresh.SCRIPT_DIR/'run_host_bf16_v_replays.py').read_text()
        self.assertGreaterEqual(body.count('verify_compiled_sources(build)'),3)

    def test_compact_tool_maps_match_actual_jar_bytes(self):
        build=self.base/'tool_build';build.mkdir();maven=build/'maven';maven.mkdir()
        jar=maven/'unit.jar';jar.write_bytes(b'unit-only compiler artifact')
        exports=self.base/'tool_export';exports.mkdir()
        pinned={'commits':{'idma':'unit-only'},'files_verified':1,'export_manifest_sha256':'a'*64}
        source_map={'idma/target/rtl/idma_generated.sv':'b'*64,'idma/include/idma/compute.svh':'c'*64}
        (exports/'SHA256SUMS.json').write_text(json.dumps(source_map))
        tools={'firtool':{'sha256':'d'*64,'version':'unit-test-only'}}
        (build/'toolchain_before.json').write_text(json.dumps(tools))
        (build/'compiler_jars.sha256.json').write_text(json.dumps({'unit.jar':fresh.sha(jar)}))
        (build/'hardfloat.sha256.json').write_text(json.dumps({'hardfloat/src/main/scala/Unit.scala':'e'*64}))
        (build/'idma_identity.json').write_text(json.dumps(pinned))
        with patch.dict(os.environ,{'IDMA_EXPORT':str(exports),'OFFLINE_TOOLS':''},clear=False),\
             patch.object(toolchain,'tool_identity',return_value=tools),\
             patch.object(toolchain,'verify_idma_export',return_value=pinned):
            report=toolchain.build_identity(build)
            self.assertTrue(report['compiler_jars_verified_after_build'])
            self.assertEqual(report['idma_export_source_sha256'],source_map)
            self.assertEqual(report['compiler_jars_sha256'],{'unit.jar':fresh.sha(jar)})
            jar.write_bytes(b'changed jar after compilation')
            with self.assertRaisesRegex(ValueError,'compiler dependency changed'):toolchain.build_identity(build)

    def test_wrong_github_commit_rejected_before_expensive_capture(self):
        args=fresh.parser().parse_args(['--output',str(self.base/'git_mismatch')])
        with patch.dict(os.environ,{'GITHUB_SHA':'1'*40},clear=False),\
             patch.object(fresh,'_git_head',return_value='0'*40),\
             patch.object(fresh,'rebuild_session') as rebuild:
            result,code=fresh.run(args)
        self.assertEqual(code,1);rebuild.assert_not_called()
        self.assertIn('GITHUB_SHA',result['error']['message'])

    def test_final_production_verification_failure_never_mints_pass(self):
        args=fresh.parser().parse_args(['--output',str(self.base/'source_drift')])
        def build(command,**kwargs):
            directory=Path(command[3]);directory.mkdir()
            (directory/'toolchain.json').write_text('{}');(directory/'sources.sha256.json').write_text('{}')
        result_stub={'actual_sha256':'a'*64,'binary_sha256':'b'*64,'rtl_sha256':'c'*64}
        with patch.dict(os.environ,{'GITHUB_SHA':'0'*40},clear=False),\
             patch.object(fresh,'_git_head',return_value='0'*40),patch.object(fresh,'_preflight',return_value={}),\
             patch.object(fresh,'rebuild_session',return_value=self.session),patch.object(fresh.subprocess,'run',side_effect=build),\
             patch.object(fresh,'run_representative',return_value=result_stub),\
             patch.object(fresh,'verify_all_build_sources',side_effect=ValueError('compiled source changed after replay')):
            result,code=fresh.run(args)
        self.assertEqual(code,1);self.assertEqual(result['stage'],'final_source_and_capture_verification')
        self.assertEqual(result['status'],'FAIL_FRESH_PRODUCTION_HOST_V_ONLY')
        self.assertIn('compiled source changed',result['error']['message'])

    def test_frozen_materializer_not_reimplemented_and_gate_capped(self):
        source=(fresh.SCRIPT_DIR/'pack_host_bf16_v_fixture.py').read_text()
        self.assertIn('capture.rebuild(ROOT,*inputs',source);self.assertIn('capture.load_materialized(',source)
        self.assertNotIn('qwen35_qkv_candidate',source)
        gate=(fresh.SCRIPT_DIR/'run_host_bf16_v_gate.sh').read_text()
        self.assertIn('JOBS=${BUILD_JOBS:-1}',gate)
        self.assertIn('BUILT_HOST_V_ONLY_NOT_NUMERICAL_PASS',gate)
        self.assertLess(gate.index('BUILT_HOST_V_ONLY_NOT_NUMERICAL_PASS'),gate.index('for MODE in pass last-write-error'))

if __name__=='__main__':unittest.main()
