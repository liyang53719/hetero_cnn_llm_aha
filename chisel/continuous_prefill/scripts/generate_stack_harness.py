#!/usr/bin/env python3
"""Generate a stack test harness from the committed scalar numerical oracle.

This generates C++ TEST code, never Chisel or production RTL. The DUT memory
model resides in the separately reviewed driver. Oracle outputs cannot service
DUT memory reads. Outputs and source identity are preserved in a fresh directory.
"""
from pathlib import Path
import argparse
import hashlib
import json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
source = root / 'tests/qwen2_block.cpp'
driver = root / 'tests/qwen2_stack_driver.inc'
s = source.read_text()
if a.output.exists():
    raise SystemExit('refuse to overwrite an existing generated harness')
# These bounded sections contain only the independent scalar oracle and bit
# conversion helpers. No source BlockTest driver or DUT instance is included.
prefix = s[s.index('#include "verilated.h"'):s.index('struct Pending')]
weights = s[s.index('  void weight('):s.index('  void loadArena(')]
weights = weights.replace('salt*2654435761u', '(salt+layerSalt)*2654435761u')
maths = s[s.index('  void norm('):s.index('  void compareStage(')]
reference = '''class NumericalReference {
public:
  std::vector<float> reference; unsigned tokens,layerSalt;
  NumericalReference(unsigned t,unsigned salt):reference(ARENA_BYTES/4,0.0f),tokens(t),layerSalt(salt){}
  void set(uint64_t offset,size_t i,float x){reference.at(offset/4+i)=x;}
  float get(uint64_t offset,size_t i)const{return reference.at(offset/4+i);}
  void put(uint64_t offset,size_t i,float x){reference.at(offset/4+i)=x;}
''' + weights + maths + '};\n'
text = '// Generated test oracle; no DUT result injection.\n#include "VQwen2LayerStack.h"\n' + prefix + '#include <optional>\n' + reference + driver.read_text()
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(text)
identity = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in (source, driver, Path(__file__))}
identity['generated_cpp_sha256'] = hashlib.sha256(a.output.read_bytes()).hexdigest()
a.output.with_suffix('.provenance.json').write_text(json.dumps(identity, indent=2)+'\n')
