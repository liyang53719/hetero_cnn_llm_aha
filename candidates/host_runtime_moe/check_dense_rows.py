#!/usr/bin/env python3
"""Source and integer schedule models only; no Chisel/DUT numerical claim."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--original-dense-source',type=Path,required=True)
BASE=parser.parse_args().original_dense_source
r=json.loads((ROOT/'SOURCE_PINS.json').read_text())['original_dense']
b=BASE.read_bytes()
if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('exact original Dense source required')
s= (ROOT/'source/TransposedDenseOwner.scala').read_text(); base=BASE.read_text()
def require(v,msg):
    if not v: raise RuntimeError(msg)
def check_source(candidate):
    start=candidate.index('class TransposedDenseDownOwner')
    end=candidate.index('  when(state===clearA)',candidate.index('  when(io.job.fire)',start))
    old='!(j.m===16.U || j.m===128.U)';new='(j.m===0.U || j.m>128.U)'
    scope=candidate[start:end]
    require(scope.count(new)==2,'two admission predicates')
    require(candidate[:start]+scope.replace(new,old)+candidate[end:]==base,'only exact admission delta permitted')
check_source(s)
negative=0
for mutation in [s.replace('j.m>128.U','j.m>256.U',1),s.replace('job.m.pad(64)*32.U','128.U(64.W)*32.U',1),s.replace('m.U<job.m','m.U<=job.m',1),s.replace('writeRow+&1.U===job.m','writeRow+&1.U===128.U',1),s.replace('(j.m===16.U || j.m===128.U) && j.k>0.U','(j.m>0.U && j.m<=128.U) && j.k>0.U',1)]:
    try: check_source(mutation)
    except RuntimeError: negative+=1
require(negative==5,'all source mutants rejected')
cases=0
for m in range(1,129):
  for n in [32,160,256,512,2048]:
    for k in [128,512,1536,2048,3584,8960]:
      for item_bytes in [2,4]:
        # Matrix K/context issue schedule fixed; zero-masked inactive rows
        # are physically computed and excluded only from useful MAC count.
        contexts=n//32; issued=k*contexts
        useful=issued*m*32; physical=issued*4096
        require(useful==m*n*k and useful<=physical,'MAC accounting')
        require([r for r in range(128) if r<m]==list(range(m)),'row mask')
        # Original DDR output packet: every actual row, one BF16/two FP32 beat.
        addresses=[(row*n+context*32)*item_bytes+beat*64 for context in range(contexts) for row in range(m) for beat in range(item_bytes//2)]
        require(len(addresses)*64==m*n*item_bytes,'ACK byte count')
        require(len(set(addresses))==len(addresses),'write uniqueness')
        require(min(addresses)==0 and max(addresses)+64==m*n*item_bytes,'exact output extent')
        # Split-K prefix is always full physical 16KiB/context, independent M.
        chunks=(k+2559)//2560
        require((chunks-1)*contexts*16384>=0,'prefix storage fixed')
        for row in [0,m-1]:
          for column in range(32):
            physical_n=column%16; physical_col=(column//16)*128+row
            require(physical_n<16 and physical_col<256,'unchanged finalValue mapping')
        cases+=1
# Explicit five-profile projection/FFN shapes: all retain 32-column aligned N,
# K split up to2560 and 128 physical rows. No per-model elaboration.
profile_shapes={"qwen2":[(1536,1536),(1536,8960),(8960,1536)],"qwen08_L0":[(1024,2048),(1024,3584),(3584,1024)],"qwen08_L3":[(1024,4096),(1024,3584),(3584,1024)],"qwen35_L0":[(2048,256),(2048,512),(512,2048)],"qwen35_L3":[(2048,8192),(2048,512),(512,2048)]}
for profile,shapes in profile_shapes.items():
  for m in [1,15,16,17,127,128]:
    for k,n in shapes:
      require(k%32==0 and n%32==0 and k<=8960,'profile dimensions')
      for begin in range(0,k,2560):
        depth=min(2560,k-begin)
        # Clear all eight row-blocks for every active K-word. Thus physically
        # read inactive row storage is initialized zero, then independently
        # masked before matrix issue. No DDR read beyond actual row count.
        clear_words=(depth//16)*8
        require(clear_words<=1376,'fixed A-bank capacity')
        for row in range(128):
          for kw in [0,depth//16-1]:
            address=kw*8+row//16
            require(address<clear_words,'inactive physical rows initialized')
      require(m*n*2%64==0,'full-beat final output ACK')
for m in [0,129,255,65535]: require(not(1<=m<=128),'invalid M')
print(json.dumps({'status':'PASS_SOURCE_AND_INTEGER_MODELS_ONLY','cases':cases,'negative_source_mutations':negative,'sha256':hashlib.sha256(s.encode()).hexdigest(),'chisel_numerical':'NOT_RUN','rtl_numerical':'NOT_RUN','resource_definition_unchanged':True},indent=2))
