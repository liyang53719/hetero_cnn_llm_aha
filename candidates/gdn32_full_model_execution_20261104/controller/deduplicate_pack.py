"""Two exact completed-build copies only. No producer edits or general cleanup.
Caller owns serial flow; lock and same-uid writable-FD census are additional
fail-closed checks, not protection against a hostile process creating a writer
between samples. No active/native build may overlap this operation.
"""
import contextlib,fcntl,hashlib,json,os,pathlib,stat,time
P=pathlib.Path
CLEAN='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'
MAX_SAVING=362_153_111
BOOT=('jdk','jars','verilator','idma','matrix','compile_tools','binding')
NATIVE=('compile155','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p):
 p=P(p);need(p.is_absolute()and '..'not in p.parts and not any(x.is_symlink()for x in(p,*p.parents)),'canonical nonalias path');s=p.lstat();need(stat.S_ISREG(s.st_mode),'regular file');return s
def identity(p):
 s=regular(p);return (s.st_dev,s.st_ino,s.st_size,stat.S_IMODE(s.st_mode),s.st_mtime_ns,s.st_ctime_ns,s.st_uid,s.st_gid,s.st_nlink)
def stable(p,want):
 before=identity(p);need(before[2]==want['bytes']and sha(p)==want['sha256'],'size/hash drift');need(identity(p)==before,'concurrent content/metadata drift');return before
def doc(p,cap=16<<20):
 need(regular(p).st_size<=cap,'bounded JSON');return json.loads(P(p).read_text())
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def complete(r):
 need(r.get('native_exit')==0 and r.get('errors')==[] and (r.get('cleanup_proof')or{}).get('status')==CLEAN and (r.get('log_capture')or{}).get('pipe_eof_observed')is True and (r.get('log_capture')or{}).get('gzip_finalized')is True,'native owner not fully complete')
CENSUS_REASONS={'PERMISSION_DENIED','PROCESS_OR_FD_DISAPPEARED','IO_UNAVAILABLE','DEADLINE','PROCESS_CAP','FD_CAP','MAPS_CAP','MALFORMED_PROC_METADATA'}
class WriterCensusUnavailable(Exception):
 def __init__(self,reason):
  need(reason in CENSUS_REASONS,'fixed writer census reason');self.reason=reason;super().__init__('writer census unavailable')
def census_need(value,reason):
 if not value:raise WriterCensusUnavailable(reason)
def unavailable_census(exc):
 return dict(status='UNAVAILABLE',reason=exc.reason,writers_absent_established=False,scope='SAMPLED_SAME_UID_FD_AND_MAPS_NOT_HOSTILE_WRITER_EXCLUSION')
def writers_absent(paths,seconds=10):
 """Inconclusive observations NEVER establish writer absence or permit mutation.
 No retry, privilege change, alternate proc access, or ignored inaccessible FD.
 Artifact identity checks stay outside this narrow observation classification.
 """
 targets={(regular(p).st_dev,regular(p).st_ino)for p in paths}
 try:return _writer_census(targets,seconds)
 except PermissionError as exc:raise WriterCensusUnavailable('PERMISSION_DENIED') from exc
 except (FileNotFoundError,ProcessLookupError) as exc:raise WriterCensusUnavailable('PROCESS_OR_FD_DISAPPEARED') from exc
 except OSError as exc:raise WriterCensusUnavailable('IO_UNAVAILABLE') from exc
def _writer_census(targets,seconds):
 start=time.monotonic();count=0
 for directory in P('/proc').iterdir():
  if not directory.name.isdigit():continue
  census_need(time.monotonic()-start<seconds,'DEADLINE');count+=1;census_need(count<=8192,'PROCESS_CAP')
  if directory.stat().st_uid!=os.geteuid():continue
  for index,fd in enumerate((directory/'fd').iterdir()):
   census_need(index<65536,'FD_CAP');census_need(time.monotonic()-start<seconds,'DEADLINE')
   st=fd.stat()
   if (st.st_dev,st.st_ino)not in targets:continue
   text=(directory/'fdinfo'/fd.name).read_text()
   try:flags=next(x.split()[1]for x in text.splitlines()if x.startswith('flags:'));mode=int(flags,8)
   except (StopIteration,IndexError,ValueError) as exc:raise WriterCensusUnavailable('MALFORMED_PROC_METADATA') from exc
   need(mode&os.O_ACCMODE==os.O_RDONLY,'observed writable descriptor')
  with (directory/'maps').open()as maps:raw=maps.read((1<<20)+1)
  census_need(len(raw)<=1<<20,'MAPS_CAP')
  for line in raw.splitlines():
   fields=line.split(None,5);census_need(len(fields)>=5,'MALFORMED_PROC_METADATA')
   if 'w'not in fields[1]:continue
   try:major,minor=(int(x,16)for x in fields[3].split(':'));key=(os.makedev(major,minor),int(fields[4]))
   except (ValueError,OverflowError) as exc:raise WriterCensusUnavailable('MALFORMED_PROC_METADATA') from exc
   need(key not in targets,'observed writable mapping')
 return dict(scope='SAMPLED_SAME_UID_FD_AND_MAPS_NOT_HOSTILE_WRITER_EXCLUSION',processes=count)
def fsync_dir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def write_json(p,value):
 raw=(json.dumps(value,indent=2)+'\n').encode();need(len(raw)<=65536,'journal64KiB');tmp=p.with_suffix('.tmp');need(not tmp.exists()and not tmp.is_symlink(),'journal temp collision')
 with tmp.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fsync_dir(p.parent)
def admitted(result_path,result_sha):
 result_path=P(result_path);need(sha(result_path)==result_sha,'owning build result pin');B=result_path.parent;need(result_path.name=='BUILD_ONLY_RESULT.json','exact result')
 r=doc(result_path,65536);need(r['status']=='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS'and r['scope']=='CHISEL_TEST_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY','actual build terminal scope')
 mpath=B/'frozen_artifact/frozen_artifact.json';v=r['artifact']['manifest'];need(v['path']==str(mpath),'same job manifest');stable(mpath,v);m=doc(mpath,65536);common=m['common'];need(set(common)=={'binary','sv','source_manifest','driver','build_receipt'},'five common roles');need(common['binary']['path']=='dut.bin'and common['sv']['path']=='hardware.sv','exact pack names')
 allpins={}
 for row in [*common.values(),m['tool_manifest']]:
  need(P(row['path']).name==row['path'],'flat artifact');p=mpath.parent/row['path'];stable(p,row);allpins[p]=dict(bytes=row['bytes'],sha256=row['sha256'])
 need({x.name for x in mpath.parent.iterdir()}=={mpath.name,*[x.name for x in allpins]},'exact seven files');need(sum(regular(x).st_size for x in [mpath,*allpins])==r['artifact']['expanded_bytes'],'pack logical sizes');allpins[mpath]=v;allpins[result_path]={'bytes':regular(result_path).st_size,'sha256':result_sha}
 source=doc(mpath.parent/common['source_manifest']['path']);receipt=doc(mpath.parent/common['build_receipt']['path'],65536)
 need(receipt['status']=='BINARY_BUILD_ONLY_NO_NUMERICS'and receipt['source_commit']==m['artifact_identity']['source_commit']and receipt['launch_commit']==m['artifact_identity']['launch_commit'],'build receipt identity')
 for name in ('binary','sv','source_manifest','driver'):need(receipt[name+'_sha256']==common[name]['sha256'],'common receipt identity')
 need(receipt['tool_manifest_sha256']==m['tool_manifest']['sha256'],'tool identity')
 phases=receipt['phases'];need([x['phase']for x in phases]==list(NATIVE[-5:]),'five actual archive/link phases')
 for name in BOOT:
  p=B.parent/('stage_'+name)/'RESULT.json';d=doc(p);complete(d);allpins[p]={'bytes':regular(p).st_size,'sha256':sha(p)}
 for name in NATIVE:
  p=B/name/'RESULT.json';d=doc(p);complete(d);allpins[p]={'bytes':regular(p).st_size,'sha256':sha(p)}
  if name in NATIVE[-5:]:need(canonical(d)==next(x['supervisor_receipt_sha256']for x in phases if x['phase']==name),'actual build phase receipt pin')
  if str(p)in source['verified_gate_pins']:need(sha(p)==source['verified_gate_pins'][str(p)],'source gate receipt pin')
 original_sv=B/'emit_host/compiled-host/HostBlockTopV4.sv';original_elf=B/'frontend/obj/VHostBlockTopV4';dep=source['p0_retained_evidence']['driver_dependency'];physical=source['physical_closure']
 need(dep['binary']==dict(path=str(original_elf),bytes=common['binary']['bytes'],sha256=common['binary']['sha256']),'exact original binary proof');need(phases[-1]['output_sha256']==common['binary']['sha256'],'host linked hash');need(canonical(dep['host_link_receipt'])==phases[-1]['supervisor_receipt_sha256'],'embedded host cleanup pin');complete(dep['host_link_receipt'])
 need(physical['initial_frontend_argv'].count(str(original_sv))==1 and source['verified_gate_pins'][str(original_sv)]==physical['top_raw_sha256']==common['sv']['sha256'],'exact original SV proof')
 pairs=[]
 for name,src in [('sv',original_sv),('binary',original_elf)]:
  target=mpath.parent/common[name]['path'];want={k:common[name][k]for k in ('bytes','sha256')};a=stable(src,want);z=stable(target,want);need(a[6]==z[6]==os.geteuid()and a[7]==z[7],'same effective-uid owner and same group required; never chown');need(a[0]==z[0]and a[1]!=z[1]and a[-1]==z[-1]==1,'same filesystem distinct single-link copies only');pairs.append(dict(role=name,source=src,target=target,want=want,before_source=a,before_target=z))
 need(sum(x['want']['bytes']for x in pairs)<=MAX_SAVING,'reviewed two-copy maximum');return pairs,allpins
@contextlib.contextmanager
def locks(paths):
 handles=[]
 try:
  for path in paths:
   need(not path.is_symlink(),'lock alias');fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);f=os.fdopen(fd,'r+b');handles.append(f);need(stat.S_ISREG(os.fstat(fd).st_mode)and os.fstat(fd).st_nlink==1,'regular single-link lock');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  yield
 finally:
  for f in reversed(handles):f.close()
