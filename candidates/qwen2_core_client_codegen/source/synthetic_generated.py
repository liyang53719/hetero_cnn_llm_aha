"""Tiny source fixtures only; never a generated/compiled actual model."""
from pathlib import Path
P='VOrderedQkBehaviorCore'
PORTS={'clock':dict(direction='input',width=1,signed=False),'reset':dict(direction='input',width=1,signed=False),'wide':dict(direction='input',width=512,signed=False),'answer':dict(direction='output',width=32,signed=False)}
def header(ports=PORTS):
 lines=['#ifndef VERILATED_VORDEREDQKBEHAVIORCORE_H_','#define VERILATED_VORDEREDQKBEHAVIORCORE_H_  // guard','#include "verilated.h"','class alignas(VL_CACHE_LINE_BYTES) '+P+' VL_NOT_FINAL : public VerilatedModel {','private:','public:']
 for name,x in ports.items():
  width=x['width'];suffix='8' if width<=8 else '16' if width<=16 else '' if width<=32 else '64' if width<=64 else 'W';word=','+str((width+31)//32) if width>64 else ''
  lines.append('VL_'+('IN' if x['direction']=='input' else 'OUT')+suffix+'(&'+name+','+str(width-1)+',0'+word+');')
 return '\n'.join(lines+['explicit '+P+'(VerilatedContext* contextp, const char* name = "TOP");','explicit '+P+'(const char* name = "TOP");','void eval() { eval_step(); }','void eval_step();','void final();','};','#endif // guard',''])
def top_make(model,harness,tool):
 model=Path(model);harness=Path(harness)
 import os
 dirs=sorted({os.path.relpath(harness.parent,model),os.path.relpath(model.parent,model)})
 fields={'PERL':'perl','PYTHON3':'python3','VERILATOR_ROOT':str(tool),'VM_PROFC':'0','VM_SC':'0','VM_SP_OR_SC':'$(VM_SC)','VM_PCLI':'1','VM_SC_TARGET_ARCH':'','VM_PREFIX':P,'VM_MODPREFIX':P}
 lines=['# synthetic fixed emitter fixture, NOT GENERATED MODEL','default: '+P]+[key+' = '+value for key,value in fields.items()]+['SYSTEMC_INCLUDE ?=','SYSTEMC_LIBDIR ?=']
 for key,items in {'VM_USER_CFLAGS':['-std=c++17'],'VM_USER_LDLIBS':[],'VM_USER_CLASSES':[harness.stem],'VM_USER_DIR':dirs}.items():lines+=[key+' = \\']+['\t'+item+' \\' for item in items]+['']
 lines+=['include '+P+'_classes.mk','include $(VERILATOR_ROOT)/include/verilated.mk','VPATH += $(VM_USER_DIR)',harness.stem+'.o: '+str(harness)+' ','\t$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<',P+': $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)','\t$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@','']
 return '\n'.join(lines)
def classes():
 fields={'VM_C11':'1','VM_TIMING':'0','VM_COVERAGE':'0','VM_PARALLEL_BUILDS':'1','VM_TRACE':'0','VM_TRACE_VCD':'0','VM_TRACE_FST':'0'}
 lines=[key+' = '+value for key,value in fields.items()]
 lists={'VM_CLASSES_FAST':[P],'VM_CLASSES_SLOW':[],'VM_SUPPORT_FAST':[],'VM_SUPPORT_SLOW':[P+'__Syms'],'VM_GLOBAL_FAST':['verilated','verilated_threads'],'VM_GLOBAL_SLOW':[]}
 for key,items in lists.items():lines+=[key+' += \\']+['\t'+item+' \\' for item in items]+['']
 return '\n'.join(lines)+'\n'
def contents(model,harness,tool,ports=PORTS):
 return {P+'.h':header(ports),P+'.cpp':'// SYNTHETIC NOT COMPILED\n',P+'.mk':top_make(model,harness,tool),P+'_classes.mk':classes(),P+'___024root.h':'// SYNTHETIC HEADER\n',P+'__Syms.h':'// SYNTHETIC HEADER\n',P+'__Syms.cpp':'// SYNTHETIC CPP\n',P+'__ver.d':'# SYNTHETIC OPAQUE DEPENDENCY METADATA\n',P+'__verFiles.dat':'SYNTHETIC OPAQUE TIMESTAMPS\n'}
