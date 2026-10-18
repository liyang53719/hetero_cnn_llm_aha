"""Bounded Host93 CHIRRTL structure only. No compiler, simulator, or file writes.

ABI expectations come from the published HostBlockTop port declaration, not
from the submitted FIR. See EXPECTED_SOURCE_EVIDENCE.json. No old 95-source,
Bench, generated-model, arithmetic, or runtime qualification is inherited.
Unknown syntax is an error; the caller must preserve the original FIR.
"""
import collections
import hashlib
import json
import os
import re
import stat

MAX_BYTES = 48 * 1024 * 1024
MAX_DEFINITIONS = 768
MAX_PATHS = 20000
MAX_DEPTH = 128
MAX_TYPE_DEPTH = 32
MAX_LEAVES = 32768
ID = r'[A-Za-z_$][A-Za-z0-9_$]*'
IDENT = re.compile(ID + r'\Z')
TOKEN = re.compile(r'\s*("(?:[^"\\\n]|\\.)*"|0[hb][0-9a-fA-F]+|-?[0-9]+|[A-Za-z_$][A-Za-z0-9_$]*|[{}\[\]()<>,.:=])')


def need(ok, message):
    if not ok:
        raise ValueError(message)


class Reader:
    def __init__(self, text):
        self.tokens = []
        pos = 0
        while pos < len(text):
            m = TOKEN.match(text, pos)
            if m is None and not text[pos:].strip():
                break
            need(m is not None, 'unsupported token near ' + text[pos:pos+80])
            self.tokens.append(m[1]); pos = m.end()
        need(len(self.tokens) <= 262144, 'line token cap')
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def pop(self, expected=None):
        t = self.peek()
        need(t is not None and (expected is None or t == expected), 'expected ' + str(expected) + ', got ' + str(t))
        self.i += 1
        return t

    def ident(self):
        t = self.pop(); need(IDENT.fullmatch(t) is not None, 'identifier required: ' + t); return t

    def integer(self, low=0, high=2**31-1):
        t = self.pop(); need(re.fullmatch(r'-?\d+', t) is not None, 'integer required')
        n = int(t); need(low <= n <= high, 'integer bound'); return n

    def end(self):
        need(self.peek() is None, 'unconsumed syntax: ' + ' '.join(self.tokens[self.i:self.i+16]))

    def type(self, depth=0):
        need(depth <= MAX_TYPE_DEPTH, 'type nesting cap')
        if self.peek() == '{':
            self.pop('{'); fields = []; names = set()
            while self.peek() != '}':
                flip = self.peek() == 'flip'
                if flip: self.pop('flip')
                name = self.ident(); need(name not in names, 'duplicate bundle field ' + name); names.add(name)
                self.pop(':'); fields.append((name, flip, self.type(depth+1)))
                if self.peek() != '}': self.pop(',')
            self.pop('}'); result = ('bundle', tuple(fields))
        else:
            kind = self.ident(); need(kind in ('UInt', 'SInt', 'Clock', 'Reset', 'AsyncReset', 'Analog'), 'unsupported type ' + kind)
            width = 1 if kind in ('Clock', 'Reset', 'AsyncReset') else None
            if self.peek() == '<':
                need(kind in ('UInt', 'SInt', 'Analog'), 'width on non-integer type')
                self.pop('<'); width = self.integer(0, 1048576); self.pop('>')
            result = ('ground', kind, width)
        while self.peek() == '[':
            self.pop('['); n = self.integer(0, 2**31-1); self.pop(']'); result = ('vector', n, result)
        return result

    def expr(self, depth=0):
        need(depth <= MAX_DEPTH, 'expression nesting cap')
        name = self.ident()
        if name in ('UInt', 'SInt') and self.peek() in ('<', '('):
            if self.peek() == '<':
                self.pop('<'); self.integer(0, 1048576); self.pop('>')
            self.pop('('); n = self.pop()
            need(re.fullmatch(r'-?\d+|0[hb][0-9a-fA-F]+|"[hbo][0-9a-fA-F_]+"', n) is not None, 'unsupported integer literal')
            self.pop(')'); return None
        if self.peek() == '(':
            spec = PRIMS.get(name); need(spec is not None, 'unsupported primitive ' + name)
            self.pop('(')
            for index in range(sum(spec)):
                if index: self.pop(',')
                if index < spec[0]: self.expr(depth+1)
                else: self.integer(0, 2**31-1)
            self.pop(')'); return None
        ref = name
        while self.peek() in ('.', '['):
            if self.peek() == '.':
                self.pop('.'); field = self.pop(); need(IDENT.fullmatch(field) or field.isdigit(), 'field required'); ref += '.' + field
            else:
                self.pop('[')
                if self.peek() and self.peek().isdigit():
                    index = self.integer(); ref += '[' + str(index) + ']'
                else:
                    self.expr(depth+1); ref = None
                self.pop(']')
            if ref is None:
                # A dynamic subaccess remains a valid expression, never a direct binding.
                while self.peek() in ('.', '['):
                    if self.peek() == '.': self.pop('.'); self.ident()
                    else: self.pop('['); self.expr(depth+1); self.pop(']')
                break
        return ref


