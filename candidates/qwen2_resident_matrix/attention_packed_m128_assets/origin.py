"""Pinned historical M128 provenance. No model, decoder, producer or ELF loading.

Exact historical receipt bytes are trusted inputs, then their source/geometry,
producer links and artifacts are independently checked. This never upgrades the
original budget-exhausted Public numerical attempt into a pass.
"""
import math
from pathlib import Path
from ..attention_packed_m16_assets import reuse as R
from ..raw_kv_public_fresh import assets as constants
need, same, digest = R.need, R.same, R.digest
HERE = Path(__file__).resolve().parent
PROFILE = 'qwen2-public-pv16-packed-m128-linked-v1'
PROVENANCE_SHA256 = '10082cdedd92040e85da2a6d2b5485ef93e9261e54cca3d291314a0dc2fbb2e6'
ARENA_SHA256 = 'e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7'
INPUT_X_SHA256 = 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'
MODES, METHODS = R.MODES, R.METHODS

def provenance():
 raw = R.safe_path(HERE/'provenance.json').read_bytes()
 need(R.sha(raw) == PROVENANCE_SHA256, 'M128 provenance contract changed')
 result = R.strict_json(raw)
 need(result['schema'] == 1 and type(result['schema']) is int and result['profile'] == PROFILE and
      all(v is False for v in result['claims'].values()), 'M128 non-execution provenance scope')
 return result

def shapes(rows=128):
 need(type(rows) is int and rows in (16,128), 'native canonical geometry')
 result = {n:[1,rows,1536] for n in ('x','n0','qr','att','o','r','n1','down','y')}
 result.update({n:[1,rows,256] for n in ('kr','v')})
 result.update({n:[1,rows,8960] for n in ('gate','up','silu','act')})
 result.update({n:[1,12,rows,rows] for n in ('scores','logits','prob','softmax_fp32')})
 result.update({n:[1,2,rows,128] for n in ('cache_k','cache_v','k')})
 result.update({n:[1,12,rows,128] for n in ('repeat_k','repeat_v','q','pv')})
 result.update(mask=[1,1,rows,rows], cos=[rows,128], sin=[rows,128])
 return result

def export_shapes(rows=128):
 result = shapes(rows); result.update(q=[1,rows,1536], k=[1,rows,256]); return result

def output_inventory():
 result = {'phase_%d_%s_recipe.f32le'%(i,n):128*w*4 for i,(n,w) in enumerate(R.STAGES)}
 result.update({n+'.f32le':4*math.prod(s) for n,s in shapes().items()
                if n in ('cache_k','cache_v','scores','logits','softmax_fp32','prob','silu')})
 return result

