"""Cold geometry, independent seal gates and original AST identity; no arithmetic."""
import ast,copy,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
from . import common as c,geometry as g,inputs as inp,reference as ref
from .stage_log import COUNTER_LIMITS

def model_record():
    counters={n:0 for n in COUNTER_LIMITS};counters.update(completed=21,jobs=17,accepted_results=1)
    return dict(status='M16_MODEL_COMPLETE_COST_DIAGNOSTIC',scope='M16_PUBLIC21_STAGE_COST_DIAGNOSTIC',logical_rows=16,physical_matrix_rows=128,
      **{n:True for n in ('model_completed','actual_outputs_sealed','whole_block_terminal','finalfence','source_post_verified','input_post_verified','native_post_verified')},
      **{n:False for n in ('formal_reference_contract','fullblock_pass','reference_executed','old_wrapper_optimizations_loaded')},
      execution=dict(host=dict(launch_result=dict(status=None,completed=21,jobs=17),accepted=dict(completion_fire=21,request_fire=17,owner_result_fire=17,result_fire=1))),
      backend_debts=dict(memory=False),native_before={'p':1},native_after={'p':1},artifact_before={'e':1},artifact_after={'e':1},final_counters=counters)

class Cold(unittest.TestCase):
    def test_fixed_geometry(self):
        self.assertEqual(g.CAUSAL,1632);self.assertEqual(g.ATTENTION['normal_steps'],19584)
        self.assertEqual(g.EXACT,dict(fmas=44040192,adds=1835008,tiles=448,write_bytes=114688,read_requests=1379328))
        self.assertEqual(g.WHOLE['dense_fma'],5637144576);self.assertEqual(g.WHOLE['normal_fma'],10027008)
        self.assertEqual(g.WHOLE['useful_macs'],749101056);self.assertEqual(g.WHOLE['executed_macs'],5691211776)
        self.assertEqual(g.WHOLE['matrix_opportunities'],5717360640)
    def test_real_fixture_extents(self):
        p=c.dependencies()['p'];f=p.make_qwen2_21_fixture(16,7)
        self.assertEqual(f.allocations['x'].storage_bytes,16*1536*4)
        self.assertEqual(f.allocations['rope'].storage_bytes,524288)
        self.assertEqual(f.config.regions[3].limit-f.config.regions[3].base,g.WORKSPACE_BYTES)
        for role,spec in inp.ROLES.items():self.assertEqual(f.allocations[role].storage_bytes,16*1536*4 if role=='x' else spec['bytes'])
        self.assertEqual(f.allocations['kv'].storage_bytes,32768)
    def test_input_slice_only_x(self):
        # Tiny mocked role payloads test the production slice rule, without
        # reading real weights or claiming a new numerical stimulus.
        with patch.object(inp,'sha',side_effect=lambda p:inp.MANIFESTS[str(p.relative_to(inp.ROOT))]), \
             patch.object(inp,'checked',side_effect=lambda path,spec: bytes(spec['bytes'])):
            values,records=inp.load_inputs()
        self.assertEqual(len(values['x']),98304);self.assertEqual(len(values['rope']),524288)
        for role in inp.ROLES:self.assertEqual(records[role]['rule'],'LEADING_16_TOKEN_ROWS' if role=='x' else 'EXACT_COMPLETE_ORIGINAL_ROLE')
    def test_original_ast_pin_geometry(self):
        R=c.dependencies()['recipe'];pins=json.loads((c.ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_text())
        self.assertEqual(len(R.official_nodes(c.ROOT,pins['model_ast_nodes'],R.MODEL_SOURCE,pins['sources'])),38)
        self.assertEqual(len(R.official_nodes(c.ROOT,pins['activation_ast_nodes'],R.ACTIVATION_SOURCE,pins['sources'])),14)
        src=Path(ref.__file__).read_text();self.assertIn('q_len=16,kv_seq_len=16',src)
        self.assertIn('0xff7f if k > q else 0',src);self.assertNotIn('float(\'-inf\')',src)
        self.assertIn('execute(nodes[36:37])',src)
    def test_model_seal_positive(self):self.assertTrue(ref.validate_model_record(model_record()))
    def test_model_seal_each_flag(self):
        for field in ('model_completed','actual_outputs_sealed','whole_block_terminal','finalfence','source_post_verified','input_post_verified','native_post_verified'):
            r=model_record();r[field]=False
            with self.assertRaises(ValueError):ref.validate_model_record(r)
        for field in ('formal_reference_contract','fullblock_pass','reference_executed','old_wrapper_optimizations_loaded'):
            r=model_record();r[field]=True
            with self.assertRaises(ValueError):ref.validate_model_record(r)
    def test_model_seal_counters_and_debt(self):
        for field in ('completion_fire','request_fire','owner_result_fire','result_fire'):
            r=model_record();r['execution']['host']['accepted'][field]-=1
            with self.assertRaises(ValueError):ref.validate_model_record(r)
        for field,value in (('backend_debts',{'pending':True}),('native_after',{}),('artifact_after',{})):
            r=model_record();r[field]=value
            with self.assertRaises(ValueError):ref.validate_model_record(r)
    def test_raw_names_mapping(self):
        pins=json.loads((c.ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_text());seen=[]
        with patch.object(inp,'checked',side_effect=lambda path,spec:seen.append((path,spec['local_name'])) or b''):
            self.assertEqual(len(inp.raw13(pins)),13)
        self.assertTrue(all(name+'.bin'==Path(path).name for path,name in seen))
        self.assertEqual(sum(p.startswith(inp.PREFIX_RAW) for p,n in seen),8)
    def test_tail_events_exact(self):
        from types import SimpleNamespace
        matrix=dict(counters={k:g.WHOLE[k] for k in ('dense_steps','normal_steps')},dense_fma_calls=g.WHOLE['dense_fma'],normal_fma_calls=g.WHOLE['normal_fma'])
        launch={k:g.WHOLE[k] for k in ('useful_macs','executed_macs')}
        silu=SimpleNamespace(calls=8960,sf_calls=lambda:8960,sf_failures=lambda:0)
        counts=dict(dense_steps=1363968,dense_groups=162,dense_results=800,owner_acquires=114,owner_releases=114,dense_seed_acks=144)
        stats=dict(full_fixed_array_issued_cell_opportunities=g.WHOLE['matrix_opportunities'],intervals=[dict(name='pc13_Dense',accepted_counter_delta=dict(matrix=counts))])
        self.assertEqual(g.whole(matrix,launch,silu,stats)['observed_tail'],counts)
        for key in counts:
            bad=copy.deepcopy(stats);bad['intervals'][0]['accepted_counter_delta']['matrix'][key]-=1
            with self.assertRaises(ValueError):g.whole(matrix,launch,silu,bad)
    def test_sources_without_private_work(self):
        original=Path.open
        def guarded(path,*args,**kw):
            if path.absolute().is_relative_to(c.ROOT/'work'):raise AssertionError('cold source inventory touched private work')
            return original(path,*args,**kw)
        with patch.object(Path,'open',guarded):sources=c.sources_now()
        self.assertGreater(len(sources),100)
        self.assertTrue(all(not name.startswith('work/') for name in sources))
        self.assertIn('candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json',sources)
    def test_no_optimizing_wrapper_import(self):
        c.dependencies();self.assertFalse(any(n.startswith(('candidates.qwen2_quiescent_ports_candidate','candidates.qwen2_idle_drain_candidate')) for n in sys.modules))
    def test_reference_avx2_profile(self):
        from candidates.qwen2_fullblock_ci_execution.runtime_profile import AVX2_BUILD_SHA256
        self.assertEqual(AVX2_BUILD_SHA256,'4096ae2ff210db4a4da17fe7e5ef17c7715c4e4dc5d4175a9357b83bf820075a')
        self.assertEqual(ref.EXPECTED_RUNTIME['capability'],'AVX2');self.assertIs(ref.EXPECTED_RUNTIME['mkldnn_enabled'],False)
        import os
        for key in ('ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
            with patch.dict(os.environ,{**c.ENV,key:'anything'},clear=True):
                with self.assertRaisesRegex(ValueError,'override'):c.check_environment()
    def test_full_inventory_required(self):
        from candidates.qwen2_exact64_diagnostic_fullblock.retention import ACTUAL_NAMES
        import math
        shapes=ref.observation_shapes();inventory={};fields={}
        for name in ACTUAL_NAMES|{'silu'}:
            width=8960 if name in ('gate','up','silu','act') else 256 if name in ('kraw','kr','k','vraw','v') else 512 if name=='kv' else 1536
            inventory['actual_'+name+'.f32le']=dict(bytes=16*width*4,sha256='0'*64)
        inventory['attention_observation/summary.json']=dict(bytes=1,sha256='0'*64)
        for name,shape in shapes.items():
            count=576 if name=='normalizer' else 24576 if name.startswith('pv_') else g.CAUSAL*(16 if name=='dot_parts' else 1)
            writes=4*g.CAUSAL if name in ('softmax_fp32','prob_bf16') else 12*g.CAUSAL if name=='normalizer' else count
            fields[name]=dict(shape=list(shape),words=math.prod(shape),observed_words=count,writes=writes)
            for suffix,mult,key in (('.u32le',4,'raw_sha256'),('.presence',1,'presence_sha256'),('.count.u16le',2,'frequency_sha256')):
                fields[name][key]='0'*64;inventory['attention_observation/'+name+suffix]=dict(bytes=math.prod(shape)*mult,sha256='0'*64)
        r=dict(local_retention=dict(schema=1,scope='DIAGNOSTIC_SOFTWARE_OWNER',status='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE',
          local_only=True,upload_authorized=False,oracle_payloads_read=False,reference_operands_in_execution=False,inventory=inventory),
          observation=dict(schema='qwen2-pv32-readonly-observation-v1',status='COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED',
          observer_error=None,probability_repeats=4,causal_only=True,future_scores_observed=False,job=dict(m=16),terminal=dict(status=None,write_bytes=98304),fields=fields))
        self.assertTrue(ref.validate_inventory(r))
        for key in inventory:
            bad=copy.deepcopy(r);del bad['local_retention']['inventory'][key]
            with self.assertRaises(ValueError):ref.validate_inventory(bad)
        for group,key,value in (('local_retention','scope','WRONG'),('local_retention','status','WRONG'),('observation','status','INCOMPLETE')):
            bad=copy.deepcopy(r);bad[group][key]=value
            with self.assertRaises(ValueError):ref.validate_inventory(bad)
    def test_default_entry_cold(self):
        from . import runner
        self.assertEqual(runner.main([]),0);self.assertEqual(ref.main([]),0)
        for fn in (runner.main,ref.main):
            with self.assertRaises(ValueError):fn(['--out','private/path'])
if __name__=='__main__':unittest.main()
