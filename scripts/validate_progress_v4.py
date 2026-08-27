#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

from heteronpu.hierarchical_attention import BlockedAttentionGeometry, causal_merge_count
from heteronpu.model_support import ModelProfile

errors=[]
control=json.loads(Path('config/control_plane.json').read_text())
if control.get('schema_version')!=4:errors.append('control schema')
if control.get('stage_namespace')!=[f'L{i}' for i in range(12)]:errors.append('stage namespace')
for path in [
    'reports/ARCHITECTURE_AND_EXECUTION_PLAN.md',
    'local_agent/stages.yaml',
    'reports/execution/MASTER_LEDGER.json',
    'reports/execution/NEXT_ACTION.json',
    'reports/execution/LOCAL_AGENT_WAITLIST.json',
    'reports/execution/qwen38_text_e0_result.json',
    'reports/execution/gdn_chunk_e0_result.json',
    'config/qwen38_tiny_e0_contract.json',
]:
    if not Path(path).is_file():errors.append('missing '+path)
for path in control.get('obsolete_paths',[]):
    if Path(path).exists():errors.append('obsolete path '+path)
for path in Path('config/model_profiles').glob('*.json'):
    profile=ModelProfile.load(path)
    if len(profile.raw.get('revision',''))!=40:errors.append('revision '+str(path))
if causal_merge_count(1024,12)!=43008:errors.append('merge count')
if BlockedAttentionGeometry(1024,12,128).live_set_bytes>=65536:errors.append('live set')
q38=ModelProfile.load('config/model_profiles/qwen3_8_flash_next.json')
if q38.support().get('qwen38_text_tiny_e2e')!='executable_e0_reference':errors.append('q38 support')
schedule=q38.runtime_schedule()
if schedule is None or len(schedule.micro_ops)!=548:errors.append('q38 schedule')
q38_result=json.loads(Path('reports/execution/qwen38_text_e0_result.json').read_text())
if q38_result.get('status')!='PASS' or q38_result.get('prefill_incremental_max_abs_diff')!=0.0:errors.append('q38 E0')
gdn_result=json.loads(Path('reports/execution/gdn_chunk_e0_result.json').read_text())
if gdn_result.get('status')!='PASS' or gdn_result.get('cases')!=100:errors.append('gdn chunk')
contract=json.loads(Path('config/qwen38_tiny_e0_contract.json').read_text())
if contract['expected']['final_hidden_sha256']!=q38_result['final_hidden_sha256']:errors.append('q38 hidden hash')
if contract['expected']['final_hyper_sha256']!=q38_result['final_hyper_sha256']:errors.append('q38 hyper hash')
result={
    'schema_version':4,
    'status':'PASS' if not errors else 'FAIL',
    'errors':errors,
    'python_tests_expected':81,
    'block128_vectors':132,
    'qwen38_text_e0':'PASS' if q38_result.get('status')=='PASS' else 'FAIL',
    'gdn_chunk_cases':gdn_result.get('cases'),
    'local_state':'WAIT_LOCAL_AGENT_E1_PUSH',
}
Path('reports/execution/SANDBOX_PROGRESS_V4.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(bool(errors))