PRIMS = {name: (2, 0) for name in 'add sub mul div rem lt leq gt geq eq neq and or xor cat dshl dshr'.split()}
PRIMS.update({name: (1, 0) for name in 'asUInt asSInt asClock asAsyncReset cvt neg not andr orr xorr'.split()})
PRIMS.update({name: (1, 1) for name in 'pad shl shr head tail'.split()})
PRIMS.update({'bits': (1, 2), 'mux': (3, 0), 'validif': (2, 0)})


def parse_type(text):
    r = Reader(text); result = r.type(); r.end(); return result


def leaves(typ, name='', flip=False, result=None):
    result = {} if result is None else result
    if typ[0] == 'ground':
        need(len(result) < MAX_LEAVES and name not in result, 'leaf cap or collision')
        result[name] = (flip, typ[1], typ[2])
    elif typ[0] == 'bundle':
        for field, f, child in typ[1]:
            leaves(child, name + ('.' if name else '') + field, flip ^ f, result)
    else:
        need(typ[1] <= MAX_LEAVES, 'vector leaf expansion cap')
        for i in range(typ[1]): leaves(typ[2], name + '[' + str(i) + ']', flip, result)
    return result


def flat_name(name):
    return re.sub(r'[.\[]', '_', name).replace(']', '')


def flat_ports(module):
    result = {}
    for name, (direction, typ) in module['ports'].items():
        for path, (flip, kind, width) in leaves(typ, name).items():
            need(width is not None and width > 0 and kind in ('UInt', 'SInt', 'Clock', 'Reset', 'AsyncReset'), 'unresolved/unsupported public leaf ' + path)
            flat = flat_name(path); need(flat not in result, 'flattened port collision ' + flat)
            result[flat] = [('input' if direction == 'output' else 'output') if flip else direction, width]
    return result


def strip_info(line):
    if ' @[' in line:
        line, info = line.split(' @[', 1)
        need(info.endswith(']'), 'malformed source info')
    return line.rstrip()


# Chisel 6.7.0 Serializer.scala emits "%[" + JSON + "]" after the colon.
# Only the observed Host93 DontTouch array profile is admitted here.
MAX_ANNOTATION_BYTES = 2 * 1024 * 1024
MAX_ANNOTATIONS = 10000
ANNOTATION_PREFIX = 'FIRRTL version 3.3.0\ncircuit HostBlockCollection :%['


def _annotation_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate annotation JSON key')
        result[key] = value
    need(set(result) == {'class', 'target'}, 'unknown annotation object shape')
    need(result['class'] == 'firrtl.transforms.DontTouchAnnotation', 'unknown annotation class')
    target = result['target']
    need(isinstance(target, str) and target.startswith('~HostBlockCollection|') and len(target) > len('~HostBlockCollection|') and not any(ord(c) < 32 for c in target), 'annotation target type/root')
    return result


def _annotation_constant(value):
    raise ValueError('non-JSON annotation constant ' + value)


def strip_inline_annotations(text):
    info = {'annotation_count': 0, 'annotation_bytes': 0, 'annotation_sha256': None}
    if not text.startswith(ANNOTATION_PREFIX):
        return text, info
    start = len(ANNOTATION_PREFIX)
    decoder = json.JSONDecoder(object_pairs_hook=_annotation_object, parse_constant=_annotation_constant)
    try:
        items, end = decoder.raw_decode(text[start:start + MAX_ANNOTATION_BYTES + 1])
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid/bounded annotation JSON: ' + str(exc)) from None
    payload = text[start:start + end].encode('utf-8')
    need(len(payload) <= MAX_ANNOTATION_BYTES, 'annotation byte cap')
    need(isinstance(items, list) and len(items) <= MAX_ANNOTATIONS and all(isinstance(item, dict) for item in items), 'annotation array/count/type')
    closing = start + end
    need(text[closing:closing + 2] == ']\n' and text[closing + 2:].startswith('  module '), 'annotation wrapper/trailing module framing')
    marker = start - 2
    # Keep original FIR line numbers in later diagnostics; do not change raw
    # bytes or the original full-FIR hash returned by check_bytes.
    stripped = text[:marker] + '\n' * text[marker:closing + 1].count('\n') + text[closing + 1:]
    return stripped, {'annotation_count': len(items), 'annotation_bytes': len(payload), 'annotation_sha256': hashlib.sha256(payload).hexdigest()}


