#!/usr/bin/env python3
"""Fresh public21 metadata/control contracts; no numeric payloads or execution."""
import ast,hashlib,json,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
PINS_PATH=Path(__file__).with_name('source_pins.json')
PINS=json.loads(PINS_PATH.read_bytes())
def verify_sources(root=ROOT):
    for name,pin in PINS['source_sha256'].items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError('reviewed current baseline source changed: '+name)
verify_sources()
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from candidates.qwen2_resident_matrix.ffn_public import model as m
from candidates.qwen2_resident_matrix.ffn_public.fixture import make_qwen2_21_fixture
HERE=Path(__file__).resolve().parent

def require(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def record(p):return dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
def validator():
    p=ROOT/'candidates/qwen2_resident_matrix/official_bf16/execution.py'
    tree=ast.parse(p.read_text());nodes=[n for n in tree.body if
        isinstance(n,ast.FunctionDef) and n.name=='validate_job' or
        isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='JOBS' for t in n.targets)]
    require(len(nodes)==2,'exact existing validate_job/JOBS extraction')
    ns={'require':require};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
    return ns['validate_job'],record(p)
VALIDATE,VALIDATOR=validator()
KINDS={n:i for i,n in enumerate(('Norm','Dense','Bias','Rope','Attention','Add','Activation','KvAppend'))}

def contracts(f,resident=False):
    host=m.group.HostControl(enabled=resident,legacy_prefix=True,legacy_attention=True)
    frontend=m.PublicFrontend(f.memory,f.config);require(frontend.launch(host),'launch admitted')
    jobs=[];events=[]
    for tick in range(10000):
        p=host.ports()
        if p['launch_result'] is not None:
            require(p['launch_result']['status'] is None,'model failed '+str(p['launch_result']))
            require(len(jobs)==(17 if resident else 19) and len(events)==21,'complete coverage')
            return jobs,events,p['launch_result']
        if p['group_request'] is not None or p['ordinary_request'] is not None:
            group=p['group_request'];job=group.act if group is not None else p['ordinary_request']
            members=(group.gate,group.up,group.act) if group is not None else (job,)
            for member in members:VALIDATE(f,member)
            pc=job.tag&65535;pcs=[16,17,18] if group is not None else [10,11,12] if pc==12 else [pc]
            role={1:'q_raw',4:'k_raw',7:'v_raw',13:'o',16:'gate',17:'up',19:'down'}.get(pc,job.kind.lower())
            j=dict(pc=pc,public_pcs=pcs,kind=job.kind,kind_id=KINDS[job.kind],role=role)
            for name in ('m','n','k','a','b','c','dst','tag'):j[name]=getattr(job,name,0)
            j.update(writeBytes=job.write_bytes,weightBf16=job.weight_bf16,activationBf16=job.activation_bf16,outputBf16=job.output_bf16)
            jobs.append(j);require(host.tick(request_ready=True)['request_fire'],'accepted job')
            for _ in range(3):require(host.ports()['completion'] is None,'early completion');host.tick()
            result=m.group.OwnerResult(job.tag,None,job.write_bytes,0,0,0)
            require(host.tick(owner_result=result)['owner_result_fire'],'accepted controlled return')
        elif p['completion'] is not None:
            e=p['completion'];require(e.status is None,'completion failure')
            events.append(dict(pc=e.pc,engine=e.engine,signal=e.signal,status=0,owner_index=len(jobs)-1,
                publication_after_this_completion=e.pc==jobs[-1]['public_pcs'][-1]))
            require(host.tick(completion_ready=True)['completion_fire'],'accepted completion')
        else:host.tick(request_ready=False)
    raise ValueError('bounded model loop exhausted')

def generate(rows,epoch,relocate,out):
    require(not out.exists(),'fresh fixture path');out.mkdir(parents=True)
    f=make_qwen2_21_fixture(rows,epoch,relocate)
    jobs,events,result=contracts(f)
    # A separate new model invocation is descriptive evidence for the candidate
    # mapping; it is never used as the expected result for current mainline RTL.
    cj,ce,cr=contracts(make_qwen2_21_fixture(rows,epoch,relocate),True)
    tables={}
    for key,table,values in (('command',f.config.command,f.commands),('descriptor',f.config.descriptor,f.records)):
        data=b''.join(v.pack().to_bytes(16,'little') for v in values)
        data=data.ljust(((len(data)+63)//64)*64,b'\0');name=key+'.bin';(out/name).write_bytes(data)
        tables[key]=dict(base=table.base,limit=table.limit,count=table.count,file=name,sha256=sha(data),bytes=len(data))
    manifest=dict(schema='qwen2-current-public21-dispatch-control-v1',scope='METADATA_ONLY_CURRENT19_CONTROL',rows=rows,epoch=epoch,
        shape=dict(hidden=1536,ffn=8960,heads=12,kvHeads=2,headDim=128,maxTokens=1024),tables=tables,
        regions=[asdict(r) for r in f.config.regions],accepted_jobs=jobs,expected_completions=events,
        controlled_model_result=result,historical_candidate17=dict(scope='DISTINCT_RESIDENT_CONTROL_MODEL_ONLY',accepted_jobs=cj,expected_completions=ce,result=cr),
        numeric_validator_source=VALIDATOR,arithmetic_executed=False,weights_materialized=False,
        full_block_numerical_pass=False,metadata_provenance=dict(f.provenance))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return dict(directory=out.name,manifest_sha256=record(out/'manifest.json')['sha256'])

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);a=parser.parse_args()
    out=a.out.resolve();require(not out.exists(),'fresh output');out.mkdir(parents=True)
    verify_sources()
    before=dict(PINS['source_sha256'])
    before[str(PINS_PATH.relative_to(ROOT))]=record(PINS_PATH)['sha256']
    for mod in list(sys.modules.values()):
        p=Path(getattr(mod,'__file__','') or '/')
        if p.is_file() and p.resolve().is_relative_to(ROOT) and 'work' not in p.resolve().relative_to(ROOT).parts:
            before[str(p.resolve().relative_to(ROOT))]=record(p)['sha256']
    before[str(Path(__file__).relative_to(ROOT))]=record(Path(__file__))['sha256']
    before['candidates/qwen2_resident_matrix/official_bf16/execution.py']=VALIDATOR['sha256']
    items=[generate(r,e,a,out/name) for r,e,a,name in ((16,7,0,'m16'),(128,8,0,'m128'),(16,9,0x10000000000000,'m16_relocated'))]
    require(all(record(ROOT/p)['sha256']==v for p,v in before.items()),'sources unchanged')
    gate=dict(schema='qwen2-public21-control-gate-v1',fixtures=items,source_sha256=before,
        scope='METADATA_CONTROL_ONLY',arithmetic_executed=False,current_owner_count=19,candidate_owner_count=17)
    (out/'gate.json').write_text(json.dumps(gate,indent=2)+'\n');print(json.dumps(items))
if __name__=='__main__':main()