def validate_native(value, declared, payload_sha, *, rows, prerequisite_sha256):
    """Recheck original logical/export shapes and verdict metadata, without arrays."""
    need(type(rows) is int and rows in (16,128) and
         (prerequisite_sha256 is None if rows == 16 else digest(prerequisite_sha256)), 'native scope prerequisite')
    need(value['status'] == 'PASS_BF16_STAGE_BUDGET' and type(value['tokens']) is int
         and value['tokens'] == rows and value['carried'] is False
         and same(value['m16_gate_sha256'],prerequisite_sha256) and type(value['torch_threads']) is int
         and value['torch_threads'] == 4 and value['payload_manifest_sha256'] == payload_sha,
         'native exact M16/M128 scope')
    for name in ('rtl_execution','hardware_recipe_acceptance','logits','full_model_quality',
                 'manifest_whole_checkpoint_hash_verified'):
        need(value[name] is False, 'native acceptance claim drift')
    need(value['official_framework_forward'] is True and set(value['modes']) == set(MODES),
         'native reference modes')
    need(same(value['policy']['operator'],{'max_abs':0.03125,'mean_abs':0.005}) and
         same(value['policy']['block'],{'max_abs':0.05,'mean_abs':0.01}) and
         value['policy']['sha256'] == '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5',
         'unchanged original numerical policy')
    need(declared['producer'] == 'qwen2-native-qkv-qk-pair-generated-v1', 'recipe-native producer')
    shape_map, export_map = shapes(rows), export_shapes(rows)
    need(set(declared['outputs']) == set(MODES), 'native export precision inventory')
    for mode in MODES:
        phases = value['modes'][mode]['phases']
        need(type(phases) is list and len(phases) == 1, 'native cold phase count')
        phase = phases[0]
        need(type(phase['phase']) is int and phase['phase'] == 0 and
             type(phase['past_tokens']) is int and phase['past_tokens'] == 0 and
             phase['token_ids'] == phase['position_ids'] == list(range(rows)) and
             all(type(v) is int for v in phase['token_ids'] + phase['position_ids']), 'native token positions')
        expected_semantics = {'mask_exact','native_fp32_probability_sum_within_2e_5',
            'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
            'native_cache_append_v_exact','independent_cache_append_k_exact',
            'independent_cache_append_v_exact','native_future_probability_zero','independent_future_probability_zero'}
        need(set(phase['semantics']) == expected_semantics and
             all(v is True for v in phase['semantics'].values()) and phase['all_semantics_exact'] is True,
             'native semantic checks')
        need(set(phase['stages']) == set(shape_map) and set(declared['outputs'][mode]) == set(METHODS),
             'native stage/method inventory')
        failures = []
        for method in METHODS:
            need(set(declared['outputs'][mode][method]) == set(shape_map), 'native export stage inventory')
        for name, shape in shape_map.items():
            item = phase['stages'][name]
            need(same(item['shape'],shape) and type(item['elements']) is int and
                 item['elements'] == math.prod(shape) and item['finite'] is True, 'native stage geometry/finite')
            if name == 'mask':
                need(item['contract'] == 'exact_causal_mask' and item['bit_exact'] is True and
                     item['passed'] is True, 'exact native causal mask')
            elif mode == 'fp32' or name == 'softmax_fp32':
                need(item['passed'] is None and item['contract'] is None and
                     item['status'] == 'DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE', 'diagnostic-only FP32')
            else:
                limits = value['policy']['block' if name == 'y' else 'operator']
                need(same(item['limits'],limits) and all(type(item[k]) in (int,float) and
                     math.isfinite(item[k]) and 0 <= item[k] <= limits[k] for k in ('max_abs','mean_abs'))
                     and item['passed'] is True and item['contract'] == 'spec/numerical_contract.md:'+
                     ('block' if name == 'y' else 'operator'), 'unchanged native BF16 stage limits')
            if item['passed'] is False:
                failures.append(name)
            for method, prefix in zip(METHODS, ('native','independent')):
                record = declared['outputs'][mode][method][name]
                relative = '%s/phase_0/%s_%s.f32le' % (mode,prefix,name)
                need(item[prefix+'_file'] == relative and same(item[prefix+'_export_shape'],export_map[name])
                     and record['path'] == ('native_m16/' if rows == 16 else 'native/') + relative and type(record['bytes']) is int
                     and record['bytes'] == 4*math.prod(shape)
                     and item[prefix+'_file_sha256'] == record['sha256'], 'native export shape/path/hash')
        need(phase['failed_stages'] == failures, 'native failure inventory')
        need(phase['status'] == ('PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32'),
             'native phase status')


def validate_assets(value, pins):
 """Pure shape checks supplement the exact immutable ASSETS receipt pin."""
 constants.exact(value, ('library','native','native_m16','past_tokens','payload','profile','readonly',
  'recipe','reduced','rows','schema','sequential','source_manifest_sha256','source_sha256','status'), 'origin ASSETS schema')
 need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == pins['origin_asset_profile'] and
      value['status'] == 'READY_FOR_ACTUAL_M128' and type(value['rows']) is int and value['rows'] == 128 and
      type(value['past_tokens']) is int and value['past_tokens'] == 0, 'unaltered original M128 asset scope')
 need(value['source_manifest_sha256'] == pins['origin_source_manifest_sha256'] ==
      R.sha(R.encoded(value['source_sha256'])), 'origin source manifest digest')
 constants.exact(value['payload']['tensors'], constants.TENSOR_PINS, 'authentic thirteen tensors')
 for name,pin in constants.TENSOR_PINS.items():
  constants.record(value['payload']['tensors'][name],size=pin['bytes'],expected=pin['sha256'])
 ro=value['readonly']
 constants.record(ro['arena'],size=constants.ARENA_BYTES,expected=ARENA_SHA256)
 constants.record(ro['input_x'],size=128*1536*4,expected=INPUT_X_SHA256)
 constants.record(ro['table'],size=(192+5*16384)*4,expected=constants.TABLE_SHA256)
 need(ro['input_x_sha256'] == INPUT_X_SHA256 and type(ro['intermediate_preloads']) is int and
      ro['intermediate_preloads'] == 0, 'M128 input identity or zero-preload policy')
 for role in ('sequential','reduced'):
  producer=value[role]
  need(producer['producer'] == constants.PRODUCERS[role], 'original oracle producer role')
  constants.record(producer['cpp'],expected=constants.CPP_SHA256[role])
  constants.record(producer['header'],expected=constants.HEADER_SHA256)
  constants.exact(producer['outputs'],output_inventory(),'exact M128 oracle output inventory')
  for name,size in output_inventory().items():constants.record(producer['outputs'][name],size=size)
 constants.exact(value['sequential']['tensors'],shapes(),'exact M128 export inventory')
 for name,shape in shapes().items():constants.record(value['sequential']['tensors'][name],size=4*math.prod(shape))
 return value