def parse_ir(text):
    modules = {}; current = None; contexts = []; circuit = None
    for number, raw in enumerate(text.splitlines(), 1):
        need(len(raw) <= 2*1024*1024, 'line byte cap')
        need('\t' not in raw and '\r' not in raw, 'unsupported whitespace line ' + str(number))
        line = strip_info(raw)
        if not line.strip() or line.lstrip().startswith(';'): continue
        indent = len(line) - len(line.lstrip()); s = line.strip()
        if indent == 0:
            need(current is None, 'top-level syntax after modules')
            if re.fullmatch(r'FIRRTL version 3\.3\.0', s):
                need(circuit is None and number == 1, 'version position'); continue
            m = re.fullmatch(r'circuit (' + ID + r')\s*:', s)
            need(m and circuit is None, 'unsupported circuit/header syntax line ' + str(number))
            circuit = m[1]; continue
        if indent == 2:
            m = re.fullmatch(r'(module|extmodule) (' + ID + r')\s*:', s)
            need(circuit is not None and m, 'unsupported module syntax line ' + str(number))
            need(m[2] not in modules and len(modules) < MAX_DEFINITIONS, 'duplicate definition or definition cap')
            current = dict(kind=m[1], ports={}, symbols={}, instances={}, connects=[], statements=0, defname=None)
            modules[m[2]] = current; contexts = []; continue
        need(current is not None and indent >= 4 and indent % 2 == 0, 'statement indentation line ' + str(number))
        closed = []
        while contexts and contexts[-1][0] >= indent: closed.append(contexts.pop())
        need(indent == 4 or (contexts and indent == contexts[-1][0] + 2), 'unsupported nesting line ' + str(number))
        conditional = any(x[1] in ('when', 'else') for x in contexts)
        def declare(name, kind, typ=None):
            need(name not in current['symbols'], 'duplicate symbol ' + name)
            current['symbols'][name] = (kind, typ)
        r = Reader(s)
        keyword = r.pop()
        try:
            if keyword in ('input', 'output'):
                need(indent == 4 and current['statements'] == 0, 'late/nested port')
                name = r.ident(); r.pop(':'); typ = r.type(); r.end(); declare(name, 'port', typ)
                current['ports'][name] = (keyword, typ); continue
            current['statements'] += 1
            if current['kind'] == 'extmodule':
                need(indent == 4, 'nested extmodule statement')
                if keyword == 'defname':
                    r.pop('='); name = r.ident(); r.end(); need(current['defname'] is None, 'duplicate defname'); current['defname'] = name
                elif keyword == 'parameter':
                    r.ident(); r.pop('='); value = r.pop(); need(re.fullmatch(r'-?\d+|"(?:[^"\\]|\\.)*"', value), 'unsupported parameter value'); r.end()
                else: raise ValueError('unsupported extmodule statement ' + keyword)
                continue
            if keyword == 'inst':
                need(indent == 4, 'conditional/nested instance')
                name = r.ident(); r.pop('of'); child = r.ident(); r.end(); declare(name, 'instance')
                current['instances'][name] = child
            elif keyword in ('wire', 'reg', 'regreset', 'cmem', 'smem'):
                name = r.ident(); r.pop(':'); typ = r.type(); declare(name, keyword, typ)
                if keyword in ('reg', 'regreset'):
                    r.pop(','); r.expr()
                    if keyword == 'regreset': r.pop(','); r.expr(); r.pop(','); r.expr()
                elif keyword == 'smem' and r.peek() == ',':
                    r.pop(','); need(r.pop() in ('undefined', 'old', 'new'), 'read-under-write value')
                r.end()
            elif keyword == 'node':
                name = r.ident(); r.pop('='); r.expr(); r.end(); declare(name, keyword)
            elif keyword == 'connect':
                need(r.i+1 >= len(r.tokens) or r.tokens[r.i+1] not in ('(', '<'), 'connect target must be a reference')
                lhs_start = r.i; dest = r.expr(); lhs_end = r.i
                if dest is None: dest = '@dynamic:' + ''.join(r.tokens[lhs_start:lhs_end]).split('[', 1)[0]
                r.pop(','); rhs_start = r.i; src = r.expr(); rhs_end = r.i; r.end()
                if src is None and r.tokens[rhs_start+1] not in ('(', '<'):
                    # Preserve dynamic RHS references for possible flipped sink aliases.
                    # Calls/literals remain None; Reader.expr is unchanged.
                    src = '@dynamic:' + ''.join(r.tokens[rhs_start:rhs_end]).split('[', 1)[0]
                # Dynamic targets are valid syntax but cannot satisfy direct path evidence.
                current['connects'].append((dest, src, conditional))
            elif keyword == 'invalidate':
                need(r.i+1 >= len(r.tokens) or r.tokens[r.i+1] not in ('(', '<'), 'invalidate target must be a reference')
                lhs_start = r.i; dest = r.expr(); lhs_end = r.i
                if dest is None: dest = '@dynamic:' + ''.join(r.tokens[lhs_start:lhs_end]).split('[', 1)[0]
                r.end()
                # Invalidating a checked sink is an additional driver, including
                # aggregate, guarded, and potentially-aliasing dynamic targets.
                current['connects'].append((dest, None, conditional))
            elif keyword in ('when', 'else'):
                if keyword == 'else': need((indent, 'when') in closed, 'orphan else')
                if keyword == 'when': r.expr()
                r.pop(':'); r.end(); contexts.append((indent, keyword))
            elif keyword in ('read', 'write', 'rdwr', 'infer'):
                r.pop('mport'); name = r.ident(); r.pop('='); r.ident(); r.pop('['); r.expr(); r.pop(']'); r.pop(','); r.expr(); r.end(); declare(name, 'mport')
            elif keyword == 'skip': r.end()
            elif keyword in ('printf', 'stop', 'assert', 'assume', 'cover'):
                r.pop('('); r.expr(); r.pop(','); r.expr(); r.pop(',')
                if keyword == 'stop': r.integer(0)
                elif keyword == 'printf':
                    need(r.pop().startswith('"'), 'printf format')
                    while r.peek() == ',': r.pop(','); r.expr()
                else:
                    r.expr(); r.pop(','); need(r.pop().startswith('"'), 'verification message')
                r.pop(')')
                if r.peek() == ':': r.pop(':'); r.ident()
                r.end()
            else: raise ValueError('unsupported statement ' + keyword)
        except ValueError as exc:
            raise ValueError('line ' + str(number) + ': ' + str(exc)) from None
    need(circuit is not None and modules, 'missing circuit/modules')
    for name, mod in modules.items():
        for child in mod['instances'].values(): need(child in modules, 'unknown module reference ' + child)
        if mod['kind'] == 'extmodule': need(mod['defname'] is not None, 'missing extmodule defname ' + name)
    return circuit, modules


