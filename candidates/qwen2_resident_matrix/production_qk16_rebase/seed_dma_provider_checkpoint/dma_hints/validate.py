import hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parent
def need(ok,msg):
 if not ok:raise ValueError(msg)
def validate(root,config=None,targets=None):
 root=Path(root);targets=json.loads((P/'TARGETS.json').read_text()) if targets is None else targets;config=(P/'structural_hints.vlt').read_text() if config is None else config
 expected=['`verilator_config']+[f'{x["rule"]} -module "{x["module"]}" -var "{x["variable"]}"' for x in targets]
 actual=[l.strip() for l in config.splitlines() if l.strip() and not l.strip().startswith('//')]
 need(len(targets)==8 and actual==expected,'exact eight rules required')
 seen=set();matches=[]
 for x in targets:
  key=x['module'],x['variable'];need(key not in seen,'duplicate target');seen.add(key)
  p=root/x['path'];need(p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],'source hash mismatch')
  s=re.sub(r'//[^\n]*|/\*.*?\*/',lambda m:'\n'*m[0].count('\n'),p.read_text(),flags=re.S)
  modules=list(re.finditer(r'\bmodule\s+'+re.escape(x['module'])+r'\b(.*?)\bendmodule\b',s,re.S));need(len(modules)==1,'module must match once');need(len(re.findall(x['declaration_regex'],modules[0][1]))==1,'declaration must match once')
  matches.append(key)
 return matches
if __name__=='__main__':print(validate(P.parent))
