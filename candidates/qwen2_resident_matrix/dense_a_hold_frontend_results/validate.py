"""Immutable original-attempt frontend archive; no compiler or RTL invocation."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
COMMIT='3ada1a4de83cfaf9062fbfa8c13604c68e8fff32'
RUN=38973350757
ZIP_SHA='513bb551c9b1b6943188c3cf7a9672d8e9550fe8381466ecffaf2eb3f3f011cd'
FILES={
 'summary.json':'8b746f888d271398658bb6e5b9701e188f7ff58d852c93f6b7e26085fecf349d',
 'source-sha256.json':'74b02cad23e0a3a57ec52e0449f6cbcb84cfca1e9997934352bafe4d465ab122',
 'dependency-sha256.json':'1c195e4c54949c75a5f453dfa0830cbd261aba6a7af2bd5b20b1273cd9789e78'}


def need(ok,message):
    if not ok:raise ValueError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        need(key not in result,'duplicate JSON key');result[key]=value
    return result


def read(path):
    need(path.stat().st_size<=65536,'oversized archive member')
    return json.loads(path.read_text(),object_pairs_hook=unique)


def validate_payloads(summary,source,dependency):
    need(summary['status']=='PASS_FRONTEND_ONLY','frontend status')
    for field in ('scala_compiled','chirrtl_generated','precompile_and_postflight_hashes_equal'):
        need(summary[field] is True,'missing frontend qualification: '+field)
    for field in ('rtl_generated','hardware_protocol_executed','arithmetic_executed','full_business_block_acceptance'):
        need(summary[field] is False,'unsupported acceptance claim: '+field)
    need(summary['budget']=={'download_workers':4,'java_active_processors':1,'java_heap_mib':1024,
        'stages_seconds':{'dependencies':120,'compile':180,'elaborate':90},'total_seconds':420},'qualified resource budget')
    need(0<summary['wall_seconds']<=420,'frontend wall budget')
    need([x['name'] for x in summary['stages']]==['dependencies','compile','elaborate'],'unexpected frontend stage')
    for stage in summary['stages']:
        need(stage['exit_code']==0 and stage['status']=='PASS' and 0<stage['seconds']<=stage['budget_seconds'],'frontend stage result')
    configs=summary['configurations']
    need(set(configs)=={f'owner_hold{h}_full{f}.fir' for h in (0,1) for f in (0,1)},'four exact configurations')
    for name,config in configs.items():
        hold=int(name[len('owner_hold')]);r=config['resources'];q=r['operand_fifo']
        need(re.fullmatch('[0-9a-f]{64}',config['sha256']) and config['bytes']>0,'CHIRRTL identity')
        fixed={'a_banks':16,'a_depth':1376,'b_banks':16,'b_depth':160,'width':256,
               'read_ports_per_bank':1,'write_ports_per_bank':1,'sram_memories':32,'total_memory_declarations':33}
        need(all(r[k]==v for k,v in fixed.items()),'bank geometry or ports changed')
        need(q['depth']==(3 if hold else 4) and q['element_bits']==4359 and q['kind']=='cmem' and q['memory']=='ram','operand Queue changed')
        need(r['hold_payload_bits']==2048*hold and r['added_hold_control_bits']==78*hold,'hold inventory changed')
        need(r['declared_fifo_and_hold_payload_bits']==(15125 if hold else 17436),'FIFO/hold declared payload changed')
        need(r['useful_operand_payload_bytes']==(1216 if hold else 1280),'useful payload accounting changed')
        need(r['matrix_or_hardfloat_instantiated'] is False and r['physical_area_or_timing_measured'] is False,'unqualified arithmetic or physical result')
        need(r['module_names']==[f'Queue{3 if hold else 4}_MatrixStreamStep','TransposedDenseDownOwner','TransposedDownDenseBanks'],'unexpected module')
    need(set(summary['register_delta'])=={'0','1'},'missing register comparison')
    for delta in summary['register_delta'].values():
        need(delta=={'added_bank_request_bits':1,'added_control_bits':78,'added_payload_bits':2048,
          'added_owner_registers':{'heldA':'UInt<16>[128]','heldAGeneration':'UInt<32>','heldAK':'UInt<12>','heldAValid':'UInt<1>','pendingAGeneration':'UInt<32>'},
          'existing_other_registers_unchanged':True,'fifo_control_shape_unchanged':True},'register delta changed')
    need(source['source_pins_sha256']=='98ffa9ada1dd5a4d7b2d27c834362b4dff1ae1aaaf51ce0007e0875a4a545972','original source pins')
    need(source['workflow_sha256']=='d7404811de8119cbf721deb627f0a56959a409ce3709396c0ae5e050eb3f7c3b','original launch workflow')
    need(len(source['inputs'])==63 and len(source['generated'])==14,'source closure count')
    need(source['generated']['AHoldElaborate.scala']=='e72963cc1782dd30688de8c49d2e266565849fde758cd91a2f81c0b1319a99a9','original emitter')
    need(dependency['lock_sha256']=='e15bbf22b74552ed6a4fc61a7137564c2543488d928cbdff77f27af2dfd3204b','original dependency lock')
    need(dependency['origin']=='https://repo.maven.apache.org/maven2/' and len(dependency['jars'])==87,'locked Maven dependency closure')
    for mapping in (source['inputs'],source['generated'],dependency['jars']):
        need(all(not k.startswith('/') and '..' not in Path(k).parts and re.fullmatch('[0-9a-f]{64}',v) for k,v in mapping.items()),'invalid identity entry')


def validate(directory=HERE):
    directory=Path(directory)
    need({p.name for p in directory.glob('*.json')}==set(FILES)|{'manifest.json'},'archive JSON allowlist')
    m=read(directory/'manifest.json')
    need(m['schema']==1 and m['repository_input_hashes_compared']==63 and m['generated_input_hashes_compared']==14 and
         m['locked_jar_identities_compared']==87,'archive verification coverage')
    need(m['repository']=='liyang53719/hetero_cnn_llm_aha' and m['commit']==COMMIT,'original repository/commit')
    need(m['run_id']==RUN and m['run_attempt']==1 and m['job_id']==117216765296 and m['artifact_id']==12076709705,'original run identity')
    need(m['run_url']==f'https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/{RUN}' and m['run_conclusion']=='success','original successful run')
    need(m['artifact_zip_sha256']==ZIP_SHA and m['artifact_zip_bytes']==10606,'original artifact identity')
    need(m['files_sha256']==FILES and m['original_receipts_preserved'] is True,'exact artifact member identity')
    for name,digest in FILES.items():
        need(hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,'archived member drift: '+name)
    for field in ('rtl_generated','hardware_protocol_executed','arithmetic_executed','full_business_block_acceptance','timing_or_utilization_measured'):
        need(m[field] is False,'unsupported manifest claim: '+field)
    validate_payloads(read(directory/'summary.json'),read(directory/'source-sha256.json'),read(directory/'dependency-sha256.json'))
    return {'status':'PASS_IMMUTABLE_FRONTEND_ARCHIVE','run_id':RUN,'commit':COMMIT,
            'scala_compiled':True,'chirrtl_generated':True,'rtl_generated':False,
            'hardware_protocol_executed':False,'arithmetic_executed':False,'full_business_block_acceptance':False}


if __name__=='__main__':print(json.dumps(validate(),sort_keys=True))
