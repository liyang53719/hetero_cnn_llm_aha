"""Bit routing and abstract accepted-group contract, not a hardware simulator.

Queue/poison behavior reuses the hash-pinned existing return-tag contract model.
No arithmetic, leaf latency, clock or waveform execution is claimed.
"""
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import re

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
_path = ROOT / "candidates/qwen2_resident_matrix/test_return_tag_contract.py"
_spec = importlib.util.spec_from_file_location("tag_contract", _path)
tag_contract = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tag_contract
_spec.loader.exec_module(tag_contract)
Step, Return = tag_contract.Step, tag_contract.Return


@dataclass(frozen=True)
class Group:
    opcode: int = 0x20
    mask: int = 0xff
    tag: int = 0
    transposed: bool | None = None


def route(a, b, transposed=False):
    """Eight (A16,B32) endpoint operands; bit patterns are never decoded."""
    if len(a) != 16 or len(b) != 256:
        raise ValueError("expected unchanged A16/B256 payload")
    if any(type(x) is not int or not 0 <= x <= 0xffff for x in (*a, *b)):
        raise ValueError("expected 16-bit words")
    return tuple((tuple(a if not transposed or s < 4 else b[128:144]),
                  tuple(b[(s % 4 if transposed else s)*32:
                          (s % 4 if transposed else s)*32+32])) for s in range(8))


