"""Profile0 input-only transport. No arithmetic, outputs, or expert IDs.
Seven transposed BF16 weight streams remain native BF16. Nonweights stay FP32.
"""
from pathlib import Path
import hashlib,json,mmap,os
from parent_inputs import path_for_sha
SPEC_SHA='34dea02dab7dd10d34ae0e3969202bbb91f10d1f7966f308eb01e4d4e803ee6e'
HERE=Path(__file__).resolve().parent
# Parent paths are resolved solely through the operator-local SHA256 map.
def sha_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while b:=f.read(1<<20): h.update(b)
    return h.hexdigest()
def require(ok,msg):
    if not ok: raise ValueError(msg)
class Reader:
    def __init__(self,path,size,expand=False):
        self.path=Path(path);self.file=open(path,'rb');self.mm=mmap.mmap(self.file.fileno(),0,access=mmap.ACCESS_READ)
        self.expand=expand;self.size=size;self.identity=os.fstat(self.file.fileno())
    def read(self,offset,length):
        require(type(offset)is int and type(length)is int and offset>=0 and length>=0 and offset+length<=self.size,'read outside input tensor')
        st=os.fstat(self.file.fileno())
        require((st.st_size,st.st_mtime_ns,st.st_ino)==(self.identity.st_size,self.identity.st_mtime_ns,self.identity.st_ino),'source identity changed')
        if not length:return b''
        if not self.expand:return self.mm[offset:offset+length]
        first=offset//4;last=(offset+length+3)//4;raw=self.mm[first*2:last*2]
        out=bytearray(len(raw)*2);out[2::4]=raw[0::2];out[3::4]=raw[1::2]
        start=offset-first*4
        return bytes(out[start:start+length])
    def close(self):self.mm.close();self.file.close()
def build_readers(manifest_path):
    specpath=path_for_sha(SPEC_SHA);require(sha_file(specpath)==SPEC_SHA,'frozen source spec changed')
    spec=json.loads(specpath.read_text());mp=Path(manifest_path)
    require(spec['metadata_sha256']=='a3e04946be19d274181ed5839b3047e19a4b450f5421ab3d748774e0312e9522','legacy source metadata binding changed')
    require(sha_file(mp)=='c5fcd45a4cee53b084a0915753186b06540342bb0620a783f528fefb83b9b561','native candidate metadata changed')
    for pk,hk in [('provider_manifest_path','provider_manifest_sha256'),('provenance_path','provenance_sha256')]:require(sha_file(path_for_sha(spec[hk]))==spec[hk],'provenance drift')
    manifest=json.loads(mp.read_text());readonly={k:v for k,v in manifest['tensors'].items() if v['readonly']}
    require(set(readonly)=={p['name'] for p in spec['providers']},'readonly tensor set drift')
    readers={};report={'profile':0,'metadata_sha256':sha_file(mp),'source_metadata_sha256':spec['metadata_sha256'],'source_manifest_sha256':spec['provider_manifest_sha256'],'sources':{},'comparison_inputs':False,'intermediate_preloads':0,'status':'INPUT_BYTES_ONLY_NOT_DUT'}
    try:
        for p in spec['providers']:
            name=p['name'];q=path_for_sha(p['sha256'],p['bytes']);t=readonly[name];native=name in spec['matrix_names'];logical=t['words']*(2 if native else 4)
            require(set(spec['matrix_names'])=={'wq','wk','wv','wo','wg','wu','wd'},'exact seven native weights')
            require(not native or (t.get('storage_dtype')==5 and t.get('storage_bytes')==logical),'native metadata dtype/size')
            require(q.is_file() and q.stat().st_size==p['bytes'],'source size '+name)
            actual=sha_file(q);require(actual==p['sha256'],'source hash '+name)
            require(logical==p['bytes'],'logical/source shape '+name)
            readers[name]=Reader(q,logical,False)
            report['sources'][name]={'path':str(q),'source_bytes':p['bytes'],'source_sha256':actual,'logical_bytes':logical,'mapping':'identity native BF16LE[K,N]' if native else 'identity FP32LE','shape':t['dims']}
        return readers,report
    except BaseException:
        for r in readers.values():r.close()
        raise
