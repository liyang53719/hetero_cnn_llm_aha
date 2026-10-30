"""Compile/run only the host collector with deterministic synthetic bit patterns."""
from pathlib import Path
import tempfile,subprocess,struct
D=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='resident-observation-synthetic-') as td:
 root=Path(td);exe=root/'collector';output=root/'output';output.mkdir()
 subprocess.run(['c++','-std=c++17','-O0','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(D/'test_collector.cpp'),'-o',str(exe)],check=True)
 subprocess.run([str(exe),str(output)],check=True)
 for slot,name in enumerate(('gate','up')):
  raw=(output/('resident_'+name+'.fp32.actual.bin')).read_bytes()
  assert len(raw)==128*8960*4
  assert all(value==0x3f000000+i+slot*0x200000 for i,(value,) in enumerate(struct.iter_unpack('<I',raw)))
print('PASS_SYNTHETIC_FULL_SHAPE_BIJECTION_ONLY_NO_DUT')
