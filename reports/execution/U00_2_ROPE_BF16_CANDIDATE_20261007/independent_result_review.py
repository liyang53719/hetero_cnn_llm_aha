#!/usr/bin/env python3
"""Independently verify final source-bound evidence, native traces, conversions.

Usage: python independent_result_review.py [result_directory_or_result.json] [output.json]
No assertion can disappear under python -O. All checks use explicit failures.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('independent_converter_review',REPORT/'independent_converter_review.py')
reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)


def require(condition,message):
    if not condition: raise ValueError(message)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'work/rope_bf16_candidate_result_final/result.json'
    if path.is_dir(): path=path/'result.json'
    r=json.loads(path.read_text());directory=path.parent
    require(r['status']=='PASS_EXPERIMENTAL_BF16_ROPE_RTL_COMPONENT_ONLY','wrong scope/status')
    for key in ('production_policy_changed','native_model_expectations_regenerated','PPA_measured','memory_packing_or_store_tested','full_block_hardware_oracle_complete','U00_2_complete','U01_complete','mac_utilization_measured'):
        require(r[key] is False,f'scope inflated: {key}')
    for filename,digest in r['source_sha256'].items():
        require(sha(ROOT/filename)==digest,f'current source mismatch: {filename}')
    for filename,item in r['artifacts'].items():
        target=directory/filename
        require(target.stat().st_size==item['bytes'] and sha(target)==item['sha256'],f'artifact changed: {filename}')
    fixture_dir=ROOT/'tests/fixtures/rope_rounding'
    for filename,digest in r['fixture_sha256'].items():
        require(sha(fixture_dir/filename)==digest,f'frozen fixture changed: {filename}')
    expected=np.load(directory/'oracle_traces.npy',allow_pickle=False)
    require(expected.shape==(177458,25),'trace count/shape')
    crows=np.concatenate([np.load(directory/(x+'_independent_c.npy'),allow_pickle=False) for x in ('local','remote','synthetic')])
    require(np.array_equal(crows,expected),'actual run used C differences')
    require(r['synthetic_independent_C']['FP32_min_normal_tininess_differences']==[],'C flag waiver used')
    sources=[]; independent_node_conversions=0
    mapping=[(i,8+i,12+i) for i in range(4)]+[(16+i,20+i,22+i) for i in range(2)]
    for pipe in (0,1):
        rows=np.load(directory/f'pipe{pipe}_stalled_rtl.npy',allow_pickle=False)
        require(np.array_equal(rows,expected),'DUT trace mismatch')
        for name,start in (('local',0),('remote',81920)):
            corpus=np.load(fixture_dir/(name+'.npz'),allow_pickle=False)
            # Immutable bundle records are widened FP32 representations of BF16.
            require(np.array_equal(rows[start:start+81920,8:12],corpus['native_products']),'native product mismatch')
            require(np.array_equal(rows[start:start+81920,20:22],corpus['native_outputs']),'native output mismatch')
        for raw,value,flags in mapping:
            for triple in rows[:,[raw,value,flags]]:
                exp=reference.nearest_neighbor_reference(int(triple[0]))
                require(exp==(int(triple[1]),int(triple[2])),'independent nearest-neighbor DUT conversion mismatch')
                independent_node_conversions+=1
        continuous=np.load(directory/f'pipe{pipe}_continuous_rtl.npy',allow_pickle=False)
        require(np.array_equal(continuous,expected[163840:163840+512]),'continuous trace mismatch')
    cin=np.load(directory/'converter_inputs.npy',allow_pickle=False)
    cout=np.load(directory/'converter_rtl.npy',allow_pickle=False)
    require(cin.shape==(331776,1) and cout.shape==(331776,2),'converter shape')
    for word,output in zip(cin[:,0],cout):
        require(reference.nearest_neighbor_reference(int(word))==tuple(map(int,output)),'standalone DUT conversion mismatch')
    protocol=json.loads((REPORT/'independent_protocol_review.json').read_text())
    for filename,digest in protocol['source_sha256'].items():
        require(sha(ROOT/filename)==digest,f'protocol source mismatch: {filename}')
    alias=json.loads((REPORT/'independent_c_alias_review.json').read_text())
    require(alias['source_sha256']==r['source_sha256']['scripts/rope_bf16_candidate_reference.c'],'C alias regression stale')
    # These are the baseline areas that must remain byte-identical. Docs and
    # entirely new candidate files are intentionally outside this assertion.
    protected=('rtl','config','configs','integration','chisel','src','scripts','tb','tests/fixtures','reports/execution/OPERATOR_PRIMITIVE_COVERAGE_V3.json')
    changed=subprocess.check_output(['git','diff','2754234','--name-only','--diff-filter=DMRTUXB','--',*protected],cwd=ROOT,text=True).splitlines()
    require(not changed,'baseline production/numeric/fixture source changed: '+repr(changed))
    summary={'status':'PASS_INDEPENDENT_FINAL_EVIDENCE_REVIEW','reviewed_result':str(path.resolve()),
      'reviewed_result_sha256':sha(path),'source_files_verified':len(r['source_sha256']),
      'result_artifacts_verified':len(r['artifacts']),'immutable_fixtures_verified':len(r['fixture_sha256']),
      'actual_DUT_node_conversions_compared_to_independent_nearest_neighbor':independent_node_conversions,
      'standalone_DUT_conversions_compared_to_independent_nearest_neighbor':len(cin),
      'all_25_DUT_columns_match_integer_oracle_and_actual_C_observations':True,
      'C_tininess_waivers_used':0,'real_pairs_per_DUT':163840,'synthetic_pairs_per_DUT':13618,
      'frozen_native_products_and_outputs_recompared':True,'protected_baseline_changed_paths':changed,
      'PPA_measured':False,'script_sha256':sha(Path(__file__))}
    output=Path(sys.argv[2]) if len(sys.argv)>2 else REPORT/'independent_result_review.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
