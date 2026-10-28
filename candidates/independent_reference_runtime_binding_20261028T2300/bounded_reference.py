#!/usr/bin/env python3
"""Parent-admitted full reference; only child process group is bounded/terminated."""
import argparse,hashlib,json,os,resource,signal,subprocess,time,shutil
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def verify(site,sidecar):
 d=json.loads(sidecar.read_text()); count=0
 for rel,digest in d['native_file_sha256'].items():
  p=site/rel
  if p.is_symlink() or not p.resolve().is_relative_to(site.resolve()) or sha(p)!=digest:raise ValueError('native drift '+rel)
  count+=1
 return count
def main():
 p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--sidecar',type=Path,required=True);p.add_argument('--sidecar-sha',required=True);p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--rss-gib',type=int,default=4);p.add_argument('--wall-seconds',type=int,default=600);p.add_argument('--cpu-seconds',type=int,default=900);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
 if not a.command or a.command[0]!='--':raise ValueError('explicit command separator')
 if sha(a.sidecar)!=a.sidecar_sha:raise ValueError('sidecar identity')
 mem=dict((x.split(':')[0],int(x.split()[1])*1024) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
 if mem['MemAvailable'] < (a.rss_gib+1)*(1<<30):raise ValueError('MemAvailable below RSS cap plus1GiB reserve')
 if shutil.disk_usage(a.run_dir.parent).free < (1<<30):raise ValueError('disk below1GiB reserve')
 pins={str(Path(x).resolve()):sha(x) for x in a.command[1:] if Path(x).is_file()}
 n=verify(a.site,a.sidecar);a.run_dir.mkdir(exist_ok=False);env=os.environ.copy();env.update(HF_HOME=str(a.run_dir.resolve()/'hf-cache'),TRANSFORMERS_CACHE=str(a.run_dir.resolve()/'hf-cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 def limits():
  os.setsid();resource.setrlimit(resource.RLIMIT_CPU,(a.cpu_seconds,a.cpu_seconds+5));resource.setrlimit(resource.RLIMIT_FSIZE,(128<<20,128<<20));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(8<<30,8<<30))
 start=time.monotonic();reason=None;peak=0;child=None;code=None;primary=None;secondary=None;post=None
 def stop():
  if child is not None:
   try:os.killpg(child.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    child.wait()
 def interrupted(signum,_frame):raise RuntimeError('monitor signal '+str(signum))
 old={sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
 try:
  with (a.run_dir/'stdout.log').open('xb') as out,(a.run_dir/'stderr.log').open('xb') as err:
   child=subprocess.Popen(a.command[1:],stdout=out,stderr=err,env=env,preexec_fn=limits)
   while child.poll() is None:
    try:
     status=Path(f'/proc/{child.pid}/status').read_text();rss=int(next(x for x in status.splitlines() if x.startswith('VmRSS:')).split()[1])*1024;peak=max(peak,rss)
    except (FileNotFoundError,StopIteration):rss=0
    total=sum(x.stat().st_size for x in a.run_dir.rglob('*') if x.is_file())
    if rss>a.rss_gib*(1<<30):reason='RSS_LIMIT'
    elif total>160*(1<<20):reason='OUTPUT_LIMIT'
    elif time.monotonic()-start>a.wall_seconds:reason='WALL_LIMIT'
    if reason:stop();break
    time.sleep(.25)
   code=child.wait()
 except BaseException as exc:
  primary=type(exc).__name__+': '+str(exc);reason=reason or 'MONITOR_EXCEPTION'
 finally:
  for sig in old:signal.signal(sig,signal.SIG_IGN)
  stop()
  if child is not None:code=child.returncode
  try:
   post=verify(a.site,a.sidecar)
   if any(sha(path)!=digest for path,digest in pins.items()):raise ValueError('launcher/source identity changed')
  except BaseException as exc:secondary=type(exc).__name__+': '+str(exc)
  for sig,handler in old.items():signal.signal(sig,handler)
 report=dict(status='EXECUTED_REFERENCE_PROCESS_ONLY' if code==0 and not reason and not secondary else 'FAIL_RESOURCE_OR_PROCESS',exit_code=code,reason=reason,primary_error=primary,postflight_error=secondary,source_and_wrapper_pins=pins,mem_available_preflight=mem['MemAvailable'],peak_child_rss_bytes=peak,wall_seconds=time.monotonic()-start,native_pre_count=n,native_post_count=post,command=a.command[1:],limits=dict(address_space_bytes=8<<30,rss_gib=a.rss_gib,cpu_seconds=a.cpu_seconds,wall_seconds=a.wall_seconds,output_bytes=160<<20),scope='RSS sampled for direct Python child; official runner does not spawn worker processes. No hardware validation.')
 (a.run_dir/'process_receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));raise SystemExit(code or (1 if reason or secondary else 0))
if __name__=='__main__':main()
