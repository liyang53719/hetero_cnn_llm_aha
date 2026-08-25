#!/usr/bin/env python3
"""Audit actual generated Gemmini busy transitions around four programs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

CMD = re.compile(r"GEMMINI_MON_CMD cycle=(\d+) count=(\d+) funct=(\d+)")
BUSY = re.compile(r"GEMMINI_MON_BUSY_(ASSERT|CLEAR) cycle=(\d+) accepted=(\d+)")
FUNCTS = [0, 0, 16, 17, 18, 19, 20, 21, 15] * 4
PASS = "GEMMINI_L2_CONV_REQUANT_EQ_PASS checksum=13907229944436499941"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = args.log.read_text(errors="replace")
    if PASS not in text:
        raise SystemExit("numerical PASS marker absent")
    commands = [{"cycle": int(a), "count": int(b), "funct": int(c)}
                for a, b, c in CMD.findall(text)]
    if [entry["count"] for entry in commands] != list(range(1, 37)):
        raise SystemExit("command counts are not contiguous 1..36")
    if [entry["funct"] for entry in commands] != FUNCTS:
        raise SystemExit("command funct sequence differs from four conv programs")
    transitions = [{"kind": kind, "cycle": int(cycle), "accepted": int(count)}
                   for kind, cycle, count in BUSY.findall(text)]
    completions = []
    for last_count in (9, 18, 27, 36):
        last_cycle = commands[last_count - 1]["cycle"]
        state = False
        start_index = 0
        for index, transition in enumerate(transitions):
            if transition["cycle"] <= last_cycle:
                state = transition["kind"] == "ASSERT"
                start_index = index + 1
        assert_cycle = None
        if not state:
            for index in range(start_index, len(transitions)):
                if transitions[index]["kind"] == "ASSERT":
                    assert_cycle = transitions[index]["cycle"]
                    start_index = index + 1
                    state = True
                    break
        clear_cycle = None
        if state:
            for index in range(start_index, len(transitions)):
                if transitions[index]["kind"] == "CLEAR":
                    clear_cycle = transitions[index]["cycle"]
                    break
        if clear_cycle is None or clear_cycle <= last_cycle:
            raise SystemExit(f"program ending at command {last_count} lacks later busy clear")
        completions.append({"last_command": last_count, "last_cycle": last_cycle,
                            "post_last_assert_cycle": assert_cycle,
                            "busy_clear_cycle": clear_cycle})
    result = {
        "status": "PASS", "retained_rocket_tile": True,
        "generated_gemmini_commands": 36,
        "programs": 4, "completion_observations": completions,
        "checksum": 13907229944436499941,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
