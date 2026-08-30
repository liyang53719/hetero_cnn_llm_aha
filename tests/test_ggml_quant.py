from heteronpu.ggml_quant import *
def test_sizes_roundtrip():
 for seed in range(64):
  for block,size in ((random_q8_0(seed),34),(random_q6_k(seed),210),(random_q3_k(seed),110)):
   assert len(block.pack())==size and type(block).unpack(block.pack())==block
def test_grouped_dot():
 for block in (random_q8_0(1),random_q6_k(2),random_q3_k(3)):
  a=[(i-37)/19 for i in range(len(block.dequantize()))];ref=sum(x*y for x,y in zip(a,block.dequantize()));assert abs(dot_groups(block.groups(),a)-ref)<1e-9
def test_fp16():
 p=pack_fp16([0.,-0.,1.,-2.5,65504.]);assert pack_fp16(unpack_fp16(p))==p
def test_contract():
 r=self_test_report(100);assert r['status']=='PASS' and r['maximum_grouped_dot_difference']<1e-8
