"""Fixed M3 passive expectations: generate source only, never execute a model."""
import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('reference',Path(__file__).with_name('reference_events.py'));r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
def render():
 out=['// Fixed normal_m3; passive descriptors, not physical memory/tensors.','#pragma once','#include "generated_abi.hpp"','#include <array>','#include <cstdint>','namespace reference {','struct Memory {std::uint64_t address,tag;bool write;};','inline constexpr std::array<Memory,1728> memory{{']
 for n,e in enumerate(r.memory_events(3)):out.append('  {0x%xULL,0x%xULL,%s},'%(e['address'],(7<<32)+n,str(e['write']).lower()))
 out+=['}};','struct Pv {std::uint16_t a0;bool clear,last;};','inline constexpr std::array<Pv,576> pv{{']
 for e in r.pv_events(3):out.append('  {0x%x,%s,%s},'%(e['a0'],str(e['clear']).lower(),str(e['last']).lower()))
 out+=['}};','struct Vector {std::uint32_t token,head,phase,lane,selected,max;bool write;};','inline constexpr std::array<Vector,1260> vector{{']
 for e in r.vector_events(3):out.append('  {%d,%d,%d,%d,%d,0x%xU,%s},'%(e['token'],e['head'],e['phase'],e['lane'],e['selected'],e['maxScore'],str(e['scoreWrite']).lower()))
 out+=['}};','inline bool other_pv_operands_zero(const abi::D& d) {return']
 fields=['a_'+str(i) for i in range(1,16)]+['b_'+str(i) for i in range(256)]
 out+=['  d.io_matrixRequest_bits_'+f+'==0'+(';' if n==len(fields)-1 else ' &&') for n,f in enumerate(fields)]
 out+=['}','} // namespace reference','']
 return '\n'.join(out)
if __name__=='__main__':
 with Path(__file__).with_name('expected_m3.hpp').open('x') as f:f.write(render())
