"""Synthetic metadata authority and real source-byte relation; no ELF/model execution."""
import hashlib,json,os,pathlib,shutil,types
P=pathlib.Path;D=P(__file__).resolve().parent;N='candidates/same_job_execution_20261030/numeric/'
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def pin(p):return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p))
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if type(v)is bytes else(json.dumps(v,indent=2)+'\n').encode());return pin(p)
def module(p):
 m=types.ModuleType('fixture_'+p.stem);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m

def build(root):
 repo=root/'repo';out=root/'payload';out.mkdir(parents=True);control=root/'control';control.mkdir()
 origin=P(os.environ.get('FIRST_FAULT_TEST_REPO',str(D.parents[2])))
 sources=['candidate_admission.py','first_fault_driver_contract.py','p0_first_fault_contract.py','MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json','first_fault_observation_contract.py','correct_first_fault_observation_policy.py']
 for name in sources:put(repo/N/name,(D/name).read_bytes())
 helper=module(repo/N/'first_fault_driver_contract.py')
 for role,rel in helper.ROLES.items():
  # Historical V1 fixture keeps its exact approved helper, not the new V2 role.
  raw=(D/'fixtures/readonly_first_fault_v1.hpp').read_bytes()if role=='host_observer'else(origin/rel).read_bytes()
  if role=='host_observer'and hashlib.sha256(raw).hexdigest()!='16c9a400a1e74dae2135c8ac6b6e40fa98e7b349d2777956279734c0f87cb818':raise ValueError('exact historical V1 observer fixture')
  put(repo/rel,raw)
 cp=put(control/'driver_contract.json',(origin/helper.C/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes())
 gen=module(repo/helper.ROLES['probe_generator']);schema,_=gen.load_schema(repo/helper.ROLES['probe_schema'])
 guard='VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_';lines=['#ifndef '+guard,'#define '+guard,'class alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root final : public VerilatedModule {','public:']
 for r in schema['signals']:
  name,port=gen.expected_member(r);w=r['width_bits'];t='CData'if w<=8 else'SData'if w<=16 else'IData'if w<=32 else'QData'
  lines.append('    VL_OUT8('+name+','+str(w-1)+',0);'if port else'    '+t+'/*'+str(w-1)+':0*/ '+name+';')
 lines+=['};','#endif',''];header=control/'VHostBlockTopV4___024root.h';put(header,'\n'.join(lines).encode())
 ev=gen.generate(repo/helper.ROLES['probe_schema'],repo/helper.ROLES['probe_config'],header,control/'readonly_first_fault_access.hpp',control/'accessor_evidence.json')
 p0pin=pin(repo/N/'MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json');sourcecontract=json.loads(P(p0pin['path']).read_text())
 overlay=put(control/'overlay.json',dict(schema='MODEL_SOURCE_OVERLAY_V1',source_count=159,files=[{}]*159))
 identity=dict(run_id=1,artifact_name='synthetic-not-runtime',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/test.json',launch_manifest_blob_sha='c'*40)
 obs=dict(schema='MODEL_CANDIDATE_OBSERVATION_V1',status='OBSERVED_UNREVIEWED',source_closure=dict(source_commit='a'*40,source_count=159,source_overlay={k:overlay[k]for k in('bytes','sha256')}))
 probe=dict(schema='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1',status='OBSERVED_UNREVIEWED',contract=dict(cp,text=P(cp['path']).read_text()),accessor_generation=ev)
 source=dict(source_commit='a'*40,sv_sha256=helper.ORIGINAL_SV_SHA,generation_input_pins={cp['path']:cp['sha256'],p0pin['path']:p0pin['sha256']},model_candidate_observation=obs,model_source_evidence=dict(schema='MODEL_CANDIDATE_P0_FIRST_FAULT_SOURCE_EVIDENCE_V1',contract=dict(p0pin,text=P(p0pin['path']).read_text())),readonly_probe=probe)
 sp=put(out/'source_manifest.json',source);driver=put(out/'driver.cpp',(repo/helper.ROLES['diagnostic_driver']).read_bytes());gate=module(repo/N/'candidate_admission.py')
 artifact=dict(schema=helper.ARTIFACT_SCHEMA,status='UNREVIEWED_MODEL_BUILD',scope=helper.SCOPE,cpp_build_policy='CPP_O1_STRICT_V1',cpp_build_overrides=gate.POLICY,profiles=list(range(5)),layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',artifact_identity=identity,common={'sv':dict(path='hardware.sv',bytes=224341716,sha256=helper.ORIGINAL_SV_SHA),'source_manifest':dict(sp,path='source_manifest.json'),'driver':dict(driver,path='driver.cpp')},tool_manifest={},model_candidate_observation_sha256=gate.canonical_sha(obs),numerical_pass=False,final_rtl_executed=False,model_numerical_evaluation_authorized=False,external_review_required=True,readonly_probe_contract={k:cp[k]for k in('bytes','sha256')})
 ap=put(out/'frozen_artifact.json',artifact)
 st=dict(schema='MODEL_CANDIDATE_STRUCTURAL_REVIEW_V1',status='VERIFIED_SOURCE_AND_ACTUAL_STRUCTURE_NOT_NUMERICAL',artifact_manifest_sha256=ap['sha256'],observation_sha256=artifact['model_candidate_observation_sha256'],source_overlay_sha256=overlay['sha256'],source_contract_sha256=p0pin['sha256'],matrix_macs=4096,shared_vector_banks=1,bank_alu_instances=32,profiles=list(range(5)),typed_port_count=122,numerical_pass=False,final_rtl_executed=False)
 retained=put(control/'retained.json',{'synthetic_data_domain':True})
 old=put(control/'old_binding.json',dict(execution_mode='STAGE_COVERAGE_DIAGNOSTIC',artifact_manifest=dict(path='/unread-historical-artifact',bytes=1,sha256='d'*64),model_candidate_review=dict(path='/unread-historical-review',bytes=1,sha256='e'*64)))
 summary=put(control/'old_summary.json',dict(schema='CLOUD_EXECUTION_SAFE_SUMMARY_V1',status='VERIFIED_REAGGREGATED',execution_mode='STAGE_COVERAGE_DIAGNOSTIC',binding_sha256=old['sha256'],artifact_manifest_sha256='d'*64,model_candidate_review_sha256='e'*64,transport_exit_code=2,numerical_pass=False,final_rtl_executed=False,profiles=[dict(profile=i,state='STARTED_NATIVE_FAILED')for i in range(5)]))
 watchdog=dict(wall_seconds=100,max_active_cycles=1000)
 wr=put(control/'watchdog_review.json',dict(schema='P0_FIRST_FAULT_WATCHDOG_REVIEW_V1',status='REVIEWED_WATCHDOG_NOT_FULL_ESTIMATE',artifact_manifest_sha256=ap['sha256'],readonly_driver_contract_sha256=cp['sha256'],historical_stage_binding_sha256=old['sha256'],historical_stage_summary_sha256=summary['sha256'],watchdog=watchdog))
 mode=module(repo/N/'p0_first_fault_contract.py');fixture=P(os.environ.get('FIRST_FAULT_TEST_FIXTURES',str(D/'fixtures/p0_reuse')))
 stimulus={}
 for key in mode.STIMULUS:
  raw=(fixture/key).read_bytes()if key=='program_manifest'else bytes.fromhex((fixture/('program_'+key+'.hex')).read_text())
  stimulus[key]=put(control/key,raw)
 stimulus.update(runtime_semantic_sha256=mode.RUNTIME,views_semantic_sha256=mode.VIEWS,retained_materials_sha256=retained['sha256'])
 doc=dict(schema='P0_FIRST_FAULT_DIAGNOSTIC_V1',scope=helper.SCOPE,profile=0,tokens=128,matrix_macs=4096,vector_lanes=32,artifact_manifest_sha256=ap['sha256'],readonly_driver_contract=cp,readonly_probe_evidence_sha256=helper.canonical_sha(probe),stimulus=stimulus,watchdog=watchdog,basis=dict(historical_stage_binding=old,historical_stage_summary=summary,independent_watchdog_review=wr),numerical_pass=False,final_rtl_executed=False)
 dp=put(control/'diagnostic.json',doc)
 review=dict(schema=helper.REVIEW_SCHEMA,status='REVIEWED_FOR_P0_FIRST_FAULT_DIAGNOSTIC',scope=helper.SCOPE,builder_identity=identity,artifact_manifest=ap,source_manifest_sha256=sp['sha256'],observation_sha256=artifact['model_candidate_observation_sha256'],source_overlay=overlay,source_contract=p0pin,structural_review=put(control/'structural.json',st),data_reference_contract=None,numerical_pass=False,final_rtl_executed=False,first_fault_diagnostic=dp)
 rp=put(control/'review.json',review)
 rows=[dict(pin(p),path=str(p.relative_to(repo)))for p in sorted(repo.rglob('*'))if p.is_file()];catalog=put(control/'catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=rows));pins={str(repo/r['path']):r['sha256']for r in rows}
 binding=dict(execution_context='CLOUD_EXECUTOR_V1',execution_mode=mode.MODE,full_block_budget=None,model_candidate_review=rp,artifact_manifest=ap,repo=str(repo),source_pins=catalog,pins=pins,retained_materials=retained,identity=dict(source_commit='f'*40,execution_id='OFFLINE_UNADMITTED_SYNTHETIC'))
 budget=put(control/'budget.json',dict(model_candidate_review=rp,execution_mode=mode.MODE));binding['cloud_budget']=budget
 approval=put(control/'approval.json',dict(schema='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1',approved=True,authority='USER_AUTHORIZED_OPERATOR_REVIEW',purpose=mode.MODE,source_commit=binding['identity']['source_commit'],execution_id=binding['identity']['execution_id'],artifact_manifest_sha256=ap['sha256'],model_candidate_review_sha256=rp['sha256'],budget_sha256=budget['sha256']));binding['execution_approval']=approval
 return dict(repo=repo,out=out,control=control,gate=gate,helper=helper,mode=mode,binding=binding,review=review,doc=doc,artifact=artifact,source=source,contract_pin=cp)
