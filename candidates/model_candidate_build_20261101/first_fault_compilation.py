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
    from first_fault_policy import artifact_policy,FIRST_FAULT_SCOPE,contract_sha,contract_path
    contract=artifact_policy(manifest,source)
    if contract is None:
        need('readonly_probe'not in source and 'readonly_probe_contract_sha256'not in receipt,'original branch cannot carry readonly evidence')
        return None
    CONTRACT_SHA=contract_sha(contract)
    terminal=contract['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V2'
    need(receipt.get('readonly_probe_contract_sha256')==CONTRACT_SHA and receipt.get('scope')==FIRST_FAULT_SCOPE,'readonly receipt scope/contract')
    row=source['readonly_probe'];need(type(row)is dict and set(row)==({'schema','status','contract','accessor_generation'}|({'terminal_accessor_generation'}if terminal else set())) and row['schema']==('FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2'if terminal else'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1') and row['status']=='OBSERVED_UNREVIEWED','readonly source evidence shape')
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
    need(cp['path']==repo+'/'+contract_path(contract),'exact producer contract location')
    hp=doc['original_hierarchy_pin'];hier=[p for p,h in generation.items()if p.endswith('/'+hp['repo_path'])and h==hp['sha256']]
    need(len(hier)==1,'original exact hierarchy source retained')
    argv=source['physical_closure']['initial_frontend_argv']
    need(type(argv)is list and all(type(a)is str for a in argv),'actual frontend argv')
    terminal_proof=verify_terminal_probe(row['terminal_accessor_generation'],gen,contract,source,dep,repo)if terminal else None
    configs=[hier[0],cfg['path']]+([terminal_proof['config_path']]if terminal else[])
    need([a for a in argv if a.endswith('.vlt')]==configs and argv.count(cfg['path'])==1,'original hierarchy plus one exact readonly frontend config')
    need('--public-flat-rw'not in argv and '--public'not in argv and '--vpi'not in argv,'no global signal exposure')
    result=dict(schema='VERIFIED_FIRST_FAULT_READONLY_COMPILATION_V2'if terminal else'VERIFIED_FIRST_FAULT_READONLY_COMPILATION_V1',scope=FIRST_FAULT_SCOPE,field_count=114,contract_sha256=CONTRACT_SHA,accessor_sha256=acc['sha256'],config_sha256=cfg['sha256'],root_header_sha256=root['sha256'],numerical_pass=False,final_rtl_executed=False)
    if terminal:result['terminal_accessor']=terminal_proof
    return result


def verify_terminal_probe(gen,scalar_gen,contract,source,dep,repo):
    import terminal_finite_probe as terminal
    expected={'schema','scope','schema_input','config','root_header','accessor','mappings','word_count','reads_hier_child_internals','extra_eval_or_clock','output_raw_words'}
    need(type(gen)is dict and set(gen)==expected and gen['schema']=='ACTUAL_TERMINAL_FINITE_ACCESSOR_EVIDENCE_V1' and gen['scope']=='READ_ONLY_TERMINAL_CLASSIFICATION_NOT_NUMERICAL_ACCEPTANCE','exact terminal evidence schema')
    need(type(gen['word_count'])is int and gen['word_count']==4096 and gen['reads_hier_child_internals']is False and gen['extra_eval_or_clock']is False and gen['output_raw_words']is False,'terminal classification only scope')
    sp=checked_pin(gen['schema_input'],False,16384);cfg=checked_pin(gen['config'],True,1<<20)
    root=checked_pin(gen['root_header'],False,probe.HEADER_CAP);acc=checked_pin(gen['accessor'],True,2<<20)
    _,raw=terminal.load_schema(P(__file__).resolve().with_name('TERMINAL_FINITE_SCHEMA.json'))
    need(sp['bytes']==len(raw)and sp['sha256']==terminal.SCHEMA_SHA,'fixed terminal schema bytes')
    need(gen['config']['text'].encode()==terminal.config_bytes(),'exact terminal-only readonly config')
    need(root==checked_pin(scalar_gen['root_header'],False,probe.HEADER_CAP),'scalar and terminal actual root identical')
    maps=gen['mappings'];need(type(maps)is list and len(maps)==4096,'all terminal mappings')
    keys={'index','row','column','sv_var','member','width_bits','declaration'}
    need(all(type(m)is dict and set(m)==keys and type(m['index'])is int and type(m['row'])is int and type(m['column'])is int and type(m['width_bits'])is int and type(m['declaration'])is str and '\n'not in m['declaration']and len(m['declaration'])<=512 for m in maps),'exact bounded terminal map fields')
    # Reconstruction validates retained declarations; actual GCC root SHA below
    # independently binds the real header, never this synthetic reconstruction.
    declarations=[m['declaration']for m in scalar_gen['mappings']]+[m['declaration']for m in maps]
    header='\n'.join(['#ifndef VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_','#define VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_','class alignas(VL_CACHE_LINE_BYTES) VHostBlockTopV4___024root final : public VerilatedModule {','  public:',*('    '+d for d in declarations),'};','#endif',''])
    need(terminal.match_header(header.encode())==maps,'exact terminal mapping order widths and declarations')
    need(gen['accessor']['text'].encode()==terminal.accessor_bytes(maps),'deterministic full terminal accessor')
    generation=source['generation_input_pins'];derived=source['derived_generated_pins'];known={**generation,**derived}
    for v in (sp,cfg,root,acc):need(known.get(v['path'])==v['sha256'],'actual terminal generation/derived pin')
    for v,role_name in ((sp,'terminal_probe_schema'),(cfg,'terminal_probe_config')):
        role=contract[role_name];need(v['path']==repo+'/'+role['repo_path']and v['bytes']==role['bytes']and v['sha256']==role['sha256']and generation.get(v['path'])==v['sha256'],'exact terminal source role '+role_name)
    cwd=P(dep['cwd']);need(acc['path']==str(cwd/'readonly_terminal_finite_access.hpp'),'fixed terminal accessor output')
    for v in (root,acc):
        need([p for p in dep['dependencies']if P(p).name==P(v['path']).name]==[v['path']]and dep['dependencies'].get(v['path'])==v,'actual unique GCC terminal dependency')
    for role_name in ('terminal_probe_generator','terminal_record_schema'):
        role=contract[role_name];need(generation.get(repo+'/'+role['repo_path'])==role['sha256'],'actual terminal generator/record role pin')
    return dict(schema='VERIFIED_TERMINAL_FINITE_COMPILATION_V1',word_count=4096,accessor_sha256=acc['sha256'],root_header_sha256=root['sha256'],config_sha256=cfg['sha256'],config_path=cfg['path'],output_raw_words=False,numerical_pass=False)


DEPENDENCY_RULE_POLICY='GCC_MMD_EXACT_REPEATED_PREREQUISITES_V1'

def parse_dependencies(text,cwd,driver):
    """New readonly-only GCC rule; preserve raw evidence, collapse exact repeat words only."""
    import json
    counts=dict(raw_count=None,unique_token_count=None,repeated_token_count=None)
    def checked(ok,reason):
        if not ok:
            record=dict(schema='FIRST_FAULT_DEPENDENCY_PARSE_DIAGNOSTIC_V1',reason=reason,**counts)
            encoded=json.dumps(record,sort_keys=True,separators=(',',':'))
            need(len(encoded.encode())<=2048,'bounded dependency diagnostic')
            print('FIRST_FAULT_DEPENDENCY_DIAGNOSTIC '+encoded,flush=True)
            raise ValueError('readonly dependency '+reason)
    checked(type(text)is str and 0<len(text.encode())<=1024**2 and text.endswith('\n') and re.fullmatch(r'[A-Za-z0-9_./+ \t:\\\n-]+',text)is not None,'TEXT_FORMAT')
    flat=text.replace('\\\n',' ');checked('\\'not in flat,'CONTINUATION')
    lines=[x.strip()for x in flat.splitlines()if x.strip()]
    checked(len(lines)==1 and lines[0].count(':')==1,'ONE_RULE')
    target,body=lines[0].split(':');checked(target.strip()==P(driver).stem+'.o','OBJECT_TARGET')
    tokens=body.split();counts.update(raw_count=len(tokens),unique_token_count=len(set(tokens)),repeated_token_count=len(tokens)-len(set(tokens)))
    checked(bool(tokens),'EMPTY');checked(len(tokens)<=4096,'TOKEN_LIMIT')
    paths=[]
    for token in dict.fromkeys(tokens):
        checked(re.fullmatch(r'[/A-Za-z0-9_.+\-]+',token)is not None,'PATH_FORMAT')
        p=P(token);checked('..'not in p.parts,'PARENT_TRAVERSAL');p=p if p.is_absolute()else P(cwd)/p
        paths.append(posixpath.normpath(str(p)))
    checked(len(paths)==len(set(paths)),'NORMALIZED_COLLISION')
    checked(paths.count(posixpath.normpath(str(driver)))==1,'DRIVER_DEPENDENCY')
    checked(sum(P(p).name=='sparse_write_memory.hpp'for p in paths)==1,'SPARSE_DEPENDENCY')
    return paths

def capture(b,phase,supervisor,completed_phases):
 from driver_dependency_proof import pin, text_pin, strict_native, verify_observer_dependencies, CPP_O1_POLICY, CPP_O1_OVERRIDES
 from first_fault_policy import binding_policy
 need(binding_policy(b) is not None,"explicit readonly dependency collector")
 obj=P(b['obj']).resolve();driver=str(P(b['driver']).resolve());stem=P(driver).stem
 need(b['cpp_build_policy']==b['admission']['cpp_build_policy']==CPP_O1_POLICY and b['cpp_build_overrides']==b['admission']['cpp_build_overrides']==CPP_O1_OVERRIDES,'actual strict O1 admission before capture')
 record=dict(schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2',dependency_rule_policy=DEPENDENCY_RULE_POLICY,cpp_build_policy=CPP_O1_POLICY,cpp_build_overrides=list(CPP_O1_OVERRIDES),cwd=str(obj),driver=driver,depfile=text_pin(obj/(stem+'.d'),1024**2),object=pin(obj/(stem+'.o')),host_make=text_pin(obj/'VHostBlockTopV4.mk'),host_hierarchy=text_pin(obj/'VHostBlockTopV4_hier.mk'),global_make=text_pin(P(b['verilator_root'])/'include/verilated.mk'),host_link_receipt=supervisor,host_link_argv=phase['argv'],binary=pin(phase['output']),make_closure_pins=b['admission']['make_closure_pins'])
 dependencies=parse_dependencies(record['depfile']['text'],obj,driver);header=next(p for p in dependencies if P(p).name=='sparse_write_memory.hpp');record['resolved_sparse_header']=pin(header)
 need(b['pins'].get(header)==record['resolved_sparse_header']['sha256'],'resolved header belongs to original build input pins')
 record['dependencies']={p:pin(p) for p in dependencies}
 for p,v in record['dependencies'].items():need(b['pins'].get(p)==v['sha256'],'all actual non-system dependencies were prebuild pinned')
 verify_observer_dependencies(record['dependencies'],driver,b['pins'])
 record['compilation_phases']=[dict(phase=r['phase'],argv=r['argv'],output=r['output'],supervisor=r['supervisor'])for r in completed_phases]+[dict(phase=phase['name'],argv=phase['argv'],output=record['binary'],supervisor=supervisor)]
 need(len(record['compilation_phases'])==5,'actual complete five-phase compilation capture')
 for r in record['compilation_phases']:strict_native(r['supervisor'])
 return record
