"""Generate C++ top-port access only from frozen reviewed ABI, never parse SV.
This script does not invoke a compiler, Verilator, native model or shell.
"""
import hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parent
ABI=R.parent/'qwen2_core_client_sv_offline_prepare_20261025T1956/STRUCTURE_EXPECTATION.json'
ABI_SHA='5bdfb398ac02c250ff40cb092dcbbb326b42236acae6da5cd4a059d8ed4e1e1a'
def generate(ports):
    need=lambda ok,msg: (_ for _ in ()).throw(ValueError(msg)) if not ok else None
    need(len(ports)==8859,'exact reviewed ABI count')
    need(sum(p['direction']=='input' for p in ports.values())==8250,'input count')
    need(all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',n) and p['direction'] in ('input','output') and not p['signed'] and p['width'] in (1,2,3,4,5,7,8,16,32,64,512) for n,p in ports.items()),'closed unsigned ABI')
    lines=['// GENERATED SOURCE ONLY; no build/RTL execution.', '#pragma once','#include <array>','#include <cstdint>','#include <vector>','#include "VOrderedQkBehaviorCore.h"','namespace abi {','using D=VOrderedQkBehaviorCore;','inline void zero_inputs(D& d) {']
    writes=[];reads=[]
    for n,p in sorted(ports.items()):
        if p['direction']!='input':continue
        writes.append(n)
        if p['width']<=64:lines.append(f'  d.{n}=0;')
        else:lines.append(f'  for (unsigned i=0;i<{(p["width"]+31)//32};++i) d.{n}[i]=0;')
    lines+=['}','inline std::array<std::uint32_t*,4096> qk_tile(D& d) {','  return {{']
    tile=[]
    for row in range(16):
        for col in range(256):
            n=f'io_packedQk_result_bits_value_{row}_{col}';need(ports[n]==dict(direction='input',signed=False,width=32),'tile exact ABI');tile.append(n);lines.append(f'    &d.{n},')
    lines+=['  }};','}']
    groups={'memory':'io_memory_bits_','group':'io_packedQk_group_bits_','step':'io_packedQk_step_bits_','pv':'io_matrixRequest_bits_','result':'io_result_bits_'}
    snapshots={}
    for label,prefix in groups.items():
        names=[n for n in sorted(ports) if n.startswith(prefix)];need(names and all(ports[n]['direction']=='output' for n in names),'snapshot output-only')
        snapshots[label]=names;reads+=names
        lines.append(f'inline std::vector<std::uint64_t> snapshot_{label}(const D& d) {{')
        lines.append('  return {')
        for n in names:
            if ports[n]['width']<=64:lines.append(f'    std::uint64_t(d.{n}),')
            else:
                for i in range((ports[n]['width']+31)//32):lines.append(f'    std::uint64_t(d.{n}[{i}]),')
        lines+=['  };','}']
    lines+=['inline bool qk_operands_zero(const D& d) {','  return true']
    for prefix,lim in [('a',16),('b',256)]:
        for i in range(lim):
            n=f'io_packedQk_step_bits_{prefix}_{i}';need(ports[n]['direction']=='output' and ports[n]['width']==16,'operands ABI');reads.append(n);lines.append(f'    && d.{n}==0')
    lines+=['    ;','}','inline bool memory_data_zero(const D& d) {','  for(unsigned i=0;i<16;++i) if(d.io_memory_bits_data[i]!=0) return false;','  return true;','}','} // namespace abi','']
    return '\n'.join(lines),dict(schema='fixed-top-port-cpp-access-map-v1',top='OrderedQkBehaviorCore',port_count=len(ports),input_ports_zeroed=writes,qk_tile_row_major_ports=tile,snapshot_groups=snapshots,read_roles=sorted(set(reads)),wide_word_order='Verilator public WData index0 is least-significant 32-bit word; all512-bit endpoint data is zero, snapshot equality uses all16 words.',no_internal_or_hierarchy_access=True,no_generic_sv_parser=True)
def main():
    raw=ABI.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ABI_SHA:raise ValueError('ABI proof drift')
    text,mapping=generate(json.loads(raw)['top_ports'])
    for name,value in [('generated_abi.hpp',text),('ABI_MAPPING.json',json.dumps(mapping,indent=2,sort_keys=True)+'\n')]:
        with (R/name).open('x') as stream:stream.write(value)
    print(json.dumps(dict(status='SOURCE_GENERATED_NOT_COMPILED',hpp_bytes=len(text.encode()),input_ports=8250,output_ports=609)))
if __name__=='__main__':main()
