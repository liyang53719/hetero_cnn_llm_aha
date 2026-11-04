"""Fresh typed resource probe for the owning full same-job controller only."""
import hashlib,importlib.util,json,pathlib
P=pathlib.Path
REL='candidates/gdn32_first_model_execution_20261104/numeric/samejob_gdn32_full.py'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load_controller(row):
 need(type(row)is dict and set(row)=={'path','sha256'},'exact owning controller pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=2<<20 and sha(p)==row['sha256'],'owning controller unchanged before resource probe')
 b=json.loads(p.read_text());need(b.get('schema')=='GDN32_FULL_MODEL_SAME_JOB_BINDING_V1','full actual162 controller resource domain')
 path=P(b['repo'])/REL;need(path.is_file()and path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents))and b['pins'].get(str(path))==sha(path),'pinned typed resource gate bridge')
 spec=importlib.util.spec_from_file_location('_actual162_resource_bridge',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 return b,m
def before_stage(row,seconds,rss_gib):
 need(type(seconds)is int and seconds>0 and type(rss_gib)is int and 0<rss_gib<=8,'fixed finite stage resource request')
 b,m=load_controller(row)
 return m.resource_gate(b,phase='MODEL_BUILD',min_memory=(rss_gib+1)*1024**3,min_disk=1_500_000_000,stage_seconds=seconds)
