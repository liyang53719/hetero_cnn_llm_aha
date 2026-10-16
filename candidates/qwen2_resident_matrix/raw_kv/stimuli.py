"""Deterministic synthetic cycle vectors, validated by the Python bank model.

Generated TSV stays local to the test run. It is not an uploaded artifact.
"""
import hashlib
from pathlib import Path
from candidates.qwen2_resident_matrix.transposed_down.model import Banks
from candidates.qwen2_resident_matrix.raw_kv.model import RawKvPort, Request, Key, Obligations

COLUMNS='acquire release req owner tag line write data ack ack_owner ack_tag ack_line ack_write parent_drained dense tile clear abort soft_reset acquired released accepted acked response response_owner response_tag response_line response_write response_data leased drained reset_required dense_ready'.split()


def generate(path):
    p=RawKvPort(Banks(1376),enabled=True);rows=[]
    def step(**kw):
        before=(p.owner is not None,p.drained,p.poison or kw.get('abort',False) or kw.get('soft_reset',False))
        out=p.tick(**kw);q=kw.get('request');k=q.key if q else Key(0,0,0,False);a=kw.get('ack') or Key(0,0,0,False)
        r=out['response'];rk=r.key if r else Key(0,0,0,False)
        row=[kw.get('acquire') or 0,kw.get('release') or 0,q is not None,k.owner,k.tag,k.line,k.write,q.data if q else 0,
             kw.get('ack') is not None,a.owner,a.tag,a.line,a.write,kw.get('obligations',Obligations()).drained,
             kw.get('dense',False),kw.get('tile',False),kw.get('clear',False),kw.get('abort',False),kw.get('soft_reset',False),
             out['acquired'],out['released'],out['accepted'],out['acked'],r is not None,rk.owner,rk.tag,rk.line,rk.write,r.data if r else 0,
             *before,out['dense_allowed']]
        if len(row)!=len(COLUMNS):raise ValueError('vector schema')
        rows.append('\t'.join(format(int(v),'x') for v in row))
        return out
    for field in Obligations.__dataclass_fields__:step(acquire=7,obligations=Obligations(**{field:True}))
    step(acquire=7,dense=True);step(acquire=7,clear=True);step(acquire=7)
    raw=int.from_bytes(bytes.fromhex('0000807f000080ff0100c07f00000080')*4,'little')
    for write in (True,False):
        for line in range(4096):
            key=Key(7,1+line+4096*int(not write),line,write)
            out=step(request=Request(key,raw^line if write else 0))
            if not out['accepted']:raise ValueError('capacity admission')
            step(ack=key) # synchronous capture; early ACK cannot retire
            if line in (0,7,8,4095):
                for _ in range(3):step(request=Request(key),ack=Key(8,key.tag,line,write),release=7,dense=True,tile=True,clear=True)
            if not write and p.response.data!=raw^line:raise ValueError('raw roundtrip')
            step(ack=key)
    # Re-read word zero after the last hostile clear during read-response stalls.
    key=Key(7,9000,0,False);step(request=Request(key));step()
    if p.response.data!=raw:raise ValueError('hostile clear changed leased SRAM')
    step(ack=key);step(release=7,dense=True,tile=True,clear=True);step(acquire=7)
    for key in (Key(8,1,0,False),Key(7,0,0,False),Key(7,1,4096,False)):
        step(request=Request(key))
    # Accepted read is retained across abort and protocol reset; foreign ACKs cannot retire.
    key=Key(7,99,4095,False);step(request=Request(key));step(abort=True,soft_reset=True,ack=key,release=7)
    for _ in range(3):step(ack=Key(7,98,4095,False),release=7)
    step(ack=key);step(release=7,dense=True,tile=True,clear=True);step(acquire=8);step(soft_reset=True)
    step(acquire=8,release=7);step(acquire=8)
    key=Key(8,1,0,True);step(request=Request(key,123));step(abort=True);step(ack=key);step(release=8);step(soft_reset=True)
    step(acquire=9)
    key=Key(9,1,8,False);step(request=Request(key));step();step(abort=True,ack=key);step(release=9);step(soft_reset=True)
    path=Path(path);path.write_text('\t'.join(COLUMNS)+'\n'+'\n'.join(rows)+'\n')
    return {'cycles':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'capacity_lines':4096,'synthetic_only':True}
