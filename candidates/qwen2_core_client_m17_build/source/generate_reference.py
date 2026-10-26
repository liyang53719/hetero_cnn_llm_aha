"""Generate passive fixed-M17 source tables only; never import driver mapping."""
import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('reference',Path(__file__).with_name('reference_events.py'));r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
def render():
 out=['// Fixed normal_m17 passive descriptors, not implemented physical tensors.','#pragma once','#include "generated_abi.hpp"','#include <array>','#include <cstdint>','namespace reference {','struct Group {std::uint32_t token,head,base,count;};','inline constexpr std::array<Group,216> groups{{']
 for e in r.group_events():out.append('  {%d,%d,%d,%d},'%(e['token'],e['head'],e['base'],e['count']))
 out+=['}};','struct Memory {std::uint64_t address,tag;bool write;};','inline constexpr std::array<Memory,32640> memory{{']
 for n,e in enumerate(r.memory_events()):out.append('  {0x%xULL,0x%xULL,%s},'%(e['address'],(7<<32)+n,str(e['write']).lower()))
 out+=['}};','struct Pv {std::uint16_t a0;bool clear,last;};','inline constexpr std::array<Pv,14688> pv{{']
 for e in r.pv_events():out.append('  {0x%x,%s,%s},'%(e['a0'],str(e['clear']).lower(),str(e['last']).lower()))
 out+=['}};','struct Vector {std::uint32_t token,head,base,phase,lane,selected,index,max;bool write;};','inline constexpr std::array<Vector,8964> vector{{']
 for e in r.vector_events():out.append('  {%d,%d,%d,%d,%d,%d,%d,0x%xU,%s},'%(e['token'],e['head'],e['keyBase'],e['phase'],e['lane'],e['selected'],e['scoreIndex'],e['maxScore'],str(e['scoreWrite']).lower()))
 out+=['}};','static_assert(sizeof(Group)==16 && sizeof(Memory)==24 && sizeof(Pv)==4 && sizeof(Vector)==36,"expected fixed ABI table layouts");','inline bool other_pv_operands_zero(const abi::D& d) {return']
 fields=['a_'+str(i) for i in range(1,16)]+['b_'+str(i) for i in range(256)]
 out+=['  d.io_matrixRequest_bits_'+f+'==0'+(';' if n==len(fields)-1 else ' &&') for n,f in enumerate(fields)]
 out+=['}','} // namespace reference',''];return '\n'.join(out)
if __name__=='__main__':
 with Path(__file__).with_name('expected_m17.hpp').open('x') as f:f.write(render())
