#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--manifest", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
commands = [json.loads(line) for line in a.manifest.read_text().splitlines()]
command = next(entry for entry in commands if entry["operation"] == "l0.kv_append")
(a.out / "kv_append_command.memh").write_text(command["word"].removeprefix("0x") + "\n")
print(json.dumps({"operation": command["operation"], "roots": command["roots"], "word": command["word"]}, sort_keys=True))