def validate_links(meta, pins, workspace):
 assets=validate_assets(meta['private/assets/ASSETS.json'],pins)
 original_actual=meta['private/actual/summary.json']; original_launch=meta['evidence/summary.json']
 need(original_actual['status'] == original_launch['status'] == 'FAILED' and
      type(original_actual['rows']) is int and original_actual['rows'] == 128 and
      original_actual['native_acceptance'] == 'PENDING_OBSERVED_NODE_GATES' and
      original_actual['error'] == 'public FFN host budget exceeded' and
      original_launch['numerical_acceptance'] is False and original_launch['full_29_node_acceptance'] is False,
      'original M128 budget failure must remain a failure')
 setup=meta['private/assets/SETUP.json']; summary=meta['private/setup_evidence/summary.json']
 need(setup['status'] == summary['status'] == 'COMPLETE_FRESH_SETUP' and
      setup['rows'] == 128 and setup['past_tokens'] == 0 and setup['enable_raw_kv'] is True and
      setup['checkout_commit'] == pins['origin_commit'] and setup['source_recheck'] == summary['source_recheck'] == 'UNCHANGED' and
      setup['completed_phases'] == summary['completed_phases'], 'authentic original completed setup')
 need(setup['asset_manifest_sha256'] == summary['manifest_sha256'] == pins['metadata']['private/assets/ASSETS.json']['sha256'] and
      summary['setup_receipt_sha256'] == pins['metadata']['private/assets/SETUP.json']['sha256'], 'original setup receipt links')
 st=workspace.stat()
 need(same(setup['workspace'],dict(path=str(workspace),device=st.st_dev,inode=st.st_ino)), 'actual original workspace identity')
 need(same(setup['source_sha256'],assets['source_sha256']) and all(x['source_manifest_sha256'] ==
      pins['origin_source_manifest_sha256'] for x in (assets,setup,summary)), 'original source receipt links')
 backend=meta['private/assets/backend.json']
 need(backend['cpu_capability'] == 'AVX512' and backend['torch_commit'] == '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0' and
      type(backend['intraop_threads']) is int and backend['intraop_threads'] == 4 and
      type(backend['interop_threads']) is int and backend['interop_threads'] == 1 and backend['deterministic'] is True,
      'recorded original backend policy')
 small=meta['private/assets/native_m16/RESULT.json']; native=meta['private/assets/native/RESULT.json']
 for role,result,rows,prereq in [('native_m16',small,16,None),('native',native,128,assets['native_m16']['result']['sha256'])]:
  validate_native(result,assets[role],assets['payload']['manifest']['sha256'],rows=rows,prerequisite_sha256=prereq)
  identity=dict(result['identity']); recipe=identity.pop('independent_qkv_recipe')
  need(identity.pop('runner_sha256') == assets['recipe']['generated_module']['sha256'] and
       recipe['backend_order_proven'] is False, 'original generated native recipe identity')
  expected=dict(backend['identity']); expected.pop('runner_sha256')
  need(same(identity,expected), 'native/backend exact source/build identity')
  for kernel in ('qk','qkv'):
   need(recipe[kernel]['library_sha256'] == assets['recipe'][kernel]['binary']['sha256'], 'native pair library identity')
   for name,digest_ in recipe[kernel]['source_sha256'].items():
    need(assets['source_sha256'].get(name) == digest_, 'native pair source closure identity')
 need(same(small['identity'],native['identity']) and same(small['policy'],native['policy']) and
      same(small['blas_environment'],native['blas_environment']), 'M128 native prerequisite identity')
 for role in ('sequential','reduced'):
  producer=assets[role];run=meta['private/assets/'+role+'/run.json'];built=meta['private/assets/'+role+'/compile.json']
  need(type(built['returncode']) is int and built['returncode'] == 0 and built['status'] == 'COMPILED' and
       built['producer'] == run['producer'] == constants.PRODUCERS[role] and same(built['source_sha256'],assets['source_sha256']) and
       built['cpp_sha256'] == producer['cpp']['sha256'] and built['header_sha256'] == producer['header']['sha256'] and
       built['binary_sha256'] == producer['executable']['sha256'], 'oracle compile/source identity')
  need(type(run['returncode']) is int and run['returncode'] == 0 and run['status'] == 'COMPLETE_REFERENCE_ONLY' and
       run['actual_chain_executed'] is False and run['readonly_sha256'] == ARENA_SHA256 and
       run['input_x_sha256'] == INPUT_X_SHA256 and run['table_sha256'] == constants.TABLE_SHA256 and
       same(run['output_sha256'],{n:r['sha256'] for n,r in producer['outputs'].items()}), 'oracle M128 receipt identity')
  p=lambda item: str(R.checked(workspace,item,content=False))
  need(built['argv'] == [built['compiler']['path'],'-O2','-std=c++17','-ffp-contract=off','-fno-fast-math',
       p(producer['cpp']),'-o',p(producer['executable'])], 'authentic original oracle compile paths')
  need(run['argv'] == [p(producer['executable']),p(assets['readonly']['arena']),'128',
       str(workspace/role/'raw_stages'),'0',p(run['empty_cache']),p(run['empty_cache'])], 'authentic original M128 oracle run paths')
  ack=run['software_ack']
  need(ack['hardware_ack_verified'] is False and ack['phase_receipts_exactly_once_in_order'] is True and
       ack['process_completion_ack'] is True, 'original oracle process-only acknowledgement')
 exports=meta['private/assets/sequential/export.json']
 need(type(exports) is list and [e['name'] for e in exports] == sorted(shapes()), 'M128 export inventory')
 for e in exports:
  name=e['name']; constants.exact(e,('name','path','shape','export_shape','sha256'),'M128 export record')
  need(e['path'] == 'candidate_'+name+'.f32le' and same(e['shape'],shapes()[name]) and
       same(e['export_shape'],export_shapes()[name]) and e['sha256'] == assets['sequential']['tensors'][name]['sha256'],
       'original token-major M128 export shape/hash')
 return assets,native,exports

