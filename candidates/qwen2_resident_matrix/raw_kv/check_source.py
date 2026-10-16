"""Short source-composition gate; not Scala compilation/elaboration or RTL proof."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
TARGET='candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseBanks.scala'

def require(ok,message):
    if not ok:raise ValueError(message)

def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def check():
    pins=json.loads((HERE/'source_pins.json').read_text())
    for name,sha in pins['git_blobs'].items():
        require(blob((ROOT/name).read_bytes())==sha,'frozen source drift: '+name)
    with tempfile.TemporaryDirectory(prefix='raw-kv-compose-') as tmp:
        d=Path(tmp);target=d/TARGET;target.parent.mkdir(parents=True);target.write_bytes((ROOT/TARGET).read_bytes())
        for name in ['candidates/qwen2_resident_matrix/transposed_down/owner_down.patch',
                     'candidates/qwen2_resident_matrix/ffn_tiles/tile_ports.patch',
                     'candidates/qwen2_resident_matrix/raw_kv/raw_kv_port.patch']:
            patch=(ROOT/name).read_text();head='--- a/'+TARGET+'\n'
            require(patch.count(head)==1,'one bank source section required')
            section=head+patch.split(head)[1].split('\n--- a/')[0]+'\n'
            subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=section,text=True,cwd=d,check=True,capture_output=True)
        s=target.read_text();down=s.split('class TransposedDownDenseBanks(')[1].split('/** Internal typed tile ABI.')[0]
        require(down.count('SyncReadMem(')==2,'only existing A and B arrays')
        require(down.count('aBanks(bank).read(')==1 and down.count('aBanks(bank).write(')==1,'single A read/write call')
        require(down.count('bBanks(bank).read(')==1 and down.count('bBanks(bank).write(')==1,'single B read/write call')
        require('enableRawKv:Boolean=false' in down,'default-off port')
        require('Seq.fill(16)(SyncReadMem(1376,UInt(256.W)))' in down,'existing A capacity')
        require('p.ack.bits.asUInt===key.asUInt' in down,'matching ACK')
        require('p.resetRequired:=poison || stop' in down,'same-edge abort invalidates publication')
        require(hashlib.sha256(target.read_bytes()).hexdigest()==pins['composed_sha256'],'composed source drift')
    return {'source_composition':'PASS','scala_compile':'NOT_RUN','rtl_simulation':'NOT_RUN'}

if __name__=='__main__':print(json.dumps(check(),sort_keys=True))
