from pathlib import Path
import argparse,subprocess,json,time,resource,os,signal,hashlib
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--wall',type=int,default=900);p.add_argument('--memory-gib',type=int,default=5);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();r=Path(__file__).resolve().parent
cmd=a.command[1:] if a.command[0]=='--' else a.command
(r/(a.stage+'_command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(a.memory_gib<<30,a.memory_gib<<30));resource.setrlimit(resource.RLIMIT_CPU,(a.wall,a.wall+5))
t=time.monotonic()
with (r/(a.stage+'.log')).open('w') as log:
 proc=subprocess.Popen(cmd,cwd=r,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
 identity={'pid':proc.pid,'pgid':proc.pid,'starttime_ticks':Path(f'/proc/{proc.pid}/stat').read_text().split()[21],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
 (r/(a.stage+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n')
 try:code=proc.wait(timeout=a.wall);timeout=False
 except subprocess.TimeoutExpired:
  os.killpg(proc.pid,signal.SIGKILL);code=proc.wait();timeout=True
result={'stage':a.stage,'exit':code,'timeout':timeout,'seconds':time.monotonic()-t,'identity':identity,'scope':'interface generation/compilation only; no numerical simulation'}
(r/(a.stage+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(code!=0)
