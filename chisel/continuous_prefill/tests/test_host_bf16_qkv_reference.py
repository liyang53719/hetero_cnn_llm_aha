"""Bounded reference bridge tests; mocked official payload, existing C core.

Mocked complete sessions test authority/plumbing only. The separate arithmetic
test compiles the unchanged existing C source and checks one synthetic K head.
No model capture, actual checkpoint reference generation or DUT is involved.
"""
import contextlib
import dataclasses
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str((SCRIPTS / 'pack_host_bf16_v_fixture.py').resolve().parent))
sys.path.insert(0, str(SCRIPTS))
import host_bf16_qkv_reference as ref
import pack_host_bf16_qkv_fixture as pack
import verify_host_bf16_qkv_fixture as admission
import host_bf16_qkv_execution as execution
sys.path.append(str(ref.ROOT / 'chisel/continuous_prefill/tests'))
import test_host_bf16_qkv_fixture as existing_fixture_tests


class FreshReferenceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.source = existing_fixture_tests.HostQkvFixtureTests(); self.source.setUp()
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(ref, 'load_payload', return_value=({'revision':pack.MODEL_REVISION}, self.source.raw)))
        self.calls = 0
        def compile_stub(directory):
            executable=directory/'c_matrix'; executable.write_bytes(b'unit-only C executable placeholder; never run')
            python=ref._tool_file(sys.executable)
            return executable, dict(compiler=python, compiler_version='UNIT_TEST_ONLY',compile_argv=['UNIT_TEST_ONLY'],
                executable=ref._tool_file(executable),dynamic_runtime={python['path']:python},python=python,
                python_version=sys.version,numpy_version=np.__version__,platform='UNIT_TEST_ONLY')
        def arithmetic_stub(activation,weight,executable,scratch):
            position=self.calls%12; self.calls+=1; columns=weight.shape[1]
            word=0x4000 if position<8 else 0x4040 if position<10 else 0x4080
            self.assertEqual(columns,512 if position<8 else 256)
            self.assertEqual(activation.dtype,np.dtype('<u2'))
            return dict(fp32=np.full(columns,word<<16,dtype='<u4').tobytes(),
                        bf16=np.full(columns,word,dtype='<u2').tobytes(),
                        fma_flags=np.zeros(columns,dtype='<u4').tobytes()), dict(
                            columns=columns,k=1024,matrix_accumulator_steps=1024*columns,
                            matrix_fp32_columns=columns,matrix_bf16_columns=columns,matrix_fma_flags=columns,
                            bit_mismatches=0,flag_mismatches=0,**{'pass':True},c_input_sha256='a'*64,
                            c_output_sha256='b'*64,integer_step_sha256='c'*64,c_step_sha256='c'*64,
                            bf16_conversion_flags_independently_checked=False)
        self.compile=self.stack.enter_context(patch.object(ref,'_compile_matrix',side_effect=compile_stub))
        self.arithmetic=self.stack.enter_context(patch.object(ref,'_project_and_crosscheck',side_effect=arithmetic_stub))

    def tearDown(self):self.stack.close(); self.source.tearDown()

    def generate(self,variants=ref.VARIANTS):
        return ref.generate_projection_references(self.source.session,self.source.base/'references',variants=variants)

    def inputs(self,variant='baseline',phase='cold',token=0):
        _,weights,_=ref._load_weights(self.source.session)
        activation,_=ref._load_window(self.source.session,self.source.official,variant,phase,token)
        return activation,weights

    def test_both_variants_and_windows_generate_once_repack_never_recomputes(self):
        session=self.generate(); receipt=session.verify(session=self.source.session)
        self.assertEqual(receipt['head_jobs'],48); self.assertEqual(receipt['matrix_accumulator_steps'],20971520)
        self.assertEqual(set(receipt['windows']),{'baseline/cold0','baseline/carried127','avx2/cold0','avx2/carried127'})
        self.assertEqual(receipt['native_full_block_gate_pass'],{'baseline':False,'avx2':False})
        self.assertFalse(receipt['full_block_supported']); self.assertFalse(receipt['persistent_accumulator_traces'])
        for variant in ref.VARIANTS:
            for phase,token,count in ref.WINDOWS:
                fixture=self.source.base/(variant+'_'+phase)
                manifest=pack.pack_fixture(fixture,variant=variant,phase=phase,token_base=token,token_count=count,
                                           session=self.source.session,reference_session=session)
                result=admission.verify(fixture,session=self.source.session,reference_session=session)
                self.assertTrue(result['fresh_reference_authority_verified']); self.assertTrue(ref.independent_admitted(result))
                self.assertFalse(manifest['independent_reference']['reused']); self.assertTrue(manifest['independent_reference']['generated'])
                self.assertEqual(manifest['native_full_block_gate_pass'],{'baseline':False,'avx2':False})
                with self.assertRaisesRegex(ValueError,'live independent reference authority'):
                    admission.verify(fixture,session=self.source.session)
        session.verify(session=self.source.session)
        self.assertEqual(self.arithmetic.call_count,48); self.compile.assert_called_once()

    def test_saved_receipt_or_forged_object_cannot_create_authority(self):
        session=self.generate(('baseline',)); activation,weights=self.inputs()
        with self.assertRaises(TypeError):ref.FreshProjectionReferenceSession(session.directory,session.receipt_sha256)
        forged=object.__new__(ref.FreshProjectionReferenceSession)
        with self.assertRaisesRegex(ValueError,'unissued'):forged.verify(session=self.source.session)
        clone=dataclasses.replace(self.source.session)
        with self.assertRaisesRegex(ValueError,'different live CaptureSession'):
            session.select(activation,weights,session=clone,variant='baseline',phase='cold',token_base=0,token_count=1)

    def test_replaced_terminal_matching_disk_receipt_hash_is_rejected(self):
        session=self.generate(('baseline',)); original=(session.directory/'receipt.json').read_bytes()
        report=json.loads(original); name=report['windows']['baseline/cold0']['terminals']['q']['bf16']
        path=session.directory/name; raw=path.read_bytes(); path.write_bytes(bytes([raw[0]^1])+raw[1:])
        with self.assertRaisesRegex(ValueError,'terminal bytes changed'):session.verify(session=self.source.session)
        report['files'][name]=ref._file_record(path)
        (session.directory/'receipt.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,'live authority'):session.verify(session=self.source.session)

    def test_different_input_full_weight_token_variant_and_geometry_rejected(self):
        session=self.generate(('baseline',)); activation,weights=self.inputs()
        kwargs=dict(session=self.source.session,variant='baseline',phase='cold',token_base=0,token_count=1)
        altered=activation.copy(); altered[127,0]^=1
        with self.assertRaisesRegex(ValueError,'activation/weight differs'):session.select(altered,weights,**kwargs)
        changed={key:value.copy() for key,value in weights.items()}; changed['v'][-1,-1]^=1
        with self.assertRaisesRegex(ValueError,'activation/weight differs'):session.select(activation,changed,**kwargs)
        for fields in ({'variant':'avx2'},{'phase':'carried','token_base':0},{'token_count':16},{'token_count':128},{'token_base':True}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):session.select(activation,weights,**(kwargs|fields))
        with self.assertRaises(ValueError):session.select(activation.astype('<u4'),weights,**kwargs)

    def test_source_tool_missing_inventory_and_symlink_drift_rejected(self):
        session=self.generate(('baseline',))
        with patch.object(ref,'_source_identity',return_value={}):
            with self.assertRaisesRegex(ValueError,'source changed'):session.verify(session=self.source.session)
        executable=session.directory/'c_matrix'; original=executable.read_bytes(); executable.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'runtime drift'):session.verify(session=self.source.session)
        executable.write_bytes(original)
        extra=session.directory/'unexpected';extra.mkdir()
        with self.assertRaisesRegex(ValueError,'directory inventory'):session.verify(session=self.source.session)
        extra.rmdir()
        receipt=session.verify(session=self.source.session); name=next(iter(receipt['files']))
        path=session.directory/name; original=path.read_bytes(); path.unlink(); path.symlink_to(session.directory/'c_matrix')
        with self.assertRaisesRegex(ValueError,'symlink'):session.verify(session=self.source.session)
        path.unlink();path.write_bytes(original)
        path.write_bytes(original[:-1])
        with self.assertRaisesRegex(ValueError,'terminal bytes changed'):session.verify(session=self.source.session)

    def test_failed_or_incomplete_generation_never_returns_receipt_authority(self):
        with patch.object(ref,'_project_and_crosscheck',side_effect=ValueError('C mismatch')):
            with self.assertRaisesRegex(ValueError,'C mismatch'):self.generate(('baseline',))
        self.assertFalse((self.source.base/'references/receipt.json').exists())
        with self.assertRaises(ValueError):self.generate(('baseline',))

    def test_pinned_branch_remains_exact_and_new_gate_needs_live_verifier_result(self):
        terminals={role:np.full(n,0x4000,dtype='<u2').tobytes() for role,n,_,_ in ref.ROLES}
        evidence=dict(status='REUSED_EXACT_INPUT_BOUND_INTEGER_AND_C_TERMINALS',reused=True,summary_sha256=pack.FROZEN_REFERENCE_SHA256)
        fixture=self.source.base/'pinned'
        with patch.object(pack,'frozen_terminals',return_value=(terminals,evidence)) as pinned:
            manifest=pack.pack_fixture(fixture,session=self.source.session)
            admitted=admission.verify(fixture,session=self.source.session)
            self.assertEqual(manifest['independent_reference'],evidence); self.assertTrue(ref.independent_admitted(admitted))
            self.assertNotIn('fresh_reference_authority_verified',admitted)
            self.assertEqual(pinned.call_count,2)
        self.compile.assert_not_called();self.arithmetic.assert_not_called()
        self.assertFalse(ref.independent_admitted({'independent_reference':{'origin':ref.ORIGIN,'generated':True,'reused':False}}))

    def test_execution_accepts_verified_fresh_authority_without_running_dut(self):
        session=self.generate(('baseline',));fixture=self.source.base/'fixture_fresh'
        pack.pack_fixture(fixture,session=self.source.session,reference_session=session)
        with patch.object(execution,'_build_identity',side_effect=RuntimeError('STOP_BEFORE_DUT')) as identity:
            with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_DUT'):
                execution.run_case(self.source.base/'no_build',fixture,session=self.source.session,reference_session=session)
            identity.assert_called_once()
        self.assertEqual(self.arithmetic.call_count,24)


class ExistingArithmeticTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc') and shutil.which('ldd'),'existing C toolchain required')
    def test_one_synthetic_k_head_existing_integer_and_c_all_steps(self):
        with tempfile.TemporaryDirectory(prefix='.qkv_reference_small_c_',dir=ref.ROOT/'work') as temporary:
            directory=Path(temporary); executable,tools=ref._compile_matrix(directory)
            a=np.zeros(1024,dtype='<u2');a[0]=0x3f80;a[1]=0x4000;a[-1]=0xbf80
            w=np.zeros((1024,256),dtype='<u2');w[0]=np.arange(256,dtype='<u2')%128+0x3f00;w[1]=0x3c00;w[-1]=0x3b80
            result,proof=ref._project_and_crosscheck(a,w,executable,directory)
            self.assertEqual(proof['matrix_accumulator_steps'],262144);self.assertTrue(proof['pass'])
            self.assertEqual(proof['integer_step_sha256'],proof['c_step_sha256'])
            self.assertEqual({key:len(value) for key,value in result.items()},{'bf16':512,'fp32':1024,'fma_flags':1024})
            self.assertFalse((directory/'matrix_c_inputs.bin').exists());self.assertFalse((directory/'matrix_c_outputs.bin').exists())
            ref._verify_tools(tools)


if __name__=='__main__':unittest.main()
