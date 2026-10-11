"""Executable tile/SFU control slice; injected arithmetic and latency are not RTL.

The physical SRAM service is model.TileBankModel. This bounded controller
checks the same tag snapshots and post-release fence as FfnTileSiluBridge.
Its SFU callable is an opaque functional dependency: numerical validation of
the unchanged 16-lane recipe lives in check_numeric.py instead.
"""
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("ffn_bridge_banks", Path(__file__).with_name("model.py"))
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


@dataclass(frozen=True)
class Invocation:
    identity: int
    ng: int
    rows: int
    cols: int


class BridgeModel:
    def __init__(self, banks, arithmetic, latency=3):
        if latency < 1:
            raise ValueError("positive injected SFU latency required")
        self.banks, self.arithmetic, self.latency = banks, arithmetic, latency
        self.state, self.call, self.index = "idle", None, 0
        self.poison, self.gate, self.sfu = False, None, None
        self.completions, self.requests = 0, 0

    @property
    def busy(self):
        return self.state not in ("idle", "locked")

    @staticmethod
    def expected(c):
        return c.rows//16*c.cols

    def matches(self, t, c):
        return (t.identity, t.ng, t.rows, t.cols, t.expected) == (
            c.identity, c.ng, c.rows, c.cols, self.expected(c))

    def admitted(self, c):
        return (m.TileBankModel._key_valid(m.Read(0, c.identity, c.ng, 0)) and
                c.rows in (16, 128) and c.cols in (32, 64, 96, 128, 160) and
                all(t.live and t.sealed and self.matches(t, c) and
                    t.produced == t.expected and t.consumed == 0 for t in self.banks.tags[:2]) and
                not self.banks.tags[2].live and self.banks.idle and self.sfu is None)

    def retired(self):
        t = self.banks.tags[2]
        return (all(not x.live for x in self.banks.tags[:2]) and
                t.live and t.sealed and self.matches(t, self.call) and
                t.produced == t.expected and t.consumed == 0 and
                self.banks.idle and self.sfu is None)

    def tick(self, *, start=None, abort=False, sfu_ready=True, bank_ready=True,
             external_response_ready=False, coordinated_reset=False):
        if coordinated_reset:
            self.banks.tick(coordinated_reset=True)
            self.state, self.call, self.index = "idle", None, 0
            self.poison, self.gate, self.sfu = False, None, None
            return {"start_fire": False, "complete": False, "reset": True}
        state = self.state
        drained_at_edge = self.banks.idle and self.sfu is None
        response = self.banks.response
        result = self.sfu if self.sfu is not None and self.sfu[0] == 0 else None
        bad = abort or self.poison or self.banks.poison or bool(response and response.error)
        bad = bad or bool(result and result[2])
        start_fire = start is not None and state == "idle" and self.banks.idle and not bad
        complete = state == "retire" and self.retired() and not bad
        ctl = read = write = None
        response_ready = external_response_ready if not self.busy else (
            bad or state == "gateWait" or (state == "upWait" and sfu_ready))
        if not bad and state in ("begin", "seal", "releaseGate", "releaseUp"):
            ctl = m.Control(0 if state == "begin" else 1 if state == "seal" else 2,
                            0 if state == "releaseGate" else 1 if state == "releaseUp" else 2,
                            self.call.identity, self.call.ng, self.call.rows, self.call.cols)
        if not bad and state in ("gateRead", "upRead"):
            read = m.Read(0 if state == "gateRead" else 1, self.call.identity, self.call.ng, self.index)
        if not bad and state == "result" and result:
            write = m.Write(2, self.call.identity, self.call.ng, self.index, result[1])
        e = self.banks.tick(control=ctl, read=read, write=write, response_ready=response_ready,
                            abort=bad, owner_quiescent=bank_ready)
        if self.sfu is not None and self.sfu[0] > 0:
            self.sfu = (self.sfu[0]-1, self.sfu[1], self.sfu[2])
        if start_fire:
            self.call, self.index = start, 0
            self.state = "begin" if self.admitted(start) else "locked"
            self.poison = self.state == "locked"
        if e["ctl_fire"]:
            self.state = {"begin": "gateRead", "seal": "releaseGate",
                          "releaseGate": "releaseUp", "releaseUp": "retire"}[state]
        if e["read_fire"]:
            self.state = "gateWait" if state == "gateRead" else "upWait"
        if e["response_fire"] and not bad and state == "gateWait":
            self.gate, self.state = e["response"].words, "upRead"
        if e["response_fire"] and not bad and state == "upWait":
            words, error = self.arithmetic(self.gate, e["response"].words)
            self.sfu = (self.latency, words, error)
            self.requests += 1
            self.state = "result"
        if e["write_fire"]:
            self.sfu = None
            self.index += 1
            self.state = "seal" if self.index == self.expected(self.call) else "gateRead"
        if state == "retire":
            self.state = "idle" if complete else "drain"
            self.poison |= not complete
            self.completions += int(complete)
        if bad:
            self.poison = True
            self.state = "locked" if state in ("idle", "locked") else "drain"
            if result:
                self.sfu = None
        if (state == "drain" or bad) and drained_at_edge:
            self.state = "locked"
        return {**e, "start_fire": start_fire, "complete": complete,
                "state": self.state, "reset_required": self.poison or self.banks.poison}
