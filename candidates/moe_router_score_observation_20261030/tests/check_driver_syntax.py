"""Syntax only against explicit fake ports; NOT real generated-ABI qualification."""
from pathlib import Path
import tempfile,re,subprocess,argparse
root=Path(__file__).resolve().parents[1]
source=root/'driver/host_axi_driver_non_dpi.cpp'
parser=argparse.ArgumentParser()
parser.add_argument('--repo',type=Path,required=True,help='Verified repository root containing the original shared driver headers')
args=parser.parse_args()
headers=(args.repo/'candidates/host_runtime_non_dpi_backend/source').resolve()
assert headers.is_dir(), 'missing shared driver header directory'
text=source.read_text()
names=set(re.findall(r'\bd\.([A-Za-z_][A-Za-z_0-9]*)',text))-{'eval','io_launch_bits_regions_'}
for i in range(4):
 for f in ('base','limit','read','write'):names.add(f'io_launch_bits_regions_{i}_{f}')
arrays={'io_axi_r_bits_data','io_axi_w_bits_data'}
with tempfile.TemporaryDirectory(prefix='p0-observation-syntax-') as td:
 d=Path(td)
 (d/'verilated.h').write_text('#pragma once\nstruct VerilatedContext {void randReset(int){} void timeInc(int){}};\n')
 ports=''.join('uint64_t '+n+('[16]' if n in arrays else '')+'{};\n' for n in sorted(names))
 (d/'VHostBlockTopV4.h').write_text('#pragma once\n#include <cstdint>\n#include "verilated.h"\nstruct VHostBlockTopV4 {explicit VHostBlockTopV4(VerilatedContext*){} void eval(){} void final(){}\n'+ports+'};\n')
 subprocess.run(['c++','-std=c++17','-fsyntax-only','-I'+str(d),'-I'+str(headers),str(source)],check=True)
print('PASS_CPP_SYNTAX_WITH_MOCK_PORTS_ONLY_REAL_ABI_PENDING')
