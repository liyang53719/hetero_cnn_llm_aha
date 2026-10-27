"""Pure source/hash-metadata reconstruction; no JVM, classes, IR or target imports."""
import argparse,hashlib,json,re
from pathlib import Path,PurePosixPath

def need(value,message):
    if not value: raise ValueError(message)

def sha(data): return hashlib.sha256(data).hexdigest()

def read(root,relative):
    p=PurePosixPath(relative)
    need(not p.is_absolute() and '..' not in p.parts and str(p)==relative and '\\' not in relative,'unsafe relative path')
    f=Path(root).joinpath(*p.parts)
    need(f.resolve()==f.absolute() and f.is_file() and not f.is_symlink(),'nonregular input')
    need(f.stat().st_size<=2*1024*1024,'small-text limit')
    b=f.read_bytes();b.decode('utf-8');need(b'\0' not in b,'binary input')
    return b

def checked(root,relative,identity):
    b=read(root,relative)
    need(len(b)==identity['bytes'] and sha(b)==identity['sha256'],'input identity')
    return b

def apply_patch(source,patch,name):
    """Apply one exact, single-file unified source patch; fail closed on context."""
    old=source.decode().splitlines(True);ls=patch.decode().splitlines(True)
    need(len(ls)>=3 and ls[:2]==['--- a/'+name+'\n','+++ b/'+name+'\n'],'patch headers')
    out=[];at=0;i=2
    while i<len(ls):
        m=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n',ls[i])
        need(m is not None,'hunk header')
        a,ac,b,bc=int(m[1]),int(m[2] or 1),int(m[3]),int(m[4] or 1)
        start=a-1 if ac else a
        need(at<=start<=len(old),'hunk ordering')
        out.extend(old[at:start]);at=start;i+=1;seen_old=seen_new=0
        need(len(out)==(b-1 if bc else b),'new hunk offset')
        while i<len(ls) and not ls[i].startswith('@@ '):
            line=ls[i];need(line[:1] in (' ','+','-'),'hunk line')
            text=line[1:]
            if line[0] in ' -':
                need(at<len(old) and old[at]==text,'hunk old context');at+=1;seen_old+=1
            if line[0] in ' +':out.append(text);seen_new+=1
            i+=1
        need((seen_old,seen_new)==(ac,bc),'hunk counts')
    out.extend(old[at:]);return ''.join(out).encode()

def classmap(rows):
    m={}
    for r in rows:
        p=PurePosixPath(r['relative'])
        need(not p.is_absolute() and '..' not in p.parts and str(p)==r['relative'] and str(p).endswith('.class'),'class relative')
        need(type(r['bytes']) is int and r['bytes']>0 and re.fullmatch('[0-9a-f]{64}',r['sha256']) is not None,'class metadata')
        need(str(p) not in m,'class shadow')
        m[str(p)]={k:r[k] for k in ('relative','bytes','sha256')}
    return m

def rebuild(repo_root,package):
    p=Path(package);root=Path(repo_root)
    refs=json.loads(read(p,'PUBLIC_REFERENCES.json'))
    public={r['path']:checked(root,r['path'],r) for r in refs}
    src=json.loads(read(p,'SOURCE_SELECTIONS.json'));memo={}
    def source(sid,active=()):
        need(sid not in active and sid in src['source_identities'],'source cycle/missing')
        if sid in memo:return memo[sid]
        r=src['source_identities'][sid]
        if 'package_path' in r:b=checked(p,r['package_path'],r)
        elif 'public_reference' in r:b=public[r['public_reference']['path']]
        else:
            q=r['reconstruction'];patch=checked(p,q['patch'],q['patch_identity'])
            b=apply_patch(source(q['base_source_sha256'],active+(sid,)),patch,r['name'])
        need(len(b)==r['bytes'] and sha(b)==r['sha256']==sid,'reconstructed source identity');memo[sid]=b;return b
    for sid in src['source_identities']:source(sid)
    need(len(memo)==47 and len(src['final_direct27_source_ids'])==27,'source counts')
    for st,row in src['stages'].items():
        ids=row['ordered_source_ids'];need(len(ids)==row['source_count'] and len(set(ids))==len(ids),'stage source duplicate')
        need(len({src['source_identities'][i]['name']for i in ids})==len(ids),'stage filename shadow')
    d=json.loads(read(p,'CLASS_SELECTIONS.json'));catalog=d['catalog']
    def select(ids):
        need(all(type(i) is int and 0<=i<len(catalog)for i in ids) and len(set(ids))==len(ids),'catalog indexes')
        return classmap([catalog[i]for i in ids])
    # Independent plain metadata recovery of public557 + exact68, never class bytes.
    bdelta=json.loads(public['candidates/retained_matrix_compiled_unseeded/CLASS_SELECTION_DELTA.json'])
    originals=[json.loads(public[n])for n in bdelta['baseline557_reference_order']]
    pool=classmap(originals[0]['classes']);need(len(pool)==550,'base550')
    old=classmap(originals[1]['classes'])
    overrides=classmap(originals[2]['override14']);need(len(overrides)==14,'override14')
    for n,r in overrides.items():need(old[n]==r,'override provenance');pool[n]=r
    need(len(pool)==554,'base554')
    fresh=classmap(originals[3]['classes']);need(len(fresh)==3 and not(set(fresh)&set(pool)),'new3');pool.update(fresh)
    g=bdelta['groups'][0];need(g['role']=='preserved68','preserved group');extra=classmap(g['classes'])
    need(len(extra)==68 and not(set(extra)&set(pool)),'68 shadow');pool.update(extra);need(len(pool)==625,'base625')
    moe=classmap(json.loads(public['candidates/moe_phase_context_typecheck/TYPECHECK_IDENTITIES.json'])['new90'])
    kinds={r['role']:r['kind']for r in json.loads(read(p,'PROVIDER_RECOVERY.json'))['providers']}
    for r in catalog:
        k=kinds[r['provider_role']]
        if k in ('base625','moe90'):
            expected=(pool if k=='base625' else moe)[r['relative']]
            need(all(r[q]==expected[q]for q in ('relative','bytes','sha256')),'public provider identity')
    stagecounts={}
    for st,row in d['stages'].items():
        a=select(row['baseline']);b=select(row['outputs']);need(not(set(a)&set(b)),'stage baseline/output shadow');stagecounts[st]=[len(a),len(b)]
    need(stagecounts=={'0735':[559,102],'0855':[724,156],'0915':[880,3],'0943':[876,4],'1012':[874,9]},'stage counts')
    final=select(d['final1044']);last=d['stages']['1012'];joined=select(last['baseline']+last['outputs'])
    need(final==joined and len(final)==883 and sum(r['bytes']for r in final.values())==14955848,'final883')
    return {'status':'PASS_SOURCE_AND_HASH_METADATA_ONLY','source_identities':len(memo),'historical_patches':6,'public_refs':len(refs),'class_catalog':len(catalog),'stage_counts':stagecounts,'final_class_count':883,'class_payloads_read':0,'target_executions':0}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,required=True);v=a.parse_args()
    print(json.dumps(rebuild(v.repo_root,Path(__file__).resolve().parent),indent=2))
