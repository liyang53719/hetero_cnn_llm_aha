import unittest,json,re
from pathlib import Path
import conditional_admission as c
D=Path(__file__).parent
class T(unittest.TestCase):
 def test_ports(self):
  p=json.loads((D/'HOST_PORTS.json').read_text());rows=[]
  for n,(d,w) in p.items():
   kind='8' if w<=8 else '16' if w<=16 else '' if w<=32 else '64' if w<=64 else 'W'
   rows.append('VL_'+('IN' if d=='input' else 'OUT')+kind+'(&'+n+','+str(w-1)+',0'+(','+str((w+31)//32) if w>64 else '')+');')
  self.assertEqual(c.header_ports('\n'.join(rows)),p)
 def test_bad_storage(self):self.assertRaises(ValueError,c.header_ports,'VL_IN8(&x,31,0);')
 def test_duplicate_port(self):self.assertRaises(ValueError,c.header_ports,'VL_IN8(&x,0,0);VL_IN8(&x,0,0);')
 def test_unknown_port(self):self.assertRaises(ValueError,c.header_ports,'VL_INOUT8(&x,0,0);')
 def test_hierarchy(self):
  libs=' '.join('V'+n+'/lib'+n+'.a' for n in c.CHILDREN)
  s='ifndef VM_HIER_VERILATION_INCLUDED\nVM_HIER_LIBS := '+libs+'\nendif\n'
  self.assertEqual(len(c.hierarchy(s)),3)
  self.assertRaises(ValueError,c.hierarchy,s.replace('VM_HIER_LIBS','endif\nVM_HIER_LIBS',1))
 def test_unknown_hierarchy(self):self.assertRaises(ValueError,c.hierarchy,'ifndef VM_HIER_VERILATION_INCLUDED\nVM_HIER_LIBS := wrong.a\nendif\n')
 def test_host_expected_official_template(self):
  s="""default: VHostBlockTopV4
PERL = perl
PYTHON3 = python3
VERILATOR_ROOT = /tool
SYSTEMC_INCLUDE ?=
SYSTEMC_LIBDIR ?=
VM_PROFC = 0
VM_SC = 0
VM_SP_OR_SC = $(VM_SC)
VM_PCLI = 1
VM_SC_TARGET_ARCH = linux
VM_PREFIX = VHostBlockTopV4
VM_MODPREFIX = VHostBlockTopV4
VM_USER_CFLAGS = -std=c++17 -I/inc
VM_USER_LDLIBS = -lcrypto
VM_USER_CLASSES = driver
VM_USER_DIR = .. ../../driver
include VHostBlockTopV4_classes.mk
include VHostBlockTopV4_hier.mk
include $(VERILATOR_ROOT)/include/verilated.mk
VPATH += $(VM_USER_DIR)
driver.o: /driver/driver.cpp
 $(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<
VHostBlockTopV4: $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)
 $(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@
"""
  args=('VHostBlockTopV4','/tool','/work/obj','/driver/driver.cpp','/inc','/work')
  c.overall(s,*args)
  for changed in (s.replace('-std=c++17','-Ofast'),s.replace('$(LINK)','evil'),s+'include unknown.mk\n',s.replace('driver.o:', 'other.o:'),s.replace('VM_USER_DIR = .. ../../driver','VM_USER_DIR = .. /wrong')):
   self.assertRaises(ValueError,c.overall,changed,*args)
 def test_arbitrary_overall(self):self.assertRaises(ValueError,c.overall,'default: x\n$(shell echo evil)','Vx','/v','/o','/driver.cpp','/inc','/o')
 def test_class_injection(self):self.assertRaises(ValueError,c.classes,'VM_C11 = $(shell evil)','Vx','/o','/v')
if __name__=='__main__':unittest.main()
