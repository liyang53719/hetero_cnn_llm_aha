"""Generate only C++ port accessors from the actual pinned owner ANSI header."""
import pathlib,re,json,hashlib,resource
resource.setrlimit(resource.RLIMIT_AS,(64<<20,64<<20))
D=pathlib.Path(__file__).resolve().parent;S=D.parent/'owner_lowering_r1/run/TransposedDenseDownOwner.sv'
with S.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()=='8f2c4a5093b848f8b5c33a0b5aae6062315e625505bde21c6a11e9230a8b69ed'
header=[];active=False
with S.open()as f:
 for line in f:
  assert len(line)<1<<20
  c=line.split('//',1)[0].strip()
  if c.startswith('module TransposedDenseDownOwner('):active=True
  if active:
   header.append(c);assert len(header)<5000
   if ');'in c:break
text=' '.join(header);body=text[text.index('(')+1:text.rindex(')')];ports={};di=None;wi=None
for clause in body.split(','):
 m=re.fullmatch(r'(?:(input|output|inout)\s+)?(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?(\w+)',clause.strip());assert m,clause
 if m[1]:di=m[1];wi=abs(int(m[2])-int(m[3]))+1 if m[2]else 1
 elif m[2]:wi=abs(int(m[2])-int(m[3]))+1
 assert di and wi and m[4]not in ports;ports[m[4]]=(di,wi)
assert len(ports)==4737 and hashlib.sha256(json.dumps(sorted(ports.items()),separators=(',',':')).encode()).hexdigest()=='4aba39c5df91a78c431ea7a080f9fe2422a828278610e4af254d18a387cd5ce4'
out=['// Generated from pinned current SV, not old harness ABI.','#pragma once','static void zero_inputs(VTransposedDenseDownOwner& d) {']
for n,(di,w)in ports.items():
 if di=='input':out.append(f'  d.{n}=0;'if w<=64 else f'  for (unsigned i=0;i<{(w+31)//32};++i) d.{n}[i]=0;')
out+=['}','static void result_values(VTransposedDenseDownOwner& d,unsigned context,unsigned group) {']
for n in range(16):
 for j in range(256):out.append(f'  d.io_matrix_result_bits_value_{n}_{j}=result_pattern(context,group,{n},{j});')
out+=['}','static void check_operands(const VTransposedDenseDownOwner& d,unsigned k,unsigned context,unsigned ng) {']
for n in range(16):out.append(f'  require(d.io_matrix_step_bits_a_{n}==weight_pattern(k,ng+context*32+{n}),"weight low lane {n}");')
for m in range(256):
 ex=f'activation_pattern({m},k)'if m<128 else f'weight_pattern(k,ng+context*32+{m-112})'if m<144 else '0'
 out.append(f'  require(d.io_matrix_step_bits_b_{m}=={ex},"operand lane {m}");')
out+=['}']
(D/'ports_generated.hpp').write_text('\n'.join(out)+'\n');(D/'PORTS.json').write_text(json.dumps({'SV_sha256':'8f2c4a5093b848f8b5c33a0b5aae6062315e625505bde21c6a11e9230a8b69ed','normalized_port_hash':'4aba39c5df91a78c431ea7a080f9fe2422a828278610e4af254d18a387cd5ce4','ports':ports},indent=2)+'\n')
print('GENERATED_CURRENT_ABI_ONLY',len(ports))
