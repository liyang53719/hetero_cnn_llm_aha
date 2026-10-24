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
DRIVER_PIN = {'bytes': 19600, 'sha256': 'b049bd763fc1d479aad942674b5960af9a9e749f6c80297d435dc72e3bb32b19'}
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
selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'need', 'validate_loaded_classes'}]
assert len(selected) == 2
ns = {'re': re, 'Path': Path}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(p), 'exec', dont_inherit=True), ns)
parse = ns['validate_loaded_classes']
OWNER = 'heteronpu.continuous.GdnChunkDerivedAndPairOwner'
OBJECT = 'heteronpu.continuous.GdnChunkAddressPlan$'
EMITTER = 'heteronpu.continuous.contracttests.GdnChunkDerivedChirrtl$'
P = {'input_class_root': '/tmp/fixed-source/classes', 'work': '/tmp/new-owned', 'input_class_relatives': ['heteronpu/continuous/ElementwiseLoanOp$.class', 'heteronpu/continuous/ElementwiseLoanPort.class', 'heteronpu/continuous/ElementwiseLoanRequest.class', 'heteronpu/continuous/ElementwiseLoanResult.class', 'heteronpu/continuous/GdnChunkAddressPlan$.class', 'heteronpu/continuous/GdnChunkAddressPlan$Phase.class', 'heteronpu/continuous/GdnChunkAddressPlan$Shape.class', 'heteronpu/continuous/GdnChunkCommittedState.class', 'heteronpu/continuous/GdnChunkDerivedAndPairJob.class', 'heteronpu/continuous/GdnChunkDerivedAndPairOwner.class', 'heteronpu/continuous/GdnChunkDerivedAndPairPort.class', 'heteronpu/continuous/GdnChunkDerivedAndPairResult.class', 'heteronpu/continuous/GdnChunkGeometry$.class', 'heteronpu/continuous/GdnChunkJob.class', 'heteronpu/continuous/GdnChunkLoadPrepResult.class', 'heteronpu/continuous/GdnChunkPrivateDecay.class', 'heteronpu/continuous/GdnChunkStageReceipt.class', 'heteronpu/continuous/GdnChunkVectorPolicy$.class', 'heteronpu/continuous/GdnScalarClient.class', 'heteronpu/continuous/MemoryRequest.class', 'heteronpu/continuous/MemoryResponse.class', 'heteronpu/continuous/ScalarOp$.class', 'heteronpu/continuous/ScalarRequest.class', 'heteronpu/continuous/Status$.class', 'heteronpu/continuous/BlockScalarFloat.class', 'heteronpu/continuous/ElementwiseRegisterLoan.class', 'heteronpu/continuous/ElementwiseMemoryEngine.class'], 'allowed_input_classes': ['heteronpu.continuous.ElementwiseLoanOp$', 'heteronpu.continuous.ElementwiseLoanPort', 'heteronpu.continuous.ElementwiseLoanRequest', 'heteronpu.continuous.ElementwiseLoanResult', 'heteronpu.continuous.GdnChunkAddressPlan$', 'heteronpu.continuous.GdnChunkAddressPlan$Phase', 'heteronpu.continuous.GdnChunkAddressPlan$Shape', 'heteronpu.continuous.GdnChunkCommittedState', 'heteronpu.continuous.GdnChunkDerivedAndPairJob', 'heteronpu.continuous.GdnChunkDerivedAndPairOwner', 'heteronpu.continuous.GdnChunkDerivedAndPairPort', 'heteronpu.continuous.GdnChunkDerivedAndPairResult', 'heteronpu.continuous.GdnChunkGeometry$', 'heteronpu.continuous.GdnChunkJob', 'heteronpu.continuous.GdnChunkLoadPrepResult', 'heteronpu.continuous.GdnChunkPrivateDecay', 'heteronpu.continuous.GdnChunkStageReceipt', 'heteronpu.continuous.GdnChunkVectorPolicy$', 'heteronpu.continuous.GdnScalarClient', 'heteronpu.continuous.MemoryRequest', 'heteronpu.continuous.MemoryResponse', 'heteronpu.continuous.ScalarOp$', 'heteronpu.continuous.ScalarRequest', 'heteronpu.continuous.Status$'], 'allowed_hidden_hosts': ['heteronpu.continuous.ElementwiseLoanPort', 'heteronpu.continuous.ElementwiseLoanRequest', 'heteronpu.continuous.ElementwiseLoanResult', 'heteronpu.continuous.GdnChunkAddressPlan$', 'heteronpu.continuous.GdnChunkCommittedState', 'heteronpu.continuous.GdnChunkDerivedAndPairJob', 'heteronpu.continuous.GdnChunkDerivedAndPairOwner', 'heteronpu.continuous.GdnChunkDerivedAndPairPort', 'heteronpu.continuous.GdnChunkDerivedAndPairResult', 'heteronpu.continuous.GdnChunkJob', 'heteronpu.continuous.GdnChunkLoadPrepResult', 'heteronpu.continuous.GdnChunkPrivateDecay', 'heteronpu.continuous.GdnChunkStageReceipt', 'heteronpu.continuous.GdnScalarClient', 'heteronpu.continuous.MemoryRequest', 'heteronpu.continuous.MemoryResponse', 'heteronpu.continuous.ScalarRequest', 'heteronpu.continuous.contracttests.GdnChunkDerivedChirrtl$'], 'expected_emitter_classes': ['heteronpu/continuous/contracttests/GdnChunkDerivedChirrtl.class', 'heteronpu/continuous/contracttests/GdnChunkDerivedChirrtl$.class', 'heteronpu/continuous/contracttests/GdnChunkDerivedChirrtl$NoExternalTools.class'], 'required_elaboration_classes': ['heteronpu.continuous.GdnChunkDerivedAndPairOwner', 'circt.stage.ChiselStage$']}
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
        name = 'heteronpu.continuous.ScalarOp$'
        self.bad(row(name, 'file:/tmp/fixed-source/classes/') + row(name + '$$Lambda/0xabc', name))
    def test_25_extra_emitter_class_rejected(self):
        extra = dict(C)
        extra['heteronpu/continuous/contracttests/GdnChunkDerivedChirrtlExtra.class'] = {'bytes': 1}
        with self.assertRaises(ValueError): parse(PREFIX.encode(), P, extra)
    def test_26_allowed_class_must_exist_in_input_pins(self):
        modified = dict(P)
        modified['input_class_relatives'] = [x for x in P['input_class_relatives'] if x != OWNER.replace('.', '/') + '.class']
        with self.assertRaises(ValueError): parse(PREFIX.encode(), modified, C)
    def test_27_interface_is_allowed_but_service_is_not(self):
        x = 'heteronpu.continuous.GdnScalarClient'
        value = evaluate(row(x, 'file:/tmp/fixed-source/classes/') + row(x + '$$Lambda/0xabc', x))
        self.assertEqual(value['hidden_host_names'], [x])

    def test_28_loan_interface_not_loan_implementation(self):
        x = 'heteronpu.continuous.ElementwiseLoanPort'
        value = evaluate(row(x, 'file:/tmp/fixed-source/classes/') + row(x + '$$Lambda/0xabc', x))
        self.assertEqual(value['hidden_host_names'], [x])
        self.bad(row('heteronpu.continuous.ElementwiseRegisterLoan', 'file:/tmp/fixed-source/classes/'))
    def test_29_compiled_memory_engine_is_forbidden(self):
        self.bad(row('heteronpu.continuous.ElementwiseMemoryEngine', 'file:/tmp/fixed-source/classes/'))
        self.bad(row('heteronpu.p0.SharedL2Fabric', 'file:/tmp/fixed-source/classes/'))


try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ParserControls))
    assert result.wasSuccessful() and result.testsRun == 29
    assert hashlib.sha256(p.read_bytes()).hexdigest() == DRIVER_PIN['sha256']
    print(json.dumps({'status': 'PASS_PURE_CLASS_LOG_PARSER_CONTROLS_ONLY', 'groups': result.testsRun,
                      'driver_pin': DRIVER_PIN, 'elapsed_seconds': time.monotonic() - START,
                      'JVM_executed': False, 'owner_constructed': False, 'old_FAIL_changed': False}))
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
