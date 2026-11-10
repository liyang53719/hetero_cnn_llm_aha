from run import *
import importlib.util
p=ROOT/'hetero_recovery_20261014T2131/chisel/continuous_prefill/scripts/attention_sigmoid_reference.py';s=importlib.util.spec_from_file_location('sig',p);sig=importlib.util.module_from_spec(s);s.loader.exec_module(sig)
for u in [0,0x80000000,0x3f000000,0xbf000000,0x3f800000,0xbf800000,0x41980000,0xc1980000,0x42a00000,0xff7f0000]:
 if exp_one(u)[0]!=sig.exp_negative(u):raise ValueError('exp recipe mismatch')
for a,b,k,y,f in [(0x80000000,0x80000000,'add',0x80000000,0),(0x3f800000,0xbf800000,'add',0,0),(0x3f800000,0x40400000,'div',0x3eaaaaab,1),(0x00800000,0x3f000000,'mul',0x00400000,0),(1,0x3f000000,'mul',0,3)]:
 if primitive(a,b,k)!=(y,f):raise ValueError('exact primitive case')
try:primitive(0x3f800000,0,'div')
except ValueError:pass
else:raise ValueError('division zero not rejected')
print('PASS exp recipe10, scalar exact5, zero-denominator rejection; no hardware')