def walk(modules, root):
    paths = {}; counts = collections.Counter()
    def visit(mod, path, stack):
        need(mod not in stack and len(stack) < MAX_DEPTH, 'recursive/deep module graph')
        need(len(paths) < MAX_PATHS, 'instance path cap')
        paths[path] = mod; counts[mod] += 1
        for name, child in modules[mod]['instances'].items(): visit(child, path + '.' + name, stack + (mod,))
    visit(root, root, ())
    return paths, counts


def base_name(name):
    return re.sub(r'_\d+$', '', name)


def resolve_signal(modules, module, ref):
    tokens = re.findall(ID + r'|\[\d+\]', ref)
    need(tokens and ''.join(tokens).replace('[', '').replace(']', '') == ref.replace('.', '').replace('[', '').replace(']', ''), 'non-static reference ' + ref)
    name = tokens.pop(0); mod = modules[module]; instance = name in mod['instances']
    if instance:
        mod = modules[mod['instances'][name]]; need(tokens, 'instance is not a signal'); name = tokens.pop(0)
    need(name in mod['ports'], 'metadata reference must name an IO port ' + ref)
    direction, typ = mod['ports'][name]
    source = (direction == 'output') if instance else (direction == 'input')
    for token in tokens:
        if token.startswith('['):
            need(typ[0] == 'vector' and int(token[1:-1]) < typ[1], 'invalid vector reference ' + ref); typ = typ[2]
        else:
            need(typ[0] == 'bundle', 'non-bundle field ' + ref)
            fields = {n:(f,t) for n,f,t in typ[1]}; need(token in fields, 'missing field ' + ref)
            flip, typ = fields[token]; source ^= flip
    return typ, source


def resolve_type(modules, module, ref):
    return resolve_signal(modules, module, ref)[0]


