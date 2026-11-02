"""Exact additive read-only host driver relation; no hardware or execution API."""
import hashlib
LEGACY_DRIVER_SHA256 = "343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61"
INSERTIONS = ((b'#include "verilated.h"\n', b'#include "readonly_first_fault.hpp"\n', 'after'), (b' moe_raw_score_observation::Collector rawScores;\n', b' readonly_first_fault::Collector firstFault;\n', 'after'), (b'  if(launched)need(!d.io_resetRequired,"DUT resetRequired");\n', b'  if(launched)firstFault.observe(d,cycles,activeCycles,completions,d.io_resetRequired);\n', 'before'))

def verify_driver(original_bytes, diagnostic_bytes):
    if type(original_bytes) is not bytes or type(diagnostic_bytes) is not bytes:
        raise ValueError("driver bytes required")
    if hashlib.sha256(original_bytes).hexdigest() != LEGACY_DRIVER_SHA256:
        raise ValueError("fixed original driver")
    restored = diagnostic_bytes
    for anchor, addition, side in INSERTIONS:
        joined = addition + anchor if side == "before" else anchor + addition
        if restored.count(addition) != 1 or restored.count(joined) != 1:
            raise ValueError("unique exact diagnostic insertion")
        restored = restored.replace(joined, anchor, 1)
    if restored != original_bytes:
        raise ValueError("original whole driver bytes")
    return {"legacy_driver_sha256": LEGACY_DRIVER_SHA256,
            "diagnostic_driver_sha256": hashlib.sha256(diagnostic_bytes).hexdigest(),
            "exact_inverse": True}
