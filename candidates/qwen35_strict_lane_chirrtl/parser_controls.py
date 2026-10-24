"""Pure source-bound class-log parser controls. No JVM or prior candidate execution."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import time
import unittest

START = time.monotonic()
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert sys.version_info[:3] == (3, 12, 14) and len(sys.argv) == 1
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
def timeout(*_):
    raise TimeoutError('PARSER_CONTROLS_10_SECOND_LIMIT')
assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
signal.signal(signal.SIGALRM, timeout)
signal.setitimer(signal.ITIMER_REAL, 10)
def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
        raise RuntimeError('parser controls prohibit process/network')
sys.addaudithook(audit)
DRIVER_PIN = {'bytes': 22401, 'sha256': 'be9b9f32ddf7a08d0bc74c6f138c5bfb1197a76869a6ed8da9475682de61671e'}
p = Path(__file__).resolve().with_name('run_chirrtl.py')
s = p.lstat()
stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
assert stat.S_ISREG(s.st_mode) and s.st_size == DRIVER_PIN['bytes']
with p.open('rb') as f:
    assert stamp(s) == stamp(os.fstat(f.fileno()))
    raw = f.read(DRIVER_PIN['bytes'] + 1)
    assert stamp(s) == stamp(os.fstat(f.fileno())) == stamp(p.lstat())
assert hashlib.sha256(raw).hexdigest() == DRIVER_PIN['sha256']
tree = ast.parse(raw)
selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'need', 'validate_loaded_classes', 'validate_ir'}]
assert len(selected) == 3
ns = {'re': re, 'Path': Path}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(p), 'exec', dont_inherit=True), ns)
parse = ns['validate_loaded_classes']
parse_ir = ns['validate_ir']
OWNER = 'heteronpu.experimental.StrictFp32MatrixLane'
OBJECT = 'hardfloat.fNFromRecFN$'
EMITTER = 'heteronpu.experimental.contracttests.StrictFp32LaneChirrtl$'
P = {'input_class_relatives': ['gemmini/EmitHeteroBF16Fma$.class', 'gemmini/EmitHeteroBF16Fma$delayedInit$body.class', 'gemmini/EmitHeteroBF16Fma.class', 'gemmini/HeteroBF16FmaLane$$anon$1.class', 'gemmini/HeteroBF16FmaLane.class', 'gemmini/HeteroBF16FmaMul$$anon$3.class', 'gemmini/HeteroBF16FmaMul.class', 'gemmini/HeteroBF16FmaPost$$anon$4.class', 'gemmini/HeteroBF16FmaPost.class', 'gemmini/HeteroBF16FmaPre$$anon$2.class', 'gemmini/HeteroBF16FmaPre.class', 'gemmini/HeteroBF16FmaRound$$anon$5.class', 'gemmini/HeteroBF16FmaRound.class', 'hardfloat/MulAddRecFN$$anon$3.class', 'hardfloat/MulAddRecFN.class', 'hardfloat/MulAddRecFNToRaw_postMul$$anon$2.class', 'hardfloat/MulAddRecFNToRaw_postMul.class', 'hardfloat/MulAddRecFNToRaw_preMul$$anon$1.class', 'hardfloat/MulAddRecFNToRaw_preMul.class', 'hardfloat/MulAddRecFN_interIo.class', 'hardfloat/RawFloat.class', 'hardfloat/RoundAnyRawFNToRecFN$$anon$1.class', 'hardfloat/RoundAnyRawFNToRecFN.class', 'hardfloat/RoundRawFNToRecFN$$anon$2.class', 'hardfloat/RoundRawFNToRecFN.class', 'hardfloat/consts$.class', 'hardfloat/consts.class', 'hardfloat/countLeadingZeros$.class', 'hardfloat/countLeadingZeros.class', 'hardfloat/fNFromRecFN$.class', 'hardfloat/fNFromRecFN.class', 'hardfloat/isSigNaNRawFloat$.class', 'hardfloat/isSigNaNRawFloat.class', 'hardfloat/lowMask$.class', 'hardfloat/lowMask.class', 'hardfloat/orReduceBy2$.class', 'hardfloat/orReduceBy2.class', 'hardfloat/orReduceBy4$.class', 'hardfloat/orReduceBy4.class', 'hardfloat/rawFloatFromFN$.class', 'hardfloat/rawFloatFromFN.class', 'hardfloat/rawFloatFromRecFN$.class', 'hardfloat/rawFloatFromRecFN.class', 'hardfloat/recFNFromFN$.class', 'hardfloat/recFNFromFN.class', 'heteronpu/experimental/HeteroFullFp32FmaPre$$anon$1.class', 'heteronpu/experimental/HeteroFullFp32FmaPre.class', 'heteronpu/experimental/StrictFp32LaneMode$.class', 'heteronpu/experimental/StrictFp32LaneMode.class', 'heteronpu/experimental/StrictFp32LaneRequest.class', 'heteronpu/experimental/StrictFp32LaneResponse.class', 'heteronpu/experimental/StrictFp32LaneStatus$.class', 'heteronpu/experimental/StrictFp32LaneStatus.class', 'heteronpu/experimental/StrictFp32MatrixLane$$anon$2.class', 'heteronpu/experimental/StrictFp32MatrixLane.class'], 'allowed_input_classes': ['gemmini.HeteroBF16FmaMul', 'gemmini.HeteroBF16FmaMul$$anon$3', 'gemmini.HeteroBF16FmaPost', 'gemmini.HeteroBF16FmaPost$$anon$4', 'gemmini.HeteroBF16FmaRound', 'gemmini.HeteroBF16FmaRound$$anon$5', 'hardfloat.MulAddRecFNToRaw_postMul', 'hardfloat.MulAddRecFNToRaw_postMul$$anon$2', 'hardfloat.MulAddRecFNToRaw_preMul', 'hardfloat.MulAddRecFNToRaw_preMul$$anon$1', 'hardfloat.MulAddRecFN_interIo', 'hardfloat.RawFloat', 'hardfloat.RoundAnyRawFNToRecFN', 'hardfloat.RoundAnyRawFNToRecFN$$anon$1', 'hardfloat.RoundRawFNToRecFN', 'hardfloat.RoundRawFNToRecFN$$anon$2', 'hardfloat.consts$', 'hardfloat.countLeadingZeros$', 'hardfloat.fNFromRecFN$', 'hardfloat.isSigNaNRawFloat$', 'hardfloat.lowMask$', 'hardfloat.orReduceBy2$', 'hardfloat.orReduceBy4$', 'hardfloat.rawFloatFromFN$', 'hardfloat.rawFloatFromRecFN$', 'hardfloat.recFNFromFN$', 'heteronpu.experimental.HeteroFullFp32FmaPre', 'heteronpu.experimental.HeteroFullFp32FmaPre$$anon$1', 'heteronpu.experimental.StrictFp32LaneMode$', 'heteronpu.experimental.StrictFp32LaneRequest', 'heteronpu.experimental.StrictFp32LaneResponse', 'heteronpu.experimental.StrictFp32LaneStatus$', 'heteronpu.experimental.StrictFp32MatrixLane', 'heteronpu.experimental.StrictFp32MatrixLane$$anon$2'], 'allowed_hidden_hosts': ['gemmini.HeteroBF16FmaMul', 'gemmini.HeteroBF16FmaMul$$anon$3', 'gemmini.HeteroBF16FmaPost', 'gemmini.HeteroBF16FmaPost$$anon$4', 'gemmini.HeteroBF16FmaRound', 'gemmini.HeteroBF16FmaRound$$anon$5', 'hardfloat.MulAddRecFNToRaw_postMul', 'hardfloat.MulAddRecFNToRaw_postMul$$anon$2', 'hardfloat.MulAddRecFNToRaw_preMul', 'hardfloat.MulAddRecFNToRaw_preMul$$anon$1', 'hardfloat.MulAddRecFN_interIo', 'hardfloat.RawFloat', 'hardfloat.RoundAnyRawFNToRecFN', 'hardfloat.RoundAnyRawFNToRecFN$$anon$1', 'hardfloat.RoundRawFNToRecFN', 'hardfloat.RoundRawFNToRecFN$$anon$2', 'hardfloat.fNFromRecFN$', 'hardfloat.lowMask$', 'hardfloat.orReduceBy2$', 'hardfloat.orReduceBy4$', 'hardfloat.rawFloatFromFN$', 'hardfloat.rawFloatFromRecFN$', 'hardfloat.recFNFromFN$', 'heteronpu.experimental.HeteroFullFp32FmaPre', 'heteronpu.experimental.HeteroFullFp32FmaPre$$anon$1', 'heteronpu.experimental.StrictFp32LaneRequest', 'heteronpu.experimental.StrictFp32LaneResponse', 'heteronpu.experimental.StrictFp32MatrixLane', 'heteronpu.experimental.StrictFp32MatrixLane$$anon$2', 'heteronpu.experimental.contracttests.StrictFp32LaneChirrtl$'], 'expected_emitter_classes': ['heteronpu/experimental/contracttests/StrictFp32LaneChirrtl.class', 'heteronpu/experimental/contracttests/StrictFp32LaneChirrtl$.class', 'heteronpu/experimental/contracttests/StrictFp32LaneChirrtl$NoExternalTools.class'], 'input_class_root': '/tmp/fixed-source/classes', 'work': '/tmp/new-owned', 'required_elaboration_classes': ['heteronpu.experimental.StrictFp32MatrixLane', 'circt.stage.ChiselStage$']}
C = {x: {'bytes': 1, 'sha256': 'synthetic'} for x in P['expected_emitter_classes']}
def row(name, source):
    return f'[0.001s][info][class,load] {name} source: {source}\n'
PREFIX = row('circt.stage.ChiselStage$', 'file:/tmp/fixed-chisel.jar') + row(OWNER, 'file:/tmp/fixed-source/classes/')
def evaluate(extra='', prefix=PREFIX):
    return parse((prefix + extra).encode(), P, C)

class ParserControls(unittest.TestCase):
    def bad(self, extra='', prefix=PREFIX):
        with self.assertRaises(ValueError):
            evaluate(extra, prefix)
    def test_01_exact_ordinary_roots(self):
        self.assertEqual(evaluate()['ordinary_candidate_count'], 1)
    def test_02_observed_no_numeric_hidden(self):
        self.assertEqual(evaluate(row(OWNER + '$$Lambda/0x000A3f', OWNER))['hidden_lambda_count'], 1)
    def test_03_old_numeric_hidden_with_hex(self):
        self.assertEqual(evaluate(row(OWNER + '$$Lambda$123/0x012ab', OWNER))['hidden_lambda_count'], 1)
    def test_04_scala_object_host(self):
        x = row(OBJECT, 'file:/tmp/fixed-source/classes/') + row(OBJECT + '$$Lambda/0xabc', OBJECT)
        self.assertEqual(evaluate(x)['hidden_host_names'], [OBJECT])
    def test_05_new_emitter_host(self):
        x = row(EMITTER, 'file:/tmp/new-owned/classes/') + row(EMITTER + '$$Lambda/0xabc', EMITTER)
        self.assertEqual(evaluate(x)['hidden_lambda_count'], 1)
    def test_06_unknown_host(self):
        self.bad(row('heteronpu.continuous.Host$$Lambda/0xabc', 'heteronpu.continuous.Host'))
    def test_07_missing_source(self):
        self.bad('[0s][info][class,load] ' + OWNER + '$$Lambda/0xabc\n')
    def test_08_empty_source(self):
        self.bad(row(OWNER + '$$Lambda/0xabc', ''))
    def test_09_source_not_host(self):
        self.bad(row(OWNER + '$$Lambda/0xabc', 'file:/tmp/fixed-source/classes/'))
    def test_10_pseudo_host_prefix(self):
        self.bad(row(OWNER + 'Extra$$Lambda/0xabc', OWNER))
    def test_11_bad_hex_and_tail(self):
        for tail in ['/0x', '/0xzz', '/0xabc/Extra', '/0xabc.class', '$bad/0xabc', '$12', '']:
            with self.subTest(tail=tail): self.bad(row(OWNER + '$$Lambda' + tail, OWNER))
    def test_12_hidden_before_host(self):
        self.bad(row(OWNER + '$$Lambda/0xabc', OWNER) + PREFIX, prefix='')
    def test_13_ordinary_wrong_root(self):
        self.bad(prefix=row('circt.stage.ChiselStage$', 'file:/tmp/fixed-chisel.jar') + row(OWNER, 'file:/tmp/other/classes/'))
    def test_14_root_alias_spelling(self):
        for root in ['file:/tmp/fixed-source/classes/../classes/', 'file:///tmp/fixed-source/classes/', 'file:/tmp/fixed-source/classes']:
            with self.subTest(root=root): self.bad(row(OWNER, root))
    def test_15_unfrozen_ordinary_candidate(self):
        self.bad(row('heteronpu.continuous.HostBlockTop', 'file:/tmp/fixed-source/classes/'))
    def test_16_hardfloat(self):
        self.bad(row('hardfloat.MulRecFN', 'file:/tmp/tool.jar'))
    def test_17_required_missing(self):
        self.bad(prefix=row(OWNER, 'file:/tmp/fixed-source/classes/'))
    def test_18_emitter_wrong_root(self):
        self.bad(row(EMITTER, 'file:/tmp/fixed-source/classes/'))
    def test_19_source_host_spoof(self):
        self.bad(row(OBJECT, 'file:/tmp/fixed-source/classes/') + row(OWNER + '$$Lambda/0xabc', OBJECT))
    def test_20_empty_log(self):
        self.bad(prefix='')
    def test_21_other_runtime_and_warnings(self):
        x = 'WARNING: fixed JVM diagnostic\n' + row('java.lang.Object', 'shared objects file')
        self.assertEqual(evaluate(x)['loaded_count'], 3)

    def test_22_compiled_service_is_not_permission(self):
        self.bad(row('heteronpu.continuous.BlockScalarFloat', 'file:/tmp/fixed-source/classes/'))
    def test_23_compiled_gemmini_is_forbidden(self):
        self.bad(row('gemmini.HeteroFP32Alu', 'file:/tmp/fixed-source/classes/'))
    def test_24_constant_class_is_not_lambda_host(self):
        name = 'heteronpu.experimental.StrictFp32LaneMode$'
        self.bad(row(name, 'file:/tmp/fixed-source/classes/') + row(name + '$$Lambda/0xabc', name))
    def test_25_extra_emitter_class_rejected(self):
        extra = dict(C)
        extra['heteronpu/continuous/contracttests/GdnChunkTransposeChirrtlExtra.class'] = {'bytes': 1}
        with self.assertRaises(ValueError): parse(PREFIX.encode(), P, extra)
    def test_26_allowed_class_must_exist_in_input_pins(self):
        modified = dict(P)
        modified['input_class_relatives'] = [x for x in P['input_class_relatives'] if x != OWNER.replace('.', '/') + '.class']
        with self.assertRaises(ValueError): parse(PREFIX.encode(), modified, C)
    def test_27_interface_is_allowed_but_service_is_not(self):
        x = 'heteronpu.experimental.StrictFp32LaneRequest'
        value = evaluate(row(x, 'file:/tmp/fixed-source/classes/') + row(x + '$$Lambda/0xabc', x))
        self.assertEqual(value['hidden_host_names'], [x])

    def test_28_loan_and_scalar_interfaces_forbidden(self):
        for x in ['ElementwiseLoanPort','ElementwiseLoanRequest','ElementwiseLoanResult','GdnScalarClient','ScalarRequest','ScalarOp$','GdnChunkDerivedAndPairOwner']:
            with self.subTest(name=x): self.bad(row('heteronpu.continuous.' + x, 'file:/tmp/fixed-source/classes/'))
    def test_29_compiled_memory_engine_is_forbidden(self):
        self.bad(row('heteronpu.continuous.ElementwiseMemoryEngine', 'file:/tmp/fixed-source/classes/'))
        self.bad(row('heteronpu.p0.SharedL2Fabric', 'file:/tmp/fixed-source/classes/'))


IR = {'module_edges': {'HeteroBF16FmaMul': [], 'HeteroBF16FmaPost': [['post', 'MulAddRecFNToRaw_postMul_e8_s24']], 'HeteroBF16FmaRound': [['round', 'RoundRawFNToRecFN_e8_s24']], 'HeteroFullFp32FmaPre': [['pre', 'MulAddRecFNToRaw_preMul_e8_s24']], 'MulAddRecFNToRaw_postMul_e8_s24': [], 'MulAddRecFNToRaw_preMul_e8_s24': [], 'RoundAnyRawFNToRecFN_ie8_is26_oe8_os24': [], 'RoundRawFNToRecFN_e8_s24': [['roundAnyRawFNToRecFN', 'RoundAnyRawFNToRecFN_ie8_is26_oe8_os24']], 'StrictFp32MatrixLane': [['pre', 'HeteroFullFp32FmaPre'], ['mul', 'HeteroBF16FmaMul'], ['post', 'HeteroBF16FmaPost'], ['round', 'HeteroBF16FmaRound']]}, 'module_ports': {'HeteroBF16FmaMul': ['output io : { flip mulAddA : UInt<24>, flip mulAddB : UInt<24>, flip mulAddC : UInt<48>, mulAddResult : UInt<49>}'], 'HeteroBF16FmaPost': ['output io : { flip meta : UInt<54>, flip mulAddResult : UInt<49>, raw : UInt<41>, invalid : UInt<1>}'], 'HeteroBF16FmaRound': ['output io : { flip raw : UInt<41>, flip invalid : UInt<1>, out : UInt<32>, exceptionFlags : UInt<5>}'], 'HeteroFullFp32FmaPre': ['output io : { flip a : UInt<32>, flip b : UInt<32>, flip c : UInt<32>, mulAddA : UInt<24>, mulAddB : UInt<24>, mulAddC : UInt<48>, meta : UInt<54>}'], 'MulAddRecFNToRaw_postMul_e8_s24': ['output io : { flip fromPreMul : { isSigNaNAny : UInt<1>, isNaNAOrB : UInt<1>, isInfA : UInt<1>, isZeroA : UInt<1>, isInfB : UInt<1>, isZeroB : UInt<1>, signProd : UInt<1>, isNaNC : UInt<1>, isInfC : UInt<1>, isZeroC : UInt<1>, sExpSum : SInt<10>, doSubMags : UInt<1>, CIsDominant : UInt<1>, CDom_CAlignDist : UInt<5>, highAlignedSigC : UInt<26>, bit0AlignedSigC : UInt<1>}, flip mulAddResult : UInt<49>, flip roundingMode : UInt<3>, invalidExc : UInt<1>, rawOut : { isNaN : UInt<1>, isInf : UInt<1>, isZero : UInt<1>, sign : UInt<1>, sExp : SInt<10>, sig : UInt<27>}}'], 'MulAddRecFNToRaw_preMul_e8_s24': ['output io : { flip op : UInt<2>, flip a : UInt<33>, flip b : UInt<33>, flip c : UInt<33>, mulAddA : UInt<24>, mulAddB : UInt<24>, mulAddC : UInt<48>, toPostMul : { isSigNaNAny : UInt<1>, isNaNAOrB : UInt<1>, isInfA : UInt<1>, isZeroA : UInt<1>, isInfB : UInt<1>, isZeroB : UInt<1>, signProd : UInt<1>, isNaNC : UInt<1>, isInfC : UInt<1>, isZeroC : UInt<1>, sExpSum : SInt<10>, doSubMags : UInt<1>, CIsDominant : UInt<1>, CDom_CAlignDist : UInt<5>, highAlignedSigC : UInt<26>, bit0AlignedSigC : UInt<1>}}'], 'RoundAnyRawFNToRecFN_ie8_is26_oe8_os24': ['output io : { flip invalidExc : UInt<1>, flip infiniteExc : UInt<1>, flip in : { isNaN : UInt<1>, isInf : UInt<1>, isZero : UInt<1>, sign : UInt<1>, sExp : SInt<10>, sig : UInt<27>}, flip roundingMode : UInt<3>, flip detectTininess : UInt<1>, out : UInt<33>, exceptionFlags : UInt<5>}'], 'RoundRawFNToRecFN_e8_s24': ['output io : { flip invalidExc : UInt<1>, flip infiniteExc : UInt<1>, flip in : { isNaN : UInt<1>, isInf : UInt<1>, isZero : UInt<1>, sign : UInt<1>, sExp : SInt<10>, sig : UInt<27>}, flip roundingMode : UInt<3>, flip detectTininess : UInt<1>, out : UInt<33>, exceptionFlags : UInt<5>}'], 'StrictFp32MatrixLane': ['input clock : Clock', 'input reset : UInt<1>', 'output io : { flip request : { flip ready : UInt<1>, valid : UInt<1>, bits : { tag : UInt<32>, mode : UInt<2>, a : UInt<32>, b : UInt<32>, acc : UInt<32>}}, result : { flip ready : UInt<1>, valid : UInt<1>, bits : { tag : UInt<32>, mode : UInt<2>, status : UInt<3>, product : UInt<32>, productValid : UInt<1>, value : UInt<32>, valueValid : UInt<1>, accCommit : UInt<1>, mulFlags : UInt<5>, mulFlagsValid : UInt<1>, addFlags : UInt<5>, addFlagsValid : UInt<1>, fmaFlags : UInt<5>, fmaFlagsValid : UInt<1>, passesCompleted : UInt<2>}}, busy : UInt<1>}']}, 'not_proven': ['arithmetic output or flags', 'timing', 'physical mapped multiplier count', 'same area/Fmax', 'full array integration'], 'top_register_bits': 553, 'top_register_count': 12, 'top_register_types': {'addPass': 'UInt<1>', 'job': '{ tag : UInt<32>, mode : UInt<2>, a : UInt<32>, b : UInt<32>, acc : UInt<32>}', 'mulMeta': 'UInt<54>', 'mulValue': 'UInt<49>', 'postInvalid': 'UInt<1>', 'postRaw': 'UInt<41>', 'preA': 'UInt<24>', 'preB': 'UInt<24>', 'preC': 'UInt<48>', 'preMeta': 'UInt<54>', 'reply': '{ tag : UInt<32>, mode : UInt<2>, status : UInt<3>, product : UInt<32>, productValid : UInt<1>, value : UInt<32>, valueValid : UInt<1>, accCommit : UInt<1>, mulFlags : UInt<5>, mulFlagsValid : UInt<1>, addFlags : UInt<5>, addFlagsValid : UInt<1>, fmaFlags : UInt<5>, fmaFlagsValid : UInt<1>, passesCompleted : UInt<2>}', 'state': 'UInt<3>'}, 'variable_mul_count': 1, 'variable_mul_module': 'HeteroBF16FmaMul', 'variable_mul_operands': ['io.mulAddA', 'io.mulAddB']}
def fixture_ir():
    # Constructed parser fixture only, NOT an elaborated or simulated hardware result.
    rows = ['FIRRTL version 3.3.0', 'circuit StrictFp32MatrixLane :']
    for module, ports in IR['module_ports'].items():
        rows.append('  module ' + module + ' :')
        rows += ['    ' + x for x in ports]
        rows += ['    inst ' + inst + ' of ' + target for inst, target in IR['module_edges'][module]]
        if module == 'StrictFp32MatrixLane':
            rows += ['    regreset ' + k + ' : ' + v + ', clock, reset, UInt<1>(0h0)' for k,v in IR['top_register_types'].items()]
        if module == 'HeteroBF16FmaMul':
            rows.append('    node product = mul(io.mulAddA, io.mulAddB)')
    return '\n'.join(rows) + '\n'

class IRControls(unittest.TestCase):
    def bad(self, text):
        with self.assertRaises(ValueError): parse_ir(text.encode(), IR)
    def test_30_exact_tree_ports_mul_registers(self):
        r=parse_ir(fixture_ir().encode(), IR)
        self.assertEqual((r['module_count'], r['instance_count'], r['variable_mul_count'], r['top_register_count']), (9,8,1,12))
    def test_31_duplicate_chain(self):
        self.bad(fixture_ir().replace('inst mul of HeteroBF16FmaMul', 'inst mul of HeteroBF16FmaMul\n    inst secondMul of HeteroBF16FmaMul'))
    def test_32_wrong_parent(self):
        t=fixture_ir().replace('    inst pre of MulAddRecFNToRaw_preMul_e8_s24\n','')
        self.bad(t.replace('    inst mul of HeteroBF16FmaMul','    inst preChild of MulAddRecFNToRaw_preMul_e8_s24\n    inst mul of HeteroBF16FmaMul'))
    def test_33_extra_module(self):
        self.bad(fixture_ir()+'  module HiddenArray :\n')
    def test_34_wrong_width(self):
        self.bad(fixture_ir().replace('flip mulAddA : UInt<24>','flip mulAddA : UInt<16>',1))
    def test_35_wrong_top_payload(self):
        self.bad(fixture_ir().replace('tag : UInt<32>','tag : UInt<31>',1))
    def test_36_wrong_direction(self):
        self.bad(fixture_ir().replace('flip request :','request :',1))
    def test_37_wrong_mul_operands(self):
        self.bad(fixture_ir().replace('mul(io.mulAddA, io.mulAddB)','mul(io.mulAddA, io.mulAddA)'))
    def test_38_second_mul_nested(self):
        self.bad(fixture_ir().replace('mul(io.mulAddA, io.mulAddB)','mul(io.mulAddA, mul(io.mulAddA, io.mulAddB))'))
    def test_39_missing_mul(self):
        self.bad(fixture_ir().replace('mul(io.mulAddA, io.mulAddB)','add(io.mulAddA, io.mulAddB)'))
    def test_40_memory_or_external_forbidden(self):
        for line in ['mem x :','cmem x : UInt<8>[2]','smem x : UInt<8>[2]','extmodule Tool :','intmodule Intrinsic :','intrinsic blackbox']:
            with self.subTest(line=line): self.bad(fixture_ir()+'    '+line+'\n')
    def test_41_descendant_register_forbidden(self):
        self.bad(fixture_ir().replace('  module HeteroBF16FmaMul :\n','  module HeteroBF16FmaMul :\n    regreset hidden : UInt<1>, clock, reset, UInt<1>(0h0)\n'))
    def test_42_missing_top_register(self):
        self.bad(fixture_ir().replace('    regreset addPass : UInt<1>, clock, reset, UInt<1>(0h0)\n',''))
    def test_43_duplicate_module(self):
        self.bad(fixture_ir()+'  module StrictFp32MatrixLane :\n')
    def test_44_old_bf16_chain_forbidden(self):
        for name in ['gemmini.HeteroBF16FmaPre','gemmini.HeteroBF16FmaLane','gemmini.EmitHeteroBF16Fma$','hardfloat.MulAddRecFN']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): evaluate(row(name,'file:/tmp/fixed-source/classes/'))
    def test_45_gemmini_and_hardfloat_exact_sources(self):
        for name in ['gemmini.HeteroBF16FmaMul','hardfloat.RoundRawFNToRecFN']:
            with self.subTest(name=name):
                self.assertEqual(evaluate(row(name,'file:/tmp/fixed-source/classes/'))['ordinary_candidate_count'],2)
                with self.assertRaises(ValueError): evaluate(row(name,'file:/tmp/other.jar'))

try:
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(ParserControls), unittest.defaultTestLoader.loadTestsFromTestCase(IRControls)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful() and result.testsRun == 45
    assert hashlib.sha256(p.read_bytes()).hexdigest() == DRIVER_PIN['sha256']
    print(json.dumps({'status': 'PASS_PURE_CLASS_LOG_AND_IR_PARSER_CONTROLS_ONLY', 'groups': result.testsRun,
                      'driver_pin': DRIVER_PIN, 'elapsed_seconds': time.monotonic() - START,
                      'JVM_executed': False, 'owner_constructed': False, 'IR_fixture_not_generated_hardware': True}))
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