def require_direct(modules, module, dest, src):
    # Project only this requested metadata leaf through a related typed aggregate.
    # A flipped leaf is driven from the RHS; ground connects never reverse.
    wanted, dest_source = resolve_signal(modules, module, dest)
    actual, src_source = resolve_signal(modules, module, src)
    need(not dest_source and src_source, 'metadata port direction ' + dest + ' <- ' + src)
    need(wanted == actual and wanted[0] == 'ground', 'metadata width/type mismatch ' + dest)
    def contains(ref):
        if ref is None: return False
        prefix = ref[len('@dynamic:'):] if ref.startswith('@dynamic:') else ref
        return dest == prefix or dest.startswith(prefix + '.') or dest.startswith(prefix + '[')
    drivers = []
    for lhs, rhs, guarded in modules[module]['connects']:
        left = contains(lhs); right = contains(rhs)
        if not left and not right: continue
        need(not any(ref is not None and ref.startswith('@dynamic:') for ref in (lhs, rhs)), 'dynamic metadata driver ' + dest)
        if rhs is None:
            # Invalidate or a non-reference expression still overlaps its LHS.
            if left: drivers.append((None, guarded))
            continue
        if dest == lhs:
            drivers.append((rhs, guarded)); continue
        need(dest != rhs, 'reverse ground metadata target ' + dest)
        left_type, left_source = resolve_signal(modules, module, lhs)
        right_type, right_source = resolve_signal(modules, module, rhs)
        need(left_type == right_type and left_type[0] in ('bundle', 'vector'), 'metadata aggregate schema/flip mismatch ' + dest)
        suffix = dest[len(lhs):] if left else dest[len(rhs):]
        left_leaf = lhs + suffix; right_leaf = rhs + suffix
        lt, ls = resolve_signal(modules, module, left_leaf)
        rt, rs = resolve_signal(modules, module, right_leaf)
        need(lt == rt == wanted and lt[2] is not None, 'metadata aggregate leaf type mismatch ' + dest)
        flipped = ls ^ left_source
        need(flipped == (rs ^ right_source), 'metadata aggregate flip mismatch ' + dest)
        target, source = (right_leaf, left_leaf) if flipped else (left_leaf, right_leaf)
        need((not rs and ls) if flipped else (not ls and rs), 'metadata aggregate leaf direction ' + dest)
        need(target == dest, 'metadata aggregate target direction ' + dest)
        drivers.append((source, guarded))
    need(drivers == [(src, False)], 'metadata direct binding missing/overridden: ' + dest + ' <- ' + src)


def require_channel(modules, module, sink, source, fields):
    for prefix in (sink, source):
        for signal in ('ready', 'valid'):
            need(resolve_type(modules, module, prefix + '.' + signal) == ('ground', 'UInt', 1), 'metadata handshake width ' + prefix)
    require_direct(modules, module, source + '.ready', sink + '.ready')
    require_direct(modules, module, sink + '.valid', source + '.valid')
    for field, width in fields.items():
        for prefix in (sink, source):
            need(resolve_type(modules, module, prefix + '.bits.' + field) == ('ground', 'UInt', width), 'metadata payload schema ' + prefix + '.' + field)
        require_direct(modules, module, sink + '.bits.' + field, source + '.bits.' + field)


