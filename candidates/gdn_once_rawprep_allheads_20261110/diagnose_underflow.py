from pathlib import Path
import struct,json
r=Path('round_20261110T0533/allheads16');m={int(a,16):int(v,16) for a,v in (x.split() for x in (r/'expected.tsv').open())};base=0x10000000+4*1679360+65536
shapes=[('gates',64,16),('q',64,128),('k',64,128),('v',64,128),('kb',64,128),('vb',64,128),('kbg',64,128),('qg',64,128),('ke',64,128),('kt',128,64),('ket',128,64),('pair',64,64),('ut',64,64),('intra',64,64),('solvek',64,128),('solvev',64,128)]
off={};o=0
for name,rows,cols in shapes:off[name]=o;o+=rows*cols*4
u=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
f=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
def read(n,row,col,cols):
 a=base+off[n]+(row*cols+col)*4;bits=(m[a//64*64]>>((a%64)*8))&0xffffffff
 return struct.unpack('<f',struct.pack('<I',bits))[0]
for row in range(64):
 for beat in range(8):
  for k in range(row):
   a=read('ut',row,k,64)
   for lane in range(16):
    b=read('solvev',k,beat*16+lane,128);exact=a*b;v=f(exact)
    if exact!=0 and abs(v)<2**-126 and v!=exact:
     out={'classification':'independent FP32 multiply tiny+inexact matches LegacyFatalUnderflow policy','head':4,'chunk':0,'phase':7,'row':row,'colbeat':beat,'k':k,'lane':lane,'a':hex(u(a)),'b':hex(u(b)),'rounded':hex(u(v)),'reference_final_words_nonfinite':False};print(json.dumps(out,indent=2));Path('round_20261110T0533/UNDERFLOW_DIAGNOSIS.json').write_text(json.dumps(out,indent=2));raise SystemExit
print('no underflow')
