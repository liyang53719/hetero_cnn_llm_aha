"""Synthetic compilation receipts only. Never compiles or runs an ELF.
Global Make bytes are a tiny synthetic stand-in in these unit fixtures; separate
actual retained-O0 replay validates the real fixed official Make/hash contract.
"""
import copy,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
import driver_dependency_proof as d
P=pathlib.Path

def hp(text,path):
 raw=text.encode();return dict(path=path,text=text,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def native(argv):return dict(argv=list(argv),native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
def fixture(policy):
 root='/synthetic/producer';cwd=root+'/obj';driver=root+'/driver.cpp';new=policy==d.CPP_O1_POLICY;overrides=d.CPP_O1_OVERRIDES if new else d.CPP_O0_OVERRIDES
 tool=dict(schema='INSTALLED_GNU_BUILD_TOOLS_V1',compile_tools={k:'/synthetic/tools/'+k for k in ('make','cxx','ar','ranlib','perl','python')});tool['pins']={v:'9'*64 for v in tool['compile_tools'].values()}
 libs=['V'+n+'/lib'+n+'.a'for n in d.CHILDREN];argvs=d.expected_phase_argv(cwd,tool['compile_tools'],overrides,libs)
 hierarchy=hp('VM_HIER_LIBS := '+' '.join(libs)+'\n',cwd+'/VHostBlockTopV4_hier.mk');host=hp('driver.o: '+driver+'\n\t$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<\n',cwd+'/VHostBlockTopV4.mk');globalmk=hp('SYNTHETIC OFFICIAL MAKE STAND-IN\n',root+'/verilated.mk')
 implementations=d.O1_PRODUCER_IMPLEMENTATION_PINS if new else d.PRODUCER_IMPLEMENTATION_PINS;collector=d.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA if new else d.PRODUCER_DEPENDENCY_CAPTURE_SHA
 generation={root+'/candidates/ci_frontend_pipeline_r2_20261029/'+k:v for k,v in dict(implementations,**{'driver_dependency_proof.py':collector}).items()};generation[globalmk['path']]=globalmk['sha256']
 m=dict(source_commit='a'*40,generation_input_pins=generation,derived_generated_pins={x['path']:x['sha256']for x in(host,hierarchy)})
 records=[];summaries=[]
 for index,(name,argv)in enumerate(argvs.items()):
  receipt=native(argv);output=dict(path=str(P(argv[2])/argv[-1]),bytes=100+index,sha256=str(index+1)*64);records.append(dict(phase=name,argv=argv,output=output,supervisor=receipt));row=dict(phase=name,output_sha256=output['sha256'],native_exit=0,supervisor_receipt_sha256=d.digest(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()))
  if new:row['argv']=argv
  summaries.append(row)
 r=dict(schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2'if new else'ACTUAL_FRESH_DRIVER_DEPENDENCY_V1',cwd=cwd,driver=driver,host_hierarchy=hierarchy,host_make=host,global_make=globalmk,make_closure_pins={x['path']:x['sha256']for x in(host,hierarchy)},host_link_receipt=records[-1]['supervisor'],host_link_argv=records[-1]['argv'],binary=records[-1]['output'])
 build=dict(source_commit='a'*40,binary_sha256=records[-1]['output']['sha256'],phases=summaries)
 if new:
  r['compilation_phases']=records
  for h in(r,m,build):h.update(cpp_build_policy=d.CPP_O1_POLICY,cpp_build_overrides=list(d.CPP_O1_OVERRIDES))
 return r,m,build,tool

class PolicyTests(unittest.TestCase):
 def setUp(self):
  self.r,self.m,self.b,self.t=fixture(d.CPP_O1_POLICY);self.patch=patch.object(d,'GLOBAL_MK_SHA',self.r['global_make']['sha256']);self.patch.start();self.addCleanup(self.patch.stop)
 def verify(self):return d.verify_compilation_policy(self.r,self.m,self.b,self.t)
 def reject(self):
  with self.assertRaises((ValueError,KeyError)):self.verify()
 def test_exact_new_policy_all_five_real_receipt_shapes(self):
  v=self.verify();self.assertEqual(v['policy'],d.CPP_O1_POLICY);self.assertEqual(v['actual_compilation_phases'],5)
 def test_old_missing_fields_only_matches_old_code(self):
  self.r,self.m,self.b,self.t=fixture(d.CPP_O0_POLICY);self.assertEqual(self.verify()['policy'],d.CPP_O0_POLICY)
 def test_old_with_new_label_reject(self):
  self.r,self.m,self.b,self.t=fixture(d.CPP_O0_POLICY);self.r['cpp_build_policy']=d.CPP_O1_POLICY;self.reject()
 def test_new_missing_policy_reject(self):del self.b['cpp_build_policy'];self.reject()
 def test_new_legacy_collector_reject(self):
  key=next(k for k in self.m['generation_input_pins']if k.endswith('/driver_dependency_proof.py'));self.m['generation_input_pins'][key]=d.PRODUCER_DEPENDENCY_CAPTURE_SHA;self.reject()
 def test_new_legacy_producer_reject(self):
  key=next(k for k in self.m['generation_input_pins']if k.endswith('/build_producer.py'));self.m['generation_input_pins'][key]=d.PRODUCER_IMPLEMENTATION_PINS['build_producer.py'];self.reject()
 def test_self_reported_arbitrary_collector_reject(self):
  key=next(k for k in self.m['generation_input_pins']if k.endswith('/driver_dependency_proof.py'));self.m['generation_input_pins'][key]='0'*64;self.reject()
 def test_every_phase_override_mutation_reject(self):
  for i in range(5):
   for flag in ('OPT_FAST=-O0','OPT_SLOW=-O3','OPT_GLOBAL=-Ofast','CXXFLAGS=-O1 -ffast-math'):
    r,m,b,t=fixture(d.CPP_O1_POLICY);record=r['compilation_phases'][i];prefix=flag.split('=')[0]+'=';argv=list(record['argv']);argv[next(j for j,x in enumerate(argv)if x.startswith(prefix))]=flag;record['argv']=argv;record['supervisor']['argv']=argv;b['phases'][i]['argv']=argv;b['phases'][i]['supervisor_receipt_sha256']=d.digest(json.dumps(record['supervisor'],sort_keys=True,separators=(',',':')).encode())
    with self.subTest(i=i,flag=flag),self.assertRaises(ValueError):d.verify_compilation_policy(r,m,b,t)
 def test_extra_lto_pgo_native_and_flags_reject(self):
  for extra in ('-flto','-fprofile-use','-march=native','CXXFLAGS=-O1','USER_CPPFLAGS=-O3','EXTRA=-Ofast'):
   self.r,self.m,self.b,self.t=fixture(d.CPP_O1_POLICY);row=self.r['compilation_phases'][0];row['argv'].insert(-1,extra);self.reject()
 def test_no_misleading_metadata_with_original_O0_argv(self):
  r,m,b,t=fixture(d.CPP_O0_POLICY);r['schema']='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2';r['compilation_phases']=self.r['compilation_phases']
  for h in(r,m,b):h.update(cpp_build_policy=d.CPP_O1_POLICY,cpp_build_overrides=d.CPP_O1_OVERRIDES)
  with self.assertRaises(ValueError):d.verify_compilation_policy(r,m,b,t)
 def test_missing_phase_reject(self):self.r['compilation_phases'].pop(0);self.reject()
 def test_reordered_phase_reject(self):self.r['compilation_phases'].reverse();self.reject()
 def test_native_bool_reject(self):self.r['compilation_phases'][1]['supervisor']['native_exit']=False;self.reject()
 def test_cleanup_or_capture_incomplete_reject(self):
  for key in ('pipe_eof_observed','gzip_finalized'):
   self.r,self.m,self.b,self.t=fixture(d.CPP_O1_POLICY);self.r['compilation_phases'][1]['supervisor']['log_capture'][key]=False;self.reject()
 def test_unbound_compiler_receipt_reject(self):self.b['phases'][0]['supervisor_receipt_sha256']='0'*64;self.reject()
 def test_changed_global_make_reject(self):self.m['generation_input_pins'][self.r['global_make']['path']]='0'*64;self.reject()
 def test_other_target_or_hierarchy_reject(self):self.r['compilation_phases'][0]['output']['path']='/other/lib.a';self.reject()
 def test_CXXFLAGS_one_argument_exact(self):
  for row in self.r['compilation_phases']:
   flags=[x for x in row['argv']if x.startswith('CXXFLAGS=')];self.assertEqual(flags,['CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off'])
 def test_new_fixed_producer_and_collector_bytes(self):
  pipeline=P(__file__).resolve().parents[2]/'ci_frontend_pipeline_r2_20261029'
  for name,want in d.O1_PRODUCER_IMPLEMENTATION_PINS.items():self.assertEqual(d.sha(pipeline/name),want)
  self.assertEqual(d.sha(pipeline/'driver_dependency_proof.py'),d.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA)

class ProducerPlanTests(unittest.TestCase):
 """Actual prepare/phase factory on synthetic Make trees; no compiler execution.
 Only the separately tested historical hardware-baseline gate is stubbed here.
 """
 def build(self):
  import types
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=P(self.tmp.name);obj=root/'obj';obj.mkdir();repo=P(__file__).resolve().parents[3];pipeline=repo/'candidates/ci_frontend_pipeline_r2_20261029';spec=importlib.util.spec_from_file_location('strict_o1_test_producer',pipeline/'build_producer.py');producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
  driver=root/'host_axi_driver_non_dpi.cpp';driver.write_bytes((repo/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp').read_bytes())
  for name in ('tool','hardware.sv','source.json','tools.json'):(root/name).write_bytes(b'SYNTHETIC NONEXECUTABLE')
  host=obj/'VHostBlockTopV4.mk';host.write_text('default: VHostBlockTopV4\nVM_USER_CLASSES = host_axi_driver_non_dpi\nVM_USER_DIR = '+str(root)+'\nVM_USER_LDLIBS = -lcrypto\nVM_USER_CFLAGS = -std=c++17 -I'+str(root)+'\ninclude VHostBlockTopV4_hier.mk\nVHostBlockTopV4: objects\n')
  libs=['V'+n+'/lib'+n+'.a'for n in producer.CHILDREN];(obj/'VHostBlockTopV4_hier.mk').write_text('ifndef VM_HIER_VERILATION_INCLUDED\nVM_HIER_LIBS := '+' '.join(libs)+'\nendif\n')
  for name in producer.CHILDREN:
   child=obj/('V'+name);child.mkdir();(child/('V'+name+'.mk')).write_text('lib'+name+'.a: objects\n')
  pins={str(p):producer.sha(p)for p in root.rglob('*')if p.is_file()};makepins={p:h for p,h in pins.items()if p.endswith('.mk')};tool=str(root/'tool');b=dict(schema='FIXED_BINARY_BUILD_BINDING_V1',source_commit='a'*40,cpp_build_policy=producer.CPP_POLICY,cpp_build_overrides=list(producer.CPP_OVERRIDES),pins=pins,driver=str(driver),obj=str(obj),make=tool,cxx=tool,ar=tool,sv=str(root/'hardware.sv'),source_manifest=str(root/'source.json'),tool_manifest=str(root/'tools.json'),compile_tools={k:tool for k in ('ranlib','perl','python')},shared_tree_cap=4<<30)
  b['admission']=dict(source_commit='a'*40,status='ACTUAL_MAKE_CLOSURE_REVIEWED',make_closure_pins=makepins,no_implicit_frontend=True,cpp_build_policy=producer.CPP_POLICY,cpp_build_overrides=list(producer.CPP_OVERRIDES),header_122_observation_ports_and_driver_ABI_reviewed=True)
  b['budgets']={name:dict(seconds=1,rss_gib=1,tree_bytes=1<<20)for name in ['archive_'+x for x in producer.CHILDREN]+['host_archive','host_link']}
  self.enter=patch.dict(sys.modules,{'observer_baseline_gate':types.SimpleNamespace(require_accepted_baseline=lambda _:None)});self.enter.start();self.addCleanup(self.enter.stop);return producer,b
 def test_actual_prepare_generates_exact_uniform_O1_five_phase_argv(self):
  producer,b=self.build();plan=producer.prepare(b);self.assertEqual(len(plan['phases']),5);self.assertEqual(plan['cpp_build_policy'],d.CPP_O1_POLICY)
  for row in plan['phases']:
   self.assertEqual([x for x in row['argv']if x.startswith(('OPT_FAST=','OPT_SLOW=','OPT_GLOBAL=','CXXFLAGS='))],d.CPP_O1_OVERRIDES)
 def test_actual_prepare_rejects_legacy_boolean_or_extra_flag(self):
  producer,b=self.build();b['admission']['uniform_O0_no_fast_math']=True
  with self.assertRaises(ValueError):producer.prepare(b)
  del b['admission']['uniform_O0_no_fast_math'];b['cpp_build_overrides'].append('CXXFLAGS=-O3')
  with self.assertRaises(ValueError):producer.prepare(b)

# Official Verilator 5.032 Make template, exact original retained source (not generated C++).
OFFICIAL_GLOBAL_MAKE_TEXT='# -*- Makefile -*-\n######################################################################\n# DESCRIPTION: Makefile commands for all verilated target files\n#\n# Copyright 2003-2025 by Wilson Snyder. This program is free software; you\n# can redistribute it and/or modify it under the terms of either the GNU\n# Lesser General Public License Version 3 or the Perl Artistic License\n# Version 2.0.\n# SPDX-License-Identifier: LGPL-3.0-only OR Artistic-2.0\n######################################################################\n\n# Tool names.\n# These are computed at configuration time, and most are not ?=\n# to avoid picking up potentially incorrect Make implicit variables\nAR = ar\nCXX = g++\nLINK = g++\nOBJCACHE ?= \nPERL = perl\nPYTHON3 = python3\n\n# Configuration time options\nCFG_WITH_CCWARN = no\nCFG_WITH_LONGTESTS = no\n\n# Compiler version found during configure. This make variable is not used\n# here, but note that if this differs from what `$(CXX) --version` prints,\n# then there may be strange results such as unexpected warnings, as\n# configure determines compiler characteristics.\nCFG_CXX_VERSION = "g++ (Debian 14.2.0-19) 14.2.0"\n\n# Compiler flags to enable profiling\nCFG_CXXFLAGS_PROFILE =  -pg\n# Select language required to compile (often empty)\nCFG_CXXFLAGS_STD = \n# Select newest language (unused by this Makefile, for some test\'s Makefiles)\nCFG_CXXFLAGS_STD_NEWEST = -std=gnu++17\n# Compiler flags to use to turn off unused and generated code warnings, such as -Wno-div-by-zero\nCFG_CXXFLAGS_NO_UNUSED =  -faligned-new -fcf-protection=none -Wno-bool-operation -Wno-shadow -Wno-sign-compare -Wno-tautological-compare -Wno-uninitialized -Wno-unused-but-set-parameter -Wno-unused-but-set-variable -Wno-unused-parameter -Wno-unused-variable\n# Compiler flags that turn on extra warnings\nCFG_CXXFLAGS_WEXTRA =  -Wextra -Wfloat-conversion -Wlogical-op\n# Compiler flags that enable coroutine support\nCFG_CXXFLAGS_COROUTINES = -fcoroutines\n# Compiler flags when creating a precompiled header\nCFG_CXXFLAGS_PCH = -x c++-header\n# Compiler option to put in front of filename to read precompiled header\nCFG_CXXFLAGS_PCH_I = -include\n# Compiler\'s filename prefix for precompiled headers, .gch if clang, empty if GCC\nCFG_GCH_IF_CLANG = \n# Linker flags\nCFG_LDFLAGS_VERILATED = \n# Linker libraries for multithreading\nCFG_LDLIBS_THREADS =  -pthread -lpthread -latomic\n\n######################################################################\n# Programs\n\nVERILATOR_COVERAGE = $(PERL) $(VERILATOR_ROOT)/bin/verilator_coverage\nVERILATOR_INCLUDER = $(PYTHON3) $(VERILATOR_ROOT)/bin/verilator_includer\nVERILATOR_CCACHE_REPORT = $(PYTHON3) $(VERILATOR_ROOT)/bin/verilator_ccache_report\n\n######################################################################\n# CCACHE flags (via environment as no command line option available)\n\nCCACHE_SLOPPINESS ?= pch_defines,time_macros\nexport CCACHE_SLOPPINESS\n\n######################################################################\n# Make checks\n\nifneq ($(words $(CURDIR)),1)\n $(error Unsupported: GNU Make cannot build in directories containing spaces, build elsewhere: \'$(CURDIR)\')\nendif\n\n######################################################################\n# OS detection\nUNAME_S := $(shell uname -s)\n\n######################################################################\n# C Preprocessor flags\n\n# Add -MMD -MP if you\'re using a recent version of GCC.\nVK_CPPFLAGS_ALWAYS += \\\n\t\t-MMD \\\n\t\t-I$(VERILATOR_ROOT)/include \\\n\t\t-I$(VERILATOR_ROOT)/include/vltstd \\\n\t\t-DVM_COVERAGE=$(VM_COVERAGE) \\\n\t\t-DVM_SC=$(VM_SC) \\\n\t\t-DVM_TIMING=$(VM_TIMING) \\\n\t\t-DVM_TRACE=$(VM_TRACE) \\\n\t\t-DVM_TRACE_FST=$(VM_TRACE_FST) \\\n\t\t-DVM_TRACE_VCD=$(VM_TRACE_VCD) \\\n\t\t$(CFG_CXXFLAGS_NO_UNUSED) \\\n\nifeq ($(CFG_WITH_CCWARN),yes)  # Local... Else don\'t burden users\nVK_CPPFLAGS_WALL += -Wall $(CFG_CXXFLAGS_WEXTRA) -Werror\nendif\n\nCPPFLAGS += -I. $(VK_CPPFLAGS_WALL) $(VK_CPPFLAGS_ALWAYS)\n\nVPATH += ..\nVPATH += $(VERILATOR_ROOT)/include\nVPATH += $(VERILATOR_ROOT)/include/vltstd\n\nLDFLAGS  += $(CFG_LDFLAGS_VERILATED)\n\n#OPT = -ggdb -DPRINTINITSTR -DDETECTCHANGE\n#OPT = -ggdb -DPRINTINITSTR\nCPPFLAGS += $(OPT)\n\n# On macOS, specify all weak symbols as dynamic_lookup.\n# Otherwise, you get undefined symbol errors.\nifeq ($(UNAME_S),Darwin)\n\tLDFLAGS += -Wl,-U,__Z15vl_time_stamp64v,-U,__Z13sc_time_stampv\nendif\n\n# Allow upper level user makefiles to specify flags they want.\n# These aren\'t ever set by Verilator, so users are free to override them.\nCPPFLAGS += $(USER_CPPFLAGS)\nLDFLAGS  += $(USER_LDFLAGS)\nLDLIBS   += $(USER_LDLIBS)\n\n# Add flags from -CFLAGS and -LDFLAGS on Verilator command line\nCPPFLAGS += $(VM_USER_CFLAGS)\nLDFLAGS  += $(VM_USER_LDFLAGS)\nLDLIBS   += $(VM_USER_LDLIBS)\n\n######################################################################\n# Optimization control.\n\n# See also the BENCHMARKING & OPTIMIZATION section of the manual.\n\n# Optimization flags for non performance-critical/rarely executed code.\n# No optimization by default, which improves compilation speed.\nOPT_SLOW =\n# Optimization for performance critical/hot code. Most time is spent in these\n# routines. Optimizing by default for improved execution speed.\nOPT_FAST = -Os\n# Optimization applied to the common run-time library used by verilated models.\n# For compatibility this is called OPT_GLOBAL even though it only applies to\n# files in the run-time library. Normally there should be no need for the user\n# to change this as the library is small, but can have significant speed impact.\nOPT_GLOBAL = -Os\n\n#######################################################################\n##### Profile builds\n\nifeq ($(VM_PROFC),1)\n  CPPFLAGS += $(CFG_CXXFLAGS_PROFILE)\n  LDFLAGS  += $(CFG_CXXFLAGS_PROFILE)\nendif\n\n#######################################################################\n##### SystemC builds\n\nifeq ($(VM_SC),1)\n  CPPFLAGS += $(SYSTEMC_CXX_FLAGS) $(addprefix -I, $(SYSTEMC_INCLUDE))\n  LDFLAGS  += $(SYSTEMC_CXX_FLAGS) $(addprefix -L, $(SYSTEMC_LIBDIR))\n  SC_LIBS   = -lsystemc\n ifneq ($(wildcard $(SYSTEMC_LIBDIR)/*numeric_bit*),)\n  # SystemC 1.2.1beta\n  SC_LIBS   += -lnumeric_bit -lqt\n endif\nendif\n\n#######################################################################\n##### Threaded builds\n\nCPPFLAGS += $(CFG_CXXFLAGS_STD)\nLDLIBS += $(CFG_LDLIBS_THREADS)\n\nifneq ($(VM_TIMING),0)\n ifneq ($(VM_TIMING),)\n  CPPFLAGS += $(CFG_CXXFLAGS_COROUTINES)\n endif\nendif\n\n\n#######################################################################\n### Aggregates\n\nVM_FAST += $(VM_CLASSES_FAST) $(VM_SUPPORT_FAST)\nVM_SLOW += $(VM_CLASSES_SLOW) $(VM_SUPPORT_SLOW)\n\n# Precompiled header filename\nVK_PCH_H = $(VM_PREFIX)__pch.h\n# Compiler read-a-precompiled-header option for precompiled header filename\nVK_PCH_I_FAST = $(CFG_CXXFLAGS_PCH_I) $(VM_PREFIX)__pch.h.fast$(CFG_GCH_IF_CLANG)\nVK_PCH_I_SLOW = $(CFG_CXXFLAGS_PCH_I) $(VM_PREFIX)__pch.h.slow$(CFG_GCH_IF_CLANG)\n\n#######################################################################\n### Overall Objects Linking\n\nVK_OBJS_FAST = $(addsuffix .o, $(VM_FAST))\nVK_OBJS_SLOW = $(addsuffix .o, $(VM_SLOW))\n\nVK_USER_OBJS = $(addsuffix .o, $(VM_USER_CLASSES))\n\n# Note VM_GLOBAL_FAST and VM_GLOBAL_SLOW holds the files required from the\n# run-time library. In practice everything is actually in VM_GLOBAL_FAST,\n# but keeping the distinction for compatibility for now.\nVK_GLOBAL_OBJS = $(addsuffix .o, $(VM_GLOBAL_FAST) $(VM_GLOBAL_SLOW))\n\n# Need to re-build if the generated makefile changes, as compiler options might\n# have changed.\n$(VK_GLOBAL_OBJS): $(VM_PREFIX).mk\n\nifneq ($(VM_PARALLEL_BUILDS),1)\n  # Fast build for small designs: All .cpp files in one fell swoop. This\n  # saves total compute, but can be slower if only a little changes. It is\n  # also a lot slower for medium to large designs when the speed of the C\n  # compiler dominates, which in this mode is not parallelizable.\n\n  VK_OBJS += $(VM_PREFIX)__ALL.o\n  $(VM_PREFIX)__ALL.cpp: $(addsuffix .cpp, $(VM_FAST) $(VM_SLOW))\n\t$(VERILATOR_INCLUDER) -DVL_INCLUDE_OPT=include $^ > $@\n  all_cpp: $(VM_PREFIX)__ALL.cpp\nelse\n  # Parallel build: Each .cpp file by itself. This can be somewhat slower for\n  # very small designs and examples, but is a lot faster for large designs.\n\n  VK_OBJS += $(VK_OBJS_FAST) $(VK_OBJS_SLOW)\nendif\n\n# When archiving just objects (.o), use single $(AR) run\n#   1. Make .verilator_deplist.tmp file with list of objects so don\'t exceed\n#      the command line limits when calling $(AR).\n#      The approach to write the dependency file is compatible with GNU Make 3,\n#      and can be simplified using the file function once GNU Make 4.x becomes\n#      the minimum supported version.\n# When merging objects (.o) and archives (.a) additionally:\n#   1. Extract object files from .a\n#   2. Create a new archive from extracted .o and given .o\n%.a: | %.verilator_deplist.tmp\n\t$(foreach L, $(filter-out %.a,$^), $(shell echo $L >>$@.verilator_deplist.tmp))\n\t@if test $(words $(filter %.a,$^)) -eq 0; then \\\n\t\t$(RM) -f $@; \\\n\t\tcat $@.verilator_deplist.tmp | xargs $(AR) -rc $@; \\\n\t\t$(AR) -s $@; \\\n\telse \\\n\t\t$(RM) -rf $@.tmpdir; \\\n\t\tfor archive in $(filter %.a,$^); do \\\n\t\t\tmkdir -p $@.tmpdir/$$(basename $${archive}); \\\n\t\t\tcd $@.tmpdir/$$(basename $${archive}); \\\n\t\t\t$(AR) -x ../../$${archive}; \\\n\t\t\tcd ../..; \\\n\t\tdone; \\\n\t\t$(RM) -f $@; \\\n\t\tcat $@.verilator_deplist.tmp | xargs $(AR) -rc $@; \\\n\t\t$(AR) -rcs $@ $@.tmpdir/*/*.o; \\\n\tfi \\\n\t; $(RM) -rf $@.verilator_deplist.tmp $@.tmpdir\n\n# Truncate the dependency list file used in the %.a target above.\n%.verilator_deplist.tmp:\n\techo "" > $@\n\n$(VM_PREFIX)__ALL.a: $(VK_OBJS) $(VM_HIER_LIBS)\n\n\n######################################################################\n### Compile rules\n\nifneq ($(VM_DEFAULT_RULES),0)\n# Compilation rule for anything not in $(VK_OBJS_FAST), $(VK_OBJS_SLOW), or\n# $(VK_GLOBAL_OBJS) including verilated.o.  This typically means user files\n# passed on the Verilator command line.\n#\n# These rules put OPT_FAST/OPT_SLOW/OPT_GLOBAL before the other flags to\n# allow USER_CPPFLAGS to override them\n%.o: %.cpp\n\t$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n\n$(VK_OBJS_FAST): %.o: %.cpp $(VK_PCH_H).fast.gch\n\t$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) $(VK_PCH_I_FAST) -c -o $@ $<\n\n$(VK_OBJS_SLOW): %.o: %.cpp $(VK_PCH_H).slow.gch\n\t$(OBJCACHE) $(CXX) $(OPT_SLOW) $(CXXFLAGS) $(CPPFLAGS) $(VK_PCH_I_SLOW) -c -o $@ $<\n\n$(VK_GLOBAL_OBJS): %.o: %.cpp\n\t$(OBJCACHE) $(CXX) $(OPT_GLOBAL) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n\n# Precompile a header file\n# PCH\'s compiler flags must match exactly the rules\' above FAST/SLOW\n# arguments used for the .cpp files, or the PCH file won\'t be used.\n%.fast.gch: %\n\t$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) $(CFG_CXXFLAGS_PCH) $< -o $@\n%.slow.gch: %\n\t$(OBJCACHE) $(CXX) $(OPT_SLOW) $(CXXFLAGS) $(CPPFLAGS) $(CFG_CXXFLAGS_PCH) $< -o $@\n\nendif\n\n#Default rule embedded in make:\n#.cpp.o:\n#\t$(CXX) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n\n######################################################################\n### ccache report\n\nifneq ($(findstring ccache-report,$(MAKECMDGOALS)),)\n  ifneq ($(OBJCACHE),ccache)\n    $(error ccache-report requires OBJCACHE to equal \'ccache\')\n  endif\n  VK_OTHER_GOALS := $(strip $(subst ccache-report,,$(MAKECMDGOALS)))\n  ifeq ($(VK_OTHER_GOALS),)\n    $(error ccache-report must be used with at least one other explicit target)\n  endif\n\n  # Report ccache behaviour for this invocation of make\n  VK_CCACHE_LOGDIR := ccache-logs\n  VK_CCACHE_REPORT := $(VM_PREFIX)__ccache_report.txt\n  # Remove previous logfiles and report\n  $(shell rm -rf $(VK_CCACHE_LOGDIR) $(VK_CCACHE_REPORT))\n\n$(VK_CCACHE_LOGDIR):\n\tmkdir -p $@\n\n$(VK_OBJS): | $(VK_CCACHE_LOGDIR)\n\n$(VK_OBJS): export CCACHE_LOGFILE=$(VK_CCACHE_LOGDIR)/$@.log\n\n$(VK_CCACHE_REPORT): $(VK_OBJS)\n\t$(VERILATOR_CCACHE_REPORT) -o $@ $(VK_CCACHE_LOGDIR)\n\n.PHONY: ccache-report\nccache-report: $(VK_CCACHE_REPORT)\n\t@cat $<\n\n# ccache-report runs last\nccache-report: $(VK_OTHER_GOALS)\nendif\n\n######################################################################\n### Debugging\n\ndebug-make::\n\t@echo\n\t@echo CPPFLAGS: $(CPPFLAGS)\n\t@echo CXXFLAGS: $(CXXFLAGS)\n\t@echo OPT_FAST: $(OPT_FAST)\n\t@echo OPT_SLOW: $(OPT_SLOW)\n\t@echo VK_OBJS: $(VK_OBJS)\n\t@echo VK_OBJS_FAST: $(VK_OBJS_FAST)\n\t@echo VK_OBJS_SLOW: $(VK_OBJS_SLOW)\n\t@echo VM_CLASSES_FAST: $(VM_CLASSES_FAST)\n\t@echo VM_CLASSES_SLOW: $(VM_CLASSES_SLOW)\n\t@echo VM_GLOBAL_FAST: $(VM_GLOBAL_FAST)\n\t@echo VM_GLOBAL_SLOW: $(VM_GLOBAL_SLOW)\n\t@echo VM_PARALLEL_BUILDS:  $(VM_PARALLEL_BUILDS)\n\t@echo VM_PREFIX:  $(VM_PREFIX)\n\t@echo VM_SUPPORT_FAST: $(VM_SUPPORT_FAST)\n\t@echo VM_SUPPORT_SLOW: $(VM_SUPPORT_SLOW)\n\t@echo\n\n######################################################################\n### Detect out of date files and rebuild.\n\nDEPS := $(wildcard *.d)\nifneq ($(DEPS),)\ninclude $(DEPS)\nendif\n'

class AllProfileHandoffGateTests(unittest.TestCase):
 """Unmocked common handoff policy gate. Metadata/native receipts are synthetic;
 only official fixed Make template text is actual retained tool source bytes.
 No binary execution, numeric claim, or P0 coverage waiver.
 """
 def fixture(self,policy):
  import artifact_handoff as a
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=P(self.tmp.name)
  r,m,b,t=fixture(policy)
  r['global_make']=hp(OFFICIAL_GLOBAL_MAKE_TEXT,r['global_make']['path']);m['generation_input_pins'][r['global_make']['path']]=r['global_make']['sha256']
  m.update(sv_sha256='7'*64,driver_sha256='8'*64,p0_retained_evidence={'driver_dependency':r})
  frozen=dict(artifact_identity={'source_commit':'a'*40},common={'sv':{'sha256':'7'*64},'driver':{'sha256':'8'*64}})
  if policy==d.CPP_O1_POLICY:frozen.update(cpp_build_policy=policy,cpp_build_overrides=list(d.CPP_O1_OVERRIDES))
  def run():
   (root/'source_manifest.json').write_text(json.dumps(m));(root/'tool_manifest.json').write_text(json.dumps(t));return a.verify_compilation_policy(frozen,root,b)
  return r,m,b,frozen,run
 def test_all_profiles_common_gate_new_five_receipts_no_mock(self):
  r,m,b,f,run=self.fixture(d.CPP_O1_POLICY);out=run();self.assertEqual(out['policy'],d.CPP_O1_POLICY);self.assertEqual(out['actual_compilation_phases'],5)
 def test_historical_O0_unmodified_label_no_mock(self):
  r,m,b,f,run=self.fixture(d.CPP_O0_POLICY);self.assertEqual(run()['policy'],d.CPP_O0_POLICY)
 def test_old_frozen_self_labels_O1_reject(self):
  r,m,b,f,run=self.fixture(d.CPP_O0_POLICY);f.update(cpp_build_policy=d.CPP_O1_POLICY,cpp_build_overrides=d.CPP_O1_OVERRIDES)
  with self.assertRaises(ValueError):run()
 def test_nonhost_archive_wrong_flags_reject(self):
  r,m,b,f,run=self.fixture(d.CPP_O1_POLICY);r['compilation_phases'][2]['argv'][4]='OPT_FAST=-O0'
  with self.assertRaises(ValueError):run()
 def test_source_identity_drift_reject(self):
  r,m,b,f,run=self.fixture(d.CPP_O1_POLICY);m['source_commit']='b'*40
  with self.assertRaises(ValueError):run()
 def test_host_make_semantics_not_whitespace_only_reject(self):
  r,m,b,f,run=self.fixture(d.CPP_O1_POLICY);h=r['host_make'];h.update(hp(h['text'].replace('$(OPT_FAST)','$(OPT_FAST) -ffast-math'),h['path']));r['make_closure_pins'][h['path']]=m['derived_generated_pins'][h['path']]=h['sha256']
  with self.assertRaises(ValueError):run()

if __name__=='__main__':unittest.main()
