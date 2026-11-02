"""Pure fixed-contract accessor/dependency/argv join; never runs codegen or ELF."""
import hashlib
import pathlib
import posixpath
import re
import first_fault_probe as probe

P=pathlib.Path

def need(v,s):
    if not v: raise ValueError(s)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def checked_pin(row, text=False, cap=128<<10):
    need(type(row)is dict and set(row)==({'path','bytes','sha256','text'} if text else {'path','bytes','sha256'}),'exact readonly pin fields')
    p=row['path'];need(type(p)is str and p.startswith('/') and posixpath.normpath(p)==p and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',p),'canonical original readonly path')
    need(type(row['bytes'])is int and 0<row['bytes']<=cap and type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),'bounded readonly pin')
    if text:
        need(type(row['text'])is str,'readonly text');raw=row['text'].encode();need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'readonly retained text bytes')
    return {k:row[k] for k in ('path','bytes','sha256')}

def verify_readonly_probe(manifest,source,receipt,dep):
    from first_fault_policy import artifact_policy,FIRST_FAULT_SCOPE,CONTRACT_SHA
    contract=artifact_policy(manifest,source)
    if contract is None:
        need('readonly_probe'not in source and 'readonly_probe_contract_sha256'not in receipt,'original branch cannot carry readonly evidence')
        return None
    need(receipt.get('readonly_probe_contract_sha256')==CONTRACT_SHA and receipt.get('scope')==FIRST_FAULT_SCOPE,'readonly receipt scope/contract')
    row=source['readonly_probe'];need(type(row)is dict and set(row)=={'schema','status','contract','accessor_generation'} and row['schema']=='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1' and row['status']=='OBSERVED_UNREVIEWED','readonly source evidence shape')
    cp=checked_pin(row['contract'],True,256<<10)
    need(cp['sha256']==CONTRACT_SHA and manifest['readonly_probe_contract']=={k:cp[k]for k in ('bytes','sha256')},'readonly manifest/source contract join')
    gen=row['accessor_generation']
    expected={'schema','scope','schema_input','config','root_header','accessor','mappings','field_count','reads_hier_child_internals','extra_eval_or_clock'}
    need(type(gen)is dict and set(gen)==expected and gen['schema']=='ACTUAL_NONHIER_READONLY_ACCESSOR_EVIDENCE_V1' and gen['scope']=='READ_ONLY_GENERATED_HEADER_DECLARATIONS_NOT_NUMERICAL_ACCEPTANCE','actual accessor evidence schema')
    need(gen['field_count']==114 and type(gen['field_count'])is int and gen['reads_hier_child_internals']is False and gen['extra_eval_or_clock']is False,'actual readonly accessor scope')
    doc,schema_raw=probe.load_schema(P(__file__).resolve().with_name('FIXED_NONHIER_SCHEMA.json'))
    sp=checked_pin(gen['schema_input'],False,256<<10);cfg=checked_pin(gen['config'],True,64<<10)
    root=checked_pin(gen['root_header'],False,probe.HEADER_CAP);acc=checked_pin(gen['accessor'],True,64<<10)
    need(sp['bytes']==len(schema_raw)and sp['sha256']==probe.SCHEMA_SHA,'fixed probe schema bytes')
    need(gen['config']['text'].encode()==probe.config_bytes(doc),'exact fixed read-only VLT content')
    # Revalidate every retained declaration against fixed schema/order/width. The
    # full actual header hash is independently joined to the fresh GCC .d below;
    # this reconstruction checks syntax only, not a substitute actual header.
    maps=gen['mappings'];need(type(maps)is list and len(maps)==114,'complete mapping list')
    need(all(type(m)is dict and set(m)=={'symbol_key','module','instance_path','sv_var','width_bits','member','declaration'}and type(m['declaration'])is str and '\n'not in m['declaration'] and len(m['declaration'])<=512 for m in maps),'bounded exact mapping fields')
    header='\n'.join(['#ifndef VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_','#define VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_','class alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root final : public VerilatedModule {','  public:',*('    '+m['declaration']for m in maps),'};','#endif',''])
    need(probe.match_header(doc,header.encode())==maps,'fixed exact generated mapping')
    need(gen['accessor']['text'].encode()==probe.accessor_bytes(maps),'deterministic complete accessor source')
    generation=source['generation_input_pins'];derived=source['derived_generated_pins']
    need(all(generation[p]==derived[p]for p in set(generation)&set(derived)),'no conflicting actual input/derived pins')
    known={**generation,**derived}
    for v in (cp,sp,cfg,root,acc):need(known.get(v['path'])==v['sha256'],'actual prebuild readonly pin')
    need(generation.get(cp['path'])==cp['sha256']and generation.get(cfg['path'])==cfg['sha256'],'contract/config actual generation input')
    cwd=P(dep['cwd']);dependencies=dep['dependencies']
    need(root['path']==str(cwd/'VHostBlockTopV4___024root.h')and acc['path']==str(cwd/'readonly_first_fault_access.hpp'),'exact generated accessor/header path')
    for v in (root,acc):
        need([p for p in dependencies if P(p).name==P(v['path']).name]==[v['path']] and dependencies.get(v['path'])==v,'actual unique GCC readonly header dependency')
    role=contract['host_observer'];need(P(role['repo_path']).name=='readonly_first_fault.hpp','fixed host observer role');helpers=[p for p in dependencies if P(p).name=='readonly_first_fault.hpp']
    need(helpers==[str(P(dep['driver']).parent/'readonly_first_fault.hpp')],'actual readonly host helper dependency beside driver')
    helper=dependencies[helpers[0]];need(helper['bytes']==role['bytes']and helper['sha256']==role['sha256']and generation.get(helpers[0])==role['sha256'],'fixed readonly helper generation identity')
    need(dep['driver'].endswith('/'+contract['diagnostic_driver']['repo_path'])and generation.get(dep['driver'])==contract['diagnostic_driver']['sha256'],'diagnostic driver actual role/path')
    repo=dep['driver'][:-len('/'+contract['diagnostic_driver']['repo_path'])]
    for v,role_name in ((sp,'probe_schema'),(cfg,'probe_config')):
        role=contract[role_name];need(v['path']==repo+'/'+role['repo_path'] and v['bytes']==role['bytes'] and v['sha256']==role['sha256'],'fixed actual source role '+role_name)
    need(cp['path']==repo+'/candidates/model_candidate_build_20261101/FIRST_FAULT_DRIVER_CONTRACT.json','exact producer contract location')
    hp=doc['original_hierarchy_pin'];hier=[p for p,h in generation.items()if p.endswith('/'+hp['repo_path'])and h==hp['sha256']]
    need(len(hier)==1,'original exact hierarchy source retained')
    argv=source['physical_closure']['initial_frontend_argv']
    need(type(argv)is list and all(type(a)is str for a in argv),'actual frontend argv')
    need([a for a in argv if a.endswith('.vlt')]==[hier[0],cfg['path']] and argv.count(cfg['path'])==1,'original hierarchy plus one exact readonly frontend config')
    need('--public-flat-rw'not in argv and '--public'not in argv and '--vpi'not in argv,'no global signal exposure')
    return dict(schema='VERIFIED_FIRST_FAULT_READONLY_COMPILATION_V1',scope=FIRST_FAULT_SCOPE,field_count=114,contract_sha256=CONTRACT_SHA,accessor_sha256=acc['sha256'],config_sha256=cfg['sha256'],root_header_sha256=root['sha256'],numerical_pass=False,final_rtl_executed=False)
