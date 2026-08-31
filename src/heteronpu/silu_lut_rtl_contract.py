"""Bit-oriented Golden for the source-ready fused BF16 SiLU(gate)*up RTL."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, math, random, struct

ENTRIES = 128
LIMIT = 8.0
FRAC_BITS = 12

def f32(v: float) -> float: return struct.unpack('<f', struct.pack('<f', float(v)))[0]
def bf16_bits(v: float) -> int:
    raw = struct.unpack('<I', struct.pack('<f', f32(v)))[0]
    if (raw & 0x7f800000) == 0x7f800000 and (raw & 0x007fffff): return ((raw >> 16) | 0x0040) & 0xffff
    raw = (raw + 0x7fff + ((raw >> 16) & 1)) & 0xffffffff
    return (raw >> 16) & 0xffff
def bf16_value(bits: int) -> float: return struct.unpack('<f', struct.pack('<I', (bits & 0xffff) << 16))[0]
def fp16_bits(v: float) -> int: return int.from_bytes(struct.pack('<e', float(v)), 'little')
def fp16_value(bits: int) -> float: return struct.unpack('<e', int(bits).to_bytes(2, 'little'))[0]
def silu(x: float) -> float:
    if x >= 0: return x / (1 + math.exp(-x))
    e = math.exp(x); return x * e / (1 + e)
ROM = tuple(fp16_bits(silu(-LIMIT + i * (2 * LIMIT) / (ENTRIES - 1))) for i in range(ENTRIES))

def bf16_to_q12_sat(bits: int) -> int:
    sign, exp, frac = (bits >> 15) & 1, (bits >> 7) & 0xff, bits & 0x7f
    if exp == 0xff: mag = 32768
    elif exp == 0: mag = 0
    else:
        sig, shift = 128 + frac, exp - 122
        if shift >= 0: mag = sig << shift
        else:
            r = -shift; mag = 0 if r >= 16 else (sig + (1 << (r - 1))) >> r
        mag = min(32768, mag)
    return -mag if sign else mag

def lookup(bits: int) -> float:
    exp, frac, x = (bits >> 7) & 0xff, bits & 0x7f, bf16_value(bits)
    if (bits & 0x7fff) == 0: return 0.0
    if exp == 0xff and frac: return x
    q = bf16_to_q12_sat(bits)
    if q <= -32768: return 0.0
    if q >= 32768: return x
    pos_q12 = ((q + 32768) * 127) >> 4
    index, fraction = min(126, pos_q12 >> 12), (pos_q12 & 0xfff) / 4096.0
    y0, y1 = fp16_value(ROM[index]), fp16_value(ROM[index + 1])
    return f32(y0 + f32((y1 - y0) * fraction))

def fused(gate: float, up: float) -> float:
    gb, ub = bf16_bits(gate), bf16_bits(up)
    return bf16_value(bf16_bits(f32(lookup(gb) * bf16_value(ub))))

@dataclass(frozen=True)
class Metrics:
    cases: int; max_abs: float; mean_abs: float; rmse: float; relative_l2: float

def evaluate(cases: int = 200_000, seed: int = 0x51A9) -> dict[str, object]:
    rng = random.Random(seed); errors=[]; refs=[]; digest=hashlib.sha256()
    for _ in range(cases):
        g=bf16_value(bf16_bits(max(-16,min(16,rng.gauss(0,2.5))))); u=bf16_value(bf16_bits(max(-4,min(4,rng.gauss(0,1.25)))))
        ref=bf16_value(bf16_bits(f32(silu(g)*u))); got=fused(g,u); errors.append(got-ref); refs.append(ref)
        digest.update(struct.pack('<HHf',bf16_bits(g),bf16_bits(u),got))
    mse=sum(e*e for e in errors)/cases; den=sum(r*r for r in refs)/cases
    m=Metrics(cases,max(map(abs,errors)),sum(map(abs,errors))/cases,math.sqrt(mse),math.sqrt(mse/den) if den else 0)
    return {"schema_version":1,"status":"PASS" if m.mean_abs<=.001 and m.relative_l2<=.0015 and m.max_abs<=.25 else "FAIL",
        "metrics":m.__dict__,"rom_entries":ENTRIES,"rom_bits":ENTRIES*16,"range":[-LIMIT,LIMIT],"fraction_bits":FRAC_BITS,
        "sha256":digest.hexdigest(),"evidence_class":"bit_oriented_LUT_contract_E0_not_RTL_E1"}
