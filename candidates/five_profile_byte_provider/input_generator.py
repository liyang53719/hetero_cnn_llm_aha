"""Standalone experimental M128x2048 BF16 input, not embeddings/upstream hidden states.
No weights, floats, Torch, randomness library or platform endianness involved.
"""
from pathlib import Path
import argparse,hashlib,json
SEED=0x35b00380
def build():
 s=SEED;b=bytearray()
 for i in range(128*2048):
  s^=(s<<13)&0xffffffff;s^=s>>17;s^=(s<<5)&0xffffffff;s&=0xffffffff
  v=0 if i%257==0 else (((s>>31)&1)<<15)|((119+((s>>8)%5))<<7)|(s&127)
  b.extend(v.to_bytes(2,'little'))
 return bytes(b)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=build()
 with a.output.open('xb') as f:f.write(b)
 print(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'seed':SEED,'shape':[1,128,2048],'dtype':'BF16_LE','provenance':'standalone experimental input; not checkpoint-derived or earlier-block hidden state'}))
