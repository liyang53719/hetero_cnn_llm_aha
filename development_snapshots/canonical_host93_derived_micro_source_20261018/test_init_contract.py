"""Finite source/synthetic contract checks; no native execution or generation."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Require -I -S -B before local loading.')
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).absolute().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pinned(path, size, digest):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'no symlink')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(before.st_size == size, 'raw size')
        raw = stream.read(size + 1)
        after = os.fstat(stream.fileno())
    key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest and
            key(before) == key(after) == key(path.stat()), 'same buffer identity')
    return raw


raw = pinned(HERE / 'init_contract.py', 5127, 'd070d9a0841ea034dd684fad3ca9fd4fa32a1ed1afa1417bf4f4a88625996365')
contract = types.ModuleType('verified_finite_initializer_contract')
contract.__file__ = str(HERE / 'init_contract.py')
exec(compile(raw, contract.__file__, 'exec', dont_inherit=True), contract.__dict__)
# Explicitly handwritten portable negative; never a real generated C++ file.
old = b'// Handwritten synthetic uninitialized container. Not generated output.\nclass Vmicro_leaf_f_container: public Vmicro_leaf_f {\n  public:\n    long long m_seqnum;\n    Vmicro_leaf_f_container(const char* scopep__V):\n    Vmicro_leaf_f(scopep__V) {}\n};\nextern "C" void synthetic_only();\n'
before = b'    Vmicro_leaf_f(scopep__V) {}\n'
after = b'    Vmicro_leaf_f(scopep__V), m_seqnum{0} {}\n'
require(old.count(before) == 1, 'known old constructor exactly once')
synthetic = old.replace(before, after)
leaf = 'micro_leaf_f'
count = 0


def test(name, fn):
    global count
    fn()
    count += 1
    print('PASS ' + name)


def accepts(data):
    result = contract.initialized_container(data, leaf)
    field = result['member_ranges']['field']
    ctor = result['member_ranges']['ctor']
    init = result['member_ranges']['initializer']
    require(field[1] <= ctor[0] <= init[0] < init[1] <= ctor[1], 'target ranges')
    require(data[init[0]:init[1]].replace(b' ', b'').replace(b'\n', b'').replace(b'\t', b'') == b'm_seqnum{0}', 'exact target initializer')


def refuses(data, part):
    try:
        contract.initialized_container(data, leaf)
    except (ValueError, UnicodeError) as error:
        require(part in str(error), 'wrong refusal ' + str(error))
        return
    raise ValueError('expected contract refusal ' + part)


test('synthetic_single_delta_positive', lambda: accepts(synthetic))
test('handwritten_uninitialized_negative', lambda: refuses(old, 'exact m_seqnum{0}'))
test('whitespace_only_variation_positive', lambda: accepts(synthetic.replace(after, b'\tVmicro_leaf_f ( scopep__V ) ,\n m_seqnum { 0 } { }\n')))
test('wrong_initializer_value', lambda: refuses(synthetic.replace(b'm_seqnum{0}', b'm_seqnum{1}'), 'exact m_seqnum{0}'))
test('initializer_elsewhere_no_compensation', lambda: refuses(old + b'\nstruct Other { long long m_seqnum{0}; };\n', 'exact m_seqnum{0}'))
test('initializer_comment_no_compensation', lambda: refuses(old + b'\n// m_seqnum{0}\n', 'exact m_seqnum{0}'))
test('initializer_string_no_compensation', lambda: refuses(old + b'\nconst char* note = "m_seqnum{0}";\n', 'exact m_seqnum{0}'))
test('duplicate_target_field', lambda: refuses(synthetic.replace(b'long long m_seqnum;', b'long long m_seqnum; long long m_seqnum;'), 'exact m_seqnum{0}'))
test('duplicate_target_initializer', lambda: refuses(synthetic.replace(b'm_seqnum{0}', b'm_seqnum{0}, m_seqnum{0}'), 'exact m_seqnum{0}'))
test('wrong_base_class', lambda: refuses(synthetic.replace(b': public Vmicro_leaf_f {', b': public Other {'), 'inheritance/header'))
test('wrong_constructor_target', lambda: refuses(synthetic.replace(b'Vmicro_leaf_f_container(const', b'Other_container(const'), 'exact m_seqnum{0}'))
test('body_assignment_not_initializer', lambda: refuses(synthetic.replace(after, b'    Vmicro_leaf_f(scopep__V) { m_seqnum = 0; }\n'), 'exact m_seqnum{0}'))
test('unsigned_zero_not_added', lambda: refuses(synthetic.replace(b'm_seqnum{0}', b'm_seqnum{0U}'), 'exact m_seqnum{0}'))
test('extra_constructor_rejected', lambda: refuses(synthetic.replace(b'    long long m_seqnum;', b'    Vmicro_leaf_f_container() {}\n    long long m_seqnum;'), 'exact m_seqnum{0}'))
test('comment_inside_class_refused', lambda: refuses(synthetic.replace(b'long long m_seqnum;', b'long long /* note */ m_seqnum;'), 'unknown comment/literal inside'))
test('string_inside_class_refused', lambda: refuses(synthetic.replace(b'long long m_seqnum;', b'const char* s = "text"; long long m_seqnum;'), 'unknown comment/literal inside'))
block = synthetic[synthetic.index(b'class Vmicro_leaf_f_container'):synthetic.index(b'\nextern "C"')].strip()
test('block_comment_fake_class_not_declaration', lambda: refuses(b'/*\n' + block + b'\n*/\n', 'exactly one real target'))
quoted_block = json.dumps(block.decode()).encode()
test('ordinary_string_fake_class_not_declaration', lambda: refuses(b'const char* fake = ' + quoted_block + b';\n', 'exactly one real target'))
test('raw_string_fake_class_unknown_refused', lambda: refuses(b'const char* fake = R"x(' + block + b')x";\n', 'unsupported literal prefix'))
test('fake_class_cannot_hide_old_failure', lambda: refuses(old + b'\nconst char* fake = ' + quoted_block + b';\n', 'exact m_seqnum{0}'))
test('duplicate_real_class_refused', lambda: refuses(synthetic + b'\n' + block, 'exactly one real target'))
test('target_inside_other_class_refused', lambda: refuses(b'struct Other {\n' + block + b'\n};\n', 'top-level scope'))
test('target_inside_namespace_refused', lambda: refuses(b'namespace N {\n' + block + b'\n}\n', 'top-level scope'))
test('unterminated_comment_refused', lambda: refuses(synthetic + b'\n/* never closed', 'unterminated block'))
test('unterminated_literal_refused', lambda: refuses(synthetic + b'\n"never closed', 'unterminated ordinary'))
test('oversize_refused', lambda: refuses(b' ' * 65537, 'fixed tiny leaf'))
test('nul_refused', lambda: refuses(synthetic + b'\x00', 'bounded ASCII'))
test('unknown_class_body_refused', lambda: refuses(synthetic.replace(b'long long m_seqnum;', b'long long m_seqnum; int other;'), 'exact m_seqnum{0}'))
test('handwritten_negative_fixed_identity', lambda: require(len(old) == 281 and hashlib.sha256(old).hexdigest() == '3ffe9eb65c69c990d3f6fa050910a37aa514629db53df937c6fee4fa070baacc', 'synthetic negative drift'))
print(json.dumps({'status': 'PASS_SOURCE_AND_SYNTHETIC_CONTRACT_ONLY', 'tests': count,
    'native_executed': False, 'derived_generated_output_seen': False,
    'handwritten_synthetic_negative': {'bytes': len(old), 'sha256': hashlib.sha256(old).hexdigest()},
    'handwritten_synthetic_positive': {'bytes': len(synthetic), 'sha256': hashlib.sha256(synthetic).hexdigest()},
    'not_general_cpp_parser': True}, sort_keys=True))
