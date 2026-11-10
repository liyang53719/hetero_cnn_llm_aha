"""Rebuild native REAL RTL leaves for eight-instance hybrid Host. No simulation."""
from pathlib import Path
import json,hashlib,subprocess,os,argparse
R=Path(__file__).resolve().parent;W=R.parents[1];A=W/'round_20261110T0833/host_real_interface';V=W/'runtime_recovery_0133/verilator-runtime/verilator-package/usr';N=R/'matrix_icg';O=R/'native_rebuild'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def sources():
 repo=W/'hetero_cnn_llm_aha';mat=[repo/'rtl/integration/qwen2_matrix_command_endpoint.sv',repo/'rtl/matrix/bf16_outer_product_array_glue512.sv']
 mat+=sorted((repo/'rtl/matrix/candidates/rev8b_a').glob('bf16_operand_distribution512_rev8b_a_candidate.sv'))
 mat+=sorted((repo/'rtl/matrix/candidates/rev8b_b').glob('*.sv'))
 tc=A/'idma_export_bc_attempt/idma_export/deps/tech_cells_generic/src/rtl/tc_clk.sv'
 return {'icg':[tc],'matrix':mat+[A/'RetainedMath.sv',tc]}
def main(build=False):
 ss=sources();pins={str(p):h(p) for v in ss.values() for p in v};O.mkdir(exist_ok=True)
 (O/'INPUT_PINS.json').write_text(json.dumps(pins,indent=2));env=dict(os.environ,VERILATOR_ROOT=str(V/'share/verilator'))
 commands=[]
 for kind,top,param in [('icg','tc_clk_gating',"-GIS_FUNCTIONAL=1'b1"),('matrix','qwen2_matrix_command_endpoint',"-GENABLE_ACCUMULATOR_SEED=1'b1")]:
  d=O/kind;prefix='V'+top
  cmd=[str(V/'bin/verilator_bin'),'--cc','--Mdir',str(d),'--top-module',top,'--prefix',prefix,param,'--output-split','10000','--output-split-cfuncs','10000','-CFLAGS','-fPIC',*map(str,ss[kind]),'-Wno-fatal'];commands.append(cmd)
  mk=O/(kind+'_no_pch.mk');mk.write_text('VM_DEFAULT_RULES := 0\ninclude '+prefix+'.mk\n$(VK_OBJS_FAST): %.o: %.cpp\n\t$(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n$(VK_OBJS_SLOW): %.o: %.cpp\n\t$(CXX) $(OPT_SLOW) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n%.o: %.cpp\n\t$(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n')
  commands.append(['make','-C',str(d),'-f',str(mk),'-j1','OPT_FAST=-O1','OPT_SLOW=-O1',prefix+'__ALL.a'])
  commands.append(['g++','-std=c++17','-O1','-fPIC','-pthread','-I'+str(d),'-I'+str(V/'share/verilator/include'),'-I'+str(V/'share/verilator/include/vltstd'),'-I'+str(N),'-shared','-Wl,-z,defs',str(N/('retained_'+kind+'_leaf.cpp')),str(d/(prefix+'__ALL.a')),str(V/'share/verilator/include/verilated.cpp'),str(V/'share/verilator/include/verilated_threads.cpp'),'-o',str(O/('libretained_'+kind+'.so'))])
 (O/'COMMANDS.json').write_text(json.dumps(commands,indent=2))
 seeded='seed_begin_valid_i' in (A/'HostBlockTopV4.sv').read_text()
 (O/'COMPATIBILITY.json').write_text(json.dumps({'current_top_seed_ports':seeded,'recovered_abi_requires_seed':True,'same_hardware_compatible':seeded,'status':'BLOCKED_ABI_MISMATCH' if not seeded else 'UNQUALIFIED_REQUIRES_REBUILD'},indent=2))
 if build:
  if not seeded:raise ValueError('Refuse seeded native ABI against current unseeded Top; no silent hardware/interface change')
  for i,c in enumerate(commands):
   with (O/('stage'+str(i)+'.log')).open('w') as log:r=subprocess.run(c,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
   if r.returncode:raise RuntimeError('native stage '+str(i)+' exit '+str(r.returncode))
  (O/'RESULT.json').write_text(json.dumps({'scope':'BUILD_ONLY_UNQUALIFIED_NATIVE_REAL_RTL_LEAVES','libraries':{p.name:h(p) for p in O.glob('*.so')},'hardware_pass':False},indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--build',action='store_true');main(a.parse_args().build)
