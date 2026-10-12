#!/usr/bin/env python3
"""Compose/audit the optional Add leaf; never compile, elaborate or fetch tools.

Apply after the exact official_bf16 composer. Only VectorSilu.scala changes.
Baseline sources preserve prepatch IO and arithmetic for an eventual independent
CHIRRTL comparison. The parent coordinates any compiler/frontend resource slot.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

from ..official_bf16 import chisel_policy as policy

HERE = Path(__file__).resolve().parent
VECTOR = policy.PREFIX + 'VectorSilu.scala'
BASE_SHA256 = 'a072de8fa15bd48cfa01806c9f85db9d39776082d287d16ada26efffe238d73f'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit(before, after):
    require(before.keys() == after.keys(), 'source set changed')
    require({p for p in before if before[p] != after[p]} == {VECTOR}, 'patch scope changed')
    require(hashlib.sha256(before[VECTOR].encode()).hexdigest() == BASE_SHA256, 'Vector preimage drift')
    for p in before:
        require(policy.source_inventory(before[p]) == policy.source_inventory(after[p]),
                'arithmetic/module/SRAM constructor drift: ' + p)
    s = after[VECTOR]
    required = (
        'val binaryAdd=if(enableBinaryAdd)Some(Bool())else None',
        'class SiluVectorInput(val lanes: Int,enableBinaryAdd:Boolean=false)',
        'val input = Reg(new SiluVectorInput(lanes,enableBinaryAdd))',
        'input := io.request.bits; phase := 0.U; error := false.B; state := issue',
        'val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))',
        'if(enableBinaryAdd){when(input.binaryAdd.get){',
        'core.io.request.bits.op:=ScalarOp.Add.U',
        'core.io.request.bits.a:=input.gate(i)', 'core.io.request.bits.b:=input.up(i)',
        'when(if(enableBinaryAdd)bad || input.binaryAdd.get || phase === 5.U else bad || phase === 5.U)',
        'require(!enableBinaryAdd || enableTileLoan',
        'new SiluVectorUnit(16,numericPolicy=numericPolicy,enableBinaryAdd=enableBinaryAdd)',
        'if(enableBinaryAdd){vector.io.request.bits.binaryAdd.get:=false.B}',
        'loanActive && vector.io.result.valid && !loanPoison && !p.abort',
        'p.result.ready || loanPoison || p.abort',
        'when(loanActive && vector.io.result.fire)',
        'loanActive:=false.B', 'when(vector.io.result.bits.error){loanPoison:=true.B}',
        'if(enableBinaryAdd){when(error){io.result.bits.value:=0.U.asTypeOf(value)}}',
        'when(p.abort){loanPoison:=true.B}',
        'p.resetRequired:=loanPoison', 'io.resetRequired:=status=/=0.U || loanPoison',
        'Mux(phase===4.U || phase===5.U,F32.bf(cores(i).io.result.bits),cores(i).io.result.bits)',
    )
    for snippet in required:
        require(snippet in s, 'missing Add control invariant: ' + snippet)
    require(s.count('enableBinaryAdd:Boolean=false') == 4, 'default-disabled constructor drift')
    return {'status': 'PASS_VECTOR_ADD_SOURCE_ONLY', 'changed_sources': [VECTOR],
            'source_constructor_inventory_unchanged': True, 'expected_added_state_bits': 1,
            'new_arithmetic_instances': 0, 'new_sram_instances': 0,
            'default_disabled': True, 'default_ir_equivalence_verified': False,
            'scala_compiled': False, 'chisel_elaborated': False, 'rtl_generated': False,
            'hardware_arithmetic_executed': False, 'dense_or_bank_connected': False}


def baseline_source(text):
    # Two actual prepatch modules and their original request/loan types. Keep the
    # result bundle unchanged; it already exists in the assembled source set.
    from ..official_bf16 import check_frontend as front
    helper = front.module('vector_add_baseline_helper', front.ROOT / 'scripts/check_matrix_interface_candidate.py')
    names = ('SiluVectorInput', 'SiluVectorUnit', 'VectorSiluOwner', 'FfnSiluLoanPort')
    body = '\n'.join(helper.declaration(text, name) for name in names)
    for name in names:
        body = re.sub(r'\b' + name + r'\b', name + 'AddBaseline', body)
    for name in ('SiluVectorUnit', 'VectorSiluOwner'):
        body = re.sub(r'(class ' + name + r'AddBaseline\b[^\n]*extends Module \{)',
                      r'\1\n  override def desiredName = "' + name + '"', body)
    return 'package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n' + body + '\n'


def compose(out):
    out = Path(out).resolve()
    require(not out.is_relative_to(policy.ROOT), 'compose outside the repository in a fresh scratch directory')
    paths, parent, _, before = policy.compose(out)
    patch = HERE / 'vector_add.patch'
    require(re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M) == [VECTOR], 'unexpected patch target')
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=out, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=out, check=True)
    after = {p: (out / p).read_text() for p in paths}
    report = audit(before, after)
    baseline = out / 'VectorAddBaseline.scala'
    baseline.write_text(baseline_source(before[VECTOR]))
    entry = out / 'VectorAddElaboration.scala'
    entry.write_bytes((HERE / entry.name).read_bytes())
    report.update(parent_source_audit=parent,
                  patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
                  assembled_source_sha256={p: hashlib.sha256((out / p).read_bytes()).hexdigest() for p in paths},
                  frontend_source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (baseline, entry)})
    return paths, report, before, after


def audit_handshake_dependencies(fir):
    """Conservative CHIRRTL dependency audit of only the new loan handshake.

    Flatten the real consumer, owner and vector control modules. Registers cut
    combinational paths; every possible assignment and its enclosing when/else
    predicate contributes an edge. This is not a general FIRRTL compiler, RTL
    loop check or arithmetic proof. Reject either proposed abort feedback loop.
    """
    text = re.sub(r' @\[[^\]]*\]', '', fir)
    modules = {m[1]: m[0] for m in re.finditer(
        r'^  module (\w+) :.*?(?=^  (?:extmodule|module) |\Z)', text, re.M | re.S)}
    chosen = (('VectorAddHandshakeHarness', 'top'),
              ('VectorSiluOwner', 'top.owner'), ('SiluVectorUnit', 'top.owner.vector'))
    require(all(name in modules for name, _ in chosen), 'missing real handshake/control module')
    graph, registers = {}, set()
    token = re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*')
    for name, prefix in chosen:
        body = modules[name]
        registers.update(prefix + '.' + r for r in re.findall(r'^\s*reg(?:reset)? (\w+) :', body, re.M))
        guards, last_when = [], {}
        def refs(expr):
            # Primitives/literals are harmless unknown leaves. Every real name
            # keeps its exact hierarchy so parent/child connects meet.
            return {prefix + '.' + x for x in token.findall(expr)}
        for line in body.splitlines()[1:]:
            indent = len(line) - len(line.lstrip())
            content = line.strip()
            guards = [(i, g) for i, g in guards if i < indent]
            if content.startswith('when '):
                condition = content[5:].rsplit(':', 1)[0].strip()
                last_when[indent] = condition
                guards.append((indent, condition))
            elif content.startswith('else :'):
                require(indent in last_when, 'unmatched else in dependency audit')
                guards.append((indent, last_when[indent]))
            elif content.startswith('node '):
                lhs, rhs = content[5:].split(' = ', 1)
                graph.setdefault(prefix + '.' + lhs, set()).update(refs(rhs))
            elif content.startswith('connect '):
                lhs, rhs = content[8:].split(', ', 1)
                target = prefix + '.' + lhs
                if any(target == r or target.startswith(r + '.') or target.startswith(r + '[') for r in registers):
                    continue
                graph.setdefault(target, set()).update(refs(rhs))
                for _, guard in guards:
                    graph[target].update(refs(guard))
    roots = ('top.owner.io.loan.abort', 'top.owner.io.loan.result.valid',
             'top.owner.io.loan.result.ready', 'top.owner.io.loan.resetRequired',
             'top.io.write.valid', 'top.io.request.ready')
    require(all(r in graph for r in roots), 'missing audited handshake endpoint')
    visited, active = set(), []
    def walk(node):
        if node in active:
            raise ValueError('combinational handshake cycle: ' + ' -> '.join(active[active.index(node):] + [node]))
        if node in visited:
            return
        active.append(node)
        for dep in graph.get(node, ()):
            walk(dep)
        active.pop(); visited.add(node)
    for root in roots:
        walk(root)
    return {'status': 'PASS_CONSERVATIVE_LOAN_CONTROL_DEPENDENCIES',
            'audited_endpoints': list(roots), 'visited_dependencies': len(visited),
            'full_design_rtl_loop_check': False, 'bank_bridge_included': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    _, report, _, _ = compose(args.out)
    print(json.dumps(report, indent=2))
