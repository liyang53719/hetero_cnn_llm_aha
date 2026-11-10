"""Synthetic phase1 handoff and full phase2 expected writes, source-order FP32."""
import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
s=(R/'scalar_core.py').read_bytes();assert hashlib.sha256(s).hexdigest()==json.loads((R/'ORACLE_PINS.json').read_text())['scalar_core.py']
n={};exec(compile(s,str(R/'scalar_core.py'),'exec'),n)
q,k,v,g,b,_=n['fixture']();q,k,v,g,b=q[:64],k[:64],v[:64],g[:64],b[:64]
c=n['cumulative'](g,0);exp=n['exp_negative'];mul=n['mul'];sub=n['sub'];bits=n['bits']
e=[exp(x,0) for x in c];remain=[exp(sub(c[-1],x),0) for x in c]
base=0x10000000+65536
pack=lambda xs:sum(bits(x)<<(i*32) for i,x in enumerate(xs))
inputs={base+i*64:pack([c[i],b[i]]) for i in range(64)};expected={}
for matrix,offset in [(q,4096),(k,36864),(v,69632)]:
 for row in range(64):
  for beat in range(8):inputs[base+offset+row*512+beat*64]=pack(matrix[row][beat*16:beat*16+16])
for row in range(64):
 kb=[mul(x,b[row]) for x in k[row]]
 for offset,words in [(102400,kb),(135168,[mul(x,b[row]) for x in v[row]]),(167936,[mul(x,e[row]) for x in kb]),(200704,[mul(x,e[row]) for x in q[row]]),(233472,[mul(x,remain[row]) for x in k[row]])]:
  for beat in range(8):expected[base+offset+row*512+beat*64]=pack(words[beat*16:beat*16+16])
 pair=[exp(sub(c[row],c[j]),0) if j<=row else 0.0 for j in range(64)]
 for beat in range(4):expected[base+331776+row*256+beat*64]=pack(pair[beat*16:beat*16+16])
for name,data in [('inputs',inputs),('expected',expected)]:
 (R/(name+'.tsv')).write_text(''.join(f'{a:x}\t{v:x}\n' for a,v in sorted(data.items())))
summary=dict(synthetic=True,phase1_handoff='oracle-generated; receipt supplied by testbench, not producer provenance',head=0,chunk=0,runtime_value_heads=16,bank_lanes=32,cumsum_policy=0,decay_policy=0,input_beats=len(inputs),expected_write_beats=len(expected),expected_write_bytes=len(expected)*64,expected_read_bytes=235584,expected_exp_calls=2209,expected_vector_add_calls=2144,expected_vector_mul_calls=2560,decay_hex=f'{bits(exp(c[-1],0)):08x}',input_sha256=hashlib.sha256((R/'inputs.tsv').read_bytes()).hexdigest(),expected_sha256=hashlib.sha256((R/'expected.tsv').read_bytes()).hexdigest())
(R/'FIXTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')

(R/'decay.txt').write_text(summary['decay_hex']+'\n')

# Independent transpose oracle, never copied into the runtime memory map.
transpose_expected={}
ke=[[mul(x,remain[row]) for x in k[row]] for row in range(64)]
for matrix,offset in [(k,266240),(ke,299008)]:
 for row in range(128):
  for beat in range(4):transpose_expected[base+offset+row*256+beat*64]=pack([matrix[column][row] for column in range(beat*16,beat*16+16)])
(R/'transpose_expected.tsv').write_text(''.join(f'{a:x}\t{v:x}\n' for a,v in sorted(transpose_expected.items())))
summary['transpose_expected_beats']=len(transpose_expected)
summary['transpose_expected_sha256']=hashlib.sha256((R/'transpose_expected.tsv').read_bytes()).hexdigest()
summary['phase2_handoff']='actual hardware full result; accepted writes retained in same memory map'
(R/'FIXTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')

phase1_expected=dict(inputs)
raw={}
for row in range(64):
 raw[0x1000000+row*25600+3*8192]=pack([g[row],b[row]])
 for matrix,offset in [(q,0),(k,8192),(v,16384)]:
  for beat in range(8):raw[0x1000000+row*25600+offset+beat*64]=pack(matrix[row][beat*16:beat*16+16])
for name,data in [('inputs',raw),('phase1_expected',phase1_expected)]:
 (R/(name+'.tsv')).write_text(''.join(f'{a:x}\t{v:x}\n' for a,v in sorted(data.items())))
summary.update(phase1_handoff='actual original LoadPrep result directly accepted by phase2',prepared_input='synthetic Q/K/V/logdecay/beta; synthetic prepared and initial-state prerequisite receipts',phase1_expected_write_beats=len(phase1_expected),full_chain_expected_reads=6305,full_chain_expected_writes=5440,input_sha256=hashlib.sha256((R/'inputs.tsv').read_bytes()).hexdigest(),phase1_expected_sha256=hashlib.sha256((R/'phase1_expected.tsv').read_bytes()).hexdigest())
(R/'FIXTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')

# Independent source-order phase5 oracle: each output accumulates ascendingK
# separate FP32 Mul then Add from+0, then one final Pair multiplication.
add=n['add'];phase5_expected={}
for row in range(64):
 kb=[mul(x,b[row]) for x in k[row]]
 outputs=[]
 for col in range(64):
  total=0.0
  for z in range(128):total=add(total,mul(kb[z],k[col][z]))
  pair_factor=exp(sub(c[row],c[col]),0) if col<=row else 0.0
  outputs.append(mul(total,pair_factor))
 for beat in range(4):phase5_expected[base+348160+row*256+beat*64]=pack(outputs[beat*16:beat*16+16])
(R/'phase5_expected.tsv').write_text(''.join(f'{a:x}\t{v:x}\n' for a,v in sorted(phase5_expected.items())))
summary.update(full_chain_expected_reads=41377,full_chain_expected_writes=5696,phase5_expected_write_beats=256,phase5_expected_read_beats=35072,phase5_expected_vector_requests=65792,phase5_expected_sha256=hashlib.sha256((R/'phase5_expected.tsv').read_bytes()).hexdigest())
(R/'FIXTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
