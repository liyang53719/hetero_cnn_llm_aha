#!/usr/bin/env python3
"""One CI recovery job. Native work requires --execute and a fixed job deadline.

Only the three strictly validated evidence JSONs may be published. Private logs,
artifacts, source archives, generated RTL and tool inventories stay in --out.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B')
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import time
import traceback
import types

HERE = Path(__file__).absolute().parent
SUPPORT = ('ci_support_v3.py', 16348, '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1')
PINS_SIZE = 3032
PINS_SHA = '64f4933bae8d2ad6ed7e6e230891f4e9a5cb720fbea623da2ed39903c022b66a'
MIB = 1024**2
GIB = 1024**3
EVIDENCE = ('summary.json', 'source_hashes.json', 'stage_exits.json')
COMPONENTS = ('toolchain', 'host_emission', 'idma319', 'retained13', 'configuration', 'host_execution')
CATEGORIES = ('NONE', 'TIMEOUT', 'INPUT_OR_CONTRACT', 'SYSTEM', 'INTERRUPTED', 'UNEXPECTED')
STAGES = ('official_source473',) + tuple('host_' + x + '-' + y for y in ('version', 'micro') for x in ('autoconf', 'autom4te', 'm4', 'flex', 'bison')) + ('fresh_autoconf', 'fresh_configure', 'fresh_make') + tuple('derived_tiny_' + x for x in ('version', 'generate', 'compile', 'run')) + ('host93_java_version', 'host93_acquire_jar87', 'host93_acquire_hardfloat20', 'host93_assemble', 'host93_class', 'host93_chirrtl', 'host93_acquire_firtool', 'host93_sv', 'idma319_extract', 'retained13_assemble', 'host93_configuration', 'host93_cpp_generate', 'host93_cpp_compile', 'host93_reset_launch')
SCOPES = ('toolchain_build', 'toolchain_tiny', 'fresh_host_sv', 'cpp_generated', 'cpp_compiled', 'reset_launch', 'n0_numeric', 'weights_loaded')
GENERATED_KINDS = ('derived_backend', 'host93_fir', 'host93_sv', 'host_elf')
MODES = ('host-reset-launch','build-diagnostic')
BUILD_STAGES = STAGES[:14]
# Exact path-only projection of FIXED_CORE_MEMBERS.json SHA256 4d21da65...; public official source names only.
DIAGNOSTIC_PATHS = frozenset(('.bake.toml', '.clang-format', '.clang-tidy', '.codacy.yml', '.codecov.yml', '.gitattributes', '.gitignore', '.pre-commit-hooks.yaml', '.style.yapf', 'AGENTS.md', 'CITATION.cff', 'CMakeLists.txt', 'CPPLINT.cfg', 'Changes', 'LICENSE', 'LICENSES/Apache-2.0.txt', 'LICENSES/Artistic-2.0.txt', 'LICENSES/BSD-3-Clause.txt', 'LICENSES/CC0-1.0.txt', 'LICENSES/ISC.txt', 'LICENSES/LGPL-3.0-only.txt', 'LICENSES/LicenseRef-Altera-No-Warranty.txt', 'LICENSES/LicenseRef-IEEE-1800.txt', 'LICENSES/MIT.txt', 'LICENSES/Unlicense.txt', 'Makefile.in', 'README.rst', 'REUSE.toml', 'bin/redirect', 'bin/verilator', 'bin/verilator_ccache_report', 'bin/verilator_coverage', 'bin/verilator_difftree', 'bin/verilator_gantt', 'bin/verilator_includer', 'bin/verilator_profcfunc', 'configure.ac', 'include/.gitignore', 'include/AGENTS.md', 'include/fstcpp/.clang-format', 'include/fstcpp/fstcpp.h', 'include/fstcpp/fstcpp_assertion.h', 'include/fstcpp/fstcpp_file.h', 'include/fstcpp/fstcpp_stream_write_helper.h', 'include/fstcpp/fstcpp_variable_info.cpp', 'include/fstcpp/fstcpp_variable_info.h', 'include/fstcpp/fstcpp_writer.cpp', 'include/fstcpp/fstcpp_writer.h', 'include/verilated.cpp', 'include/verilated.h', 'include/verilated.mk.in', 'include/verilated.v', 'include/verilated_config.h.in', 'include/verilated_cov.cpp', 'include/verilated_cov.h', 'include/verilated_cov_key.h', 'include/verilated_cov_model.h', 'include/verilated_covergroup.cpp', 'include/verilated_covergroup.h', 'include/verilated_dpi.cpp', 'include/verilated_dpi.h', 'include/verilated_force.h', 'include/verilated_fst_c.cpp', 'include/verilated_fst_c.h', 'include/verilated_fst_sc.cpp', 'include/verilated_fst_sc.h', 'include/verilated_funcs.h', 'include/verilated_imp.h', 'include/verilated_intrinsics.h', 'include/verilated_probdist.cpp', 'include/verilated_profiler.cpp', 'include/verilated_profiler.h', 'include/verilated_random.cpp', 'include/verilated_random.h', 'include/verilated_saif_c.cpp', 'include/verilated_saif_c.h', 'include/verilated_saif_sc.h', 'include/verilated_save.cpp', 'include/verilated_save.h', 'include/verilated_sc.h', 'include/verilated_sc_trace.h', 'include/verilated_std.sv', 'include/verilated_std_waiver.vlt', 'include/verilated_sym_props.h', 'include/verilated_syms.h', 'include/verilated_threads.cpp', 'include/verilated_threads.h', 'include/verilated_timing.cpp', 'include/verilated_timing.h', 'include/verilated_trace.h', 'include/verilated_trace_imp.h', 'include/verilated_types.h', 'include/verilated_vcd_c.cpp', 'include/verilated_vcd_c.h', 'include/verilated_vcd_sc.cpp', 'include/verilated_vcd_sc.h', 'include/verilated_vpi.cpp', 'include/verilated_vpi.h', 'include/verilatedos.h', 'include/verilatedos_c.h', 'include/vltstd/sv_vpi_user.h', 'include/vltstd/svdpi.h', 'include/vltstd/veriuser.h', 'include/vltstd/vpi_user.h', 'install-sh', 'python-dev-requirements.txt', 'src/.gdbinit', 'src/.gdbinit.py', 'src/.gitignore', 'src/AGENTS.md', 'src/CMakeLists.txt', 'src/Makefile.in', 'src/Makefile_obj.in', 'src/V3Active.cpp', 'src/V3Active.h', 'src/V3ActiveTop.cpp', 'src/V3ActiveTop.h', 'src/V3Assert.cpp', 'src/V3Assert.h', 'src/V3AssertNfa.cpp', 'src/V3AssertNfa.h', 'src/V3AssertPre.cpp', 'src/V3AssertPre.h', 'src/V3Ast.cpp', 'src/V3Ast.h', 'src/V3AstAttr.h', 'src/V3AstInlines.h', 'src/V3AstNodeDType.h', 'src/V3AstNodeExpr.h', 'src/V3AstNodeOther.h', 'src/V3AstNodeStmt.h', 'src/V3AstNodes.cpp', 'src/V3AstPatterns.h', 'src/V3AstUserAllocator.h', 'src/V3Begin.cpp', 'src/V3Begin.h', 'src/V3Branch.cpp', 'src/V3Branch.h', 'src/V3Broken.cpp', 'src/V3Broken.h', 'src/V3CCtors.cpp', 'src/V3CCtors.h', 'src/V3CUse.cpp', 'src/V3CUse.h', 'src/V3Case.cpp', 'src/V3Case.h', 'src/V3Cast.cpp', 'src/V3Cast.h', 'src/V3Cfg.cpp', 'src/V3Cfg.h', 'src/V3CfgBuilder.cpp', 'src/V3CfgLiveVariables.cpp', 'src/V3Class.cpp', 'src/V3Class.h', 'src/V3ClassGraph.cpp', 'src/V3ClassGraph.h', 'src/V3Clean.cpp', 'src/V3Clean.h', 'src/V3Clock.cpp', 'src/V3Clock.h', 'src/V3Combine.cpp', 'src/V3Combine.h', 'src/V3Common.cpp', 'src/V3Common.h', 'src/V3Const.cpp', 'src/V3Const.h', 'src/V3ConstPool.cpp', 'src/V3ConstPool.h', 'src/V3Container.h', 'src/V3Control.cpp', 'src/V3Control.h', 'src/V3Coverage.cpp', 'src/V3Coverage.h', 'src/V3CoverageJoin.cpp', 'src/V3CoverageJoin.h', 'src/V3Covergroup.cpp', 'src/V3Covergroup.h', 'src/V3Dead.cpp', 'src/V3Dead.h', 'src/V3DebugBisect.h', 'src/V3Delayed.cpp', 'src/V3Delayed.h', 'src/V3Depth.cpp', 'src/V3Depth.h', 'src/V3DepthBlock.cpp', 'src/V3DepthBlock.h', 'src/V3Descope.cpp', 'src/V3Descope.h', 'src/V3Dfg.cpp', 'src/V3Dfg.h', 'src/V3DfgAstToDfg.cpp', 'src/V3DfgBreakCycles.cpp', 'src/V3DfgCache.h', 'src/V3DfgColorSCCs.cpp', 'src/V3DfgContext.h', 'src/V3DfgCse.cpp', 'src/V3DfgDataType.cpp', 'src/V3DfgDataType.h', 'src/V3DfgDecomposition.cpp', 'src/V3DfgDfgToAst.cpp', 'src/V3DfgOptimizer.cpp', 'src/V3DfgOptimizer.h', 'src/V3DfgPasses.cpp', 'src/V3DfgPasses.h', 'src/V3DfgPeephole.cpp', 'src/V3DfgPeepholePatterns.h', 'src/V3DfgPushDownSels.cpp', 'src/V3DfgRegularize.cpp', 'src/V3DfgSynthesize.cpp', 'src/V3DfgVertices.h', 'src/V3DiagSarif.cpp', 'src/V3DiagSarif.h', 'src/V3DupFinder.cpp', 'src/V3DupFinder.h', 'src/V3EmitC.h', 'src/V3EmitCBase.cpp', 'src/V3EmitCBase.h', 'src/V3EmitCConstInit.h', 'src/V3EmitCConstPool.cpp', 'src/V3EmitCFunc.cpp', 'src/V3EmitCFunc.h', 'src/V3EmitCHeaders.cpp', 'src/V3EmitCImp.cpp', 'src/V3EmitCInlines.cpp', 'src/V3EmitCMain.cpp', 'src/V3EmitCMain.h', 'src/V3EmitCModel.cpp', 'src/V3EmitCPch.cpp', 'src/V3EmitCSyms.cpp', 'src/V3EmitMk.cpp', 'src/V3EmitMk.h', 'src/V3EmitMkJson.cpp', 'src/V3EmitMkJson.h', 'src/V3EmitV.cpp', 'src/V3EmitV.h', 'src/V3Error.cpp', 'src/V3Error.h', 'src/V3ExecGraph.cpp', 'src/V3ExecGraph.h', 'src/V3Expand.cpp', 'src/V3Expand.h', 'src/V3File.cpp', 'src/V3File.h', 'src/V3FileLine.cpp', 'src/V3FileLine.h', 'src/V3Force.cpp', 'src/V3Force.h', 'src/V3Fork.cpp', 'src/V3Fork.h', 'src/V3FsmDetect.cpp', 'src/V3FsmDetect.h', 'src/V3FuncOpt.cpp', 'src/V3FuncOpt.h', 'src/V3FunctionTraits.h', 'src/V3Gate.cpp', 'src/V3Gate.h', 'src/V3Global.cpp', 'src/V3Global.h', 'src/V3Graph.cpp', 'src/V3Graph.h', 'src/V3GraphAcyc.cpp', 'src/V3GraphAlg.cpp', 'src/V3GraphAlg.h', 'src/V3GraphPathChecker.cpp', 'src/V3GraphPathChecker.h', 'src/V3GraphStream.h', 'src/V3GraphTest.cpp', 'src/V3Hash.cpp', 'src/V3Hash.h', 'src/V3HashTable.cpp', 'src/V3HashTable.h', 'src/V3Hasher.cpp', 'src/V3Hasher.h', 'src/V3HierBlock.cpp', 'src/V3HierBlock.h', 'src/V3Inline.cpp', 'src/V3Inline.h', 'src/V3InlineCFuncs.cpp', 'src/V3InlineCFuncs.h', 'src/V3Inst.cpp', 'src/V3Inst.h', 'src/V3InstrCount.cpp', 'src/V3InstrCount.h', 'src/V3Interface.cpp', 'src/V3Interface.h', 'src/V3LangCode.h', 'src/V3LanguageWords.h', 'src/V3LibMap.cpp', 'src/V3LibMap.h', 'src/V3Life.cpp', 'src/V3Life.h', 'src/V3LifePost.cpp', 'src/V3LifePost.h', 'src/V3LiftExpr.cpp', 'src/V3LiftExpr.h', 'src/V3LinkCells.cpp', 'src/V3LinkCells.h', 'src/V3LinkDot.cpp', 'src/V3LinkDot.h', 'src/V3LinkDotIfaceCapture.cpp', 'src/V3LinkDotIfaceCapture.h', 'src/V3LinkInc.cpp', 'src/V3LinkInc.h', 'src/V3LinkJump.cpp', 'src/V3LinkJump.h', 'src/V3LinkLValue.cpp', 'src/V3LinkLValue.h', 'src/V3LinkLevel.cpp', 'src/V3LinkLevel.h', 'src/V3LinkParse.cpp', 'src/V3LinkParse.h', 'src/V3LinkResolve.cpp', 'src/V3LinkResolve.h', 'src/V3LinkWith.cpp', 'src/V3LinkWith.h', 'src/V3List.h', 'src/V3Localize.cpp', 'src/V3Localize.h', 'src/V3MemberMap.h', 'src/V3MergeCond.cpp', 'src/V3MergeCond.h', 'src/V3Mutex.h', 'src/V3Name.cpp', 'src/V3Name.h', 'src/V3Number.cpp', 'src/V3Number.h', 'src/V3OptionParser.cpp', 'src/V3OptionParser.h', 'src/V3Options.cpp', 'src/V3Options.h', 'src/V3Order.cpp', 'src/V3Order.h', 'src/V3OrderCFuncEmitter.h', 'src/V3OrderGraph.h', 'src/V3OrderGraphBuilder.cpp', 'src/V3OrderInternal.h', 'src/V3OrderMTaskContraction.cpp', 'src/V3OrderMTaskFixHazards.cpp', 'src/V3OrderMTaskGraph.cpp', 'src/V3OrderMTaskGraph.h', 'src/V3OrderMoveGraph.cpp', 'src/V3OrderMoveGraph.h', 'src/V3OrderParallel.cpp', 'src/V3OrderProcessDomains.cpp', 'src/V3OrderSerial.cpp', 'src/V3Os.cpp', 'src/V3Os.h', 'src/V3PairingHeap.h', 'src/V3Param.cpp', 'src/V3Param.h', 'src/V3Parse.h', 'src/V3ParseGrammar.cpp', 'src/V3ParseGrammar.h', 'src/V3ParseImp.cpp', 'src/V3ParseImp.h', 'src/V3ParseLex.cpp', 'src/V3PatternStats.cpp', 'src/V3PchAstMT.h', 'src/V3PchAstNoMT.h', 'src/V3PoolAllocator.h', 'src/V3PreExpr.h', 'src/V3PreLex.h', 'src/V3PreLex.l', 'src/V3PreProc.cpp', 'src/V3PreProc.h', 'src/V3PreShell.cpp', 'src/V3PreShell.h', 'src/V3Premit.cpp', 'src/V3Premit.h', 'src/V3ProtectLib.cpp', 'src/V3ProtectLib.h', 'src/V3RandSequence.cpp', 'src/V3RandSequence.h', 'src/V3Randomize.cpp', 'src/V3Randomize.h', 'src/V3Reloop.cpp', 'src/V3Reloop.h', 'src/V3Reorder.cpp', 'src/V3Reorder.h', 'src/V3Rtti.h', 'src/V3Sampled.cpp', 'src/V3Sampled.h', 'src/V3Sched.cpp', 'src/V3Sched.h', 'src/V3SchedAcyclic.cpp', 'src/V3SchedCovergroup.cpp', 'src/V3SchedPartition.cpp', 'src/V3SchedReplicate.cpp', 'src/V3SchedTiming.cpp', 'src/V3SchedTrigger.cpp', 'src/V3SchedUtil.cpp', 'src/V3SchedVirtIface.cpp', 'src/V3Scope.cpp', 'src/V3Scope.h', 'src/V3SenExprBuilder.h', 'src/V3SenTree.h', 'src/V3Simulate.h', 'src/V3Slice.cpp', 'src/V3Slice.h', 'src/V3Split.cpp', 'src/V3Split.h', 'src/V3SplitVar.cpp', 'src/V3SplitVar.h', 'src/V3StackCount.cpp', 'src/V3StackCount.h', 'src/V3Stats.cpp', 'src/V3Stats.h', 'src/V3StatsReport.cpp', 'src/V3StdFuture.h', 'src/V3String.cpp', 'src/V3String.h', 'src/V3Subst.cpp', 'src/V3Subst.h', 'src/V3SymTable.h', 'src/V3Table.cpp', 'src/V3Table.h', 'src/V3Task.cpp', 'src/V3Task.h', 'src/V3ThreadPool.cpp', 'src/V3ThreadPool.h', 'src/V3Timing.cpp', 'src/V3Timing.h', 'src/V3Trace.cpp', 'src/V3Trace.h', 'src/V3TraceDecl.cpp', 'src/V3TraceDecl.h', 'src/V3Tristate.cpp', 'src/V3Tristate.h', 'src/V3Udp.cpp', 'src/V3Udp.h', 'src/V3Undriven.cpp', 'src/V3Undriven.h', 'src/V3UndrivenCapture.cpp', 'src/V3UndrivenCapture.h', 'src/V3UniqueNames.h', 'src/V3Unknown.cpp', 'src/V3Unknown.h', 'src/V3Unroll.cpp', 'src/V3Unroll.h', 'src/V3UnrollGen.cpp', 'src/V3VariableOrder.cpp', 'src/V3VariableOrder.h', 'src/V3Waiver.cpp', 'src/V3Waiver.h', 'src/V3Width.cpp', 'src/V3Width.h', 'src/V3WidthCommit.cpp', 'src/V3WidthCommit.h', 'src/V3WidthRemove.h', 'src/V3WidthSel.cpp', 'src/Verilator.cpp', 'src/VlcBucket.h', 'src/VlcMain.cpp', 'src/VlcOptions.h', 'src/VlcPoint.h', 'src/VlcSource.h', 'src/VlcTest.h', 'src/VlcTop.cpp', 'src/VlcTop.h', 'src/astgen', 'src/bisonpre', 'src/config_build.h', 'src/config_package.h.in', 'src/config_rev', 'src/cppcheck-suppressions.txt', 'src/flexfix', 'src/mkinstalldirs', 'src/verilog.l', 'src/verilog.y', 'src/vlcovgen', 'verilator-config-version.cmake.in', 'verilator-config.cmake.in', 'verilator.pc.in'))



def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain_path(value):
    p = Path(value)
    require(re.fullmatch('[A-Za-z0-9_/.-]+', str(p)) is not None, 'finite ASCII make-safe path required')
    require(p.is_absolute() and '..' not in p.parts, 'absolute normalized path required')
    for q in (p,) + tuple(p.parents):
        require(not q.is_symlink(), 'symlink path rejected')
    return p


def bounded_read(path, cap):
    p = plain_path(path)
    with p.open('rb') as f:
        a = os.fstat(f.fileno())
        require(stat.S_ISREG(a.st_mode) and 0 <= a.st_size <= cap, 'bounded regular input')
        raw = f.read(cap + 1)
        z = os.fstat(f.fileno())
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(raw) == a.st_size and stamp(a) == stamp(z) == stamp(p.stat()), 'stable bounded input')
    return raw



def compiler_log_tail(path):
    """Read at most 1 MiB from the fixed merged native.log, after supervision."""
    p = plain_path(path)
    with p.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= GIB, 'bounded merged compiler log')
        truncated = before.st_size > MIB
        stream.seek(max(0, before.st_size-MIB))
        raw = stream.read(MIB+1)
        after = os.fstat(stream.fileno())
    stamp=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
    require(len(raw)==min(before.st_size,MIB) and stamp(before)==stamp(after)==stamp(p.stat()), 'stable merged compiler log tail')
    if truncated:
        raw=raw.partition(b'\n')[2]  # Never parse a partial line as a new source location.
    return raw,truncated


def exact(path, size, digest):
    require(type(size) is int and size >= 0 and re.fullmatch('[0-9a-f]{64}', digest or ''), 'fixed source pin bound')
    raw = bounded_read(path, size)
    require(len(raw) == size and sha(raw) == digest, 'fixed source identity before compile')
    return raw


def load(path, size, digest, name):
    raw = exact(path, size, digest)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def keys(value, names):
    require(type(value) is dict and set(value) == set(names), 'strict evidence object keys')


def pin(value, path=False):
    keys(value, ('path', 'bytes', 'sha256') if path else ('bytes', 'sha256'))
    require(type(value['bytes']) is int and 0 <= value['bytes'] <= 8*GIB and
            type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'safe content identity')
    if path:
        name = value['path']
        require(type(name) is str and len(name) <= 240 and re.fullmatch('[A-Za-z0-9_./-]+', name) and
                not name.startswith('/') and '..' not in name.split('/') and
                name.startswith(('candidates/host93_ci_recovery/', 'development_snapshots/', 'candidates/qwen2_resident_matrix/')),
                'only project-relative source names')


def empty_diagnostics(state='NOT_COLLECTED'):
    require(state in ('NOT_COLLECTED','READ_ERROR','SANITIZER_ERROR'), 'finite empty context state')
    return {'observations': [], 'merged_log_tail': '', 'truncated': False, 'context_state': state}


DIAGNOSTIC_MESSAGES = {
    'syntax_error_reported': 'Compiler reported a syntax error.',
    'undeclared_name_reported': 'Compiler reported an undeclared name.',
    'unknown_type_reported': 'Compiler reported an unknown type.',
    'header_unavailable_reported': 'Compiler reported an unavailable header.',
    'compiler_termination_reported': 'Compiler reported signal termination; cause is unestablished.',
}
FAILURE_CODES = ('NONE', 'UNKNOWN', 'RECEIPT_UNAVAILABLE', 'RECEIPT_INVALID', 'RECEIPT_PARTIAL',
    'SAMPLER_CONTRACT', 'SUPERVISOR_TIMEOUT_CLASSIFICATION', 'LOG_LIMIT', 'CHILD_SIGNAL',
    'CHILD_EXIT_NONZERO', 'CLEANUP_UNCONFIRMED', 'PHASE_POSTFLIGHT')
OBSERVATION_KEYS = ('exit_code','final_reap_signal','receipt_timed_out','cleanup_confirmed',
    'waitid_code','waitid_status','kill_attempted','kill_result','native_record_status',
    'failure_code','failure_boundary','child_user_cpu_seconds','child_system_cpu_seconds',
    'child_maxrss_kib_cumulative')


def validate_diagnostics(value):
    keys(value, ('observations','merged_log_tail','truncated','context_state'))
    require(value['context_state'] in ('NOT_COLLECTED','AVAILABLE','READ_ERROR','SANITIZER_ERROR'), 'finite context collection state')
    require(type(value['observations']) is list and len(value['observations']) <= 20 and
            type(value['truncated']) is bool and type(value['merged_log_tail']) is str, 'finite diagnostic shape')
    for row in value['observations']:
        require(type(row) is dict and row.get('category') in DIAGNOSTIC_MESSAGES and
                row.get('message') == DIAGNOSTIC_MESSAGES[row['category']], 'fixed diagnostic prose only')
        category=row['category']
        if category=='compiler_termination_reported':
            keys(row,('category','message'));location=''
        else:
            keys(row,('path','line','column','category','message'))
            require(row['path'] in DIAGNOSTIC_PATHS and type(row['line']) is int and 1 <= row['line'] <= 9999999 and
                    (row['column'] is None or type(row['column']) is int and 1 <= row['column'] <= 9999999), 'fixed public source location')
            location=row['path']+':'+str(row['line'])+(':'+str(row['column']) if row['column'] is not None else '')+': '
    tail=value['merged_log_tail']
    require(all(32 <= ord(c) <= 126 or c=='\n' for c in tail), 'context must visibly escape controls and non-ASCII')
    lines=tail.split('\n') if tail else []
    require(len(lines)<=80 and all(len(line)<=512 for line in lines), 'context line count/length cap')
    if value['context_state']!='AVAILABLE':
        require(not value['observations'] and not tail and not value['truncated'], 'unavailable context cannot contain evidence')
    require(len((json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode('ascii'))<=16384,
            'diagnostic canonical byte cap')


def validate_observation(row):
    for name in ('cleanup_confirmed','receipt_timed_out','kill_attempted'):
        require(row[name] is None or type(row[name]) is bool, 'unknown booleans must be null')
    require(row['native_record_status'] in ('UNKNOWN','PASS','FAIL') and row['failure_code'] in FAILURE_CODES and
            row['failure_boundary'] in ('NONE','UNKNOWN','PREPARE','NATIVE_SUPERVISION','USAGE_OR_POSTFLIGHT'), 'finite observation labels')
    require(row['kill_result'] in ('UNKNOWN','NOT_REQUESTED','SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT'), 'finite kill observation')
    require(row['exit_code'] is None or type(row['exit_code']) is int and -255 <= row['exit_code'] <= 255, 'final reap exit')
    wanted=-row['exit_code'] if row['exit_code'] is not None and row['exit_code']<0 else None
    require(row['final_reap_signal']==wanted and (row['final_reap_signal'] is None or type(row['final_reap_signal']) is int), 'final reap signal only')
    require((row['waitid_code'] is None and row['waitid_status'] is None) or
            (type(row['waitid_code']) is int and 1<=row['waitid_code']<=6 and type(row['waitid_status']) is int and 0<=row['waitid_status']<=255), 'finite unreaped waitid tuple')
    for name in ('child_user_cpu_seconds','child_system_cpu_seconds'):
        require(row[name] is None or finite(row[name]), 'child CPU aggregate')
    require(row['child_maxrss_kib_cumulative'] is None or type(row['child_maxrss_kib_cumulative']) is int and row['child_maxrss_kib_cumulative']>=0,
            'cumulative children peak RSS')
    validate_diagnostics(row['diagnostics'])


def validate_evidence(objects):
    keys(objects, EVIDENCE)
    summary, sources, exits = (objects[n] for n in EVIDENCE)
    keys(summary, ('schema', 'mode', 'status', 'failure_category', 'completed_components', 'scope', 'seconds'))
    require(summary['schema'] == 'host93-ci-summary-v2' and summary['mode'] in MODES and summary['status'] in
            ('INCOMPLETE', 'READY_REQUIRES_ACTIONS_EXIT0') and summary['failure_category'] in CATEGORIES and
            finite(summary['seconds']) and summary['seconds'] <= 6600, 'summary values')
    mode=summary['mode']
    component_order=('toolchain_build',) if mode=='build-diagnostic' else COMPONENTS
    required_stages=BUILD_STAGES if mode=='build-diagnostic' else STAGES
    completed = summary['completed_components']
    require(type(completed) is list and len(completed) == len(set(completed)) and
            all(x in component_order for x in completed) and completed == list(component_order[:len(completed)]), 'finite ordered completed components')
    keys(summary['scope'], SCOPES)
    require(all(type(x) is bool for x in summary['scope'].values()) and
            not summary['scope']['n0_numeric'] and not summary['scope']['weights_loaded'], 'finite scope flags')
    scope = summary['scope']
    require(scope['toolchain_build'] == bool(completed) and scope['toolchain_tiny'] == ('toolchain' in completed) and
            scope['fresh_host_sv'] == ('host_emission' in completed) and
            scope['reset_launch'] == ('host_execution' in completed), 'scope/component consistency')
    require(not scope['reset_launch'] or scope['cpp_compiled'] and scope['cpp_generated'], 'scope sequencing')
    require(mode!='build-diagnostic' or all(not scope[k] for k in SCOPES if k!='toolchain_build'), 'build-only cannot claim executed backend/tiny/Host')
    keys(sources, ('schema', 'project_sources', 'fixed_inputs', 'generated'))
    require(sources['schema'] == 'host93-ci-source-hashes-v2', 'source schema')
    require(type(sources['project_sources']) is list and len(sources['project_sources']) <= 512, 'source count')
    names = []
    for item in sources['project_sources']:
        pin(item, True); names.append(item['path'])
    require(len(names) == len(set(names)), 'unique project source identities')
    if mode=='host-reset-launch':
        keys(sources['fixed_inputs'], ('idma_archive',))
        pin(sources['fixed_inputs']['idma_archive'])
        require(sources['fixed_inputs']['idma_archive'] == {'bytes':9926876, 'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}, 'fixed official archive identity')
    else:
        keys(sources['fixed_inputs'], ())
    require(type(sources['generated']) is dict and set(sources['generated']) <= set(GENERATED_KINDS), 'generated identity names')
    for item in sources['generated'].values():
        pin(item)
        require(item['bytes'] > 0, 'generated identity must be nonempty')
    if sources['project_sources']:
        project_map = {item['path']:{k:item[k] for k in ('bytes','sha256')} for item in sources['project_sources']}
        canonical = (json.dumps({'schema':1,'files':project_map}, indent=2, sort_keys=True)+'\n').encode()
        require(len(canonical) == PINS_SIZE and sha(canonical) == PINS_SHA,
                'evidence must reproduce the fixed immediate project source map')
    require(not completed or bool(sources['project_sources']), 'component claim needs source identities')
    expected_generated = set()
    if scope['toolchain_build']: expected_generated.add('derived_backend')
    if scope['fresh_host_sv']: expected_generated.update(('host93_fir','host93_sv'))
    if scope['cpp_compiled']: expected_generated.add('host_elf')
    require(set(sources['generated']) == expected_generated, 'scope needs exact generated identities')
    if scope['fresh_host_sv']:
        require(sources['generated']['host93_fir'] == {'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'} and
                sources['generated']['host93_sv'] == {'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'},
                'scope requires the deterministic fixed FIR and SV')
    keys(exits, ('schema', 'stages'))
    require(exits['schema'] == 'host93-ci-stage-exits-v3' and type(exits['stages']) is list and len(exits['stages']) <= len(STAGES), 'stage schema/count')
    seen = []
    failed = False
    for row in exits['stages']:
        keys(row, ('name','status','seconds','diagnostics')+OBSERVATION_KEYS)
        require(row['name'] in required_stages and row['name'] not in seen and row['status'] in ('EXIT0_CLEANED','FAILED') and finite(row['seconds']), 'stage values')
        seen.append(row['name'])
        validate_observation(row)
        require(row['name']=='fresh_make' and row['status']=='FAILED' or
                row['diagnostics']==empty_diagnostics(), 'only failed fresh_make collects compiler context')
        if row['status'] == 'EXIT0_CLEANED':
            require(row['exit_code'] == 0 and row['cleanup_confirmed'] is True and row['failure_code']=='NONE' and
                    row['failure_boundary']=='NONE' and row['native_record_status']=='PASS', 'stage terminal tuple')
        else:
            failed = True
    require(not seen or bool(sources['project_sources']), 'native stage evidence needs source identities')
    if summary['status'] == 'READY_REQUIRES_ACTIONS_EXIT0':
        require(summary['failure_category'] == 'NONE' and completed == list(component_order) and
                (scope['toolchain_build'] if mode=='build-diagnostic' else all(scope[x] for x in SCOPES[:6])) and not failed and set(seen) == set(required_stages), 'ready requires every finite stage')
    else:
        require(summary['failure_category'] != 'NONE', 'failure status cannot hide error')
    return True


def verify_evidence(out):
    root = plain_path(out) / 'evidence'
    require(root.is_dir() and not root.is_symlink() and set(x.name for x in root.iterdir()) == set(EVIDENCE), 'exact evidence three files')
    buffers = {name: bounded_read(root / name, MIB) for name in EVIDENCE}
    require(sum(map(len, buffers.values())) <= MIB, 'safe evidence combined size')
    validate_evidence({name: decode(raw) for name, raw in buffers.items()})
    return 0


def write_json(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= MIB, 'bounded JSON output')
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(bounded_read(path, MIB) == raw, 'JSON readback')


def interrupted(_signal, _frame):
    raise TimeoutError('shared CI deadline')


def limits(total, work, cpu, address, fsize, log=MIB):
    return {'total_seconds':total,'work_seconds':work,'cpu_seconds':cpu,
            'as_bytes':address,'fsize_bytes':fsize,'log_bytes':log,'sample_rows':total+16}


# Approved finite per-process maxima. Components may only tighten these values.
# Aggregate tree limits remain component postflight acceptance, not OS hard caps.
PHASE_CAPS = {
    'official_source473': (420,400,400,512*MIB,64*MIB,2*MIB),
    'fresh_autoconf': (180,160,160,GIB,64*MIB,MIB),
    'fresh_configure': (180,160,160,GIB,64*MIB,MIB),
    'fresh_make': (3600,3570,3570,4*GIB,GIB,4*MIB),
    'derived_tiny_version': (30,10,10,512*MIB,4*MIB,MIB),
    'derived_tiny_generate': (120,90,90,GIB,8*MIB,MIB),
    'derived_tiny_compile': (300,240,240,2*GIB,32*MIB,MIB),
    'derived_tiny_run': (30,10,10,512*MIB,4*MIB,MIB),
    'host93_java_version': (30,10,10,4*GIB,2*MIB,2*MIB),
    'host93_acquire_jar87': (1200,1190,300,512*MIB,64*MIB,2*MIB),
    'host93_acquire_hardfloat20': (300,290,120,512*MIB,2*MIB,2*MIB),
    'host93_assemble': (60,45,40,512*MIB,4*MIB,2*MIB),
    'host93_class': (330,300,300,4*GIB,48*MIB,2*MIB),
    'host93_chirrtl': (90,60,60,4*GIB,48*MIB,2*MIB),
    'host93_acquire_firtool': (180,170,120,512*MIB,64*MIB,2*MIB),
    'host93_sv': (390,360,360,2*GIB,128*MIB,2*MIB),
    'idma319_extract': (60,45,40,512*MIB,4*MIB,MIB),
    'retained13_assemble': (60,45,40,512*MIB,4*MIB,MIB),
    'host93_configuration': (60,45,45,768*MIB,4*MIB,MIB),
    'host93_cpp_generate': (600,540,540,6*GIB,128*MIB,4*MIB),
    'host93_cpp_compile': (1800,1740,1740,6*GIB,512*MIB,4*MIB),
    'host93_reset_launch': (30,10,10,2*GIB,8*MIB,MIB),
}
for _name in STAGES:
    if _name.startswith('host_'):
        PHASE_CAPS[_name]=(30,10,10,512*MIB,4*MIB,65536)


def phase_limits(name, bound):
    require(name in PHASE_CAPS and type(bound) is dict, 'finite phase budget names')
    names=('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes')
    require(set(names+('sample_rows',)) <= set(bound) and
            set(bound) <= set(names+('sample_rows','tree_bytes','file_count','entry_count')),
            'finite resource keys')
    for key,maximum in zip(names,PHASE_CAPS[name]):
        require(type(bound[key]) is int and 0 < bound[key] <= maximum, 'phase resource exceeds approval')
    require(bound['work_seconds'] < bound['total_seconds'] and
            type(bound['sample_rows']) is int and 0 < bound['sample_rows'] <= bound['total_seconds']+16,
            'finite sampling cap')
    for key in ('tree_bytes','file_count','entry_count'):
        if key in bound:require(type(bound[key]) is int and 0 < bound[key] <= (4*GIB if key=='tree_bytes' else 200000), 'finite output bound')


def memory_disk_gate(folder, memory_bytes, disk_bytes):
    with open('/proc/meminfo', 'rb') as stream:
        raw = stream.read(65537)
    require(0 < len(raw) <= 65536, 'bounded fixed proc memory observation')
    raw = raw.decode('ascii')
    found = re.search(r'^MemAvailable:\s+(\d+) kB$', raw, re.M)
    require(found is not None and int(found[1])*1024 >= memory_bytes, 'available memory below fixed phase floor')
    require(shutil.disk_usage(folder).free >= disk_bytes, 'free disk below fixed phase floor')


def project_pin_map(repo):
    document = decode(exact(HERE / 'RUN_PINS.json', PINS_SIZE, PINS_SHA))
    keys(document, ('schema', 'files'))
    require(document['schema'] == 1 and type(document['files']) is dict, 'fixed source map')
    buffers = {}
    for name, row in document['files'].items():
        pin({'path':name, **row}, True)
        buffers[name] = exact(repo / name, row['bytes'], row['sha256'])
    return document['files'], buffers


def module_from(repo, pins, relative, name):
    row = pins[relative]
    return load(repo / relative, row['bytes'], row['sha256'], name)



def collect_build_diagnostics(repo, pins, log_path, build_root):
    # Fixed caller path only, after failed fresh_make; do not expose exceptions.
    try:
        private, read_truncated = compiler_log_tail(log_path)
    except BaseException:
        return empty_diagnostics('READ_ERROR')
    try:
        diagnostic = module_from(repo,pins,'candidates/host93_ci_recovery/safe_build_diagnostics.py','verified_safe_build_diagnostics')
        result = diagnostic.sanitize_build_context(private,build_root,DIAGNOSTIC_PATHS)
        result['truncated'] = result['truncated'] or read_truncated
        validate_diagnostics(result)
        require(result['context_state']=='AVAILABLE', 'successful context sanitizer state')
        return result
    except BaseException:
        return empty_diagnostics('SANITIZER_ERROR')


def execute(repo, out, archive, supplied_deadline, mode='host-reset-launch'):
    started = time.monotonic()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and type(supplied_deadline) is float and
            math.isfinite(supplied_deadline) and started < supplied_deadline <= started+6600,
            'explicit current GitHub job monotonic deadline required')
    shared_stop = min(supplied_deadline, started+6600)
    work_stop = shared_stop-5
    require(work_stop > started, 'shared evidence reserve unavailable')
    require(mode in MODES and ((mode=='build-diagnostic' and archive is None) or (mode=='host-reset-launch' and archive is not None)), 'mode-specific fixed archive arguments')
    repo, out = map(plain_path, (repo, out))
    if archive is not None: archive=plain_path(archive)
    require(repo.is_dir() and out.parent.is_dir() and not os.path.lexists(out) and
            not out.is_relative_to(repo) and not repo.is_relative_to(out), 'fresh disjoint private workroot')
    support = load(HERE / SUPPORT[0], SUPPORT[1], SUPPORT[2], 'verified_ci_support_v3')
    support.deadline_ready()
    old_mask = os.umask(0o077)
    old_alarm = signal.signal(signal.SIGALRM, interrupted)
    old_term = signal.signal(signal.SIGTERM, interrupted)
    signal.setitimer(signal.ITIMER_REAL, work_stop-time.monotonic())
    owner = {'handler':interrupted,'deadline':work_stop}
    stages, completed, generated, source_rows = [], [], {}, []
    scopes = {x:False for x in SCOPES}
    failure = None
    try:
        out.mkdir(mode=0o700)
        (out/'private').mkdir(mode=0o700)
        (out/'phases').mkdir(mode=0o700)
        (out/'home').mkdir(mode=0o700)
        (out/'tmp').mkdir(mode=0o700)
        pins, buffers = project_pin_map(repo)
        source_rows = [{'path':name,**row} for name,row in sorted(pins.items())]
        if archive is not None: exact(archive,9926876,'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce')
        base_support, base_plan, _ = support.fixed_support(repo)
        def call_phase(name, argv, cwd, environment, bound):
            require(name in (BUILD_STAGES if mode=='build-diagnostic' else STAGES) and name not in {x['name'] for x in stages}, 'one finite phase invocation')
            require(time.monotonic() < work_stop-15, 'shared work window exhausted')
            phase_limits(name, bound)
            if name in ('host93_cpp_generate','host93_cpp_compile'):
                memory_disk_gate(out,8*GIB,3*GIB)
            began=time.monotonic()
            evidence=out/'phases'/name
            observation={}
            row={'name':name,'status':'FAILED','seconds':0.0,'diagnostics':empty_diagnostics(),**support.diagnostic_defaults()}
            stages.append(row)
            print(json.dumps({'phase':name,'status':'START'},sort_keys=True),flush=True)
            try:
                record, raw, usage=support.run_phase(base_support,base_plan,name,argv,cwd,evidence,environment,bound,work_stop,owner,diagnostics=observation)
                row.update(observation)
                row.update(status='EXIT0_CLEANED',exit_code=record['exit_code'],cleanup_confirmed=record['cleanup_confirmed'],
                           child_user_cpu_seconds=usage['child_user_cpu_seconds'],child_system_cpu_seconds=usage['child_system_cpu_seconds'])
                return {'record':record,'raw_log':raw,'usage':usage,'evidence_root':str(evidence)}
            except BaseException:
                row.update(observation)
                if name=='fresh_make':
                    row['diagnostics']=collect_build_diagnostics(repo,pins,evidence/'native.log',str(out/'toolchain'/'verilator'))
                raise
            finally:
                row['seconds']=round(time.monotonic()-began,6)
                print(json.dumps({'phase':name,'status':row['status'],'seconds':row['seconds']},sort_keys=True),flush=True)
        prefix='candidates/host93_ci_recovery/'
        tool=module_from(repo,pins,prefix+'toolchain/ci_toolchain.py','verified_ci_toolchain')
        tools=tool.run(repo,out/'toolchain',call_phase,stop_after_build=mode=='build-diagnostic')
        scopes['toolchain_build']=True
        generated['derived_backend']={k:tools['backend'][k] for k in ('bytes','sha256')}
        if mode=='build-diagnostic':
            completed.append('toolchain_build')
        else:
            completed.append('toolchain');scopes['toolchain_tiny']=True
            emission=module_from(repo,pins,prefix+'emission/host_emission.py','verified_ci_host_emission')
            host=emission.run(repo,out/'emission',call_phase)
            completed.append('host_emission');scopes['fresh_host_sv']=True
            generated['host93_fir']={k:host['fir'][k] for k in ('bytes','sha256')}
            generated['host93_sv']={k:host['sv'][k] for k in ('bytes','sha256')}
            environment={'PATH':'/usr/bin:/bin','HOME':str(out/'home'),'TMPDIR':str(out/'tmp'),'LC_ALL':'C','LANG':'C','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
            entry=decode(buffers[prefix+'idma319/ENTRY.json'])
            extractor=repo/(prefix+'idma319/extract_idma.py')
            idma=out/'idma319'
            call_phase('idma319_extract',[sys.executable,'-I','-S','-B','-c',entry['bootstrap'],str(extractor),'--archive',str(archive),'--out',str(idma)],out,environment,limits(60,45,40,512*MIB,4*MIB))
            completed.append('idma319')
            retained=out/'retained13'
            call_phase('retained13_assemble',[sys.executable,'-I','-S','-B',str(repo/(prefix+'retained13/run_retained13.py')),'--repo',str(repo),'--out',str(retained)],out,environment,limits(60,45,40,512*MIB,4*MIB))
            completed.append('retained13')
            entry=decode(buffers[prefix+'configuration/ENTRY.json'])
            configuration=out/'configuration'
            # ENTRY supplies the immutable same-buffer bootstrap; source path is caller-bound.
            argv=[sys.executable,'-I','-S','-B','-c',entry['argv_prefix'][5],str(repo/(prefix+'configuration/generate_4vlt.py')),
                  '--repo',str(repo),'--sv',host['sv']['path'],'--idma-root',str(idma/'sources'),'--out',str(configuration)]
            call_phase('host93_configuration',argv,out,environment,limits(60,45,45,768*MIB,4*MIB))
            completed.append('configuration')
            execution=module_from(repo,pins,prefix+'execution/host_execution.py','verified_ci_host_execution')
            result=execution.run(repo,out/'host_execution',call_phase,tools,host,idma,retained,configuration)
            completed.append('host_execution')
            for name in ('cpp_generated','cpp_compiled','reset_launch'):scopes[name]=True
            generated['host_elf']={k:result['elf'][k] for k in ('bytes','sha256')}
        # All fixed source content is checked again after the final native phase.
        for name,row in pins.items():exact(repo/name,row['bytes'],row['sha256'])
        if archive is not None: exact(archive,9926876,'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce')
    except BaseException as error:
        failure=error
        if (out/'private').is_dir():
            try:
                with (out/'private'/'failure.txt').open('x') as stream:traceback.print_exc(file=stream)
            except BaseException:pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, max(0.001,shared_stop-time.monotonic()))
        try:
            category='NONE' if failure is None else ('TIMEOUT' if isinstance(failure,TimeoutError) else 'INPUT_OR_CONTRACT' if isinstance(failure,(ValueError,KeyError,AssertionError)) else 'SYSTEM' if isinstance(failure,OSError) else 'INTERRUPTED' if isinstance(failure,(KeyboardInterrupt,SystemExit)) else 'UNEXPECTED')
            summary={'schema':'host93-ci-summary-v2','mode':mode,'status':'READY_REQUIRES_ACTIONS_EXIT0' if failure is None else 'INCOMPLETE',
                     'failure_category':category,'completed_components':completed,'scope':scopes,'seconds':round(time.monotonic()-started,6)}
            sources={'schema':'host93-ci-source-hashes-v2','project_sources':source_rows,
                     'fixed_inputs':({'idma_archive':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}} if mode=='host-reset-launch' else {}),'generated':generated}
            objects={'summary.json':summary,'source_hashes.json':sources,'stage_exits.json':{'schema':'host93-ci-stage-exits-v3','stages':stages}}
            validate_evidence(objects)
            evidence=out/'evidence';evidence.mkdir(mode=0o700)
            for name,value in objects.items():write_json(evidence/name,value)
            verify_evidence(out)
            require(time.monotonic()<shared_stop,'evidence final shared deadline')
        except BaseException as report_error:
            if failure is None:failure=report_error
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,old_alarm);signal.signal(signal.SIGTERM,old_term);os.umask(old_mask)
    print(json.dumps({'status':'READY_REQUIRES_ACTIONS_EXIT0' if failure is None else 'INCOMPLETE'},sort_keys=True),flush=True)
    return 0 if failure is None else 1


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--repo',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--idma-archive',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--verify-evidence',action='store_true')
    parser.add_argument('--job-deadline',type=float)
    parser.add_argument('--mode',choices=MODES)
    args=parser.parse_args(argv)
    if args.verify_evidence:
        require(not args.execute and args.repo is None and args.idma_archive is None and args.job_deadline is None and args.mode is None,'evidence-only arguments')
        return verify_evidence(args.out)
    if not args.execute:
        require(args.repo is not None and args.idma_archive is None and args.job_deadline is None,'source-only arguments')
        pins,_=project_pin_map(plain_path(args.repo))
        print(json.dumps({'status':'SOURCE_ONLY_NOT_NATIVE_OR_FULL_JOB_QUALIFIED','fixed_files':len(pins)},sort_keys=True))
        return 0
    require(args.repo is not None and args.job_deadline is not None,'complete execution arguments')
    return execute(args.repo,args.out,args.idma_archive,args.job_deadline,args.mode or 'host-reset-launch')


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'INCOMPLETE','error_category':type(error).__name__ if type(error) in (ValueError,OSError,TimeoutError,FileNotFoundError) else 'UNEXPECTED'},sort_keys=True),flush=True)
        raise SystemExit(1)
