#!/usr/bin/env python3
"""Fresh P0 observation-policy overlay only. Never executes a model, compiler or DUT.
Requires caller's original runtime/views SHA AND independently locked P0 source/program
contracts. Reads source/metadata only; no weight or reference tensor payloads.
"""
import argparse, hashlib, json, pathlib, re, resource
P=pathlib.Path
HERE=P(__file__).resolve().parent
CONTRACT_SHA='ac2db97abc2dec264fd8e5d0eda06da11c1b955017075d7a2c79c49d1efdccd4'
RUNTIME_SEMANTIC_SHA='184bd5c1785b8ef756838a60c90aa38906372041c018f0acce5e469b48e494f6'
VIEWS_SEMANTIC_SHA='06ce2ef0332a5dc14385b353c15ad57a5d26c305a57cd38dc848e9d2c4c9bb0d'
EXPECTED_SHAPE={'H':1536,'F':8960,'HEADS':12,'KVHEADS':2,'HD':128,'MAX_TOKENS':1024}
TARGETS={'gate':(16,4492318720,4587520),'up':(17,4496906304,4587520)}

def need(ok,why):
    if not ok:raise ValueError(why)
def digest(data):return hashlib.sha256(data).hexdigest()
def sha_text(s):need(isinstance(s,str) and re.fullmatch('[0-9a-f]{64}',s) is not None,'explicit lowercase SHA256 required')
def read_small(path,limit=2*1024*1024):
    p=P(path);need(p.is_absolute() and p.is_file() and not p.is_symlink(),'absolute regular nonsymlink source/metadata required')
    need(p.stat().st_size<=limit,'source/metadata size bound')
    data=p.read_bytes();need(len(data)<=limit,'source/metadata grew');return data

def contract():
    data=read_small(HERE/'LOCKED_SOURCE_CONTRACT.json',65536)
    need(digest(data)==CONTRACT_SHA,'independent source contract drift')
    c=json.loads(data);need(c['schema']=='P0_RESIDENT_OBSERVATION_CONTRACT_V1','source contract schema');return c

def anchors(bindings):
    c=contract();need(type(bindings) is dict and set(bindings)==set(c['sources']),'exact independent anchor inventory')
    data={};pins={}
    for name,p in bindings.items():
        b=read_small(p);want=c['sources'][name]
        need(len(b)==want['bytes'] and digest(b)==want['sha256'],'independent '+name+' identity')
        data[name]=b;pins[name]=dict(path=str(P(p)),**want)
    m=json.loads(data['program_manifest'])
    need(m['shape']==EXPECTED_SHAPE and m['tokens']==128 and m['commands']==21 and m['descriptors']==215,'independent P0 M128 resident shape')
    need(m['weight_storage']=='bf16' and m['input_identity']=='NEW_EXTERNAL_BOUNDARY_FRESH_OFFICIAL_WEIGHTS','original storage/input contract')
    cb=data['commands'];db=data['descriptors'];cw=[int.from_bytes(cb[i:i+16],'little') for i in range(0,len(cb),16)];dw=[int.from_bytes(db[i:i+16],'little') for i in range(0,len(db),16)]
    need(not any(cw[21:]) and not any(dw[215:]),'program padding')
    for s in m['schedule']:
        roots=[(cw[s['pc']]>>n)&0xffffff for n in (56,80,104)]
        need(roots==s['roots'],'Command128 roots')
        for name,index in zip([s['a'],s['b'],s['dst']],roots):
            if name is None:need(index==0xffffff,'absent operand sentinel');continue
            t=m['tensors'][name];w=dw[index];n=(w>>32)&0xffffff;d=dw[n];rank=(w>>116)&15
            need((w&255,d&255)==(1,2),'TypedTensor prefix')
            address=((w>>56)&((1<<48)-1))|(((w>>120)&255)<<48)
            dims=[(d>>(56+18*i))&((1<<18)-1) for i in range(rank)]
            need(address==t['address'] and dims==t['dims'] and ((w>>108)&15)==t.get('storage_dtype',7),'independent actual tensor binding '+name)
    for name,(pc,address,size) in TARGETS.items():
        t=m['tensors'][name];s=m['schedule'][pc]
        need(t['address']==address and t['words']*4==size and t['dims']==[128,8960] and not t['readonly'],'resident destination span')
        need(s['dst']==name and s['a']=='n1' and s['b']==('wg' if name=='gate' else 'wu'),'resident command role')
    return data,pins

