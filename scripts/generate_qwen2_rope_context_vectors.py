#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--manifest", type=Path, required=True)
p.add_argument("--chains", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
manifest = [json.loads(line) for line in a.manifest.read_text().splitlines()]
commands = [entry for entry in manifest if entry["operation"] in ("l0.q_rope", "l0.k_rope")]
assert [entry["operation"] for entry in commands] == ["l0.q_rope", "l0.k_rope"]
chains = {entry["root"]: entry for entry in map(json.loads, a.chains.read_text().splitlines())}
addresses = []
for command in commands:
    for role in ("src0", "src1", "dst"):
        root = command["roots"][role]
        base = next(record for record in chains[root]["records"] if record["record_type"] == "tensor_base")
        addresses.append(base["address"])
(a.out / "rope_commands.memh").write_text("".join(entry["word"].removeprefix("0x") + "\n" for entry in commands))
(a.out / "rope_addresses.memh").write_text("".join(f"{address:014x}\n" for address in addresses))
(a.out / "position0_beat.memh").write_text("0" * 128 + "\n")
print(json.dumps({"operations": [entry["operation"] for entry in commands], "addresses": addresses}, sort_keys=True))
