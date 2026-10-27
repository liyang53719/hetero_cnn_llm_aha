"""Rebuild only class-name/size/hash records. No JVM, class I/O or target execution."""
import argparse,hashlib,json,re
from pathlib import Path,PurePosixPath

def fail(ok,message):
    if not ok: raise ValueError(message)

def rows(items):
    out={}
    for r in items:
        p=PurePosixPath(r['relative'])
        fail(not p.is_absolute() and '..' not in p.parts and '\\' not in str(p) and str(p)==r['relative'] and str(p).endswith('.class'),'class relative path')
        fail(type(r['bytes']) is int and r['bytes']>0,'class bytes')
        fail(type(r['sha256']) is str and re.fullmatch('[0-9a-f]{64}',r['sha256']) is not None,'class hash')
        fail(str(p) not in out,'duplicate class')
        out[str(p)]={k:r[k] for k in ('relative','bytes','sha256')}
    return out

def compose(base,old,delta,new,groups):
    m=rows(base['classes']);fail(len(m)==550,'550 base')
    oldrows={r['relative']:r for r in old['classes']}
    replace=delta['override14'];fail(len(replace)==14 and len(rows(replace))==14,'14 overrides')
    for r in replace:
        fail(r['relative'] in oldrows and all(oldrows[r['relative']][k]==r[k] for k in ('relative','bytes','sha256','source_file')),'override provenance')
        m[r['relative']]={k:r[k] for k in ('relative','bytes','sha256')}
    fail(len(m)==554 and sum(r['bytes'] for r in m.values())==9631197,'554 stage')
    add=rows(new['classes']);fail(len(add)==3 and not(set(add)&set(m)),'3 new')
    m.update(add);fail(len(m)==557 and sum(r['bytes']for r in m.values())==9695031,'557 stage')
    stages=[557]
    for g,name,n in zip(groups,['preserved68','backend39','observer2','lowering3','emitter13'],[68,39,2,3,13]):
        fail(g['role']==name,'group order');a=rows(g['classes'])
        fail(len(a)==n and not(set(a)&set(m)),'group count/shadow');m.update(a);stages.append(len(m))
    fail(len(groups)==5 and stages==[557,625,664,666,669,682],'stage counts')
    fail(sum(r['bytes']for r in m.values())==10937493,'682 total bytes')
    return {'class_count':682,'class_bytes':10937493,'stage_counts':stages,'classes':[m[k]for k in sorted(m)],'class_payloads_read':False,'target_executed':False}

def rebuild(repo_root,package):
    root=Path(repo_root).absolute();p=Path(package).absolute()
    fail(root.resolve()==root and p.resolve()==p,'symlink root')
    refs={r['path']:r for r in json.loads((p/'PUBLIC_REFERENCES.json').read_text())}
    d=json.loads((p/'CLASS_SELECTION_DELTA.json').read_text());objects=[]
    for n in d['baseline557_reference_order']:
        rel=PurePosixPath(n);fail(not rel.is_absolute() and '..' not in rel.parts,'ref path')
        f=root.joinpath(*rel.parts);fail(f.resolve()==f and f.is_file() and not f.is_symlink(),'regular reference')
        b=f.read_bytes();r=refs[n];fail(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'ref hash')
        objects.append(json.loads(b))
    return compose(*objects,d['groups'])

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,required=True);v=a.parse_args()
    print(json.dumps(rebuild(v.repo_root,Path(__file__).resolve().parent),indent=2))
