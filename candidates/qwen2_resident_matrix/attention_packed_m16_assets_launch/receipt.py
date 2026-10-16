"""Post-exit, hash-only validation of the private M16 reference-preparation receipt."""
import math
from pathlib import Path
import re

from ..attention_packed_m16_assets import reuse as R

PROFILE='qwen2-public-pv16-packed-m16-reference-preparation-v1'
STATUS='REFERENCE_PREPARATION_ONLY_NOT_NUMERICALLY_ADMITTED'


def exact(value,keys):
    R.need(type(value) is dict and set(value)==set(keys),'exact private receipt schema')


def seconds(value,maximum):
    R.need(type(value) in (int,float) and math.isfinite(value) and 0<=value<=maximum,'private timing bound')


def bound_bytes(root,item,maximum):
    path=R.checked(root,item,content=False)
    R.need(item['bytes']<=maximum,'private metadata bound')
    raw=path.read_bytes()
    R.need(len(raw)==item['bytes'] and R.sha(raw)==item['sha256'],'private parsed bytes identity')
    return raw


def read_record(root,item):
    return R.strict_json(bound_bytes(root,item,R.MAX_JSON))


def validate_ack(stdout,value):
    expected=[(str(i),name,str(16*width)) for i,(name,width) in enumerate(R.STAGES)]
    R.need(re.findall(r'^SOFTWARE_RECIPE_STAGE phase=(\d+) name=(\w+) values=(\d+)$',stdout,re.M)==expected
        and stdout.count('SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15')==1
        and stdout.count('SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10')==1
        and stdout.count('CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1')==1,
        'original software completion ACK')
    R.need(R.same(value,dict(phase_receipts_exactly_once_in_order=True,process_completion_ack=True,
        scope='software file/process contract only',hardware_ack_verified=False)),'original ACK metadata')


def validate_scope(value,sources):
    claims=R.contract()['claims']
    exact(value,('schema','profile','status','rows','past_tokens','contract_sha256',
        'preparation_source_sha256','origin','readonly','origin_table','origin_native_m16','producers',
        'current_backend_verified','packed_source_profile_linked','ready_for_actual','elapsed_seconds',*claims))
    R.need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE
        and value['status']==STATUS and type(value['rows']) is int and value['rows']==16
        and type(value['past_tokens']) is int and value['past_tokens']==0
        and value['contract_sha256']==R.PINS_SHA256 and R.same(value['preparation_source_sha256'],sources)
        and value['current_backend_verified'] is True and value['packed_source_profile_linked'] is False
        and value['ready_for_actual'] is False and all(value[k] is False for k in claims),'preparation-only receipt scope')
    seconds(value['elapsed_seconds'],120)