def rows(data,header):
    need(type(data) is bytes and 0<len(data)<=65536 and data.endswith(b'\n') and b'\r' not in data and b'\0' not in data,'canonical bounded TSV')
    text=data.decode('utf-8');lines=text.splitlines()
    need(data==('\n'.join(lines)+'\n').encode('utf-8'),'strict LF TSV roundtrip; no alternate separators')
    need(lines[0]==header and all(lines),'TSV header/nonempty')
    return [line.split('\t') for line in lines]

def input_rows(runtime,expected_sha,views_path):
    sha_text(expected_sha);need(digest(runtime)==expected_sha,'original runtime SHA mismatch')
    r=rows(runtime,'HOST_COMPILED_INPUT_V2')
    v=[x for x in r if x[0]=='views'];need(v==[['views',str(P(views_path))]],'exact original views binding')
    launch=[x for x in r if x[0]=='launch'];need(len(launch)==1 and len(launch[0])==10 and launch[0][1:4]==['1','0','1'],'P0 launch only')
    canonical=('\n'.join('\t'.join(x) for x in r if x[0]!='views')+'\n').encode()
    need(digest(canonical)==RUNTIME_SEMANTIC_SHA,'independent P0 original runtime semantics')
    return r

def validate_views(view_bytes,expected_sha,bindings):
    sha_text(expected_sha);need(digest(view_bytes)==expected_sha,'original views SHA mismatch')
    v=rows(view_bytes,'AFFINE_BYTES_V1');canonical=[v[0]];seen=set()
    for r in v[1:]:
        need(len(r)==16 and r[0]=='map' and r[1] not in seen,'complete unique view map');seen.add(r[1])
        need(P(r[8]).is_absolute() and '..' not in P(r[8]).parts,'absolute source view path')
        need('reference_only' not in P(r[8]).parts,'golden output view prohibited')
        if r[1] in ['commands','descriptors']:
            need(P(r[8]).resolve()==P(bindings[r[1]]).resolve(),'program view versus independently pinned bytes')
        x=r.copy();x[8]='<SOURCE_PATH>';canonical.append(x)
    need(digest(('\n'.join('\t'.join(x) for x in canonical)+'\n').encode())==VIEWS_SEMANTIC_SHA,'independent input/weight/program view pins/geometry')
    return v

def rewrite(original_rows):
    out=[];changed=[];omitted=[]
    for r in original_rows:
        if r[0]=='allocation' and r[1] in TARGETS:
            pc,address,size=TARGETS[r[1]]
            need(r==['allocation',r[1],str(address),str(size),str(size),'rw'],'exact original gate/up allocation')
            changed.append(r[1]);r=r.copy();r[-1]='virtual'
        if r[0]=='observe' and r[2] in TARGETS:
            pc,address,size=TARGETS[r[2]]
            need(r==['observe',str(pc),r[2],str(address),str(size),'7'],'exact impossible observation')
            omitted.append(r[2]);continue
        out.append(r)
    need(sorted(changed)==sorted(omitted)==['gate','up'],'exact four-line correction')
    return ('\n'.join('\t'.join(r) for r in out)+'\n').encode()

def verify_delta(original,corrected,expected_sha,views_path):
    # Approval is derived again from independent ORIGINAL semantics, never from
    # a newly rewritten file's self-reported hash or a reduced observer count.
    before=input_rows(original,expected_sha,views_path);after=rows(corrected,'HOST_COMPILED_INPUT_V2')
    need(corrected==rewrite(before),'only reviewed four-line delta allowed')
    oldobs=[r for r in before if r[0]=='observe'];newobs=[r for r in after if r[0]=='observe']
    need(len(oldobs)==20 and len(newobs)==18,'exact observation counts')
    need(newobs==[r for r in oldobs if r[2] not in TARGETS],'all other observation bytes/order unchanged')
    for kind in ['launch','region','views']:
        need([r for r in before if r[0]==kind]==[r for r in after if r[0]==kind],kind+' unchanged')
    need({r[2] for r in newobs}>={'y','cache_k','cache_v'},'mandatory final observations retained')

