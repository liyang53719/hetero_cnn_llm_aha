#!/usr/bin/env python3
"""Publish immutable completed native-BF16 evidence, keeping the 50% gate FAILED.

The tested source is checked against its historical Git commit, NOT current
main: later transport code must not inherit this older numeric result.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,os,re,struct,subprocess,uuid
SOURCE='52adab91c89335f29eb8af49b5a04843662dc67e'
PREFIX='reports/execution/NATIVE_BF16_REAL2_52adab91c893'
VALUES=1409024

def need(condition,message):
    if not condition:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args,data=None,env=None):
    return subprocess.check_output(['git',*args],input=data,env=env)

def audit(root,source_read):
    p=root/'work/native_real2'
    need((root/'native_tested_source.txt').read_text().strip()==SOURCE,'WRONG_TESTED_SOURCE')
    need((p/'source_base_commit.txt').read_text().strip()==SOURCE,'WRONG_NUMERIC_SOURCE')
    for n in ('gate.exit','simulation.exit'):
        need((p/n).read_text().strip()=='0','NUMERICAL_FAILURE:'+n)
    need((p/'performance.exit').read_text().strip()=='3','PERFORMANCE_STATUS_WAS_REWRITTEN')
    need((root/'native_real2_gate.exit').read_text().strip()=='3','OVERALL_TARGET_FAILURE_WAS_REWRITTEN')
    identities=json.loads((p/'sources.sha256.json').read_text())
    need(len(identities)==331,'INCOMPLETE_SOURCE_IDENTITY')
    for n,h in identities.items():need(sha(source_read(n))==h,'TESTED_SOURCE_DRIFT:'+n)
    m=json.loads((p/'fixture/manifest.json').read_text())
    need((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'],m['commands'],m['descriptors'])==(16,2,1536,8960,42,430),'WRONG_WORKLOAD')
    log=(p/'run.log').read_text()
    need(not re.search(r'HOST_BLOCK_FAIL|%Error|Fatal',log),'FAILED_NUMERIC_LOG')
    completion=re.findall(r'^OWNER_COMPLETION pc=(\d+) ',log,re.M)
    need(list(map(int,completion))==list(range(42)),'MISSING_OR_REORDERED_COMMAND')
    final=[s for s in log.splitlines() if s.startswith('HOST_BLOCK_ALL_OWNERS_PASS ')]
    need(len(final)==1,'AMBIGUOUS_FINAL_RECEIPT')
    counters=dict(re.findall(r'(\w+)=([^ ]+)',final[0]))
    for n,v in {'tokens':16,'layers':2,'host_commands':42,'completed':42,'owner_jobs':38,'checked_fp32':VALUES,'bit_differences':0,'useful_macs':1498202112,'executed_macs':1524105216,'matrix_macs':4096,'original_matrix_instances':8,'original_idma_instances':1,'host_intermediate_writes':0,'legacy_block_launch':0}.items():
        need(counters.get(n)==str(v),'WRONG_COUNTER:'+n)
    count=0
    with gzip.open(p/'all_owner_elements.csv.gz','rt',newline='') as f:
        rows=csv.reader(f)
        need(next(rows,None)==['pc','tensor','index','actual_hex','reference_hex'],'BAD_CSV_HEADER')
        for op in m['schedule']:
            for n in op['outputs']:
                a=(p/'tensors'/(n+'_actual.f32le')).read_bytes()
                b=(p/'tensors'/(n+'_reference.f32le')).read_bytes()
                need(len(a)==m['tensors'][n]['words']*4 and a==b,'NUMERIC_MISMATCH:'+n)
                for i,(v,) in enumerate(struct.iter_unpack('<I',a)):
                    need(v&0x7f800000!=0x7f800000,'NONFINITE_VALUE')
                    h=f'{v:08x}'
                    need(next(rows,None)==[str(op['pc']),n,str(i),h,h],'CSV_BINARY_MISMATCH')
                    count+=1
        need(next(rows,None) is None and count==VALUES,'INCOMPLETE_CSV')
    r=json.loads((p/'PERFORMANCE.json').read_text());c=int(counters['cycles'])
    u=1498202112/(4096*c)
    need(r['performance_accepted'] is False and r['whole_request_target']==0.5,'MISREPORTED_PERFORMANCE_PASS')
    need(abs(r['optimized']['useful_wall_mac_utilization']-u)<1e-15 and u<0.5,'INVALID_UTILIZATION')
    need(r['optimized']['cycles']==c,'CYCLE_MISMATCH')
    return {'status':'NUMERICAL_PASS_PERFORMANCE_BELOW_50_PERCENT','tested_source':SOURCE,
            'checked_fp32':count,'bit_differences':0,'cycles':c,
            'useful_wall_mac_utilization':u,'required_useful_utilization':0.5,
            'performance_accepted':False,'source_files_checked':len(identities),
            'full_new_transport_acceptance':False,
            'log_sha256':sha((p/'run.log').read_bytes())}

def publish(root):
    report=audit(root,lambda n:git('show',SOURCE+':'+n))
    selected={}
    for p in sorted(root.rglob('*')):
        need(not p.is_symlink(),'SYMLINK_NOT_ALLOWED')
        if p.is_file():selected[str(p.relative_to(root))]=p.read_bytes()
    need(len(selected)==149,'WRONG_ARTIFACT_FILE_COUNT')
    selected['INDEPENDENT_PUBLICATION_AUDIT.json']=(json.dumps(report,indent=2)+'\n').encode()
    selected['PUBLISHED_SHA256.json']=(json.dumps({n:sha(b) for n,b in selected.items()},indent=2)+'\n').encode()
    blobs={n:git('hash-object','-w','--stdin',data=b).decode().strip() for n,b in selected.items()}
    for attempt in range(3):
        subprocess.run(['git','fetch','--no-tags','origin','main'],check=True)
        parent=git('rev-parse','origin/main').decode().strip()
        subprocess.run(['git','merge-base','--is-ancestor',SOURCE,parent],check=True)
        env=dict(os.environ,GIT_INDEX_FILE=str(Path.cwd()/('native_proof_index_'+uuid.uuid4().hex)),
                 GIT_AUTHOR_NAME='heteronpu-verified-native-proof',GIT_AUTHOR_EMAIL='heteronpu-verified@users.noreply.github.com',
                 GIT_COMMITTER_NAME='heteronpu-verified-native-proof',GIT_COMMITTER_EMAIL='heteronpu-verified@users.noreply.github.com')
        git('read-tree',parent,env=env)
        for n,b in selected.items():
            name=PREFIX+'/'+n;old=subprocess.run(['git','show',parent+':'+name],capture_output=True)
            need(old.returncode!=0 or old.stdout==b,'REFUSE_PROOF_OVERWRITE:'+name)
            git('update-index','--add','--cacheinfo','100644',blobs[n],name,env=env)
            need(git('show',':'+name,env=env)==b,'INDEX_MISMATCH')
        tree=git('write-tree',env=env).decode().strip()
        commit=git('commit-tree',tree,'-p',parent,'-m','test: preserve native-BF16 real16 two-layer numeric proof; 50-percent performance gate remains failed [skip ci]',env=env).decode().strip()
        if subprocess.run(['git','push','origin',commit+':main']).returncode==0:
            subprocess.run(['git','fetch','--no-tags','origin','main'],check=True)
            subprocess.run(['git','merge-base','--is-ancestor',commit,'origin/main'],check=True)
            for n,b in selected.items():need(git('show','origin/main:'+PREFIX+'/'+n)==b,'REMOTE_PROOF_MISMATCH')
            report.update(commit=commit,path=PREFIX,files=len(selected),remote_bytes_verified=True)
            Path('native_real2_publication.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2));return
    raise RuntimeError('FAST_FORWARD_PUBLICATION_FAILED_NO_FORCE_PUSH')
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('artifact',type=Path);x=a.parse_args()
    publish(x.artifact.resolve())
