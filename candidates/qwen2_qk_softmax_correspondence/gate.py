"""Pinned source projection only: no production import, compiler or numerical execution.

This is a deliberately narrow recognizer for two exact source versions, not a
Scala interpreter, a generic equivalence prover, or a hardware acceptance gate.
Its executable check enumerates integer Matrix cell coordinates. Arithmetic
nodes are compared symbolically; no FMA, BF16, exp, or softmax is evaluated.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
PINS_SHA256 = '45a636cc2c267af6328a5bbe08bb1e5f0c6571810bf46c866e822ba0f69e530b'
PREFIX = 'candidates/qwen2_resident_matrix/'
SCALA = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'
SNAPSHOT = 'development_snapshots/canonical_host_observation_taps_source_20261017/baseline/Qwen2Block.scala'
SCHEDULE = PREFIX + 'attention_packed_owner/schedule.py'
CLIENT = PREFIX + 'attention_packed_owner/client.py'
M16_PATCH = PREFIX + 'attention_packed_m16/m16.patch'
M128_PATCH = PREFIX + 'attention_packed_m128/tiled.patch'
M128_PINS = PREFIX + 'attention_packed_m128/pins.json'
POSTIMAGE = PREFIX + 'production_qk16_rebase/POSTIMAGE_PINS.json'
EVIDENCE = 'reports/execution/QWEN2_SAME_HOST_M128_REPLAY_IDENTITY_20261017/'
UNPROVEN = (
    'six_head_schedule_equivalence', 'shared_bank_scratch_ack_release',
    'physical_384_byte_panel', 'pv6_supply_and_context_retention',
    'final_all_resource_debt_join', 'scalar_exception_policy_equivalence',
    'full_block_source_binding', 'explicit_mask_tensor_observation',
    'official_softmax_fp32_elementwise_acceptance',
)


class Rejected(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise Rejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def invalid(value):
        raise Rejected('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_bound(root, relative, record):
    path = root / relative
    need(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
         'SOURCE_PATH')
    need(all(not p.is_symlink() for p in (path, *path.parents)), 'SOURCE_SYMLINK')
    need(path.is_file() and path.stat().st_size == record['bytes'] and
         record['bytes'] <= 2 * 1024 * 1024, 'SOURCE_SIZE:' + relative)
    raw = path.read_bytes()
    need(len(raw) == record['bytes'] and sha(raw) == record['sha256'],
         'SOURCE_HASH:' + relative)
    return raw


def apply_target_patch(source, patch, target):
    """Apply only the target's exact line-number hunks, with no fuzz or offset.

    The entire patch is separately hash-bound. No patch subprocess is used and
    no other file is installed. Generated schedule SHA is checked afterwards.
    """
    lines = patch.splitlines(keepends=True)
    marker = '--- a/' + target + '\n'
    starts = [i for i, line in enumerate(lines) if line == marker]
    need(len(starts) == 1, 'PATCH_TARGET')
    i = starts[0] + 1
    need(i < len(lines) and lines[i] == '+++ b/' + target + '\n', 'PATCH_NEW_TARGET')
    i += 1
    original = source.splitlines(keepends=True)
    result, cursor, hunks = [], 0, 0
    while i < len(lines) and not lines[i].startswith('--- a/'):
        m = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n', lines[i])
        need(m is not None, 'PATCH_HUNK_HEADER')
        old_start, old_count, new_start, new_count = map(int, m.groups())
        need(old_start >= 1 and new_start >= 1 and old_start - 1 >= cursor,
             'PATCH_HUNK_ORDER')
        result.extend(original[cursor:old_start - 1])
        need(len(result) == new_start - 1, 'PATCH_OFFSET')
        i += 1
        old, new = [], []
        while i < len(lines) and not lines[i].startswith(('@@ ', '--- a/')):
            line = lines[i]
            need(line[:1] in (' ', '+', '-'), 'PATCH_LINE')
            if line[0] in (' ', '-'):
                old.append(line[1:])
            if line[0] in (' ', '+'):
                new.append(line[1:])
            i += 1
        need(len(old) == old_count and len(new) == new_count, 'PATCH_COUNTS')
        need(original[old_start - 1:old_start - 1 + old_count] == old, 'PATCH_CONTEXT')
        result.extend(new)
        cursor = old_start - 1 + old_count
        hunks += 1
    need(hunks > 0, 'PATCH_EMPTY')
    result.extend(original[cursor:])
    return ''.join(result)


def dump(node):
    return ast.dump(node, include_attributes=False)


def expression(text):
    return ast.parse(text, mode='eval').body


def equal_ast(actual, expected, code):
    need(dump(actual) == dump(expected), code)


def unique(nodes, code):
    need(len(nodes) == 1, code)
    return nodes[0]


def integer(node, values):
    """Tiny integer-expression evaluator, not eval/compile of selected sources."""
    if isinstance(node, ast.Constant):
        need(type(node.value) is int and 0 <= node.value <= 256, 'INTEGER_LITERAL')
        return node.value
    if isinstance(node, ast.Name):
        need(node.id in values, 'INTEGER_NAME')
        return values[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        a, b = integer(node.left, values), integer(node.right, values)
        return a + b if isinstance(node.op, ast.Add) else a * b
    raise Rejected('INTEGER_EXPRESSION')


FOLD = '''for local in range(count):
    total=0
    for x in lanes[local*16:(local+1)*16]:
        total=o._op('add',total,x)
    score=o._op('bf',o._op('mul',o._op('bf',total),0x3db504f3))
    scores.append(score)
    if o._less(maxima[h],score):
        maxima[h]=score
'''


def python_projection(source, client):
    tree = ast.parse(source)
    cls = unique([n for n in tree.body if isinstance(n, ast.ClassDef) and
                  n.name == 'PackedSchedule'], 'PYTHON_SCHEDULE_CLASS')
    run = unique([n for n in cls.body if isinstance(n, ast.FunctionDef) and
                  n.name == 'run'], 'PYTHON_RUN')
    nodes = list(ast.walk(run))
    calls = [n for n in nodes if isinstance(n, ast.Call)]
    qk = unique([n for n in calls if isinstance(n.func, ast.Name) and
                 n.func.id == 'PackedRequest' and n.args and
                 dump(n.args[0]) == dump(expression('0x23'))], 'PYTHON_QK_REQUEST')
    need(len(qk.args) == 8 and not qk.keywords, 'PYTHON_QK_ABI')
    qk_assignment = unique([n for n in nodes if isinstance(n, ast.Assign) and
                           isinstance(n.value, ast.Yield) and n.value.value is qk],
                           'PYTHON_QK_ASSIGNMENT')
    need([dump(n) for n in qk_assignment.targets] ==
         [dump(ast.parse('result=0').body[0].targets[0])], 'PYTHON_QK_RESULT_BINDING')
    selector = qk.args[-1]
    need(isinstance(selector, ast.IfExp), 'PYTHON_SELECTOR_CONDITION')
    equal_ast(selector.test, expression('final'), 'PYTHON_SELECTOR_CONDITION')
    equal_ast(selector.orelse, expression('()'), 'PYTHON_NONFINAL_SELECTOR')
    selected = selector.body
    need(isinstance(selected, ast.Call) and dump(selected.func) == dump(expression('tuple'))
         and len(selected.args) == 1 and not selected.keywords and
         isinstance(selected.args[0], ast.GeneratorExp), 'PYTHON_SELECTOR_GENERATOR')
    gen = selected.args[0]
    expected_gen = expression('(r for k in range(count) for r in range(16))')
    need([dump(g) for g in gen.generators] == [dump(g) for g in expected_gen.generators],
         'PYTHON_SELECTOR_ORDER')
    need(isinstance(gen.elt, ast.Tuple) and len(gen.elt.elts) == 2, 'PYTHON_COORDINATES')
    consume = ast.parse('lanes=result.selected_words()').body[0]
    need(sum(dump(n) == dump(consume) for n in nodes) == 1, 'PYTHON_QK_RESULT_CONSUMER')
    fold = unique([n for n in nodes if isinstance(n, ast.For) and
                   isinstance(n.target, ast.Name) and n.target.id == 'local' and
                   any(isinstance(c, ast.Assign) and any(isinstance(t, ast.Name) and
                       t.id == 'score' for t in c.targets) for c in n.body)], 'PYTHON_FOLD')
    equal_ast(fold, ast.parse(FOLD).body[0], 'PYTHON_FOLD_SCORE_MAX_TOPOLOGY')
    exp = unique([n for n in calls if isinstance(n.func, ast.Name) and
                  n.func.id == 'exp_negative'], 'PYTHON_EXP')
    equal_ast(exp, expression("exp_negative(o.scalar,o,o._op('add',score,maxima[h]^0x80000000))"),
              'PYTHON_SOFTMAX_SUBTRACT')
    for fragment, code in (
        ("self.scratch('write',generation,token,kv,4096+8*h+first//16,tuple(scores)+(0,)*(16-count))", 'PYTHON_SCORE_WRITE'),
        ("self.scratch('read',generation,token,kv,4096+8*h+first//16)", 'PYTHON_SCORE_READ'),
    ):
        need(sum(dump(n) == dump(expression(fragment)) for n in calls) == 1, code)
    score_read = ast.parse("scores=(yield self.scratch('read',generation,token,kv,4096+8*h+first//16)).words").body[0]
    need(sum(dump(n) == dump(score_read) for n in nodes) == 1, 'PYTHON_SCORE_READ_BINDING')
    exp_loop = unique([n for n in nodes if isinstance(n, ast.For) and
                      any(c is exp for c in ast.walk(n)) and
                      dump(n.target) == dump(ast.parse('score=0').body[0].targets[0])],
                      'PYTHON_SOFTMAX_LOOP')
    equal_ast(exp_loop.iter, expression('scores[:count]'), 'PYTHON_SOFTMAX_SCORE_BINDING')
    ctree = ast.parse(client)
    for name, fields in (
        ('PackedRequest', 'opcode: int\na: tuple\nb: tuple\nclear: bool\nlast: bool\nsteps: int\nslice_mask: int = 1\nselected: tuple = ()'),
        ('PackedResult', 'tag: PackedTag\nservice_result: object\nselected: tuple'),
    ):
        record = unique([n for n in ctree.body if isinstance(n, ast.ClassDef) and
                         n.name == name], 'PYTHON_RECORD:' + name)
        need([dump(n) for n in record.body if isinstance(n, ast.AnnAssign)] ==
             [dump(n) for n in ast.parse(fields).body], 'PYTHON_RECORD_FIELDS:' + name)
        if name == 'PackedResult':
            value = unique([n for n in record.body if isinstance(n, ast.FunctionDef) and
                            n.name == 'value'], 'PYTHON_RESULT_VALUE')
            need([dump(n) for n in value.body] ==
                 [dump(n) for n in ast.parse('return self.service_result.value').body],
                 'PYTHON_RESULT_VALUE_FORWARDING')
    forward = ast.parse('self.response=PackedResult(self.tag,result,self.request.selected)').body[0]
    need(sum(dump(n) == dump(forward) for n in ast.walk(ctree)) == 1,
         'PYTHON_RESULT_SELECTED_FORWARDING')
    method = unique([n for n in ast.walk(ctree) if isinstance(n, ast.FunctionDef)
                     and n.name == 'selected_words'], 'PYTHON_SELECTED_WORDS')
    body = method.body[1:] if isinstance(method.body[0], ast.Expr) and isinstance(
        method.body[0].value, ast.Constant) and isinstance(method.body[0].value.value, str) else method.body
    expected = ast.parse('self.check_selected()\nreturn tuple(self.value[row][column] for row,column in self.selected)').body
    need([dump(n) for n in body] == [dump(n) for n in expected], 'PYTHON_SELECTED_WORDS_ORDER')
    return gen.elt.elts


TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[A-Za-z_$][\w$]*|\d+|\S')


def tokens(source):
    return [s for s in TOKEN.findall(source) if not s.startswith(('//', '/*'))]


def compact(source):
    return ''.join(tokens(source))


def state_block(source, name):
    words = tokens(source)
    prefix = tokens('when(state===st("' + name + '")')
    positions = [i for i in range(len(words) - len(prefix) + 1)
                 if words[i:i + len(prefix)] == prefix]
    start = unique(positions, 'SCALA_STATE_COUNT:' + name)
    opening = words.index('{', start)
    depth = 1
    end = opening + 1
    while end < len(words) and depth:
        depth += (words[end] == '{') - (words[end] == '}')
        end += 1
    need(depth == 0, 'SCALA_STATE_BALANCE')
    return ''.join(words[start:opening]), ''.join(words[opening + 1:end - 1])


SCALA_BODIES = {
    'attReduce': 'calc(ScalarOp.Add,sum,acc(lane),"attReduceDone")',
    'attReduceDone': '''sum:=scalarValue;when(lane===15.U){
        val dotValue=materialize(scalarValue)
        when(enableProductionPackedQk16.B && !TensorMath.finite(dotValue)){packedSelectedFault:=true.B}
        .otherwise{calc(ScalarOp.Mul,dotValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}
        }.otherwise{lane:=lane+1.U;state:=st("attReduce")}''',
    'attScore': '''val score=materialize(scalarValue)
        when(enableProductionPackedQk16.B && !TensorMath.finite(score)){packedSelectedFault:=true.B}
        .otherwise{if(enableProductionPackedQk16){packedCommitted.get:=packedSelected.get+&1.U===packedKeys};scores.write(key+packedSelected.getOrElse(0.U),score);when(F32.less(maxScore,score)){maxScore:=score};state:=st("attNextKey")}''',
    'attExpWait': 'calc(ScalarOp.Add,scoreOut,F32.neg(maxScore),"attExpDiff")',
    'attExpDiff': 'calc(ScalarOp.ExpNegative,scalarValue,0.U,"attExpResult")',
}


def scala_projection(source):
    text = compact(source)
    for fragment, code in (
        ('require(!enableProductionPackedQk16 || (ownerDriven && externalMatrix && Qwen2NumericPolicy.official(numericPolicy)), "production QK16 requires the official external-Matrix owner; capacity stays 1024")', 'SCALA_OFFICIAL_OPT_IN'),
        ('private val officialBf16=Qwen2NumericPolicy.official(numericPolicy)', 'SCALA_POLICY_BINDING'),
        ('def materialize(x:UInt):UInt=if(officialBf16)F32.bf(x)else x', 'SCALA_MATERIALIZE_BINDING'),
        ('val scoreOut=scores.read(key,state===st("attExpRead"))', 'SCALA_SCORE_READ'),
        ('val packedSelected=if(enableProductionPackedQk16)Some(RegInit(0.U(4.W)))else None', 'SCALA_SELECTED_WIDTH'),
        ('val packedKeys=Mux(token-key>=15.U,16.U(5.W),(token-key+1.U)(4,0))', 'SCALA_KEY_TAIL_DOMAIN'),
        ('when(depth===112.U){acc:=fmOut;lane:=0.U;sum:=0.U;state:=st("attReduce")}', 'SCALA_FIRST_FOLD_INIT'),
        ('.otherwise{acc:=selected;lane:=0.U;sum:=0.U;state:=st("attReduce")}', 'SCALA_HELD_FOLD_INIT'),
    ):
        need(text.count(compact(fragment)) == 1, code)
    for name, expected in SCALA_BODIES.items():
        header, body = state_block(source, name)
        if name == 'attScore':
            expected_header = 'when(state===st("attScore") && (!enableProductionPackedQk16.B || (!poisoned && !packedQk.map(_.io.resetRequired).getOrElse(false.B) && !packedQk.map(_.io.port.done.valid).getOrElse(false.B))))'
        else:
            expected_header = 'when(state===st("' + name + '"))'
        need(header == compact(expected_header) and body == compact(expected),
             'SCALA_TOPOLOGY:' + name)
    # Both the initial-result and retained-result reads must have the same map.
    initial = re.findall(r'for\(i<-0until(\d+)\)\{fmOut\(i\):=c\.io\.result\.bits\.value\(i\)\(\(packedSelected\.get<<(\d+)\)\+i\.U\)\}', text)
    held = re.findall(r'valselected=VecInit\(\(0until(\d+)\)\.map\(i=>packedQk\.get\.io\.result\.bits\.value\(i\)\(\(packedSelected\.get<<(\d+)\)\+i\.U\)\)\)', text)
    initial_lanes, shift = map(int, unique(initial, 'SCALA_INITIAL_SELECTION'))
    lanes, held_shift = map(int, unique(held, 'SCALA_HELD_SELECTION'))
    need(shift == held_shift and shift <= 8 and lanes == initial_lanes == 16,
         'SCALA_SELECTION_AGREEMENT')
    return shift


def check_coordinates(py_coordinates, scala_shift):
    checked = 0
    for count in range(1, 17):
        actual = [(integer(py_coordinates[0], {'k': k, 'r': lane}),
                   integer(py_coordinates[1], {'k': k, 'r': lane}))
                  for k in range(count) for lane in range(16)]
        expected = [(lane, (k << scala_shift) + lane)
                    for k in range(count) for lane in range(16)]
        need(actual == expected, 'QK_SELECTED_CELL_MAPPING')
        need(len(set(actual)) == count * 16 and all(0 <= r < 16 and 0 <= c < 256
             for r, c in actual), 'QK_SELECTED_CELL_BOUNDS')
        checked += len(actual)
    return {'tail_key_counts': list(range(1, 17)), 'ordered_coordinate_comparisons': checked,
            'full_tile_unique_cells': 256, 'integer_only': True}


def inspect(root):
    raw = (HERE / 'SOURCE_PINS.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'PIN_MANIFEST_HASH')
    pins = strict_json(raw)
    root = Path(root).absolute()
    sources = {name: read_bound(root, name, record) for name, record in pins['sources'].items()}
    postimages = strict_json(sources[POSTIMAGE])
    post = unique([p for p in postimages if p['path'] == SCALA], 'POSTIMAGE_TARGET')
    need(post['post_sha256'] == pins['target_postimage_sha256'] == sha(sources[SNAPSHOT]),
         'POSTIMAGE_IDENTITY')
    generated = apply_target_patch(sources[SCHEDULE].decode(), sources[M16_PATCH].decode(), SCHEDULE)
    generated = apply_target_patch(generated, sources[M128_PATCH].decode(), SCHEDULE)
    need(sha(generated.encode()) == pins['derived_schedule_sha256'] ==
         strict_json(sources[M128_PINS])['generated'][SCHEDULE], 'COMPOSED_SCHEDULE_IDENTITY')
    py = python_projection(generated, sources[CLIENT].decode())
    scala_shift = scala_projection(sources[SNAPSHOT].decode())
    coordinates = check_coordinates(py, scala_shift)
    receipt = strict_json(sources[EVIDENCE + 'full_m128_summary.json'])
    archive = strict_json(sources[EVIDENCE + 'MANIFEST.json'])
    need(receipt['status'] == 'PASS_FRESH_SAME_HOST_M128_ASSIGNED27' and
         receipt['validation']['rows'] == 128 and
         receipt['validation']['assigned_official_gates'] == 27 and
         receipt['validation']['official_observed_stages'] == 28 and
         receipt['ci'] == archive['ci'] and
         archive['files']['full_m128_summary.json']['sha256'] ==
             sha(sources[EVIDENCE + 'full_m128_summary.json']) and
         archive['identity_retention']['policy']['missing_stages'] == ['explicit_mask_tensor'] and
         archive['identity_retention']['policy']['diagnostic_stages'] == ['softmax_fp32'],
         'HISTORICAL_SCOPE')
    current_matches = sources[SCALA] == sources[SNAPSHOT]
    main = compact(sources[SCALA].decode())
    return {
        'schema': 1, 'status': 'INCOMPLETE',
        'bounded_slice_status': 'PASS_PINNED_QK_CELL_MAP_AND_SOURCE_TOPOLOGY_ONLY',
        'source_commit': pins['source_commit'],
        'selected_scala': {'kind': 'HISTORICAL_PRODUCTION_POSTIMAGE_NOT_CURRENT_MAIN',
            'path': SNAPSHOT, 'sha256': sha(sources[SNAPSHOT]),
            'postimage_ledger': POSTIMAGE},
        'current_main_binding': {'matches_selected_postimage': current_matches,
            'status': 'MATCH' if current_matches else 'MISMATCH', 'path': SCALA,
            'sha256': sha(sources[SCALA]),
            'has_production_packed_qk16_selector': 'enableProductionPackedQk16' in main,
            'has_official_materialize_function': 'defmaterialize(' in main,
            'att_score_body_matches_selected': state_block(sources[SCALA].decode(), 'attScore')[1] ==
                compact(SCALA_BODIES['attScore'])},
        'python_schedule': {'path': SCHEDULE, 'sha256': sha(generated.encode()),
            'composition': [M16_PATCH, M128_PATCH], 'source_imported': False},
        'coordinate_check': coordinates,
        'symbolic_topology': ['16 ordered Add folds from +0', 'materialize completed dot',
            'Mul by headDim-dependent scale; selected Qwen2 geometry is 128',
            'materialize scaled score', 'same score feeds storage and max update',
            'stored score plus negated per-head max feeds exp'],
        'scope': {'projection_only': True, 'arithmetic_equivalence': False,
            'scalar_arithmetic_executed': False, 'scala_executed': False,
            'native_model_imported': False, 'rtl_executed': False, 'cycle_or_timing_claim': False,
            'full_block_acceptance': False, 'full29_acceptance': False,
            'mask_tensor_fabricated': False, 'new_tolerance': False,
            'scale_constant_numerically_validated': False},
        'unproven': {name: 'INCOMPLETE' for name in UNPROVEN},
        'historical_cold_m128': {'status': receipt['status'], 'ci': receipt['ci'],
            'assigned_gates': 27, 'observed_stages': 28, 'carried': False,
            'model': {k: archive['identity_retention']['model'][k]
                      for k in ('model_id', 'revision', 'layer')},
            'result_reexecuted': False, 'acceptance_inherited_by_this_gate': False},
        'source_pins_sha256': PINS_SHA256,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect(args.source_root)
    except (Rejected, OSError, ValueError, KeyError, TypeError, IndexError, SyntaxError) as exc:
        report = {'schema': 1, 'status': 'REJECTED', 'reason': str(exc),
                  'full_block_acceptance': False}
        print(json.dumps(report, sort_keys=True, indent=2))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    # Partial source success must never masquerade as model/RTL acceptance.
    return 2


if __name__ == '__main__':
    sys.exit(main())
