import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.silu_lut_rtl_contract import ROM,bf16_bits,evaluate,fused,lookup

def test_endpoints_and_zero():
 assert lookup(bf16_bits(-8.0))==0.0 and lookup(bf16_bits(8.0))==8.0 and fused(0.0,2.0)==0.0

def test_fixed_index_is_monotonic_near_origin():
 values=[lookup(bf16_bits(-1+i/64)) for i in range(129)];assert all(values[i]<=values[i+1]+1e-7 for i in range(64,128))

def test_random_metrics():
 r=evaluate(50000);assert r['status']=='PASS' and r['metrics']['relative_l2']<.0015

def test_rom_shape(): assert len(ROM)==128 and all(0<=x<65536 for x in ROM)
