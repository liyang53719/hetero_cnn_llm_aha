"""Rebuild the exact 13 physical Matrix providers from pinned repository source only.
No EDA, network, archive, cached generated provider, or numerical qualification.
"""
import argparse,hashlib,importlib.util,json,pathlib,re,subprocess
D=pathlib.Path(__file__).parent
def need(x,m):
 if not x:raise ValueError(m)
def run(repo,out,from_git=False):
 need(not out.exists(),'fresh output')
 raw=(D/'MATRIX_REPO_SOURCE_MAP.json').read_bytes();need(hashlib.sha256(raw).hexdigest()=='f13b224355a89e8dcee3e8d90def92f5ec612dc78aedb60ad575984869844d1d','source mapping pin');mapping=json.loads(raw)
 def read(rel):
  return subprocess.check_output(['git','-C',str(repo),'show',mapping['commit']+':'+rel]) if from_git else (repo/rel).read_bytes()
 pkg=repo/'candidates/qwen2_public21_binding'
 need(hashlib.sha256((pkg/'compose.py').read_bytes()).hexdigest()=='730994443ca60d750eb13b0561dd3cd0a24ec024bb24be63cf2d1b793071e6c6','compose source pin')
 spec=importlib.util.spec_from_file_location('checked_compose',pkg/'compose.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 manifest,overlay,assets,_=c.load_inputs(pkg)
 names=[n for n in overlay['before_sha256'] if n.endswith('.sv')];need(len(names)==6,'six baseline providers')
 sources={n:c.checked(read(n),overlay['before_sha256'][n],n) for n in names}
 selected=b''.join(p for p in re.split(rb'(?=^--- a/)',assets['current_overlay.patch'],flags=re.M) if p.startswith(b'--- a/rtl/'))
 rebuilt=c.strict_patch(sources,selected,names)
 for n,b in rebuilt.items():c.checked(b,overlay['post_sha256'][n],n)
 byname={pathlib.PurePosixPath(n).name:b for n,b in rebuilt.items()}
 prepared=[]
 for row in mapping['files']:
  paths=row['matching_repo_paths']
  if paths:need(len(paths)==1,'unique checked source');body=read(paths[0])
  else:body=byname[row['name']]
  c.checked(body,row['sha256'],row['name']);prepared.append((row['name'],body,row['sha256']))
 need(len(prepared)==13 and sum(len(b) for n,b,h in prepared)==43047,'exact 13 provider closure')
 out.mkdir()
 for n,b,h in prepared:(out/n).write_bytes(b)
 (out/'SOURCE_ONLY_RECEIPT.json').write_text(json.dumps({'status':'PASS_13_PROVIDER_SOURCE_BYTES_ONLY','files':[{'name':n,'sha256':h,'bytes':len(b)} for n,b,h in prepared]},indent=2)+'\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--from-verified-git',action='store_true');v=a.parse_args();run(v.repo,v.output,v.from_verified_git)