def validate(origin,output,*,child_returncode,sources,origin_before):
    R.need(type(child_returncode) is int and child_returncode==0,'successful child exit required')
    origin=R.safe_path(origin,directory=True);output=R.safe_path(output,directory=True)
    R.need(not output.is_relative_to(origin) and not origin.is_relative_to(output),'output/origin overlap')
    path=R.below(output,'M16_REFERENCES.json')
    R.need(path.stat().st_size<=R.MAX_JSON,'private receipt bound')
    raw=path.read_bytes();value=R.strict_json(raw)
    validate_scope(value,sources)
    R.need(R.same(R.snapshot(),sources),'asset source snapshot changed')
    origin_after=R.verify_reuse(origin,metadata_only=False)
    R.need(R.same(origin_after,origin_before) and R.same(value['origin'],origin_before),'origin identity changed')
    pins=R.contract();assets=R.read_metadata(origin,'private/assets/ASSETS.json',pins['metadata']['private/assets/ASSETS.json'])
    R.need(R.same(value['origin_table'],assets['readonly']['table']) and
           R.same(value['origin_native_m16'],assets['native_m16']),'explicit retained origin references')
    R.need({p.name for p in output.iterdir()}=={'M16_REFERENCES.json','readonly','sequential','reduced','tmp'},'fresh root inventory')
    exact(value['readonly'],('arena','input_x'))
    R.need({p.name for p in (output/'readonly').iterdir()}=={'readonly_arena.f32le','input_x.f32le'},'fresh readonly inventory')
    checked=[]
    for key,name in (('arena','readonly_arena.f32le'),('input_x','input_x.f32le')):
        item=value['readonly'][key]
        R.need(item['path']=='readonly/'+name and R.same({k:item[k] for k in ('bytes','sha256')},pins['m16_readonly'][key]),'fresh M16 readonly pin')
        checked.append(R.checked(output,item,content=True))
    readonly_expected=dict(token_ids=list(range(16)),position_ids=list(range(16)),past_tokens=0,
        readonly_sha256=pins['m16_readonly']['arena']['sha256'],input_x_sha256=pins['m16_readonly']['input_x']['sha256'],
        intermediate_preloads=0,rope_table_sha256=pins['m16_readonly']['table']['sha256'],
        rope_recipe='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only')
    exact(value['producers'],('sequential','reduced'))
    for role in ('sequential','reduced'):
        result=value['producers'][role]
        keys=('run','schema','status','producer','origin_compile_receipt','origin_executable','origin_receipts_rewritten',
            'argv','software_ack','outputs','stdout','stderr','empty_cache','readonly','actual_chain_executed',
            'returncode','elapsed_seconds','requested_timeout_seconds')
        if role=='sequential':keys+=('export_receipt','tensors')
        exact(result,keys)
        R.need(result['run']['path']==role+'/run.json' and R.same(read_record(output,result['run']),
            {k:v for k,v in result.items() if k!='run'}),'fresh run JSON/runtime identity')
        R.need(type(result['schema']) is int and result['schema']==1 and result['status']=='FRESH_M16_REFERENCE_ONLY'
            and result['producer']==assets[role]['producer'] and result['origin_receipts_rewritten'] is False
            and result['actual_chain_executed'] is False and type(result['returncode']) is int and result['returncode']==0
            and R.same(result['origin_compile_receipt'],assets[role]['compile'])
            and R.same(result['origin_executable'],assets[role]['executable'])
            and R.same(result['readonly'],readonly_expected),'original producer identity')
        seconds(result['elapsed_seconds'],120);seconds(result['requested_timeout_seconds'],30)
        R.need(result['requested_timeout_seconds']>0,'positive producer timeout')
        directory=output/role
        entries={'raw_stages','empty_cache.bin','stdout.log','stderr.log','run.json'}
        if role=='sequential':entries|={'tensors','export.json'}
        R.need({p.name for p in directory.iterdir()}==entries,'fresh producer directory inventory')
        for key,name in (('stdout','stdout.log'),('stderr','stderr.log'),('empty_cache','empty_cache.bin'),('run','run.json')):
            item=result[key];R.need(item['path']==role+'/'+name,'fresh producer metadata path')
            if key in ('stdout','stderr'):R.need(item['bytes']<=16384,'producer log bound')
            if key=='empty_cache':R.need(item['bytes']==0 and item['sha256']==R.sha(b''),'empty cache identity')
            checked.append(R.checked(output,item,content=True))
        empty=directory/'empty_cache.bin'
        R.need(result['argv']==[str(origin/'private/assets'/assets[role]['executable']['path']),
            str(output/'readonly/readonly_arena.f32le'),'16',str(directory/'raw_stages'),'0',str(empty),str(empty)],
            'exact cold M16 producer invocation')
        validate_ack(bound_bytes(output,result['stdout'],16384).decode(),result['software_ack'])
        exact(result['outputs'],R.output_inventory())
        R.need({p.name for p in (directory/'raw_stages').iterdir()}==set(R.output_inventory()),'exact raw output directory')
        for name,size in R.output_inventory().items():
            item=result['outputs'][name]
            R.need(item['path']==role+'/raw_stages/'+name and type(item['bytes']) is int and item['bytes']==size,'M16 raw output path/size')
            checked.append(R.checked(output,item,content=True))
        if role=='sequential':
            item=result['export_receipt'];R.need(item['path']==role+'/export.json','sequential export receipt path')
            exported=read_record(output,item);checked.append(R.checked(output,item,content=True))
            exact(result['tensors'],R.shapes())
            R.need(type(exported) is list and [x.get('name') for x in exported]==sorted(R.shapes()),'sequential export order')
            R.need({p.name for p in (directory/'tensors').iterdir()}=={'candidate_'+name+'.f32le' for name in R.shapes()},'sequential tensor directory')
            for entry in exported:
                exact(entry,('name','path','shape','export_shape','sha256'))
                name=entry['name'];record=result['tensors'][name]
                R.need(entry['path']=='candidate_'+name+'.f32le' and R.same(entry['shape'],R.shapes()[name])
                    and R.same(entry['export_shape'],R.export_shapes()[name]) and entry['sha256']==record['sha256']
                    and record['path']==role+'/tensors/'+entry['path'] and type(record['bytes']) is int
                    and record['bytes']==4*math.prod(R.shapes()[name]),'sequential logical/export identity')
                checked.append(R.checked(output,record,content=True))
    origin_paths=[R.checked(origin/'private/assets',item,content=False) for item in R.reuse_records(assets)]
    R.no_aliases([path,*checked,*origin_paths])
    R.need(path.read_bytes()==raw and R.same(R.snapshot(),sources),'postflight receipt/source drift')
    return dict(receipt_sha256=R.sha(raw),fresh_artifacts=len(checked)+1,origin_artifacts=len(origin_paths),
        numerical_acceptance=False,ready_for_actual=False,full_29_node_acceptance=False)
