"""Patch only external stimulus setup in the pinned original Host AXI bench.
Its existing C++ oracle remains a diagnostic, not the requested independent
Python full-block reference. No compiled hardware/PASS is implied.
"""
from pathlib import Path
import argparse,hashlib,json

def bind(source,out):
 s=source.read_text();original=hashlib.sha256(source.read_bytes()).hexdigest()
 start=s.index('   weight(A_WQ,H,H,1);');end=s.index('   for(unsigned t=0;t<MAX_TOKENS;',start)
 mappings=[('wq','A_WQ','H*H'),('wk','A_WK','H*KV'),('wv','A_WV','H*KV'),('wo','A_WO','H*H'),('wg','A_WG','H*F'),('wu','A_WU','H*F'),('wd','A_WD','F*H'),('gamma0','A_GAMMA0','H'),('gamma1','A_GAMMA1','H'),('bq','A_BQ','H'),('bk','A_BK','KV'),('bv','A_BV','KV'),('x','A_X','TOKENS*H')]
 replacement='   check(LAYERS==1 && TOKENS==128 && H==1536 && F==8960,"real M128 L0 scope");\n   static_assert(OWNER_MATRIX_MACS==4096 && OWNER_BF16_WEIGHTS==0,"fixed 4096 and original FP32 storage required");\n'
 replacement+='   auto realInput=[&](const char* name,uint64_t addr,uint64_t count){load(fixture/name,addr,count*4);for(uint64_t i=0;i<count;i++)oracle[pos(addr)+i]=fp(mem[pos(addr)+i]);};\n'
 for name,addr,count in mappings:replacement+=f'   realInput("{name}.f32le",{addr},uint64_t({count}));\n'
 s=s[:start]+replacement+s[end:]
 line='   if(layer==0)for(unsigned t=0;t<TOKENS;t++)for(unsigned i=0;i<H;i++)put(A_X,size_t(t)*H+i,float(int((i*37u+t*101u+73u+inputSalt*17u)%1021)-510)*0.00390625f);\n'
 if s.count(line)!=1:raise ValueError('synthetic input anchor drift')
 s=s.replace(line,'').replace('#define OWNER_MATRIX_MACS 512','#define OWNER_MATRIX_MACS 4096')
 s=s.replace('VHostBlockTop','VHostBlockTopV4')
 s=s.replace('   check(d.io_launch_ready,', '   d.io_launch_bits_version=1;d.io_launch_bits_profileId=0;\n   check(d.io_launch_ready,')
 s=s.replace('HOST_BLOCK_ALL_OWNERS_PASS','LEGACY_CPP_ORACLE_DIAGNOSTIC_ONLY_FULL_PYTHON_ACCEPTANCE_PENDING')
 if out.exists():raise ValueError('preserve output')
 out.write_text(s)
 return dict(status='SOURCE_ADAPTER_ONLY_NOT_EXECUTED',original_sha256=original,adapted_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),hardware_modified=False,cpp_reference_is_diagnostic_only=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(bind(a.source,a.output),indent=2))
