#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from heteronpu.planning_v6 import audit_control,arch_collateral,build_qwen38_program,compile_mock,load_arch,render_arch_sv,SequenceMemory
ROOT=Path(__file__).resolve().parents[1]
arch=load_arch('configs/arch_v2_qwen38_candidate.yaml',ROOT);coll=arch_collateral(arch)
out=ROOT/'generated/archspec';out.mkdir(parents=True,exist_ok=True)
(out/'heteronpu_v2_qwen38_candidate.collateral.json').write_text(json.dumps(coll,indent=2,sort_keys=True)+'\n')
(out/'heteronpu_v2_qwen38_candidate_pkg.sv').write_text(render_arch_sv(coll))
profile=json.loads((ROOT/'config/model_profiles/qwen3_8_flash_next.json').read_text())
prefill=build_qwen38_program(profile,'prefill',1024,weight_bits=4);decode=build_qwen38_program(profile,'decode',1,262144,4)
pmock=compile_mock(prefill);dmock=compile_mock(decode)
program={'schema_version':1,'status':'PASS','evidence_class':'full_shape_and_mock_backend_E0','prefill':{'program_sha256':prefill['program_sha256'],'operations':prefill['operation_count'],'macs':prefill['total_macs'],'weight_bytes':prefill['total_weight_bytes'],'mock_sha256':pmock['mock_sha256'],'analytical_cycles':pmock['analytical_total_cycles']},'decode':{'program_sha256':decode['program_sha256'],'operations':decode['operation_count'],'macs':decode['total_macs'],'weight_bytes':decode['total_weight_bytes'],'mock_sha256':dmock['mock_sha256'],'analytical_cycles':dmock['analytical_total_cycles']},'non_claims':['no official-weight inference','no RTL E1','no integrated E3','no E4']}
(ROOT/'reports/execution/qwen38_full_shape_program_v6_result.json').write_text(json.dumps(program,indent=2,sort_keys=True)+'\n')
sm=SequenceMemory();sm.create(17,5,3,9)
for p in range(32):sm.map_page(17,5,3,9,p,1000+p)
cold=[sm.translate(17,5,3,9,p*16) for p in range(32)];warm=[sm.translate(17,5,3,9,p*16) for p in range(32)]
stale=False
try:sm.translate(17,5,3,10,0)
except ValueError:stale=True
seq={'schema_version':1,'status':'PASS' if stale else 'FAIL','evidence_class':'cycle_structured_E0_not_AXI_iDMA_E3','cold_paths':{k:sum(x['path']==k for x in cold) for k in {'page_walk','leaf_cache_hit','tlb_hit'}},'warm_tlb_hits':sum(x['path']=='tlb_hit' for x in warm),'stale_generation_rejected':stale,'cow_copy_cycles_one_4KiB_page':sm.cow_cycles()}
(ROOT/'reports/execution/sequence_memory_cycle_v6_result.json').write_text(json.dumps(seq,indent=2,sort_keys=True)+'\n')
audit=audit_control(ROOT);(ROOT/'reports/execution/control_plane_v6_audit.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
ares={'schema_version':1,'status':'PASS','evidence_class':'Archspec_collateral_E0_not_RTL','arch_id':arch['arch_id'],'archspec_sha256':coll['archspec_sha256'],'total_sram_kib':coll['total_sram_bytes']//1024,'owner_count':len(coll['sram_map'])}
(ROOT/'reports/execution/archspec_v6_collateral_result.json').write_text(json.dumps(ares,indent=2,sort_keys=True)+'\n')
result={'schema_version':1,'status':'PASS' if audit['status']=='PASS' and stale else 'FAIL','archspec':ares,'program':program,'sequence_memory':seq,'control_audit':audit}
print(json.dumps(result,sort_keys=True))
if result['status']!='PASS':raise SystemExit(1)
