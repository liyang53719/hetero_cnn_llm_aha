import copy, hashlib, json, pathlib, sys, tempfile
import os
BASE=pathlib.Path(os.environ['FIXTURE_WORK'])
sys.path.insert(0,str(BASE/'provider_candidate'))
from memory_provider import MemoryProvider,MemoryAccessError,BytesReader,metadata_from_directory
checks=[]
def check_reject(label,doc,readers):
 try:MemoryProvider(doc,readers)
 except (MemoryAccessError,ValueError,TypeError):checks.append(label)
 else:raise AssertionError('accepted '+label)
t={'address':4096,'dims':[4,4],'words':16,'readonly':True,'storage_dtype':5,'storage_bytes':32}
base={'weight_storage':'bf16','tensors':{'wq':t}}
reader={'wq':BytesReader(bytes(range(32)))}
p=MemoryProvider(base,reader);assert p.read(4096,32)==bytes(range(32));checks.append('native direct exact32')
for label,change in [('RW',{'readonly':False}),('dtype7',{'storage_dtype':7}),('larger',{'storage_bytes':64}),('smaller',{'storage_bytes':16}),('floatwords',{'words':16.0}),('shape',{'dims':[4,5]}),('rank3',{'dims':[2,2,4]}),('bytesconflict',{'bytes':64}),('readerdisagrees',{'storage_bytes':32})]:
 d=copy.deepcopy(base);d['tensors']['wq'].update(change);r={} if label=='RW' else {'wq':BytesReader(bytes(64 if label=='readerdisagrees' else 32))};check_reject(label,d,r)
d=copy.deepcopy(base);d['launch']={'profileId':4};check_reject('runtimeprofileoverride',d,reader)
d=copy.deepcopy(base);d['tensors']['other']=d['tensors'].pop('wq');check_reject('unexpectedweight',d,{'other':reader['wq']})
for action in [lambda:p.read(4128,1),lambda:p.write(4096,b'a'),lambda:p.write(4096,b'a',b'\x00')]:
 try:action()
 except MemoryAccessError:checks.append('range/RO')
 else:raise AssertionError('guard not enforced')
d=copy.deepcopy(base);d['tensors']['wk']=copy.deepcopy(t);check_reject('ROalias',d,{'wq':reader['wq'],'wk':reader['wq']})
meta=metadata_from_directory(BASE/'native_candidate');assert len(meta)==2;checks.append('native metadata hashes')
with tempfile.TemporaryDirectory() as tmp:
 q=pathlib.Path(tmp)
 for f in ('manifest.json','host_commands.bin','host_descriptors.bin'):(q/f).write_bytes((BASE/'native_candidate'/f).read_bytes())
 bad=bytearray((q/'host_descriptors.bin').read_bytes());bad[0]^=1;(q/'host_descriptors.bin').write_bytes(bad)
 try:metadata_from_directory(q)
 except MemoryAccessError:checks.append('metadata tamper rejected')
 else:raise AssertionError('accepted descriptor tamper')
out={'scope':'SYNTHETIC_TRANSPORT_AND_METADATA_ONLY_NOT_WEIGHT_OR_DUT','checks':checks,'count':len(checks),'candidate_sources':{str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (BASE/'provider_candidate/memory_provider.py',BASE/'provider_candidate/qwen2/payloads.py')}}
(BASE/'INDEPENDENT_PROVIDER_RETEST.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