def run(result_path,result_sha,job_root,expected_build_returncode):
 need(expected_build_returncode==0,'serial original build process must have returned0');job=P(job_root);B=P(result_path).parent;need(B==job/'build/frontend','exact owning build layout')
 need(job.is_absolute()and job.is_dir()and B.is_dir()and not any(x.is_symlink()for x in(B,*B.parents))and '..'not in B.parts,'canonical existing owning directories before locks')
 journal=job/'PACK_DEDUPLICATION.json';need(not journal.exists()and not journal.is_symlink()and not journal.with_suffix('.tmp').exists()and not journal.with_suffix('.tmp').is_symlink(),'single invocation; interrupted journal requires explicit recovery')
 with locks([job/'exclusive.lock',B.parent/'bootstrap.lock',B/'exclusive.lock']):
  need(not journal.exists()and not journal.is_symlink()and not journal.with_suffix('.tmp').exists()and not journal.with_suffix('.tmp').is_symlink(),'single invocation rechecked under all locks; prior transaction requires review')
  pairs,pins=admitted(result_path,result_sha);paths=[p for x in pairs for p in(x['source'],x['target'])]
  rows=[dict(role=x['role'],source=str(x['source'].relative_to(job)),target=str(x['target'].relative_to(job)),**x['want'],source_mode=x['before_source'][3],target_mode=x['before_target'][3],owner_uid=x['before_source'][6],owner_gid=x['before_source'][7],status='PENDING')for x in pairs]
  report=dict(schema='EXACT_TWO_COPY_DEDUPLICATION_V1',status='PREPARED',scope='LIFECYCLE_ONLY_NOT_NUMERICAL_PASS',build_result_sha256=result_sha,pairs=rows,logical_saved_bytes=0,writer_census=None,physical_space_saved='NOT_MEASURED')
  try:report['writer_census']=writers_absent(paths)
  except WriterCensusUnavailable as exc:
   report.update(status='NO_OP_WRITER_CENSUS_UNAVAILABLE',writer_census=unavailable_census(exc),artifact_mutation_started=False)
   for row in rows:row['status']='UNCHANGED_NOT_DEDUPLICATED'
   write_json(journal,report);return report
  if any(x['before_source'][3]!=x['before_target'][3]for x in pairs):
   report['status']='NO_OP_MODE_MISMATCH';write_json(journal,report);return report
  write_json(journal,report);backups=[]
  try:
   for x,row in zip(pairs,rows):
    src,dst=x['source'],x['target'];backup=job/('PACK_DEDUP_BACKUP_'+x['role']);temp=dst.with_name('.dedup_'+dst.name)
    need(not backup.exists()and not backup.is_symlink()and not temp.exists()and not temp.is_symlink(),'transaction path collision');need(identity(src)==x['before_source']and identity(dst)==x['before_target'],'copy drift since admission');writers_absent([src,dst])
    row.update(backup=str(backup.relative_to(job)),temporary=str(temp.relative_to(job)));write_json(journal,report)
    os.link(dst,backup,follow_symlinks=False);backups.append((src,dst,backup,temp,x));fsync_dir(job)
    os.link(src,temp,follow_symlinks=False);x['temporary_inode']=identity(temp)[:2]
    a=identity(src);z=identity(dst);need(a[:4]==x['before_source'][:4]and a[4]==x['before_source'][4]and a[6:8]==x['before_source'][6:8]and a[-1]==2 and z[:4]==x['before_target'][:4]and z[4]==x['before_target'][4]and z[6:8]==x['before_target'][6:8]and z[-1]==2,'copy drift before atomic replace');stable(src,x['want']);stable(dst,x['want']);writers_absent([src,dst]);need(identity(src)==a and identity(dst)==z,'identity changed during writer census');os.replace(temp,dst);fsync_dir(dst.parent);stable(src,x['want']);stable(dst,x['want']);need(os.path.samefile(src,dst),'link replacement identity');row['status']='REPLACED_BACKUP_RETAINED';write_json(journal,report)
   writers_absent(paths)
   for p,w in pins.items():stable(p,w)
   for src,dst,backup,temp,x in backups:
    need(identity(src)[6:8]==identity(dst)[6:8]==x['before_source'][6:8]and identity(src)[3]==identity(dst)[3]==x['before_source'][3]and identity(src)[-1]==identity(dst)[-1]==2,'mode/link count changed');stable(backup,x['want'])
   report['status']='VERIFIED_BACKUPS_RETAINED';write_json(journal,report)
  except BaseException as exc:
   if isinstance(exc,WriterCensusUnavailable):
    report['writer_census']=unavailable_census(exc);report['artifact_mutation_started']=bool(backups)
    if not backups:
     report['status']='NO_OP_WRITER_CENSUS_UNAVAILABLE'
     for row in rows:row['status']='UNCHANGED_NOT_DEDUPLICATED'
     write_json(journal,report);return report
   report['status']='RECOVERY_REQUIRED';write_json(journal,report)
   # Restore copied targets; original source is never removed. If rollback cannot
   # prove identity, leave backup+journal and fail for explicit recovery.
   for src,dst,backup,temp,x in reversed(backups):
    stable(backup,x['want']);stable(dst,x['want']);need(identity(backup)[:2]==x['before_target'][:2]and identity(dst)[:2]in(x['before_source'][:2],x['before_target'][:2]),'rollback refuses foreign inode')
    if os.path.samefile(backup,dst):backup.unlink()
    else:os.replace(backup,dst)
    if temp.exists():
     stable(temp,x['want']);need(identity(temp)[:2]==x.get('temporary_inode')==x['before_source'][:2],'rollback refuses foreign temporary inode');temp.unlink()
    fsync_dir(dst.parent)
   report['status']='ROLLED_BACK';write_json(journal,report);raise
  # Redundant backups are removed only after ALL original references/hash checks.
  for src,dst,backup,temp,x in backups:
   stable(backup,x['want']);need(identity(backup)[:2]==x['before_target'][:2]and identity(backup)[-1]==1,'commit refuses foreign backup inode');backup.unlink();fsync_dir(job)
  report['status']='COMPLETE';report['logical_saved_bytes']=sum(x['want']['bytes']for x in pairs)
  for row in rows:row['status']='BOTH_PATHS_RETAINED_SAME_INODE'
  write_json(journal,report);return report