def apply(runtime_path,expected_runtime_sha,views_path,expected_views_sha,bindings,output_dir):
    runtime_path=P(runtime_path);views_path=P(views_path);output_dir=P(output_dir)
    need(output_dir.is_absolute() and not output_dir.exists() and not output_dir.is_symlink(),'NEW output directory only')
    original=read_small(runtime_path,65536);viewbytes=read_small(views_path,65536)
    source_bytes,source_pins=anchors(bindings)
    rr=input_rows(original,expected_runtime_sha,views_path);validate_views(viewbytes,expected_views_sha,bindings)
    corrected=rewrite(rr);verify_delta(original,corrected,expected_runtime_sha,views_path)
    # No metadata output exists until all independent input/source checks pass.
    output_dir.mkdir(parents=False,exist_ok=False)
    new_runtime=output_dir/'runtime.tsv'
    with new_runtime.open('xb') as f:f.write(corrected)
    verify_delta(original,read_small(new_runtime,65536),expected_runtime_sha,views_path)
    need(read_small(runtime_path,65536)==original and read_small(views_path,65536)==viewbytes,'original runtime/views changed')
    for name,p in bindings.items():need(read_small(p)==source_bytes[name],'independent source/program changed '+name)
    required={name:dict(required=True,actual_observation='UNOBSERVED',status='INCOMPLETE_INTERNAL_RESIDENT_VALUE_NOT_DDR_OBSERVED',reference_key='stage.mlp.'+name+'_proj.0',numeric_pass=False) for name in TARGETS}
    receipt=dict(schema='P0_RESIDENT_OBSERVATION_CORRECTION_V1',status='CORRECTED_METADATA_ONLY_REQUIRED_GATES_INCOMPLETE',hardware_executed=False,numeric_acceptance=False,
        original_runtime=dict(path=str(runtime_path),bytes=len(original),sha256=expected_runtime_sha,unchanged=True),
        corrected_runtime=dict(path=str(new_runtime),bytes=len(corrected),sha256=digest(corrected)),
        views=dict(path=str(views_path),bytes=len(viewbytes),sha256=expected_views_sha,unchanged=True),
        corrector_source_sha256=digest(read_small(P(__file__).resolve())),independent_source_contract_sha256=CONTRACT_SHA,independent_original_runtime_semantic_sha256=RUNTIME_SEMANTIC_SHA,
        independent_input_weight_program_view_semantic_sha256=VIEWS_SEMANTIC_SHA,source_pins=source_pins,
        corrections=['allocation gate rw -> virtual','allocation up rw -> virtual','omit observe PC16 gate','omit observe PC17 up'],
        preserved_observation_count=18,required_hidden_gates=required,
        unchanged=['hardware','driver','consumer','tolerances','command bytes','descriptor bytes','input/weight/view bytes and bindings','all addresses/sizes','all other18 observations','final y/cache_k/cache_v requirements'],
        nonclaims=['not DUT execution','not C++ config parse or EDA','not hidden-gate numerical acceptance','not payload rehash: existing payload SHA pins are preserved, payload files not read','no new runtime bundle emitted; future integration requires fresh bundle identity and coverage sidecar'],
        zero_fill=False,reference_fill=False,other_ddr_borrowing=False,raw_payloads_read=False)
    with (output_dir/'OBSERVATION_POLICY.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    return receipt

def main():
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
    a=argparse.ArgumentParser();a.add_argument('--runtime',type=P,required=True);a.add_argument('--expected-runtime-sha256',required=True)
    a.add_argument('--views',type=P,required=True);a.add_argument('--expected-views-sha256',required=True)
    a.add_argument('--bindings',type=P,required=True);a.add_argument('--output-dir',type=P,required=True);args=a.parse_args()
    bindings=json.loads(read_small(args.bindings,65536))
    r=apply(args.runtime,args.expected_runtime_sha256,args.views,args.expected_views_sha256,bindings,args.output_dir)
    print(json.dumps(dict(status=r['status'],corrected_runtime=r['corrected_runtime'],required_hidden_gates=r['required_hidden_gates']),indent=2))
if __name__=='__main__':main()