def snapshot(origin, *, content=True):
 """Stream bytes only; caller compares two complete snapshots around admission."""
 need(type(content) is bool, 'canonical content mode')
 root=R.safe_path(origin,directory=True); pins=provenance()
 meta={n:R.read_metadata(root,n,p) for n,p in pins['metadata'].items()}
 workspace=R.safe_path(root/'private/assets',directory=True)
 assets,native,exports=validate_links(meta,pins,workspace)
 sources={n:R.file_hash(R.below(root/'private/checkout',n)) for n in assets['source_sha256']}
 need(same(sources,assets['source_sha256']), 'historical composed source changed')
 declared=list(R.records(assets))
 # These two ancillary records are part of the original run receipts too.
 for role in ('sequential','reduced'):
  run=meta['private/assets/'+role+'/run.json'];declared.extend([run['stdout'],run['empty_cache']])
 paths=[];identity={}
 for item in declared:
  suffix=Path(item['path']).suffix
  path=R.checked(workspace,item,content=content or suffix in ('.json','.cpp','.py','.h','.log'))
  st=path.stat(); paths.append(path)
  identity[item['path']]=dict(bytes=item['bytes'],sha256=item['sha256'],device=st.st_dev,inode=st.st_ino)
 R.no_aliases(paths)
 for role in ('sequential','reduced'):
  compiler=meta['private/assets/'+role+'/compile.json']['compiler']
  if content: need(R.file_hash(compiler['path']) == compiler['sha256'], 'original oracle compiler bytes changed')
 return dict(schema=1,profile=PROFILE,origin=str(root),origin_commit=pins['origin_commit'],
  origin_manifest_sha256=pins['metadata']['private/assets/ASSETS.json']['sha256'],
  source_manifest_sha256=R.sha(R.encoded(sources)),metadata_sha256={n:p['sha256'] for n,p in pins['metadata'].items()},
  artifacts=identity,payload_bytes_hashed=content,actual_chain_executed=False,old_pass_inherited=False,
  full_29_node_acceptance=False),assets,native,exports

def source_snapshot():
 """Preparation-time asset adapter closure, independent of entry installation."""
 root=HERE.parents[2]; pins=R.strict_json(R.safe_path(HERE/'pins.json').read_bytes())
 need(type(pins) is dict and set(pins)=={'schema','profile','sources','execution_authorized'} and
  type(pins['schema']) is int and pins['schema']==1 and pins['profile']==PROFILE and pins['execution_authorized'] is False, 'asset source-only contract')
 expected=pins['sources'];need(type(expected) is dict and expected, 'asset source closure')
 for name,digest_ in expected.items():
  need(R.digest(digest_) and R.file_hash(R.below(root,name))==digest_, 'M128 asset source drift: '+name)
 result=dict(expected)
 result['candidates/qwen2_resident_matrix/attention_packed_m128_assets/pins.json']=R.file_hash(HERE/'pins.json')
 return result