def physical_result(leaves, mask=255):
    """Preserve existing 16x256 row-major physical result, no transpose here."""
    if len(leaves) != 8 or any(len(leaf) != 512 for leaf in leaves):
        raise ValueError("expected eight physical 16x32 endpoint returns")
    return tuple(tuple(leaves[c//32][r*32+c%32] if mask & (1 << (c//32)) else 0
                       for c in range(256)) for r in range(16))


class ServiceContract(tag_contract.QueueContract):
    def __init__(self, enabled=False, bits=0):
        self.enabled = enabled
        super().__init__(bits)

    def reset(self):
        super().reset()
        self.group = None
        self.command_count = 0

    def cycle(self, *args, group=None, group_valid=False, command_ready=True,
              endpoint_ready=True, a=None, b=None, **kw):
        old = self.state
        ready = old == "idle" and not self.poison
        group_fire = ready and group_valid
        step = kw.get("step", args[0] if args else None)
        if not endpoint_ready and step is not None:
            legal = (0 <= step.context < 5 and step.clear == (step.context not in self.seen)
                     and step.context not in self.closed and
                     (not step.finish or (step.last and self.closed | {step.context} == self.seen | {step.context})))
            if legal:
                if args:
                    args = (None, *args[1:])
                else:
                    kw["step"] = None
        result = super().cycle(*args, **kw)
        if kw.get("reset", False):
            return result
        issued = old == "command" and command_ready
        if issued:
            self.command_count += self.group.mask.bit_count()
            if self.state == "command":
                self.state = "running"
        if group_fire:
            if group is None or not 0 <= group.opcode <= 255 or not 0 <= group.mask <= 255:
                raise ValueError("invalid group wire value")
            if (group.transposed is None) == self.enabled:
                raise ValueError("mode field presence differs from constructor")
            self.group = group
            self.seen.clear(); self.closed.clear(); self.end_issued = False
            legal = (group.mask != 0 and group.opcode in (0x20, 0x21, 0x23, 0x24) and
                     (not group.transposed or (group.opcode == 0x20 and group.mask == 255)))
            if legal:
                self.state = "command"
            else:
                self.poison = True
                self.state = "finish"
        result.update(group_ready=ready, group_fire=group_fire, command_issued=issued,
                      group_tag=self.group.tag if self.group else None,
                      operands=None)
        if result.get("accepted"):
            result["operands"] = route(a, b, bool(self.group.transposed))
        return result


def retained_counts(fir, bits, enabled):
    leaves = len(re.findall(r"^\s*inst leaves_\d+ of qwen2_matrix_command_endpoint(?:_\d+)?\b", fir, re.M))
    gates = len(re.findall(r"^\s*inst gate(?:_\d+)? of tc_clk_gating(?:_\d+)?\b", fir, re.M))
    if leaves != 8 or gates != 8:
        raise ValueError("retained endpoint or gate count drift")
    group = re.search(r"^\s*reg group : ([^\n]+)", fir, re.M)
    if group is None or ("transposedDense : UInt<1>" in group.group(1)) != enabled:
        raise ValueError("accepted group mode register shape drift")
    for kind, name, depth in (("cmem", "ram", 8), ("reg", "storage", 2)):
        line = re.search(r"^\s*"+kind+" "+name+r" : ([^\n]+)", fir, re.M)
        if line is None or not re.search(r"\}\s*\["+str(depth)+r"\]", line.group(1)):
            raise ValueError("metadata/result depth drift")
        expected = f"returnTag : UInt<{bits}>"
        if (expected in line.group(1)) != (bits > 0):
            raise ValueError("return tag width drift")
        if "transposedDense" in line.group(1):
            raise ValueError("mode incorrectly duplicated in per-step/result storage")
    if not re.search(r"regreset seen : UInt<5>", fir) or not re.search(r"regreset closed : UInt<5>", fir):
        raise ValueError("five-context bookkeeping drift")
    return {"retained_endpoints": leaves, "clock_gates": gates, "physical_fma_lanes": 4096,
            "retained_contexts": 5, "metadata_depth": 8, "result_depth": 2,
            "added_group_register_bits": int(enabled), "added_operand_buffers": 0,
            "conservative_unshared_data_mux_bit_selects": 3072 if enabled else 0,
            "source_shared_mux_bit_selects": 2304 if enabled else 0,
            "physical_area_or_timing_measured": False}


class OperandGraph:
    """Only unconditional operand cones in exactly one MatrixPipelineService.

    Other modules and unrelated FSM last-connect assignments are not evaluated.
    Every definition reachable from an operand root must be unique. Both mux
    branches are checked structurally before selecting one for bit evaluation.
    """
    def __init__(self, fir):
        modules = list(re.finditer(r"^  (?:public )?(?:extmodule|module) (\S+)\s*:", fir, re.M))
        selected = [i for i, m in enumerate(modules) if m.group(1) == "MatrixPipelineService"]
        if len(selected) != 1:
            raise ValueError("expected exactly one MatrixPipelineService module")
        index = selected[0]
        body = fir[modules[index].end():modules[index+1].start() if index+1 < len(modules) else len(fir)]
        definitions = {}
        for line in body.splitlines():
            node = re.match(r"(\s*)node (\S+) = (.*)", line)
            connect = re.match(r"(\s*)connect (\S+), (.*)", line)
            if node or connect:
                indent, name, value = (node or connect).groups()
                definitions.setdefault(name, []).append((value, len(indent)))
        self.nodes, active = {}, set()

        def visit(expr):
            if expr in self.nodes:
                return
            if expr in active:
                raise ValueError("cyclic operand-cone definition: "+expr)
            if expr in definitions:
                if len(definitions[expr]) != 1:
                    raise ValueError("duplicate operand-cone definition: "+expr)
                value, indent = definitions[expr][0]
                if indent != 4:
                    raise ValueError("conditional operand-cone definition: "+expr)
                active.add(expr); visit(value); active.remove(expr)
                self.nodes[expr] = value
                return
            if expr == "group.transposedDense":
                return
            if expr == "io.port.group.bits.transposedDense":
                raise ValueError("operand cone depends on live group pin")
            word = re.fullmatch(r"io\.port\.step\.bits\.(a|b)\[(\d+)\]", expr)
            if word and int(word.group(2)) < (16 if word.group(1) == "a" else 256):
                return
            operation = re.fullmatch(r"(cat|mux)\((.*)\)", expr)
            if operation:
                args = self.arguments(operation.group(2))
                if len(args) != (2 if operation.group(1) == "cat" else 3):
                    raise ValueError("operand-cone expression arity")
                for arg in args:
                    visit(arg)
                return
            raise ValueError("unsupported operand-cone expression: "+expr)

        for leaf in range(8):
            for operand in ("a", "b"):
                visit(f"leaves_{leaf}.step_{operand}_i")

    @staticmethod
    def arguments(expr):
        args, depth, start = [], 0, 0
        for i, char in enumerate(expr):
            depth += (char == "(") - (char == ")")
            if depth < 0:
                raise ValueError("unbalanced operand-cone expression")
            if char == "," and depth == 0:
                args.append(expr[start:i].strip()); start = i+1
        args.append(expr[start:].strip())
        if depth or any(not arg for arg in args):
            raise ValueError("unbalanced or empty operand-cone expression")
        return args

    def evaluate(self, a, b, accepted_mode, live_mode):
        cache = {"group.transposedDense": (int(accepted_mode), 1),
                 "io.port.group.bits.transposedDense": (int(live_mode), 1)}
        cache.update({f"io.port.step.bits.a[{i}]": (v, 16) for i, v in enumerate(a)})
        cache.update({f"io.port.step.bits.b[{i}]": (v, 16) for i, v in enumerate(b)})
        seen_inputs = set()

        def value(expr):
            if expr in cache:
                seen_inputs.add(expr)
                return cache[expr]
            if expr in self.nodes:
                answer = value(self.nodes[expr]); cache[expr] = answer
                return answer
            if expr.startswith("cat("):
                left, right = map(value, self.arguments(expr[4:-1]))
                return ((left[0] << right[1]) | right[0], left[1]+right[1])
            if expr.startswith("mux("):
                pred, yes, no = self.arguments(expr[4:-1])
                return value(yes if value(pred)[0] else no)
            raise ValueError("unsupported operand-cone expression: "+expr)

        routed = []
        for leaf in range(8):
            aw, awidth = value(f"leaves_{leaf}.step_a_i")
            bw, bwidth = value(f"leaves_{leaf}.step_b_i")
            if (awidth, bwidth) != (256, 512):
                raise ValueError("endpoint operand ABI width drift")
            routed.append((tuple((aw >> (16*i)) & 65535 for i in range(16)),
                           tuple((bw >> (16*i)) & 65535 for i in range(32))))
        if "io.port.group.bits.transposedDense" in seen_inputs:
            raise ValueError("operand cone depends on live group pin")
        return tuple(routed)


def graph_checks(fir, enabled):
    import random
    graph = OperandGraph(fir)
    rng = random.Random(0x20261011)
    patterns = [0, 0x8000, 1, 0x7f, 0x80, 0x3f80, 0xbf80, 0x7f80, 0xff80, 0x7fc1, 0x7f81, 0xffff]
    vectors = [(list(range(16)), list(range(256)))]
    vectors += [([patterns[(i+k) % len(patterns)] for i in range(16)],
                 [patterns[(3*i+k) % len(patterns)] for i in range(256)]) for k in range(len(patterns))]
    vectors += [([rng.randrange(65536) for _ in range(16)], [rng.randrange(65536) for _ in range(256)]) for _ in range(8)]
    checks = 0
    for mode in (False, True) if enabled else (False,):
        for live in (False, True):
            for a, b in vectors:
                got = graph.evaluate(a, b, mode, live)
                if got != route(a, b, mode):
                    raise ValueError("emitted operand cone differs from contract")
                # Independently inspect all 4096 physical multiplication coordinates.
                for s, (wa, xb) in enumerate(got):
                    for r in range(16):
                        for c in range(32):
                            expect_a = (a if not mode or s < 4 else b[128:144])[r]
                            expect_b = b[((s % 4) if mode else s)*32+c]
                            if (wa[r], xb[c]) != (expect_a, expect_b):
                                raise ValueError("physical operand coordinate mismatch")
                            checks += 1
    return {"operand_pair_coordinates_checked": checks, "vectors": len(vectors),
            "live_group_mode_perturbed": True, "scope": "CHIRRTL combinational operand cone only"}
