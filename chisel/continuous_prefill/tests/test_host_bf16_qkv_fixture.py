"""Mocked official-source admission tests. No Torch, oracle build or RTL work."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pack_host_bf16_qkv_fixture as pack
import verify_host_bf16_qkv_fixture as admission
from host_bf16_qkv_descriptor import parse_host_qkv_descriptor


class HostQkvFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='.host_qkv_unit_',dir=pack.ROOT/'work')
        self.base=Path(self.tmp.name); self.capture_dir=self.base/'official'; self.capture_dir.mkdir()
        self.payloads=[self.base/name for name in ('payload0','payload3','extra')]
        self.payload_records={'layer0':{'sha256':'0'*64},'layer3':{'sha256':'3'*64},'additional_prefix':{'sha256':'4'*64}}
        self.official={'payload_manifests':self.payload_records,'corpora':{}}
        self.activation=np.broadcast_to(np.arange(1,129,dtype='<f4').reshape(1,128,1),(1,128,1024)).copy()
        self.raw={}
        for role,n in zip(pack.ROLES,pack.COLUMNS):
            # Distinct row/column markers test the exact official transpose.
            word=(np.arange(n*1024,dtype=np.uint32).reshape(n,1024)%256+0x3f00).astype('<u2')
            self.raw['self_attn.'+role+'_proj.weight']=word.tobytes()
        arrays={'07':self.activation, '08':np.full((1,128,4096),2,dtype='<f4'),
                '17':np.full((1,128,512),3,dtype='<f4'), '26':np.full((1,128,512),4,dtype='<f4')}
        for variant in ('baseline','avx2'):
            directory=self.capture_dir/variant/'native'; directory.mkdir(parents=True)
            np.savez(directory/'all_bf16_producers.npz',**{phase+'_m128_native_producer_'+index:value for phase in ('cold','carried') for index,value in arrays.items()})
            report={'status':'BLOCKED_BF16_PRODUCER_GATE','gate_pass':False,
                    'failed_producers':[{'producer':'unit-only failed stage','pass':False}]}
            (directory/'result.json').write_text(json.dumps(report))
            self.official['corpora'][variant]={'native_audit_gate_pass':False,'native_audit_status':report['status'],
                'native_failed_comparisons':1, 'fresh_audit_arrays':pack.capture._record(directory/'all_bf16_producers.npz'),
                'fresh_audit_report':pack.capture._record(directory/'result.json')}
        (self.capture_dir/'provenance.json').write_text(json.dumps(self.official))
        self.digest=pack.sha((self.capture_dir/'provenance.json').read_bytes())
        def verify_source(root,directory,*,trusted_manifest_sha256):
            if trusted_manifest_sha256!=self.digest or pack.sha((Path(directory)/'provenance.json').read_bytes())!=self.digest:
                raise ValueError('untrusted source digest')
            return {}
        self.stack=contextlib.ExitStack()
        self.stack.enter_context(patch.object(pack.capture,'load_materialized',side_effect=verify_source))
        self.stack.enter_context(patch.object(pack.capture,'_payload_inputs',return_value=(self.payload_records,{})))
        self.stack.enter_context(patch.object(pack,'load_payload',return_value=({'revision':pack.MODEL_REVISION},self.raw)))
        self.stack.enter_context(patch.object(pack,'FROZEN_REFERENCE',self.base/'absent_reference'))
        self.session=pack.CaptureSession(self.capture_dir,self.digest,*self.payloads,True)

    def tearDown(self):
        self.stack.close(); self.tmp.cleanup()

    def test_source_bound_fanout_and_boundary_guard_geometry(self):
        fixture=self.base/'fixture'
        manifest=pack.pack_fixture(fixture,variant='avx2',phase='carried',token_base=127,token_count=1,session=self.session)
        result=admission.verify(fixture,session=self.session)
        self.assertEqual(result['scope'],'PROJECTION_ONLY')
        self.assertEqual(manifest['producer_native'],{'q':'carried_m128_native_producer_08','k':'carried_m128_native_producer_17','v':'carried_m128_native_producer_26'})
        self.assertEqual(manifest['native_full_block_gate_pass'],{'baseline':False,'avx2':False})
        self.assertEqual((manifest['fresh_official_executions'],manifest['reused_official_executions']),(2,0))
        self.assertFalse(manifest['full_block_supported']); self.assertFalse(manifest['norm_supported'])
        self.assertEqual(len((fixture/'host_commands.bin').read_bytes()),64)
        descriptor_raw=(fixture/'host_descriptors.bin').read_bytes()
        records={index:int.from_bytes(descriptor_raw[index*16:(index+1)*16],'little') for index in range(63)}
        command_raw=(fixture/'host_commands.bin').read_bytes()
        bindings=[parse_host_qkv_descriptor(int.from_bytes(command_raw[index*16:(index+1)*16],'little'),records) for index in range(3)]
        self.assertEqual([binding.job['writeBytes'] for binding in bindings],[8192,1024,1024])
        self.assertEqual(len({binding.job['a'] for binding in bindings}),1)
        for role,n in zip(pack.ROLES,pack.COLUMNS):
            expected=np.frombuffer(self.raw['self_attn.'+role+'_proj.weight'],dtype='<u2').reshape(n,1024).T.copy()
            self.assertEqual((fixture/('weight_'+role+'.bf16le')).read_bytes(),expected.tobytes())
        self.assertEqual(result['input_sha256']['activation_window'],pack.sha((fixture/'activation.bf16le').read_bytes()[127*2048:]))

    def test_fresh_receipt_not_cli_trust_anchor_and_tamper_rejected(self):
        fixture=self.base/'fixture'; manifest=pack.pack_fixture(fixture,session=self.session)
        with self.assertRaisesRegex(ValueError,'live same-invocation'):admission.verify(fixture)
        file=fixture/'weight_k.bf16le'; raw=bytearray(file.read_bytes()); raw[0]^=1; file.write_bytes(raw)
        # Matching self-declared hashes cannot authenticate an altered weight.
        manifest['files'][file.name]['sha256']=pack.sha(raw)
        manifest['input_sha256']['weight_tensor']['k']=pack.sha(raw)
        (fixture/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):admission.verify(fixture,session=self.session)
        for flag in ('--capture','--npz','--source','--trusted-manifest-sha256','--expected-output','--reference'):
            with self.subTest(flag=flag),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                pack.parser().parse_args([str(self.base/'out'),flag,'untrusted'])

    def test_native_array_hash_and_live_capture_drift_rejected(self):
        native=self.capture_dir/'baseline/native/all_bf16_producers.npz'
        native.write_bytes(native.read_bytes()+b'caller alteration')
        with self.assertRaises(ValueError):pack.pack_fixture(self.base/'bad_native',session=self.session)
        (self.capture_dir/'provenance.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'untrusted'):pack.pack_fixture(self.base/'bad_capture',session=self.session)

    def test_independent_terminal_reuse_requires_exact_actual_inputs(self):
        frozen=self.base/'frozen'; frozen.mkdir()
        activation=np.ones((128,1024),dtype='<u2')
        weights={role:np.ones((1024,n),dtype='<u2') for role,n in zip(pack.ROLES,pack.COLUMNS)}
        cases=[]
        for role,n in zip(pack.ROLES,pack.COLUMNS):
            width=512 if role=='q' else 256
            for head in range(n//width):
                directory=frozen/(role+str(head)); directory.mkdir()
                raw=('3f80\n'*width).encode(); (directory/'projected.memh').write_bytes(raw)
                cases.append(dict(variant='baseline',phase='carried',role=role,token=127,head=head,columns=width,
                    activation_sha256=pack.sha(activation[127].tobytes()),selected_weight_k_major_sha256=pack.sha(np.ones((1024,width),dtype='<u2').tobytes()),
                    directory=directory.name,c_reference=dict(pass_=True),files={'projected':dict(file='projected.memh',bytes=len(raw),sha256=pack.sha(raw),hex_digits=4)}))
                cases[-1]['c_reference']={'pass':True,'bit_mismatches':0,'flag_mismatches':0,'matrix_bf16_columns':width}
        summary=dict(revision=pack.MODEL_REVISION,framework_revision=pack.FRAMEWORK_REVISION,token_count_per_phase=128,cases=cases)
        raw=json.dumps(summary).encode(); (frozen/'summary.json').write_bytes(raw)
        with patch.object(pack,'FROZEN_REFERENCE',frozen),patch.object(pack,'FROZEN_REFERENCE_SHA256',pack.sha(raw)):
            result,evidence=pack.frozen_terminals(activation,weights,variant='baseline',phase='carried',token_base=127,token_count=1)
            self.assertTrue(evidence['reused']); self.assertEqual({role:len(data) for role,data in result.items()},{'q':8192,'k':1024,'v':1024})
            activation[127,0]=2
            result,evidence=pack.frozen_terminals(activation,weights,variant='baseline',phase='carried',token_base=127,token_count=1)
            self.assertEqual(result,{}); self.assertFalse(evidence['reused'])
            activation[127,0]=1; weights['v'][0,0]=2
            result,evidence=pack.frozen_terminals(activation,weights,variant='baseline',phase='carried',token_base=127,token_count=1)
            self.assertEqual(result,{}); self.assertFalse(evidence['reused'])


if __name__=='__main__':unittest.main()
