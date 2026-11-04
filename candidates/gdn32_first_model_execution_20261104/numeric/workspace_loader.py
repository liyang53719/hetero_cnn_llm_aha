"""Exact original builder DSOs in a private workspace. Never weakens SHA identity.
Pure validation/argv construction; actual loader/DUT execution belongs to the
existing strict supervisor. No system mutation, LD_LIBRARY_PATH, or fallback.
"""
import hashlib,json,pathlib,re
P=pathlib.Path
SONAMES={'ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libcrypto.so.3','libgcc_s.so.1','libstdc++.so.6'}

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def checked(row,cap=32<<20):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact workspace pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file(),'canonical regular workspace file')
 need(type(row['bytes'])is int and 0<row['bytes']<=cap and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'exact workspace file bytes');return p

def read(contract):return json.loads(checked(contract,65536).read_text())

def verify(contract,binary,binary_sha,tool_manifest,tool_sha,elf_reader):
 d=read(contract)
 need(set(d)=={'schema','scope','builder_source_commit','artifact_manifest_sha256','binary','tool_manifest','root','libraries','aliases','provenance','later_dlopen','numerical_pass'},'exact workspace loader contract')
 need(d['schema']=='PINNED_WORKSPACE_ELF_STARTUP_V1'and d['scope']=='ORIGINAL_BUILDER_DSO_BYTES_NOT_NUMERICAL'and d['later_dlopen']=='NOT_QUALIFIED'and d['numerical_pass']is False,'workspace startup-only scope')
 need(re.fullmatch('[0-9a-f]{40}',d['builder_source_commit'])and re.fullmatch('[0-9a-f]{64}',d['artifact_manifest_sha256']),'fixed actual builder provenance')
 need(checked(d['binary'],4<<30)==P(binary).resolve()and d['binary']['sha256']==binary_sha,'same unmodified binary')
 need(checked(d['tool_manifest'])==P(tool_manifest).resolve()and d['tool_manifest']['sha256']==tool_sha,'same builder tool inventory')
 artifact=P(binary).resolve().parent/'frozen_artifact.json'
 need(artifact.is_file()and not artifact.is_symlink()and artifact.stat().st_size<=1<<20 and sha(artifact)==d['artifact_manifest_sha256'],'actual immutable artifact manifest')
 frozen=json.loads(artifact.read_text())
 need(frozen['artifact_identity']['source_commit']==d['builder_source_commit']and frozen['common']['binary']['sha256']==binary_sha and frozen['tool_manifest']['sha256']==tool_sha,'original builder identity/binary/tool joins')
 checked(d['provenance'],1<<20)
 tool=json.loads(P(tool_manifest).read_text());need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','original builder tool schema')
 root=P(d['root']);need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not q.is_symlink()for q in(root,*root.parents)),'canonical private DSO root')
 need(type(d['libraries'])is dict and set(d['libraries'])==SONAMES,'exact observed six startup objects')
 need(d['aliases']=={'libstdc++.so.6':'libstdc++.so.6.0.33'},'only original bounded SONAME alias')
 expected={'libstdc++.so.6.0.33',*SONAMES};need({p.name for p in root.iterdir()}==expected,'no extra file/subdir/hwcaps or unreviewed library')
 libs={}
 for name,row in d['libraries'].items():
  need(type(row)is dict and set(row)=={'pin','original_resolved'},'exact original-to-workspace library mapping')
  p=checked(row['pin']);need(p.parent==root and p.name==d['aliases'].get(name,name),'fixed library basename')
  original=row['original_resolved'];need(type(original)is str and original.startswith('/usr/lib/x86_64-linux-gnu/')and str(P(original))==original and '..'not in P(original).parts,'canonical original builder library path')
  need(P(original).name==d['aliases'].get(name,name),'exact original SONAME-to-basename role')
  need(tool['pins'].get(original)==row['pin']['sha256'],'identical actual builder library bytes, not version/SONAME waiver')
  info=elf_reader(p,require_interpreter=False);need(set(info['needed'])<=SONAMES,'complete static needed closure; no fallback DSO')
  libs[name]=dict(path=str(root/name),resolved=str(p),bytes=row['pin']['bytes'],sha256=row['pin']['sha256'],original_resolved=original)
 for alias,target in d['aliases'].items():
  p=root/alias;need(p.is_symlink()and p.readlink()==P(target)and p.resolve()==root/target,'exact internal SONAME alias')
 elf=elf_reader(binary);need(set(elf['needed'])==SONAMES,'same actual six direct dependencies')
 return dict(manifest=contract,root=str(root),loader=libs['ld-linux-x86-64.so.2'],libraries=libs,elf=elf,artifact_manifest_sha256=d['artifact_manifest_sha256'],builder_source_commit=d['builder_source_commit'],binary=d['binary'],tool_manifest=d['tool_manifest'])

def resolved_libraries(text_map,verified,pin):
 need(set(text_map)==SONAMES,'actual loader resolution must be exact six, no system fallback')
 result={}
 for name,path in text_map.items():
  observed=pin(path);expected=verified['libraries'][name]
  need(observed['resolved']==expected['resolved']and observed['bytes']==expected['bytes']and observed['sha256']==expected['sha256'],'actual resolved original library byte identity')
  need(P(observed['path']).parent==P(verified['root']),'actual loader path stays in private closure')
  result[name]=observed
 return result

def prefix(verified):return [verified['loader']['resolved'],'--inhibit-cache','--library-path',verified['root']]
