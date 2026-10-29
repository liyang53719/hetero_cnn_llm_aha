"""Restricted Verilator 5.032 writeDepend single rule, never a make evaluator."""
from pathlib import Path
import hashlib,json,re,stat
SAFE=re.compile(r'/[A-Za-z0-9_./+\-]+')
GENERATED={'.mk','.cpp','.h','.v','.sv','.dat','.f'}
def digest(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def fail(code,p,obj,out):
 s=p.lstat();r={'schema':'GENERATED_TREE_REJECTION_V1','code':code,'relative_path':p.relative_to(obj).as_posix(),'suffix':p.suffix,'bytes':s.st_size,'sha256':digest(p) if stat.S_ISREG(s.st_mode) else None}
 (Path(out)/'generated_tree_failure.json').write_text(json.dumps(r,sort_keys=True)+'\n')
 raise ValueError('generated tree rejection '+code+' file='+p.name+' suffix='+p.suffix)
def admit_native_dependencies(obj,prefixes,known_pins,out):
 obj=Path(obj).resolve();expected={}
 for prefix,cwd in prefixes.items():
  cwd=Path(cwd).resolve();expected[cwd/(prefix+'__ver.d')]=prefix
  if cwd==obj:expected[cwd/(prefix+'__hierVer.d')]=prefix
 generated={};deps=[]
 for p in sorted(obj.rglob('*')):
  if p.is_symlink():raise ValueError('generated tree symlink')
  if not p.is_file():continue
  if p.suffix in ('.o','.a','.gch'):fail('COMPILED_PRODUCT',p,obj,out)
  if p.suffix=='.d':
   if p not in expected:fail('UNEXPECTED_DEPENDENCY_NAME',p,obj,out)
   deps.append(p)
  elif p.suffix in GENERATED:generated[str(p)]=digest(p)
 dep_pins={str(p):digest(p) for p in deps};allowed={**known_pins,**generated,**dep_pins};rows=[]
 for p in deps:
  if not 0<p.stat().st_size<=1024*1024:fail('DEPENDENCY_SIZE',p,obj,out)
  raw=p.read_bytes()
  if not re.fullmatch(rb'[A-Za-z0-9_./+ :\-]+\n',raw) or raw.count(b':')!=1 or b' : 'not in raw:fail('DEPENDENCY_GRAMMAR',p,obj,out)
  a,b=raw[:-1].decode('ascii').split(' : ');targets=a.split();inputs=b.split()
  if not targets or not inputs or str(p)not in targets or len(set(targets))!=len(targets):fail('DEPENDENCY_GRAMMAR',p,obj,out)
  for value in targets+inputs:
   q=Path(value)
   if not SAFE.fullmatch(value) or '..'in q.parts or str(q)!=value or str(q.resolve())!=value or not q.is_file()or q.is_symlink():fail('DEPENDENCY_PATH',p,obj,out)
  for value in targets:
   q=Path(value)
   if q.parent!=p.parent or not (q.name.startswith(expected[p]) or q.name in (expected[p][1:]+'.cpp',expected[p][1:]+'.sv') or (p.parent==obj and q.name in {n+'__hierMkArgs.f' for n in prefixes})) or value not in {**generated,**dep_pins}:fail('UNBOUND_TARGET',p,obj,out)
  for value in inputs:
   if value not in allowed:fail('UNBOUND_PREREQUISITE',p,obj,out)
   if digest(value)!=allowed[value]:fail('DEPENDENCY_PIN_DRIFT',p,obj,out)
  if digest(p)!=dep_pins[str(p)]:fail('DEPENDENCY_PIN_DRIFT',p,obj,out)
  rows.append({'relative_path':p.relative_to(obj).as_posix(),'bytes':len(raw),'sha256':dep_pins[str(p)],'targets':len(targets),'prerequisites':len(inputs)})
 generated.update(dep_pins)
 return generated,dep_pins,rows
