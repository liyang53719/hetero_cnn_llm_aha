"""Independent composed RawPrep -> selected-head phase1-17 reference, never DUT feedback.
Only original BF16 Conv/QKV/AB boundaries are runtime inputs. Prepared rows are
expected writes, NOT initial memory. Run this script in its source directory.
"""
import pathlib,hashlib,json,argparse,numpy as np
parser=argparse.ArgumentParser();parser.add_argument("--head",type=int,choices=range(16),default=0);args=parser.parse_args();head=args.head
R=pathlib.Path(__file__).resolve().parent
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins=json.loads((R/'REFERENCE_PINS.json').read_text())
def pinned(name):
 source=(R/name).read_bytes();assert h(R/name)==pins[name]
 ns={'__name__':'pinned_reference'};exec(compile(source,str(R/name),'exec'),ns);return ns
n=pinned('original_prep_reference.py')
F=np.float32;bf16=n['bf16'];recipe=n['recipe'];pack=lambda b:int.from_bytes(b,'little')
assert h(R/'conv_reference.py')==pins['conv_reference.py']
from conv_reference import conv4
channels=6144
raw_qkv=bf16(np.array([[((c*3+t*5)%31-15)/32 for c in range(channels)] for t in range(128)],dtype='<f4'))
weights=bf16(np.array([[((c+t*3)%9-4)/32 for t in range(4)] for c in range(channels)],dtype='<f4'))
conv_out,history=conv4(raw_qkv,weights)
inputs={};expected={};q=[];k=[];v=[];g=[];b=[];alog=np.array([F(.25+h/32) if h%4==0 else F(-.5-h/64) for h in range(16)],dtype='<f4');bias=bf16(np.array([(h%5-2)/16 for h in range(16)],dtype='<f4'))
inputs[0x8000000]=pack(alog.tobytes());inputs[0x9000000]=pack(bias.tobytes()+bytes(32))
for t in range(128):
 matrices=list(conv_out[t].reshape(3,16,128))
 av=bf16(np.array([(h%7-3+t%3)/8 for h in range(16)],dtype='<f4'));bv=bf16(np.array([(h%9-4-t%2)/4 for h in range(16)],dtype='<f4'))
 inputs[0x7000000+t*64]=pack(av.tobytes()+bv.tobytes())
 raw=b''.join(x.tobytes() for x in matrices)
 for off in range(0,len(raw),64):expected[0x6000000+t*12288+off]=pack(raw[off:off+64])
 outputs=recipe(*matrices,av,bv,alog,bias,recurrent_mode=False)
 q.append(outputs[0][head].tolist());k.append(outputs[1][head].tolist());v.append(outputs[2][head].tolist());g.append(float(outputs[3][head,0]));b.append(float(outputs[3][head,1]))
 data=b''.join(x.astype('<f4').tobytes() for x in outputs)
 assert len(data)==25600
 for off in range(0,len(data),64):expected[0x1000000+t*25600+off]=pack(data[off:off+64])

# Dense projection remains synthetic ingress; Conv output/history are writes only.
for base,array in [(0xa000000,raw_qkv),(0xb000000,weights)]:
 data=array.tobytes()
 for off in range(0,len(data),64):inputs[base+off]=pack(data[off:off+64])
data=history.tobytes()
for off in range(0,len(data),64):expected[0xd000000+off]=pack(data[off:off+64])

n=pinned('scalar_core.py');on=pinned('oracle_phases.py')
bits=n['bits'];pack=lambda xs:sum(bits(x)<<(i*32) for i,x in enumerate(xs))
shapes=[('gates',64,16),('q',64,128),('k',64,128),('v',64,128),('kb',64,128),('vb',64,128),('kbg',64,128),('qg',64,128),('ke',64,128),('kt',128,64),('ket',128,64),('pair',64,64),('ut',64,64),('intra',64,64),('solvek',64,128),('solvev',64,128),('pred',64,128),('vnew',64,128),('inter',64,128),('local',64,128),('out',64,128),('state_update',128,128),('decay_state',128,128),('next_state',128,128)]
offsets={};offset=0
for name,rows,cols in shapes:offsets[name]=offset;offset+=rows*cols*4
assert offset==806912
names={5:'ut',6:'intra',7:'solvev',8:'solvek',9:'pred',10:'vnew',11:'inter',12:'local',13:'out',14:'state_update',15:'decay_state',16:'next_state'}
raw=inputs;decays=[];phase_hashes={};initial=[[0.0]*128 for _ in range(128)]
for i in range(1024):expected[0x10000000+head*(65536+2*806912)+i*64]=0
for chunk in range(2):
 sl=slice(chunk*64,chunk*64+64);base=0x10000000+head*(65536+2*806912)+65536+chunk*806912
 result=on['compute'](n,q[sl],k[sl],v[sl],g[sl],b[sl],initial)
 for row in range(64):expected[base+row*64]=pack([result['cumulative'][row],b[chunk*64+row]])
 allmat={'q':q[sl],'k':k[sl],'v':v[sl],**result['derived']}
 allmat.update({names[p]:m for p,m in result['phases'].items() if p!=17})
 for name,matrix in allmat.items():
  for row,values in enumerate(matrix):
   for beat in range(len(values)//16):expected[base+offsets[name]+row*len(values)*4+beat*64]=pack(values[beat*16:beat*16+16])
 for row,values in enumerate(result['phases'][17]):
  for beat in range(4):expected[0x4000000+(chunk*64+row)*16*256+head*256+beat*64]=sum(n['bf16_bits'](x)<<(16*i) for i,x in enumerate(values[beat*32:beat*32+32]))
 initial=result['phases'][16]
 decays.append(f"{bits(result['decay']):08x}")
 phase_hashes[str(chunk)]={str(p):n['matrix_sha'](m,'bf16' if p==17 else 'fp32') for p,m in result['phases'].items()}
for row,values in enumerate(initial):
 for beat in range(8):expected[0x3000000+head*65536+row*512+beat*64]=pack(values[beat*16:beat*16+16])
assert len(raw)==25474 and len(expected)==104320 and set(raw).isdisjoint(expected)
for name,data in [('inputs',raw),('expected',expected)]:
 (R/f'{name}.tsv').write_text(''.join(f'{a:x}\t{v:x}\n' for a,v in sorted(data.items())))
(R/'decay.txt').write_text('\n'.join(decays)+'\n')
summary=dict(status='REFERENCE_GENERATED_NOT_HARDWARE_PASS',tokens=128,rawprep_heads=16,chain_heads=[head],chunks=2,raw_boundary_beats=len(raw),prepared_expected_write_beats=51200,chain_expected_write_beats=27776,conv_expected_write_beats=25344,total_expected_write_beats=len(expected),prepared_initial_memory=False,raw_addresses={'conv':'0x6000000','ab':'0x7000000','aLog':'0x8000000','dtBias':'0x9000000'},prepared_address='0x1000000',oracle_matrix_hashes=phase_hashes,full_block_pass=False,scope='synthetic Dense QKV AB and Conv weights; actual Conv outputs required before RawPrep; no trained projection, no physical4096MAC proof',input_sha256=h(R/'inputs.tsv'),expected_sha256=h(R/'expected.tsv'),decay_sha256=h(R/'decay.txt'))
(R/'FIXTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
