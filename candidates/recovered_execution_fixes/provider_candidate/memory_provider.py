"""Byte transport only. No model, arithmetic, reference output, or expert-ID source.
Read-only tensor readers supply actual inputs/weights. Sparse RW bytes are readable
only after DUT writes; explicit cold-state readers are the sole zero initializers.
This synchronous byte adapter does not model timing, AXI IDs, or performance.
"""
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

class MemoryAccessError(ValueError): pass

@dataclass(frozen=True)
class BytesReader:
    data: bytes
    @property
    def size(self): return len(self.data)
    def read(self, offset, length):
        if type(offset) is not int or type(length) is not int or offset < 0 or length < 0 or offset + length > self.size:
            raise MemoryAccessError('reader range')
        return self.data[offset:offset+length]

@dataclass(frozen=True)
class ZeroReader:
    size: int
    def read(self, offset, length):
        if type(offset) is not int or type(length) is not int or offset < 0 or length < 0 or offset+length > self.size:
            raise MemoryAccessError('zero range')
        return bytes(length)

class MemoryProvider:
    PAGE = 4096
    def __init__(self, manifest, readers, metadata=(), extra_rw=(), rw_alias_groups=()):
        self.manifest = manifest
        alias_groups=[frozenset(g) for g in rw_alias_groups]
        if any(len(g)<2 for g in alias_groups): raise MemoryAccessError('invalid alias group')
        self.regions=[]; self.pages={}; self.valid={}
        self.bytes_read=0; self.bytes_written=0
        self.ro_hashes={}
        names=set()
        for name,t in manifest['tensors'].items():
            if t.get('virtual'): continue
            size=t.get('bytes',t.get('words',0)*4)
            if 'storage_bytes' in t:
                dims=t.get('dims',[])
                if not ('launch' not in manifest and manifest.get('weight_storage')=='bf16' and type(t.get('words')) is int and name in {'wq','wk','wv','wo','wg','wu','wd'} and t.get('readonly') is True and t.get('storage_dtype')==5 and len(dims)==2 and all(type(d) is int and d>0 for d in dims) and t.get('words')==dims[0]*dims[1] and t['storage_bytes']==2*t['words'] and 'bytes' not in t):
                    raise MemoryAccessError('unsupported storage override '+name)
                size=t['storage_bytes']
            address=t['address']; ro=t['readonly']
            if type(size) is not int or size <= 0 or type(address) is not int or address < 0 or address+size>2**64:
                raise MemoryAccessError('invalid tensor range '+name)
            if ro:
                if name not in readers: raise MemoryAccessError('unbound readonly tensor '+name)
                reader=readers[name]
                if reader.size != size: raise MemoryAccessError('reader size '+name)
                names.add(name)
            else: reader=None
            self.regions.append((address,address+size,name,ro,reader))
        if names != set(readers): raise MemoryAccessError('unexpected readonly reader')
        for name,address,data in metadata:
            if not isinstance(data,bytes) or not data or type(address) is not int or address<0 or address+len(data)>2**64: raise MemoryAccessError('metadata range/bytes')
            self.regions.append((address,address+len(data),name,True,BytesReader(data)))
        for name,address,size in extra_rw:
            if type(size) is not int or type(address) is not int or size<=0 or address<0 or address+size>2**64: raise MemoryAccessError('extra rw range')
            self.regions.append((address,address+size,name,False,None))
        self.regions.sort()
        # Address aliases among writable tensor views refer to the same physical
        # bytes (e.g. Qwen2 kv and its K/V subviews). Never merge an RO overlap.
        merged=[]; self.rw_aliases=[]
        for r in self.regions:
            if merged and merged[-1][1] > r[0]:
                q=merged[-1]
                names=frozenset(q[2].split('|')+[r[2]])
                if q[3] or r[3] or not any(names <= g for g in alias_groups): raise MemoryAccessError('undeclared/incompatible overlap')
                self.rw_aliases.append({'left':q[2],'right':r[2],'start':r[0],'end':min(q[1],r[1])})
                merged[-1]=(q[0],max(q[1],r[1]),q[2]+'|'+r[2],False,None)
            else: merged.append(r)
        self.regions=merged
        self.starts=[x[0] for x in self.regions]
    def _segments(self,address,length):
        if type(address) is not int or type(length) is not int or address<0 or address>=2**64 or length<0 or address+length>2**64:
            raise MemoryAccessError('invalid access')
        stop=address+length
        while address<stop:
            i=bisect_right(self.starts,address)-1
            if i<0 or address>=self.regions[i][1]: raise MemoryAccessError('unmapped address '+hex(address))
            r=self.regions[i]; end=min(stop,r[1]); yield r,address,end-address; address=end
    def read(self,address,length):
        # Validate entire request first; no partial success/counter increment.
        pieces=list(self._segments(address,length)); out=[]
        for r,a,n in pieces:
            if r[3]:
                b=r[4].read(a-r[0],n)
                if not isinstance(b,bytes) or len(b)!=n: raise MemoryAccessError('reader short result')
                out.append(b)
            else:
                b=bytearray()
                for pos in range(a,a+n):
                    page,off=divmod(pos,self.PAGE)
                    if page not in self.valid or not self.valid[page][off]: raise MemoryAccessError('read before DUT write '+hex(pos))
                    b.append(self.pages[page][off])
                out.append(bytes(b))
        self.bytes_read+=length
        return b''.join(out)
    def write(self,address,data,strobes=None):
        if not isinstance(data,bytes): raise MemoryAccessError('data must be bytes')
        if strobes is None: strobes=bytes([1])*len(data)
        if not isinstance(strobes,bytes) or len(strobes)!=len(data) or any(x not in (0,1) for x in strobes):
            raise MemoryAccessError('invalid strobe')
        pieces=list(self._segments(address,len(data)))
        # Any attempted transaction into RO fails, even if all strobes are clear.
        if any(r[3] for r,_,_ in pieces): raise MemoryAccessError('write to readonly')
        for i,b in enumerate(data):
            if not strobes[i]: continue
            page,off=divmod(address+i,self.PAGE)
            if page not in self.pages:
                self.pages[page]=bytearray(self.PAGE); self.valid[page]=bytearray(self.PAGE)
            self.pages[page][off]=b; self.valid[page][off]=1; self.bytes_written+=1
    def stream_ro_hashes(self,chunk=1<<20):
        if type(chunk) is not int or chunk<=0: raise MemoryAccessError('chunk')
        result={}
        for start,end,name,ro,reader in self.regions:
            if not ro: continue
            h=hashlib.sha256()
            for offset in range(0,end-start,chunk):
                n=min(chunk,end-start-offset); b=reader.read(offset,n)
                if not isinstance(b,bytes) or len(b)!=n: raise MemoryAccessError('short hash read')
                h.update(b)
            result[name]={'address':start,'bytes':end-start,'sha256':h.hexdigest()}
        return result

def metadata_from_directory(directory):
    p=Path(directory); m=json.loads((p/'manifest.json').read_text())
    if 'launch' in m:
        c='commands.bin';d='descriptors.bin';l=m['launch']
    else: c='host_commands.bin';d='host_descriptors.bin';l=m
    result=[]
    for name,file,key,startkey,endkey,countkey in [('command_bytes',c,'commands','commandBase','commandLimit','commands'),('descriptor_bytes',d,'descriptors','descriptorBase','descriptorLimit','descriptors')]:
        data=(p/file).read_bytes()
        hashes=m['sha256'] if 'launch' in m else m['table_sha256']
        expected=hashes.get(file,hashes.get(key))
        if not expected or hashlib.sha256(data).hexdigest()!=expected:raise MemoryAccessError('metadata binary hash drift '+file)
        if not (l[countkey]*16<=len(data)<=l[endkey]-l[startkey]):raise MemoryAccessError('metadata binary size drift '+file)
        # Declared metadata allocation tail is deterministic zero bus padding.
        data=data+bytes(l[endkey]-l[startkey]-len(data))
        result.append((name,l[startkey],data))
    return result
