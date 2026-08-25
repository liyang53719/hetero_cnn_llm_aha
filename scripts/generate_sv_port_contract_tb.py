#!/usr/bin/env python3
"""Generate a compile-only named-port binding test from a module manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def declaration(port: dict[str, str]) -> str:
    width = port["width"]
    return f"logic {width} {port['name']};" if width != "1" else f"logic {port['name']};"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top", default="tb_generated_port_contract")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    ports = manifest["ports"]
    lines = ["`timescale 1ns/1ps", f"module {args.top};"]
    lines.extend(f"  {declaration(port)}" for port in ports)
    lines.append("")
    lines.append(f"  {manifest['module']} dut (")
    lines.extend(f"    .{port['name']}({port['name']})" + ("," if index + 1 < len(ports) else "")
                 for index, port in enumerate(ports))
    lines.append("  );")
    lines.append("")
    lines.append("  initial begin")
    for port in ports:
        if port["direction"] in {"input", "inout"}:
            lines.append(f"    {port['name']} = '0;")
    if any(port["name"] == "clk" and port["direction"] == "input" for port in ports):
        lines.append("    #1 clk = 1'b1;")
    lines.append("    #1 $finish;")
    lines.append("  end")
    lines.append("endmodule")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n")
    print(f"generated {args.output} for {manifest['module']} ({len(ports)} ports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
