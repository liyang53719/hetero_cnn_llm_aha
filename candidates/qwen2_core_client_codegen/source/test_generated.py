"""Pure stdlib source/negative controls, no C++ compiler or actual model."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parent

def load(n):
 sp=importlib.util.spec_from_file_location('generated_control_'+n,R/(n+'.py'));m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
c=load('check_generated');f=load('synthetic_generated')
class Content(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory(prefix='tiny_codegen_text_only_');self.addCleanup(t.cleanup);self.root=Path(t.name);self.model=self.root/'model';self.model.mkdir();self.harness=self.root/'source/m1_main.cpp';self.harness.parent.mkdir();self.harness.write_text('TINY');self.tool=self.root/'tool';(self.tool/'include').mkdir(parents=True)
  for n in ('verilated','verilated_threads'):(self.tool/'include'/(n+'.cpp')).write_text('TINY')
  self.files=f.contents(self.model,self.harness,self.tool)
  for n,t in self.files.items():(self.model/n).write_text(t)
 def check(self):return c.check(self.model,f.PORTS,self.harness,self.tool)
 def reject(self,name,fn):
  p=self.model/name;p.write_text(fn(p.read_text()))
  with self.assertRaises(ValueError):self.check()
 def test_positive_contents_no_type_claim(self):
  r=self.check();self.assertEqual(r['header']['port_count'],4);self.assertFalse(r['full_cpp_semantics_or_compile'])
 def test_full_8859_abi(self):
  ports=json.loads((R.parent/'qwen2_core_client_verilator_source_review_20261025T2045/TOP_ABI.json').read_text())['ports'];r=c.header_contract(f.header(ports),ports);self.assertEqual((r['port_count'],r['inputs'],r['outputs']),(8859,8250,609))
 def test_missing_port(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock,0,0);',''))
 def test_extra_port(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock,0,0);','VL_IN8(&clock,0,0);\nVL_IN8(&extra,0,0);'))
 def test_duplicate_port(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock,0,0);','VL_IN8(&clock,0,0);\nVL_IN8(&clock,0,0);'))
 def test_wrong_direction(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock','VL_OUT8(&clock'))
 def test_width(self):self.reject(f.P+'.h',lambda t:t.replace('&clock,0,0','&clock,1,0'))
 def test_storage_macro(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock','VL_IN16(&clock'))
 def test_missing_reference(self):self.reject(f.P+'.h',lambda t:t.replace('&clock','clock'))
 def test_wide_word_count(self):self.reject(f.P+'.h',lambda t:t.replace('&wide,511,0,16','&wide,511,0,15'))
 def test_private_port(self):self.reject(f.P+'.h',lambda t:t.replace('public:\nVL_IN8','private:\nVL_IN8'))
 def test_unparsed_port(self):self.reject(f.P+'.h',lambda t:t.replace('VL_IN8(&clock,0,0);','VL_IN8(&clock,0,0); unrelated;'))
 def test_guard(self):self.reject(f.P+'.h',lambda t:t.replace('VERILATED_VORDEREDQKBEHAVIORCORE_H_','WRONG'))
 def test_if0_hidden_ports(self):self.reject(f.P+'.h',lambda t:t.replace('public:','public:\n#if 0'))
 def test_guard_unclosed(self):self.reject(f.P+'.h',lambda t:t.replace('#endif // guard',''))
 def test_missing_constructor(self):self.reject(f.P+'.h',lambda t:t.replace('VerilatedContext* contextp','void* contextp'))
 def test_missing_eval(self):self.reject(f.P+'.h',lambda t:t.replace('void eval()','void other()'))
 def test_missing_final(self):self.reject(f.P+'.h',lambda t:t.replace('void final();',''))
 def test_missing_class_close(self):self.reject(f.P+'.h',lambda t:t.replace('};',''))
 def test_early_class_close(self):self.reject(f.P+'.h',lambda t:t.replace('public:','public:\n};'))
 def test_port_before_class(self):self.reject(f.P+'.h',lambda t:t.replace('#include "verilated.h"','#include "verilated.h"\nVL_IN8(&clock,0,0);'))
 def test_api_after_class(self):self.reject(f.P+'.h',lambda t:t.replace('void final();','').replace('};','};\nvoid final();'))
 def test_private_api(self):self.reject(f.P+'.h',lambda t:t.replace('void final();','private:\nvoid final();\npublic:'))
 def test_make_prefix(self):self.reject(f.P+'.mk',lambda t:t.replace('VM_PREFIX = '+f.P,'VM_PREFIX = Wrong'))
 def test_make_root(self):self.reject(f.P+'.mk',lambda t:t.replace(str(self.tool),'/untrusted'))
 def test_cpp17(self):self.reject(f.P+'.mk',lambda t:t.replace('-std=c++17','-std=c++11'))
 def test_extra_cflags(self):self.reject(f.P+'.mk',lambda t:t.replace('-std=c++17','-std=c++17 -DNDEBUG'))
 def test_extra_user_source(self):self.reject(f.P+'.mk',lambda t:t.replace('\tm1_main \\','\tm1_main other \\'))
 def test_harness_rule(self):self.reject(f.P+'.mk',lambda t:t.replace('m1_main.o: '+str(self.harness),'m1_main.o: /wrong.cpp'))
 def test_user_directory(self):self.reject(f.P+'.mk',lambda t:t.replace('../source','../evil'))
 def test_extra_include(self):self.reject(f.P+'.mk',lambda t:t+'include /wrong.mk\n')
 def test_shell_injection(self):self.reject(f.P+'.mk',lambda t:t.replace('SYSTEMC_INCLUDE ?=','SYSTEMC_INCLUDE ?= $(shell evil)'))
 def test_extra_recipe(self):self.reject(f.P+'.mk',lambda t:t+'\tmake --build\n')
 def test_recipe_missing_tab(self):self.reject(f.P+'.mk',lambda t:t.replace('\t$(OBJCACHE)','$(OBJCACHE)'))
 def test_recipe_space_not_tab(self):self.reject(f.P+'.mk',lambda t:t.replace('\t$(LINK)','    $(LINK)'))
 def test_assignment_in_recipe(self):self.reject(f.P+'.mk',lambda t:t.replace('VM_PREFIX =','\tVM_PREFIX ='))
 def test_include_in_recipe(self):self.reject(f.P+'.mk',lambda t:t.replace('include '+f.P+'_classes.mk','\tinclude '+f.P+'_classes.mk'))
 def test_duplicate_variable(self):self.reject(f.P+'.mk',lambda t:t+'VM_PREFIX = '+f.P+'\n')
 def test_make_continuation_truncation(self):self.reject(f.P+'.mk',lambda t:t+'VM_BAD = \\')
 def test_unknown_generated_cpp(self):
  (self.model/(f.P+'_unknown.cpp')).write_text('TINY')
  with self.assertRaises(ValueError):self.check()
 def test_missing_listed_cpp(self):
  (self.model/(f.P+'__Syms.cpp')).unlink()
  with self.assertRaises(ValueError):self.check()
 def test_class_duplicate(self):self.reject(f.P+'_classes.mk',lambda t:t.replace('\t'+f.P+' \\','\t'+f.P+' '+f.P+' \\'))
 def test_extra_global(self):self.reject(f.P+'_classes.mk',lambda t:t.replace('\tverilated_threads \\','\tverilated_threads verilated_dpi \\'))
 def test_timing_enabled(self):self.reject(f.P+'_classes.mk',lambda t:t.replace('VM_TIMING = 0','VM_TIMING = 1'))
 def test_trace_enabled(self):self.reject(f.P+'_classes.mk',lambda t:t.replace('VM_TRACE = 0','VM_TRACE = 1'))
 def test_unknown_group(self):self.reject(f.P+'_classes.mk',lambda t:t+'VM_BAD += evil\n')
 def test_class_path_escape(self):self.reject(f.P+'_classes.mk',lambda t:t.replace('\t'+f.P+' \\','\t../'+f.P+' \\'))
if __name__=='__main__':unittest.main(verbosity=2)
