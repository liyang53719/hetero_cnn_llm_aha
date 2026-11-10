"""Pinned 35B L0/L3 only, two bounded workers, strict HTTP ranges, local bytes.
No full checkpoint digest claim. No automatic retry or network-route override.
"""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,os,time,sys,signal,threading
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--wall-seconds',type=int,default=7200);a=p.parse_args()
sys.path.insert(0,str(a.root.resolve()/'src'))
from heteronpu.weight_header_contract import verify_bundle,load_json,read_record,decode_header,BUNDLE_ROOT,PINS
from heteronpu.pinned_block_payload import fetch_range
key='qwen3_5_35b_a3b';verify_bundle(a.root,key);bundle=load_json(a.root/BUNDLE_ROOT/key/'manifest.json');layers={0:[],3:[]}
for shard in bundle['shards']:
 raw=read_record(a.root,shard['header']);header=decode_header(raw,shard['file_bytes'])
 for layer in layers:
  prefix=f'model.language_model.layers.{layer}.'
  for name,t in sorted(header.items()):
   if name.startswith(prefix):
    lo,hi=t['data_offsets'];layers[layer].append(dict(name=name,local_name=name[len(prefix):],dtype=t['dtype'],shape=t['shape'],start=len(raw)+lo,end=len(raw)+hi-1,bytes=hi-lo,url=shard['url'],file_bytes=shard['file_bytes'],header_sha256=shard['header']['sha256']))
if [sum(t['bytes'] for t in layers[l]) for l in [0,3]]!=[1685402304,1672492032]:raise ValueError('layer inventory drift')
a.output.mkdir(parents=True,exist_ok=False)
start=time.monotonic();stop=threading.Event()
def save(p,j):
 temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(j,indent=2)+'\n');temp.replace(p)
identity={'pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'starttime_ticks':Path('/proc/self/stat').read_text().split()[21]}
save(a.output/'IDENTITY.json',identity);save(a.output/'PLAN.json',{'model':PINS[key],'layers':layers,'wall_seconds':a.wall_seconds,'workers':2,'max_range_bytes':8<<20,'automatic_retries':0})
def deadline(*_):raise TimeoutError('overall acquisition wall budget exceeded')
signal.signal(signal.SIGALRM,deadline);signal.alarm(a.wall_seconds)
def worker(layer):
 directory=a.output/f'L{layer}';directory.mkdir();records=[];count=0
 for t in layers[layer]:
  filename=directory/(t['local_name']+'.bin');h=hashlib.sha256();receipts=[]
  with filename.with_suffix('.partial').open('xb') as f:
   for offset in range(t['start'],t['end']+1,8<<20):
    if stop.is_set() or time.monotonic()-start>a.wall_seconds:raise TimeoutError('peer failed or wall limit')
    end=min(offset+(8<<20)-1,t['end']);raw,receipt=fetch_range(t['url'],offset,end,t['file_bytes']);f.write(raw);h.update(raw);receipts.append(receipt);count+=len(raw)
    with (directory/'RANGE_RECEIPTS.jsonl').open('a') as journal:
     journal.write(json.dumps({'tensor':t['local_name'],**receipt})+'\n');journal.flush();os.fsync(journal.fileno())
    save(directory/'PROGRESS.json',{'status':'RUNNING_NOT_PASS','bytes':count,'tensor':t['local_name'],'last_range':receipt,'seconds':time.monotonic()-start})
  filename.with_suffix('.partial').replace(filename)
  records.append({**t,'sha256':h.hexdigest(),'http_ranges':receipts})
  save(directory/'PARTIAL_MANIFEST.json',{'status':'INCOMPLETE','tensors':records});print(f'L{layer} tensor={t["local_name"]} bytes={count}',flush=True)
 save(directory/'MANIFEST.json',{'status':'ACQUIRED_PINNED_REVISION_LAYER_BYTES_ONLY','model':PINS[key],'layer':layer,'payload_bytes':count,'tensors':records,'sha256_kind':'observed_payload_not_independent_content_pin','whole_checkpoint_hash_verified':False,'hardware_executed':False})
 return {'layer':layer,'bytes':count,'tensors':len(records)}
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
  futures=[ex.submit(worker,l) for l in [0,3]]
  for future in futures:
   future.add_done_callback(lambda f: stop.set() if f.exception() is not None else None)
  result=[f.result() for f in concurrent.futures.as_completed(futures)]
 save(a.output/'TERMINAL.json',{'status':'ACQUIRED_LAYER_BYTES_ONLY','layers':result,'seconds':time.monotonic()-start,'identity':identity})
except BaseException as e:
 stop.set();save(a.output/'TERMINAL.json',{'status':'FAIL_OR_INCOMPLETE','error':repr(e),'seconds':time.monotonic()-start,'identity':identity});raise
finally:signal.alarm(0)
