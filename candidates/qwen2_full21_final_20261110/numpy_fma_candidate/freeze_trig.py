"""Freeze original Host input formula, not a C++ forward/oracle."""
import pathlib,hashlib,json,subprocess,sys
p=pathlib.Path(__file__).resolve().parent;src=p.parents[1]/'round_20261110T0733/qwen2_execution/host_real_inputs.cpp'
line=next(x.strip() for x in src.read_text().splitlines() if 'double angle=t/std::pow(1000000.0,2.0*i/HD)' in x)
if sys.byteorder!='little':raise RuntimeError('generator writes host binary, little-endian required')
code='''#include <cmath>
#include <fstream>
int main(int argc,char**argv){constexpr unsigned MAX_TOKENS=1024,HD=128;
std::ofstream c(argv[1],std::ios::binary),s(argv[2],std::ios::binary);
for(unsigned t=0;t<MAX_TOKENS;t++)for(unsigned i=0;i<HD/2;i++){
double angle=t/std::pow(1000000.0,2.0*i/HD);
float cv=float(std::cos(angle)),sv=float(std::sin(angle));
c.write(reinterpret_cast<const char*>(&cv),4);s.write(reinterpret_cast<const char*>(&sv),4);}
return !c || !s;}
'''
(p/'freeze_trig.cpp').write_text(code)
subprocess.run(['g++','-std=c++17','-O0','-fno-fast-math',str(p/'freeze_trig.cpp'),'-o',str(p/'freeze_trig.local')],check=True)
subprocess.run([str(p/'freeze_trig.local'),str(p/'cos.local.f32'),str(p/'sin.local.f32')],check=True)
pins={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [src,p/'freeze_trig.cpp',p/'freeze_trig.local',p/'cos.local.f32',p/'sin.local.f32',pathlib.Path('/usr/bin/g++'),pathlib.Path('/lib/x86_64-linux-gnu/libm.so.6')]}
(p/'TRIG_MANIFEST.json').write_text(json.dumps(dict(status='TEMP_CURRENT_PLATFORM_HOST_INPUT_FREEZE',scope='original Host formula frozen now, not official Torch table or recovered historical hash',source_line=line,sha256=pins,compiler=subprocess.check_output(['g++','--version'],text=True),libc=subprocess.check_output(['ldd','--version'],text=True),shape=[1024,64],dtype='little-endian FP32'),indent=2))