SIBLINGS = {'top':'HostBlockTop', 'pre':'HeteroBF16FmaPre', 'mul':'HeteroBF16FmaMul', 'post':'HeteroBF16FmaPost', 'round':'HeteroBF16FmaRound'}
EXPECTED_PATHS = {
    'cmd':'HostBlockCommands', 'cmd.reader':'Record128Reader', 'cmd.tensor':'TypedTensorReader',
    'owner':'QwenOwnerKernel', 'owner.core':'Qwen2ContinuousBlock',
    'owner.qkvRouter':'Public21QkvReductionRouter', 'owner.resident':'FfnResidentCoordinator',
    'owner.resident.bridge':'FfnTileSiluBridge', 'owner.silu':'ScheduledSiluOwner',
    'owner.silu.dut':'VectorSiluOwner', 'owner.silu.dut.vector':'SiluVectorUnit',
    'hub':'SharedMemoryArbiter', 'dma':'RetainedIdmaWeightBurstAdapter',
    'dma.backend':'idma_backend_rw_axi_flat_wrap',
}
TAPS = {
    'owner.core': {
        'canonicalScoreTap': '{ valid : UInt<1>, ownerTag : UInt<32>, head : UInt<16>, token : UInt<16>, keyBase : UInt<16>, packedSelected : UInt<4>, value : UInt<32> }',
        'canonicalProbTap': '{ valid : UInt<1>, ownerTag : UInt<32>, head : UInt<16>, token : UInt<16>, key : UInt<16>, col : UInt<16>, value : UInt<16> }',
        'canonicalCosTap': '{ valid : UInt<1>, ownerTag : UInt<32>, head : UInt<16>, token : UInt<16>, col : UInt<16>, value : UInt<512> }',
        'canonicalSinTap': '{ valid : UInt<1>, ownerTag : UInt<32>, head : UInt<16>, token : UInt<16>, col : UInt<16>, value : UInt<512> }',
        'canonicalPvRequestTap': '{ valid : UInt<1>, ownerTag : UInt<32>, head : UInt<16>, token : UInt<16>, col : UInt<16> }',
        'canonicalPvAckTap': '{ valid : UInt<1> }',
    },
    'owner.resident.bridge': {
        'canonicalTileTap': '{ valid : UInt<1>, slot : UInt<2>, identity : UInt<32>, ng : UInt<16>, index : UInt<11>, rows : UInt<8>, cols : UInt<8>, value : UInt<32>[16] }',
    },
    'owner.silu.dut': {'canonicalLoanContextTap': '{ active : UInt<1>, poison : UInt<1>, abort : UInt<1> }'},
    'owner.silu.dut.vector': {'canonicalSiluTap': '{ valid : UInt<1>, value : UInt<32>[16] }'},
}
REQUEST = {'write':1, 'address':64, 'data':512, 'mask':64, 'tag':64}
RESPONSE = {'data':512, 'tag':64, 'error':1}
# ABI oracle, embedded to avoid any unpinned expectation-file load.
HOST_PORTS = {'clock': ['input', 1], 'reset': ['input', 1], 'io_launch_ready': ['output', 1], 'io_launch_valid': ['input', 1], 'io_launch_bits_commandBase': ['input', 64], 'io_launch_bits_commandLimit': ['input', 64], 'io_launch_bits_commands': ['input', 16], 'io_launch_bits_descriptorBase': ['input', 64], 'io_launch_bits_descriptorLimit': ['input', 64], 'io_launch_bits_descriptors': ['input', 25], 'io_launch_bits_epoch': ['input', 16], 'io_launch_bits_regions_0_base': ['input', 64], 'io_launch_bits_regions_0_limit': ['input', 64], 'io_launch_bits_regions_0_read': ['input', 1], 'io_launch_bits_regions_0_write': ['input', 1], 'io_launch_bits_regions_1_base': ['input', 64], 'io_launch_bits_regions_1_limit': ['input', 64], 'io_launch_bits_regions_1_read': ['input', 1], 'io_launch_bits_regions_1_write': ['input', 1], 'io_launch_bits_regions_2_base': ['input', 64], 'io_launch_bits_regions_2_limit': ['input', 64], 'io_launch_bits_regions_2_read': ['input', 1], 'io_launch_bits_regions_2_write': ['input', 1], 'io_launch_bits_regions_3_base': ['input', 64], 'io_launch_bits_regions_3_limit': ['input', 64], 'io_launch_bits_regions_3_read': ['input', 1], 'io_launch_bits_regions_3_write': ['input', 1], 'io_result_ready': ['input', 1], 'io_result_valid': ['output', 1], 'io_result_bits_status': ['output', 8], 'io_result_bits_completed': ['output', 16], 'io_result_bits_failedPc': ['output', 16], 'io_result_bits_epoch': ['output', 16], 'io_completion_ready': ['input', 1], 'io_completion_valid': ['output', 1], 'io_completion_bits': ['output', 56], 'io_axi_aw_ready': ['input', 1], 'io_axi_aw_valid': ['output', 1], 'io_axi_aw_bits_addr': ['output', 64], 'io_axi_aw_bits_id': ['output', 8], 'io_axi_aw_bits_len': ['output', 8], 'io_axi_aw_bits_size': ['output', 3], 'io_axi_aw_bits_burst': ['output', 2], 'io_axi_w_ready': ['input', 1], 'io_axi_w_valid': ['output', 1], 'io_axi_w_bits_data': ['output', 512], 'io_axi_w_bits_strb': ['output', 64], 'io_axi_w_bits_last': ['output', 1], 'io_axi_b_ready': ['output', 1], 'io_axi_b_valid': ['input', 1], 'io_axi_b_bits_id': ['input', 8], 'io_axi_b_bits_resp': ['input', 2], 'io_axi_ar_ready': ['input', 1], 'io_axi_ar_valid': ['output', 1], 'io_axi_ar_bits_addr': ['output', 64], 'io_axi_ar_bits_id': ['output', 8], 'io_axi_ar_bits_len': ['output', 8], 'io_axi_ar_bits_size': ['output', 3], 'io_axi_ar_bits_burst': ['output', 2], 'io_axi_r_ready': ['output', 1], 'io_axi_r_valid': ['input', 1], 'io_axi_r_bits_id': ['input', 8], 'io_axi_r_bits_data': ['input', 512], 'io_axi_r_bits_resp': ['input', 2], 'io_axi_r_bits_last': ['input', 1], 'io_resetRequired': ['output', 1], 'io_idmaTransfers': ['output', 64], 'io_idmaStreamedWriteBeats': ['output', 64], 'io_idmaStreamedBeats': ['output', 64], 'io_pipelineIssues': ['output', 64], 'io_pipelineStalls': ['output', 64], 'io_idmaReadBursts': ['output', 64], 'io_idmaReadBeats': ['output', 64], 'io_idmaCacheHits': ['output', 64], 'io_pc': ['output', 16], 'io_issuedJobs': ['output', 16], 'io_usefulMacs': ['output', 64], 'io_executedMacs': ['output', 64], 'io_writeBytes': ['output', 64], 'io_memoryAccepted_0': ['output', 64], 'io_memoryAccepted_1': ['output', 64], 'io_memoryReturned_0': ['output', 64], 'io_memoryReturned_1': ['output', 64]}


