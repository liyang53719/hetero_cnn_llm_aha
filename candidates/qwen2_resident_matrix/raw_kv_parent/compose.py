"""Compose only three exact existing parent sources; no compile or RTL run."""
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/'
TARGETS=[PREFIX+'transposed_owner/'+n for n in ('TransposedDenseBanks.scala','DenseOwnerIO.scala','TransposedDenseOwner.scala')]
PATCHES=[PREFIX+p for p in ('transposed_seed/owner_prefix.patch','transposed_down/owner_down.patch','ffn_tiles/tile_ports.patch',
    'ffn_window/window.patch','ffn_drain/drain.patch','official_bf16/chisel_policy.patch','dense_block_reduce/k_window.patch','dense_block_reduce/dense_drain.patch')]

OMITTED=[PREFIX+p for p in ("transposed_host/host_workspace.patch","ffn_group/group.patch","dense_block_reduce/vector_add.patch")]

def sha(data):return hashlib.sha256(data).hexdigest()
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)

def apply(out,path):
    source=(ROOT/path).read_text()
    for target in TARGETS:
        head='--- a/'+target+'\n'
        if head in source:
            need(source.count(head)==1,'duplicate patch target')
            section=head+source.split(head)[1].split('\n--- a/')[0]+'\n'
            subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=section,text=True,cwd=out,check=True,capture_output=True,timeout=10)

def raw_blocks(source):
    blocks=[];position=0
    while True:
        start=source.find('if(enableRawKv){',position)
        if start<0:return blocks
        depth=0
        for i in range(start,len(source)):
            if source[i]=='{':depth+=1
            if source[i]=='}':
                depth-=1
                if depth==0:
                    blocks.append(source[start:i+1]);position=i+1;break
        else:raise ValueError('unterminated raw control block')

def check_raw_reference(bank):
    with tempfile.TemporaryDirectory(prefix='raw-kv-reference-') as d:
        out=Path(d);target=out/TARGETS[0]
        target.parent.mkdir(parents=True);target.write_bytes((ROOT/TARGETS[0]).read_bytes())
        for name in ('transposed_down/owner_down.patch','ffn_tiles/tile_ports.patch','raw_kv/raw_kv_port.patch'):
            source=(ROOT/PREFIX/name).read_text();head='--- a/'+TARGETS[0]+'\n'
            need(source.count(head)==1,'reference target scope')
            section=head+source.split(head)[1].split('\n--- a/')[0]+'\n'
            subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=section,text=True,cwd=out,
                           check=True,capture_output=True,timeout=10)
        old=target.read_text()
        need(raw_blocks(old)==raw_blocks(bank),'tested raw control block drift')
        need(old[old.index('class RawKvKey'):].strip()==
             bank[bank.index('class RawKvKey'):bank.index('/** Parent-facing loan:')].strip(),
             'tested raw ABI drift')

def compose(out, *, integrated=True, verify=True):
    out=Path(out);need(not out.exists(),'fresh source output required');out.mkdir(parents=True)
    pins=json.loads((HERE/'source_pins.json').read_text()) if verify else None
    if verify:
        for p,h in pins['inputs'].items():need(blob((ROOT/p).read_bytes())==h,'original input drift: '+p)
    for p in TARGETS:
        dest=out/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/p).read_bytes())
    for patch in OMITTED:
        text=(ROOT/patch).read_text()
        need(all("+++ b/"+t+"\n" not in text for t in TARGETS), "omitted patch now changes parent: "+patch)
    for patch in PATCHES:apply(out,patch)
    if verify:
        for p,h in pins['parent_sha256'].items():need(sha((out/p).read_bytes())==h,'final parent preimage drift: '+p)
    if integrated:
        integration=(HERE/'integration.patch').read_text()
        touched=re.findall(r'^\+\+\+ b/(.+)$',integration,re.M)
        need(sorted(touched)==sorted(TARGETS),'integration target scope drift')
        apply(out,PREFIX+'raw_kv_parent/integration.patch')
        if verify:
            for p,h in pins['integrated_sha256'].items():need(sha((out/p).read_bytes())==h,'integrated source drift: '+p)
        bank_source=(out/TARGETS[0]).read_text()
        check_raw_reference(bank_source)
        bank=bank_source.split('class TransposedDownDenseBanks(')[1]
        need(bank.count('SyncReadMem(')==2,'no additional SRAM declarations')
        need(bank.count('aBanks(bank).read(')==1 and bank.count('aBanks(bank).write(')==1,'one existing A read/write site')
        owner=(out/TARGETS[2]).read_text().split('class TransposedDenseDownOwner(')[1]
        need('enableRawKv:Boolean=false' in owner,'default-off owner loan')
        need('p.parentDrained:=' not in owner,'no parent-controllable drain attestation')
        need('banks.io.rawKv.get.parentDrained:=rawLocalDrained' in owner,'actual owner drain derivation')
    return {p:sha((out/p).read_bytes()) for p in TARGETS}

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='raw-kv-parent-') as d:
        compose(Path(d)/'source')
    print('PASS: zero-fuzz source composition only; parent Scala/RTL NOT RUN')
