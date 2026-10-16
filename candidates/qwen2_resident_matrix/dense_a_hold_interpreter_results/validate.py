"""Validate the original failed attempt without launching Java, EDA or network."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
RUN=38976754470
COMMIT='00d1d6540a2a8359adc7b64e86e5d30ad6cd678e'
FILES={
 'summary.json':'03f2ab34730bf2857c2aa182b6287d55d9b5d91b6012601a482b49552b5e2c48',
 'source-sha256.json':'9edc013f8bd46290f92adbd3b98b5751f478bd26741780454893da9d12336862',
 'dependency-sha256.json':'c13bf5a849bf397dd0385c1bfb1c54832c15d3ef4a88c49f68cf9fb371cd380f',
 'diagnostic.txt':'778420d6fd0c76a8198445990f4bc0cbafea810a575684d4b4adc66d08a30168'}


def need(ok,message):
    if not ok:raise ValueError(message)


def unique(pairs):
    result={}
    for k,v in pairs:need(k not in result,'duplicate JSON key');result[k]=v
    return result


def read(path):
    need(path.stat().st_size<=65536,'oversized safe receipt')
    return json.loads(path.read_text(),object_pairs_hook=unique)


def validate_payloads(summary,source,dependency):
    need(summary['status']=='FAILED','original failure must remain failed')
    need(summary['scala_compiled'] is True and summary['chirrtl_generated'] is True,'completed frontend stages')
    for field in ('interpreted_hardware_protocol','emitted_rtl_simulation','rtl_generated','matrix_arithmetic','full_business_block_acceptance','hardware_timing_or_utilization'):
        need(summary[field] is False,'unsupported runtime acceptance: '+field)
    need(summary.get('precompile_and_postflight_hashes_equal',False) is False,'postflight was not reached')
    need(summary['java_version']=='21.0.12.1','actual Java version')
    need(summary['interpret_progress']=={'case_begin_seen':True,'case_pass_marker_seen':False,'last_reported_cycle':None,'sim_ready_seen':False},'observed progress changed')
    need('case' not in summary and 'loaded_class_origins' not in summary,'unretained runtime evidence invented')
    need(summary['budget']=={'cleanup_reserve_seconds':30,'download_workers':4,'java_active_processors':1,'java_heap_mib':2048,'java_stack_mib':4,'max_test_cycles':20000,
        'stages_seconds':{'compile':180,'dependencies':120,'interpret':240,'structure':30},'total_seconds':600},'approved original budget')
    need(0<summary['wall_seconds']<600,'original total bound')
    stages=summary['stages'];need([x['name'] for x in stages]==['dependencies','compile','structure','interpret'],'exact original stages')
    for x in stages[:3]:need(x['status']=='PASS' and x['exit_code']==0 and 0<x['seconds']<=x['budget_seconds'],'frontend stage changed')
    x=stages[-1];need(x['status']=='TIMEOUT' and x['budget_seconds']==240 and 240<=x['seconds']<241 and 'exit_code' not in x,'original interpreter timeout')
    structure=summary['structure'];r=structure['resources']
    need(structure['probe_changes_registers'] is False and structure['scope']=='original CHIRRTL before memory lowering','original probe inventory')
    for k,v in {'a_banks':16,'a_depth':1376,'b_banks':16,'b_depth':160,'width':256,'read_ports_per_bank':1,'write_ports_per_bank':1,'sram_memories':32,'total_memory_declarations':33,
                'hold_payload_bits':2048,'added_hold_control_bits':78,'declared_fifo_and_hold_payload_bits':15125,'useful_operand_payload_bytes':1216}.items():need(r[k]==v,'resource inventory: '+k)
    need(r['operand_fifo']['depth']==3 and r['operand_fifo']['element_bits']==4359,'actual Queue3')
    need(r['matrix_or_hardfloat_instantiated'] is False and r['physical_area_or_timing_measured'] is False,'unsupported physical/numeric acceptance')
    need(source['source_pins_sha256']=='2727a52d6a64860bc92b4419b97fba4fdb9d244a3ce1d6de27302250106daff4','original source pins')
    need(source['workflow_sha256']=='ba00dccf2b0a64db26bc15fc87e6c7e09c62b647b751154300050b55d661038b','original workflow')
    lock='75559554a865bcc72d74e2ec14795b031baa319ecf575f2e5d9aa4f87960a907'
    need(source['dependency_lock_sha256']==dependency['lock_sha256']==lock,'original dependency lock')
    need(dependency['origin']=='https://repo.maven.apache.org/maven2/','official dependency origin')
    need(len(source['inputs'])==75 and len(source['generated'])==15 and len(source['compiled_classes'])==112 and len(dependency['jars'])==106,'original identity counts')
    for mapping in (source['inputs'],source['generated'],source['compiled_classes'],dependency['jars']):
        need(all(not Path(k).is_absolute() and '..' not in Path(k).parts and re.fullmatch('[0-9a-f]{64}',v) for k,v in mapping.items()),'invalid recorded identity')
    need(all(p.endswith('.class') for p in source['compiled_classes']),'recorded compiler output type')


def validate(directory=HERE):
    directory=Path(directory)
    allowed={'manifest.json','summary.json','source-sha256.json','dependency-sha256.json','diagnostic.txt','validate.py','test_evidence.py'}
    need(all(not p.is_symlink() and (p.name=='__pycache__' and p.is_dir() or p.name in allowed and p.is_file()) for p in directory.iterdir()),'safe archive member allowlist')
    need({p.name for p in directory.glob('*.json')}=={'manifest.json','summary.json','source-sha256.json','dependency-sha256.json'},'archive JSON allowlist')
    m=read(directory/'manifest.json')
    need(m['schema']==1 and m['repository']=='liyang53719/hetero_cnn_llm_aha' and m['commit']==COMMIT,'original repository/commit')
    need(m['run_id']==RUN and m['run_attempt']==1 and m['job_id']==117227926193 and m['artifact_id']==12079995425,'original run identity')
    need(m['run_url']==f'https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/{RUN}' and m['run_conclusion']=='failure','original failed run')
    need(m['artifact_zip_bytes']==17524 and m['artifact_zip_sha256']=='664e58185552c968a84b3e8dc69b2f5a2215baf48922c86a6bbbb5cd7ef9a64a','original ZIP identity')
    need(m['files_sha256']==FILES and m['original_receipts_preserved'] is True,'original safe member map')
    for name,digest in FILES.items():need(hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,'original receipt changed: '+name)
    need(m['repository_input_hashes_verified']==75 and m['generated_sources_recomposed']==15 and m['locked_dependency_identities_matched']==106 and m['recorded_compiled_class_hashes']==112,'verification coverage')
    need(m['actual_clock_cycles_observed'] is None and m['specific_startup_subphase']=='unknown' and m['startup_timeout_is_inference'] is True,'unknown runtime facts must remain unknown')
    need(m['resource_inventory_equals_prior_frontend'] is True,'prior frontend inventory comparison')
    for field in ('compiled_class_bytes_downloaded','test_callback_observed','runtime_class_origins_retained','postflight_hash_equality_claimed','interpreted_hardware_protocol','emitted_rtl_simulation','matrix_arithmetic','full_business_block_acceptance','hardware_timing_or_utilization'):
        need(m[field] is False,'unsupported manifest evidence: '+field)
    need((directory/'diagnostic.txt').stat().st_size<=4096,'diagnostic size')
    validate_payloads(read(directory/'summary.json'),read(directory/'source-sha256.json'),read(directory/'dependency-sha256.json'))
    return {'status':'PASS_IMMUTABLE_FAILURE_ARCHIVE','original_run_conclusion':'failure','run_id':RUN,
        'scala_compiled':True,'chirrtl_generated':True,'interpreted_hardware_protocol':False,'actual_clock_cycles_observed':None}


if __name__=='__main__':print(json.dumps(validate(),sort_keys=True))