def check_bytes(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, 'CHIRRTL byte cap/type')
    need(b'\x00' not in raw, 'NUL in CHIRRTL')
    text = raw.decode('utf-8', errors='strict')
    parsed_text, annotation_info = strip_inline_annotations(text)
    circuit, modules = parse_ir(parsed_text)
    need(circuit == 'HostBlockCollection', 'wrong collection circuit root')
    need('HostBlockCollection' in modules and modules['HostBlockCollection']['kind'] == 'module', 'collection definition missing')
    need(modules['HostBlockCollection']['instances'] == SIBLINGS, 'exact collection sibling inventory')
    need(not any('Bench' in name or 'Mock' in name or 'Spec' in name for name in modules), 'Bench/Mock/Spec definition prohibited')
    for name in SIBLINGS.values():
        need(modules[name]['kind'] == 'module' and modules[name]['ports'] and modules[name]['statements'], 'real module definition missing ' + name)
    collection_paths, unused = walk(modules, 'HostBlockCollection')
    need(set(collection_paths.values()) == set(modules), 'unreachable/orphan definition')
    paths, counts = walk(modules, 'HostBlockTop')
    need(set(modules['HostBlockTop']['ports']) == {'clock', 'reset', 'io'} and modules['HostBlockTop']['ports']['io'][1][0] == 'bundle', 'original unflattened Host IO required')
    need(flat_ports(modules['HostBlockTop']) == HOST_PORTS, 'original Host83 names/directions/widths differ')
    for path, expected in EXPECTED_PATHS.items():
        name = paths.get('HostBlockTop.' + path)
        need(name is not None and base_name(name) == expected, 'required Host hierarchy ' + path + ' -> ' + expected)
        need(modules[name]['kind'] == ('extmodule' if path == 'dma.backend' else 'module'), 'required Host hierarchy definition kind ' + path)
    canonical = collections.Counter()
    for name, count in counts.items():
        canonical[base_name(name)] += count
    for name in ('HostBlockTop', 'HostBlockCommands', 'Record128Reader', 'TypedTensorReader', 'QwenOwnerKernel', 'SharedMemoryArbiter', 'RetainedIdmaWeightBurstAdapter'):
        need(canonical[name] == 1, 'unique Host resource ' + name)
    for name, count in [('qwen2_matrix_command_endpoint',8), ('tc_clk_gating',8), ('idma_backend_rw_axi_flat_wrap',1)]:
        need(canonical[name] == count, 'external resource instance count ' + name)
        need(sum(ncount for n,ncount in counts.items() if modules[n]['kind'] == 'extmodule' and modules[n]['defname'] == name) == count, 'external defname alias count ' + name)
        matching = [n for n in counts if base_name(n) == name]
        for n in matching:
            need(modules[n]['kind'] == 'extmodule' and modules[n]['defname'] == name, 'real external identity ' + name)
    tap_evidence = []; expected_taps = set()
    for path, declarations in TAPS.items():
        modname = paths['HostBlockTop.' + path]; mod = modules[modname]
        for name, source_type in declarations.items():
            typ = parse_type(source_type)
            need(mod['symbols'].get(name) == ('wire', typ), 'exact combinational tap declaration ' + path + '.' + name)
            flattened = leaves(typ)
            expected_taps.add(('HostBlockTop.' + path, name))
            tap_evidence.append(dict(path='HostBlockTop.' + path, module=modname, name=name, kind='wire', bits=sum(x[2] for x in flattened.values()), leaves={key:{'flipped':f, 'type':k, 'width':w} for key,(f,k,w) in flattened.items()}))
    observed_taps = {(path.replace('HostBlockCollection.top', 'HostBlockTop', 1), name) for path, mod in collection_paths.items() for name in modules[mod]['symbols'] if re.fullmatch(r'canonical.*Tap', name)}
    need(observed_taps == expected_taps, 'extra/missing/duplicated canonical observation tap')
    need(sum(x['bits'] for x in tap_evidence) == 2604, 'tap width total')
    top = 'HostBlockTop'; cmd = paths[top + '.cmd']
    # Real metadata reader and Host owner share one original hub and iDMA path.
    for sink, source, fields in [
        ('hub.io.requests[0]', 'cmd.io.memory', REQUEST),
        ('cmd.io.response', 'hub.io.responses[0]', RESPONSE),
        ('hub.io.requests[1]', 'owner.io.memory', REQUEST),
        ('owner.io.response', 'hub.io.responses[1]', RESPONSE),
        ('dma.io.request', 'hub.io.memory', REQUEST),
        ('hub.io.response', 'dma.io.response', RESPONSE),
    ]: require_channel(modules, top, sink, source, fields)
    require_channel(modules, cmd, 'io.memory', 'reader.io.memory', REQUEST)
    require_channel(modules, cmd, 'reader.io.response', 'io.response', RESPONSE)
    # The typed descriptor reader's payload reaches the same record reader.
    # Conditional command/policy overrides are expected here, so this report
    # claims topology only for that mux, not command scheduling equivalence.
    record_fields = {'tableBase':64, 'tableLimit':64, 'entryCount':25, 'index':24, 'requestTag':64}
    for field, width in record_fields.items():
        for ref in ('reader.io.request.bits.', 'tensor.io.record.bits.'):
            need(resolve_type(modules, cmd, ref + field) == ('ground','UInt',width), 'typed/record metadata schema')
        need(any(lhs in ('reader.io.request.bits','reader.io.request.bits.'+field) and rhs in ('tensor.io.record.bits','tensor.io.record.bits.'+field) and not guarded for lhs,rhs,guarded in modules[cmd]['connects']), 'typed record default payload binding ' + field)
    for field in ('data','requestTag','status'):
        require_direct(modules, cmd, 'tensor.io.recordResult.bits.'+field, 'reader.io.result.bits.'+field)
    return dict(**annotation_info, status='PASS', scope='HOST93_COLLECTION_CHIRRTL_STATIC_STRUCTURE_ONLY', emission_root=circuit, execution_top='HostBlockTop', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), definition_count=len(modules), collection_instance_count=len(collection_paths), host_instance_count=len(paths), collection_direct_instances=dict(SIBLINGS), host_port_count=83, host_input_count=39, host_output_count=44, host_ports=HOST_PORTS.copy(), host_resource_counts=dict(canonical), external_modules={n:modules[n]['defname'] for n in modules if modules[n]['kind']=='extmodule'}, metadata_paths={p:paths['HostBlockTop.'+p] for p in EXPECTED_PATHS}, metadata_direct_request_response_routes=8, typed_record_payload_default_observed=True, taps=tap_evidence, observation_source_files=3, observation_bundles=9, observation_bits=2604, resource_count_scope='HostBlockTop subtree; four collection FMA siblings excluded', arithmetic_executed=False, metadata_protocol_executed=False, tap_event_semantics_proved=False, generated_cpp_binding_verified=False, job_launched=False, rtl_verified=False, full_block_qualified=False, historical_identity_inherited=False)


def check(path):
    """Read one regular, bounded FIR file once; return static evidence or raise."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(os.fspath(path), flags)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES, 'regular FIR within 48 MiB required')
        with os.fdopen(fd, 'rb', closefd=False) as handle: raw = handle.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), 'FIR changed during read')
        need(len(raw) == before.st_size, 'FIR size changed')
        return check_bytes(raw)
    finally:
        os.close(fd)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fir')
    args = parser.parse_args()
    print(json.dumps(check(args.fir), sort_keys=True))
