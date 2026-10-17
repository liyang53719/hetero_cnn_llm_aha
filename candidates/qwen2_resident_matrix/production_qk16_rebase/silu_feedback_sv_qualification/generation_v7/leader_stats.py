"""Bounded direct-leader /proc sampling; not aggregate tree or hard RSS bound."""
import os
from pathlib import Path

def stat_fields(text,pid):
 end=text.rfind(')');head=text[:text.find('(')].strip();v=text[end+1:].split()
 if head!=str(pid) or end<0 or len(v)<22:raise ValueError('proc stat format')
 result={'pid':pid,'pgrp':int(v[2]),'session':int(v[3]),'start_ticks':int(v[19]),'user_ticks':int(v[11]),'system_ticks':int(v[12])}
 if result['pgrp']!=pid or result['session']!=pid:raise ValueError('not direct session leader')
 return result

def read_bounded(path,limit):
 with path.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('proc read cap')
 return b.decode('ascii')

def sample(pid,identity=None,root=Path('/proc')):
 base=root/str(pid);a=stat_fields(read_bounded(base/'stat',8192),pid)
 status=read_bounded(base/'status',32768);b=stat_fields(read_bounded(base/'stat',8192),pid)
 key={k:a[k] for k in ['pid','pgrp','session','start_ticks']}
 if any(b[k]!=v for k,v in key.items()) or (identity is not None and key!=identity):raise ValueError('leader identity drift')
 values={}
 for l in status.splitlines():
  if l.startswith(('VmRSS:','VmHWM:')):
   k,value,unit=l.split()
   if unit!='kB' or int(value)<0:raise ValueError('proc memory format')
   values[k[:-1]+'_bytes']=int(value)*1024
 # Zombie may lack memory fields; preserve missing explicitly, never report zero peak.
 return key,dict(user_ticks=b['user_ticks'],system_ticks=b['system_ticks'],**values)

def observe(stats,pid,elapsed):
 key,x=sample(pid,stats.get('_identity'));stats['_identity']=key
 stats['samples']+=1;stats['last_sample_elapsed_seconds']=elapsed
 stats['last_user_seconds']=x['user_ticks']/stats['ticks_per_second'];stats['last_system_seconds']=x['system_ticks']/stats['ticks_per_second']
 for k in ('VmRSS_bytes','VmHWM_bytes'):
  if k in x:stats['max_observed_'+k]=max(stats.get('max_observed_'+k,0),x[k])
 if stats['samples']>2048:raise ValueError('bounded sample count')

def initial():return {'scope':'DIRECT_LEADER_SAMPLED_NOT_TREE_PEAK','ticks_per_second':os.sysconf('SC_CLK_TCK'),'samples':0}
