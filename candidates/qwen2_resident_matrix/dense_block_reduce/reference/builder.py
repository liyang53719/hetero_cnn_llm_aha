"""Prepare an independent v2 reference with only explicit QKV dot-order changes.

Preparation regenerates/guards the old C++ and writes source; it never compiles
or runs the block, native framework, owners, Matrix model, Chisel, or RTL.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
if __package__:
    from . import workload as w
else:
    import workload as w

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
VERSION='qwen2-official-bf16-v2-qkv-block-pair-reference-v1'
ORIGINAL_CPP_SHA='0cdfd2c6927eec8dfb72e315e9a1107d6966d47b6326de077bf77a9e3a73ded6'
HEADER_SHA='79d4b81277f3431d2e89e6807dc2deee425957a5549c7fffa71d8db8cba9af30'
PROFILE_REL='candidates/qwen2_resident_matrix/dense_block_reduce/reference/profile.json'
PROFILE_SHA='07008af966dbe4d64b10f75c37e4d19e17159e3708543982a70c8ec996f1d5a5'
CONTRACT_SHA='5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'
ARCHIVES={16:('68299c6687734408bf4ac03eae5efe149ed4042113f919eff4c379e78a8558a2','5f2a709fc932ba5cbf436847010c4154d4e7c68ecc1d90f2c82db3b6785ed3f9'),128:('99d551a40ca38af3d196015cf2dbb6e4ea80bdfec1f33f7c0d5cbb58a9131ac0','ae99b4ce2aceebcbbd9c83b1cbf2ab64605314ae60dfbf5423258db6469d2ab9')}
GENERATOR_PINS={
 'scripts/qwen2_rms_rope_prefill_candidate.py':'41aea07ba09fc5c11f6aafbe14e83ebdba6e843a3cf47080a954a1032b6461e9',
 'scripts/qwen2_carried_prefill_candidate.py':'9df9ad51f98c7273ce8847a47a090093edd23c48289cf9e964f44a8ac3cd41b6',
 'scripts/qwen2_bf16_materialization_candidate.py':'357a74dd10b69fb78e2aff34410d1a01c881edbebbcf5d422bed2ee8acb47dbd',
 'scripts/qwen2_rms_rope_policy_diagnostic.py':'9117f240243357786bd538908343fcfb3a791769f2061d585524594b96b76ef6',
 'scripts/qwen2_block_recipe_model.py':'2b7a4384bc619d39546714b251f286708646029eea172de8c28fb4946b69a2f6',
 'scripts/qwen2_layer0_model_gate.py':'917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85',
}
CALLS=(
 'dense(OFF_N0,OFF_WQ,OFF_QR,H,H,OFF_BQ);',
 'dense(OFF_N0,OFF_WK,OFF_KR,H,KV,OFF_BK);',
 'dense(OFF_N0,OFF_WV,OFF_V,H,KV,OFF_BV);',
)
BEGIN='  // BEGIN '+VERSION+'\n'
END='  // END '+VERSION+'\n'
ANCHOR='  void dense(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias=-1){'
FLAGS=['-O2','-std=c++17','-ffp-contract=off','-fno-fast-math']

def require(ok,message):
    if not ok: raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def file_sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def frozen_json(path,expected):
    raw=Path(path).read_bytes();require(sha(raw)==expected,'frozen JSON identity: '+str(path));return json.loads(raw)

def validate_blocks(blocks,k):
    require(type(k) is int and k>0 and isinstance(blocks,(tuple,list)) and len(blocks)==2,
            'two explicit K blocks required')
    require(all(type(n) is int and n>0 and n%2==0 for n in blocks) and sum(blocks)==k,
            'positive even blocks must cover K exactly')
    return tuple(blocks)

def profile_parameters(raw):
    require(sha(raw)==PROFILE_SHA,'unreviewed backend profile bytes')
    value=json.loads(raw);p=value['parameters'];blocks=validate_blocks(p['block_sizes'],1536)
    require(p['pair_width']==2 and p['pair_order']=='high_then_low' and
            p['output']=='BF16 RNE once after bias','profile rounding/order differs')
    cases=value['numerically_verified_cases']
    expected={(f'm{m}_{role}',m,n) for m in (16,128) for role,n in (('q',1536),('k',256),('v',256))}
    actual={(c['case'],c['input_shape'][1],c['weight_shape'][0]) for c in cases}
    require(actual==expected and len(cases)==6 and
            all(c['input_shape']==[1,c['input_shape'][1],1536] and c['weight_shape'][1]==1536 and
                c['model_sha256']==c['native_sha256'] for c in cases),'profile full-shape evidence differs')
    return value,blocks

def regenerate_sources(root=ROOT):
    """Recreate both numerical C++ and header using guarded repository sources."""
    root=Path(root)
    for relative,digest in GENERATOR_PINS.items():
        require(file_sha(root/relative)==digest,'generator source drift before import: '+relative)
    sys.path.insert(0,str(root/'scripts'))
    try:
        spec=importlib.util.spec_from_file_location('qkv_independent_archived_generator',root/'scripts/qwen2_rms_rope_prefill_candidate.py')
        require(spec is not None and spec.loader is not None,'generator loader unavailable')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        text,identity=module.candidate_source(root)
        layout=module.R.make_layout();module.G.validate_layout(layout)
        header=module.R.header(layout).encode()
    finally:sys.path.pop(0)
    raw=text.encode();require(sha(raw)==ORIGINAL_CPP_SHA,'regenerated original C++ differs')
    require(sha(header)==HEADER_SHA,'regenerated original header differs')
    for relative,digest in GENERATOR_PINS.items():require(file_sha(root/relative)==digest,'generator source changed during regeneration')
    return raw,header,identity

def regenerate_original(root=ROOT):
    raw,_,identity=regenerate_sources(root)
    return raw,identity

def helper_source(blocks):
    blocks=validate_blocks(blocks,1536)
    dot=(HERE/'dot16.inc').read_text()
    wrapper='''  void dense_qkv_block_pair(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias){
    need(K==1536 && (N==1536 || N==256) && (tokens==16 || tokens==128) && past==0,
         "QKV reference profile covers cold M16/M128 K1536 only");
    const std::array<int,2> blocks{{BLOCK_SIZES}};
    std::vector<float> a(K);
    for(unsigned t=0;t<tokens;t++){
      for(int k=0;k<K;k++)a[k]=bf(get(in,size_t(t)*K+k));
      for(int col=0;col<N;col+=16){
        float sums[16]={};
        reference_qkv_pair_dot16(a.data(),reference.data()+w/4,K,N,col,blocks.data(),blocks.size(),sums);
        for(int j=0;j<16;j++)put(out,size_t(t)*N+col+j,bf(bias>=0?add(sums[j],get(bias,col+j)):sums[j]));
      }
    }
  }
'''.replace('BLOCK_SIZES',','.join(map(str,blocks)))
    return BEGIN+dot+wrapper+END

def transform(original:bytes,profile_raw:bytes):
    require(sha(original)==ORIGINAL_CPP_SHA,'original numerical C++ identity differs')
    profile,blocks=profile_parameters(profile_raw);source=original.decode();helper=helper_source(blocks)
    require(BEGIN not in source and END not in source and source.count(ANCHOR)==1,'original insertion anchor differs')
    changed=source.replace(ANCHOR,helper+ANCHOR,1)
    for call in CALLS:
        require(changed.count(call)==1,'QKV call identity differs: '+call)
        changed=changed.replace(call,call.replace('dense(','dense_qkv_block_pair(',1),1)
    raw=changed.encode();audit=verify_transform(original,raw,profile_raw)
    audit.update(version=VERSION,original_cpp_sha256=sha(original),candidate_cpp_sha256=sha(raw),
                 profile_sha256=sha(profile_raw),dot16_source_sha256=file_sha(HERE/'dot16.inc'),
                 block_sizes=list(blocks),changed_call_count=3,helper_sha256=sha(helper.encode()))
    return raw,audit

def verify_transform(original:bytes,candidate:bytes,profile_raw:bytes):
    require(sha(original)==ORIGINAL_CPP_SHA,'original numerical C++ identity differs')
    _,blocks=profile_parameters(profile_raw);text=candidate.decode();helper=helper_source(blocks)
    require(text.count(helper)==1 and text.count(BEGIN)==text.count(END)==1,'explicit helper changed/duplicated')
    restored=text.replace(helper,'',1)
    for call in CALLS:
        replacement=call.replace('dense(','dense_qkv_block_pair(',1)
        require(restored.count(replacement)==1,'QKV replacement missing/duplicated')
        restored=restored.replace(replacement,call,1)
    require(restored.encode()==original,'non-QKV source differs after masking explicit change')
    return dict(all_other_source_byte_exact=True,restored_original_sha256=sha(restored.encode()),
                unchanged_original_dense=True,unchanged_RMS_RoPE_QK_PV_FFN_softmax_bias_BF16=True,
                acceptance='Independent producer auxiliary only; original official target and thresholds unchanged; no dual-AND with old sequential producer')

def archive_context(rows,root=ROOT,*,archive_directory=None):
    require(type(rows) is int and rows in ARCHIVES,'reference supports M16/M128 only')
    require(archive_directory is not None,'explicit archive_directory required for real preparation/completed evidence')
    root=Path(root);directory=Path(archive_directory).resolve()
    top=frozen_json(directory/'RESULT.json',ARCHIVES[rows][0]);cold=frozen_json(directory/'cold/RESULT.json',ARCHIVES[rows][1])
    require(top['tokens']==cold['tokens']==rows and cold['past_tokens']==0 and cold['inputs']['intermediate_preloads']==0,'archive workload differs')
    require(top['phase_result_sha256']['cold']==ARCHIVES[rows][1] and
            top['build']['cpp_sha256']==ORIGINAL_CPP_SHA and
            top['build']['header_sha256']==HEADER_SHA,'archive source/header identities differ')
    require(file_sha(root/'spec/numerical_contract.md')==CONTRACT_SHA,'official thresholds/contract changed')
    return directory,top,cold

def verify_actual_source(rows,source,thresholds):
    rows=w.cold_rows(rows);pin=w.INPUT_PINS[rows]
    require(source['summary_sha256']==pin['summary_sha256'] and source['snapshot_sha256']==pin['snapshot_sha256'],
            'actual input metadata identities differ')
    summary=frozen_json(source['summary_path'],pin['summary_sha256'])
    require(summary['snapshot_sha256']==pin['snapshot_sha256'],'actual summary/snapshot binding differs')
    snapshot=frozen_json(source['snapshot_path'],pin['snapshot_sha256'])
    expected_x=dict(bytes=rows*1536*4,sha256=pin['input_x_sha256'])
    require(summary['rows']==snapshot['rows']==rows and summary['loaded_inputs']['x']==snapshot['loaded_inputs']['x']==expected_x and
            summary['prelaunch_intermediate_payloads']==snapshot['prelaunch_intermediate_payloads']==[],
            'actual raw input shape or intermediate preload differs')
    require(snapshot['reference']['threshold_policy']==thresholds,
            'official gate policy differs')

def verify_input_binding(prepared,top,cold,*,require_actual_source=True):
    rows=w.cold_rows(prepared['rows'],prepared['past_tokens'])
    record=prepared['readonly_input'];pin=w.validate_input_metadata(rows,cold,record)
    arena=Path(record['path']);layout=top['build']['layout']
    require(arena.is_file() and arena.stat().st_size==record['bytes']==layout['writable_start'] and
            file_sha(arena)==record['sha256'],'original readonly arena bytes differ')
    x=next(r for r in layout['regions'] if r['name']=='x')
    with arena.open('rb') as stream:stream.seek(x['offset']);raw_x=stream.read(rows*1536*4)
    require(len(raw_x)==rows*1536*4 and sha(raw_x)==pin['input_x_sha256'],'original raw x slice differs')
    require(prepared['thresholds']==top['threshold_policy'],'official gate policy differs')
    source=prepared.get('actual_input_source')
    if source is None:
        require(not require_actual_source,'explicit actual summary/snapshot input provenance required')
        return
    verify_actual_source(rows,source,prepared['thresholds'])

def prepare(rows,out,*,archive_directory,snapshot_path,actual_summary_path,root=ROOT,readonly_arena=None,profile_path=None):
    rows=w.cold_rows(rows)
    root=Path(root);out=Path(out).resolve();require(not out.exists(),'fresh preparation directory required')
    directory,top,cold=archive_context(rows,root,archive_directory=archive_directory)
    original,header,identity=regenerate_sources(root)
    profile_path=Path(profile_path) if profile_path else root/PROFILE_REL;profile_raw=profile_path.read_bytes()
    candidate,audit=transform(original,profile_raw)
    arena=Path(readonly_arena) if readonly_arena else directory/'cold/readonly_arena.f32le'
    require(arena.is_file() and file_sha(arena)==cold['inputs']['readonly_sha256'],'same original readonly arena required')
    layout=top['build']['layout'];require(arena.stat().st_size==layout['writable_start'],'readonly arena length differs')
    x=next(r for r in layout['regions'] if r['name']=='x')
    with arena.open('rb') as stream:stream.seek(x['offset']);raw_x=stream.read(rows*1536*4)
    require(sha(raw_x)==cold['inputs']['input_x_sha256'],'original raw x slice differs')
    input_record=dict(path=str(arena.resolve()),bytes=arena.stat().st_size,sha256=file_sha(arena),input_x_sha256=sha(raw_x),actual_snapshot_raw_x_bit_exact=True,intermediate_preloads=0)
    pin=w.INPUT_PINS[rows]
    actual_source=dict(summary_path=str(Path(actual_summary_path).resolve()),summary_sha256=pin['summary_sha256'],
                       snapshot_path=str(Path(snapshot_path).resolve()),snapshot_sha256=pin['snapshot_sha256'])
    verify_input_binding(dict(rows=rows,past_tokens=0,readonly_input=input_record,actual_input_source=actual_source,
                              thresholds=top['threshold_policy']),top,cold)
    compiler=shutil.which('g++');require(compiler is not None,'g++ unavailable')
    out.mkdir(parents=True);(out/'candidate.cpp').write_bytes(candidate);(out/'block_layout.h').write_bytes(header);(out/'empty_cache.bin').write_bytes(b'')
    receipt=dict(schema=1,version=VERSION,status='PREPARED_SOURCE_ONLY_NOT_EXECUTED',rows=rows,past_tokens=0,
        transform=audit,source_sha256={str(p.relative_to(root)):file_sha(p) for p in (Path(__file__),HERE/'dot16.inc',HERE/'workload.py')},
        original_generator_source_sha256=GENERATOR_PINS,original_generator_identity=identity,
        old_archive=dict(directory=str(directory),top_sha256=ARCHIVES[rows][0],cold_sha256=ARCHIVES[rows][1],
                         preserved_failures={k:v['failed_stages'] for k,v in cold['evaluation']['methods'].items()}),
        profile_path=str(profile_path),profile_sha256=PROFILE_SHA,header_sha256=HEADER_SHA,
        readonly_input=input_record,actual_input_source=actual_source,
        compile_command=[compiler,*FLAGS,str(out/'candidate.cpp'),'-o',str(out/'candidate')],
        proposed_execution_command=[str(out/'candidate'),str(arena.resolve()),str(rows),str(out/'raw_stages'),'0',str(out/'empty_cache.bin'),str(out/'empty_cache.bin')],
        output_directory_must_be_created_before_launch=str(out/'raw_stages'),
        thresholds=top['threshold_policy'],threshold_contract_sha256=CONTRACT_SHA,
        acceptance=dict(official_target_unchanged=True,independent_reference_is_auxiliary=True,dual_AND_with_old_sequential_reference=False,old_FAIL_preserved=True,native_acceptance=False),
        estimates=dict(historical_M16_full_reference_seconds=4.228034998999647,historical_M128_full_reference_seconds=30.55065688200193,proposed_M16_reference_seconds=[4,10],recommended_compile_wall_timeout_seconds=w.COMPILE_WALL_SECONDS,recommended_run_wall_timeout_seconds=w.RUN_WALL_SECONDS[rows],basis='Historical same-source independent producer; only QKV reduction changes. Estimate, not a new execution.'),
        compiled=False,full_block_executed=False,new_native_executed=False,rtl_executed=False)
    (out/'PREPARED.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rows',type=int,choices=(16,128),required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--archive-directory',type=Path,required=True);parser.add_argument('--snapshot-path',type=Path,required=True)
    parser.add_argument('--actual-summary-path',type=Path,required=True)
    args=parser.parse_args();r=prepare(args.rows,args.out,archive_directory=args.archive_directory,snapshot_path=args.snapshot_path,actual_summary_path=args.actual_summary_path);print(json.dumps(dict(status=r['status'],rows=r['rows'],candidate_cpp_sha256=r['transform']['candidate_cpp_sha256'],all_other_source_byte_exact=True)))
