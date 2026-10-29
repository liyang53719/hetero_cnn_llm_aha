"""Actual job-local live-byte census + unchanged resource gates. No deletion/download.
Metadata archive sizes are lower bounds unless a reviewed phase upper bound exists.
"""
import hashlib,json,pathlib,os,stat,time,shutil,zipfile
P=pathlib.Path
TREE_CAP=12081306272;RESERVE=1500000000;SETUP_FREE=8*1024**3

def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def census(roots,max_entries=200000,max_seconds=30):
 roots=sorted({P(r).resolve(strict=True)for r in roots},key=lambda p:len(p.parts));roots=[p for i,p in enumerate(roots)if not any(p.is_relative_to(q)for q in roots[:i])];need(roots and all(p.is_dir()for p in roots),'actual owned directory roots')
 start=time.monotonic();logical=unique=allocated=entries=links=0;inodes=set();devices={};largest=[]
 for root in roots:
  disk=shutil.disk_usage(root);devices.setdefault(root.stat().st_dev,{'free_bytes':disk.free,'total_bytes':disk.total})
  for parent,dirs,files in os.walk(root,followlinks=False):
   for name in dirs+files:
    entries+=1;need(entries<=max_entries and time.monotonic()-start<=max_seconds,'bounded live census');p=P(parent)/name;s=p.lstat()
    if stat.S_ISLNK(s.st_mode):links+=1;continue
    need(stat.S_ISDIR(s.st_mode)or stat.S_ISREG(s.st_mode),'nonregular job-local entry')
    if not stat.S_ISREG(s.st_mode):continue
    logical+=s.st_size;key=(s.st_dev,s.st_ino)
    if key not in inodes:inodes.add(key);unique+=s.st_size;allocated+=s.st_blocks*512
    largest.append(s.st_size);largest=sorted(largest,reverse=True)[:8]
 need(len(devices)==1,'same filesystem job roots required for free gate')
 return {'schema':'JOB_LOCAL_LIVE_BYTES_V1','path_count_logical_bytes':logical,'unique_inode_logical_bytes':unique,'allocated_unique_bytes':allocated,'entries':entries,'symlinks_not_followed':links,'largest_file_sizes':largest,'disk':next(iter(devices.values())),'elapsed_seconds':time.monotonic()-start,'scope':'OBSERVED_SAMPLE_NOT_PEAK_OR_ATOMIC_SNAPSHOT'}

def admit(snapshot,phase,additional_bytes_upper_bound,remaining_wall_seconds,phase_wall_seconds):
 need(phase in ('runtime_setup','weight_acquisition','reference','provider','dut','compare'),'known phase')
 need(type(additional_bytes_upper_bound)is int and additional_bytes_upper_bound>=0,'reviewed additional-byte upper bound missing')
 need(type(phase_wall_seconds)is int and phase_wall_seconds>0 and remaining_wall_seconds>=phase_wall_seconds+120,'remaining job wall including summary reserve')
 live=snapshot['unique_inode_logical_bytes'];free=snapshot['disk']['free_bytes']
 need(type(live)is int and type(free)is int and live>=0 and free>=0,'observed byte values')
 if phase in ('runtime_setup','weight_acquisition'):need(free>=SETUP_FREE,'unchanged 8GiB setup/acquisition gate')
 need(live+additional_bytes_upper_bound<=TREE_CAP,'owned tree projected upper bound')
 need(free-additional_bytes_upper_bound>=RESERVE,'free reserve after admitted phase')
 return {'status':'ADMITTED_RESOURCE_BOUNDS_ONLY_NOT_EXECUTION','phase':phase,'snapshot':snapshot,'additional_bytes_upper_bound':additional_bytes_upper_bound,'phase_wall_seconds':phase_wall_seconds,'continuous_supervisor_still_required':True}

def metadata(tensor_plan,runtime_root):
 tensor_plan=P(tensor_plan);runtime_root=P(runtime_root);t=json.loads(tensor_plan.read_text());profiles=[]
 for i,(model,layer)in enumerate([('qwen2_1p5b',0),('qwen3_5_0p8b',0),('qwen3_5_0p8b',3),('qwen3_5_35b_a3b',0),('qwen3_5_35b_a3b',3)]):
  prefix=('model.layers.'if i==0 else 'model.language_model.layers.')+str(layer)+'.';rows=[r for r in t[model]['tensors']if r['name'].startswith(prefix)];need(len(rows)==[12,14,11,18,15][i],'complete profile tensor count')
  profiles.append({'profile':i,'tensor_count':len(rows),'tensor_bytes':sum(r['bytes']for r in rows)})
 need(sum(x['tensor_count']for x in profiles)==70 and sum(x['tensor_bytes']for x in profiles)==3531306272,'full70 byte contract')
 runtime=[];all_artifacts={};pins={str(tensor_plan):sha(tensor_plan)}
 q=runtime_root/'QWEN2_WHEEL_LOCK.json';d=json.loads(q.read_text());pins[str(q)]=sha(q);groups={'qwen2':[{'filename':r['filename'],'bytes':r['size_bytes'],'sha256':r['sha256']}for r in d['packages']]}
 for name in ('qwen35_08b','qwen35_35b'):
  q=runtime_root/name/'ARTIFACT_SPEC.json';d=json.loads(q.read_text());pins[str(q)]=sha(q);groups[name]=d['artifacts']+[d['transformers']]
 for name,items in groups.items():
  runtime.append({'runtime':name,'archive_bytes':sum(r['bytes']for r in items),'archive_count':len(items),'installed_bytes_upper_bound':None})
  for r in items:
   key=(r['sha256'],r['bytes']);all_artifacts[key]={'filename':r['filename'],'bytes':r['bytes'],'sha256':r['sha256']}
 return {'schema':'FIVE_PROFILE_LIVE_BYTES_METADATA_V1','profiles':profiles,'tensor_bytes':3531306272,'runtime_archives':runtime,'shared_cache_distinct_content_bytes':sum(r['bytes']for r in all_artifacts.values()),'artifacts':list(all_artifacts.values()),'metadata_pins':pins,'unknown_required':['installed+temporary unpack peak','reference intermediate/output bytes','provider/output bytes','fresh build final live/free bytes','full-DUT RSS/rate'],'scope':'METADATA_COUNTS_ONLY_NOT_PHASE_ADMISSION'}

def wheel_unpacked(path,expected_sha):
 p=P(path);need(p.stat().st_size<=350*1024**2 and sha(p)==expected_sha,'locked archive pin')
 with zipfile.ZipFile(p)as z:
  rows=z.infolist();need(len(rows)<=100000,'bounded archive member count');need(all(0<=r.file_size<=1024**3 for r in rows),'bounded members')
  total=sum(r.file_size for r in rows);need(total<=4*1024**3,'bounded total uncompressed')
 return {'archive_sha256':expected_sha,'archive_bytes':p.stat().st_size,'uncompressed_member_bytes':total,'largest_member_bytes':max((r.file_size for r in rows),default=0),'scope':'ZIP_METADATA_ONLY_NOT_INSTALL_PEAK_OR_INSTALLED_IDENTITY'}
