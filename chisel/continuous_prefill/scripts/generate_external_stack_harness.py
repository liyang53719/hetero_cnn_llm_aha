#!/usr/bin/env python3
"""Generate the external-arena variant of the independent stack TEST harness.

Only C++ test code is transformed. Production Chisel and generated RTL are not
modified. The numerical reference is never connected to DUT memory responses.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('test harness contract changed: ' + old[:100])
    return text.replace(old, new, 1)


EXTERNAL_METHODS = r'''
  void loadPacked(const std::string& path) {
    static_assert(sizeof(float)==4 && sizeof(uint32_t)==4, "FP32 word width");
    const uint32_t endianProbe=1;
    need(*reinterpret_cast<const unsigned char*>(&endianProbe)==1, "little endian test host required");
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    need(bool(in), "cannot open packed arena");
    need(in.tellg()==std::streamoff(total), "packed arena byte count mismatch");
    in.seekg(0);
    in.read(reinterpret_cast<char*>(mem.data()), std::streamsize(total));
    need(bool(in), "short packed arena read");
    auto isNaNWord=[](uint32_t w){return (w&0x7f800000u)==0x7f800000u && (w&0x007fffffu)!=0;};
    // The caller may provide inputs, weights and position tables only. Hidden B
    // and scratch must still be poison, never a previous reference run's output.
    for(uint64_t a=hiddenB;a<hiddenB+STACK_HIDDEN_BYTES;a+=4)
      need(isNaNWord(mem.at(a/4)), "packed hiddenB contains a precomputed value");
    for(uint64_t a=scratch;a<total;a+=4)
      need(isNaNWord(mem.at(a/4)), "packed scratch contains a precomputed value");
    auto asFloat=[](uint32_t w){float f;std::memcpy(&f,&w,4);return f;};
    std::vector<float> previous;
    for(unsigned l=0;l<STACK_LAYERS;l++) {
      NumericalReference ref(tokens,0);
      for(uint64_t i=0;i<STACK_WEIGHT_BYTES/4;i++)
        ref.reference.at(i)=asFloat(mem.at((weights+l*STACK_WEIGHT_BYTES)/4+i));
      for(uint64_t i=0;i<STACK_ROPE_BYTES/4;i++)
        ref.reference.at(OFF_COS/4+i)=asFloat(mem.at(rope/4+i));
      for(size_t i=0;i<size_t(tokens)*H;i++)
        ref.set(OFF_X,i,l?previous.at(i):asFloat(mem.at(hiddenA/4+i)));
      ref.computeReference();
      for(unsigned phase=0;phase<15;phase++) {
        const auto& stage=STAGES[phase];
        const auto begin=ref.reference.begin()+stage.off/4;
        expected[l][phase].assign(begin,begin+size_t(tokens)*stage.width);
        for(float x:expected[l][phase])need(std::isfinite(x), "nonfinite independent reference");
      }
      previous=expected[l][14];
    }
    packed=true;
  }
  void dumpHidden(const std::string& path) const {
    need(layers==STACK_LAYERS && commits==STACK_LAYERS*15, "cannot dump incomplete stack");
    {std::ifstream prior(path,std::ios::binary);need(!prior.good(), "refuse hidden output overwrite");}
    std::ofstream out(path,std::ios::binary);
    need(bool(out), "cannot create actual hidden output");
    const uint64_t first=output(STACK_LAYERS-1)/4;
    for(size_t i=0;i<size_t(tokens)*H;i++) {
      need(produced.at(first+i), "hidden output was not produced by DUT");
      const uint32_t word=mem.at(first+i);
      out.write(reinterpret_cast<const char*>(&word),4);
    }
    out.close();need(bool(out), "actual hidden output write failed");
  }
'''


def transform(text: str) -> str:
    text = '#include <fstream>\n#include <cstring>\n#include <cmath>\n' + text
    text = replace_once(text, 'unsigned commits=0,layers=0;', 'unsigned commits=0,layers=0;\n  bool packed=false;')
    text = replace_once(text, '  void load(){', EXTERNAL_METHODS + '\n  void load(){')
    text = replace_once(text,
        '<<" host_intermediate_writes=0 synthetic_weights=true canonical_512_array=0"',
        '<<" host_intermediate_writes=0 synthetic_weights="<<(packed?"false":"true")<<" canonical_512_array=0 official_forward_validated=false"')
    text = replace_once(text,
        'StackSim sim(n);sim.load();sim.run();return 0;',
        'StackSim sim(n);if(argc>2){sim.loadPacked(argv[2]);}else{sim.load();}sim.run();if(argc>3){sim.dumpHidden(argv[3]);}return 0;')
    return text


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    a=p.parse_args(); root=Path(__file__).resolve().parents[1]
    if a.output.exists():
        raise SystemExit('refuse to overwrite generated external harness')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    base=a.output.with_suffix('.base.cpp')
    subprocess.run([sys.executable,str(root/'scripts/generate_stack_harness.py'),str(base)],check=True)
    a.output.write_text(transform(base.read_text()))
    proof={
        'kind':'CXX_TEST_ONLY_NO_RTL_REWRITE',
        'base_cpp_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'output_cpp_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
        'requires_poisoned_intermediates':True,
        'oracle_serves_dut_memory':False,
    }
    a.output.with_suffix('.provenance.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    main()
