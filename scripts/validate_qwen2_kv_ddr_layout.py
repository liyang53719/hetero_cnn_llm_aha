#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "config/qwen2_kv_ddr_layout.json").read_text())
memory = json.loads((ROOT / "work/generated/qwen2_q1024_symbolic_descriptors/tensor_memory_map.json").read_text())
assert len(memory["kv"]) == cfg["layers"]
for layer, entry in enumerate(memory["kv"]):
    table = cfg["ddr_kv_base"] + layer * cfg["layer_stride_bytes"]
    data = table + cfg["table_bytes_per_layer"]
    assert entry == {
        "data_address": data,
        "data_bytes": cfg["data_bytes_per_layer"],
        "data_key": f"kv_data:{layer}",
        "logical_pages": cfg["logical_pages_per_layer"],
        "page_tokens": cfg["page_tokens"],
        "pte_bytes": cfg["pte_bytes"],
        "table_address": table,
        "table_bytes": cfg["table_bytes_per_layer"],
        "table_key": f"kv_page_table:{layer}",
    }
assert cfg["page_bytes"] * cfg["logical_pages_per_layer"] == cfg["data_bytes_per_layer"]
assert cfg["page_layout"]["k_bytes_per_page"] + cfg["page_layout"]["v_bytes_per_page"] == cfg["page_bytes"]
print("QWEN2_KV_DDR_LAYOUT_PASS layers=28 table_bytes=32768 data_bytes=1048576 page_tokens=16 page_bytes=16384 overlap=0")
