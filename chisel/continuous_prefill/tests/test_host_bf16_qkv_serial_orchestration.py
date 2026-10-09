#!/usr/bin/env python3
"""Regression contract for the host QKV hierarchy build orchestration.

Install in chisel/continuous_prefill/tests/. The default subject is the current
repository scripts/run_host_bf16_qkv_gate.sh, located relative to this file.
HOST_QKV_BUILD_SCRIPT_UNDER_TEST is an explicit test-only path override for
reviewing an unapplied recipe. No source snapshots or build evidence are needed.

Run with unittest or pytest. Verilator, Make, compilation, and identity tools are
stubbed; only shell orchestration runs, inside ordinary temporary directories.
"""
from pathlib import Path
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

def recipe_path():
    """Find the production entrypoint from either its tests dir or repo tree."""
    override = os.environ.get('HOST_QKV_BUILD_SCRIPT_UNDER_TEST')
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Explicit QKV recipe override does not exist: {path}')
        return path
    for ancestor in Path(__file__).resolve().parents:
        for relative in ('scripts/run_host_bf16_qkv_gate.sh',
                         'chisel/continuous_prefill/scripts/run_host_bf16_qkv_gate.sh'):
            candidate = ancestor / relative
            if candidate.is_file():
                return candidate
    raise FileNotFoundError('Cannot locate the repository host QKV build script')


RECIPE_PATH = recipe_path()
TEXT = RECIPE_PATH.read_text()
BASH = shutil.which('bash')
FIND = shutil.which('find')
SHELL_TOOLS = all(shutil.which(name) for name in ('bash', 'env', 'grep', 'sort', 'find', 'cmp'))
START = 'mapfile -t IDMA_OPTIONS '
END = 'python3 - "$OUT" "$HARDFLOAT_SOURCE" <<\'PY_BUILD\''
BLOCK = TEXT[TEXT.index(START):TEXT.index(END)]
FLAGS = {
    'MAKEFLAGS': '-j8 VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O0 OPT_SLOW=-O0',
    'MFLAGS': '-k',
    'GNUMAKEFLAGS': '-n -j64',
}
STUB = r'''import hashlib,json,os,subprocess,sys
from pathlib import Path
name=Path(sys.argv[0]).name
argv=sys.argv[1:]
out=Path(os.environ['MOCK_OUT']);obj=out/'obj'
scenario=os.environ['MOCK_SCENARIO']
def event(phase,**extra):
    with (out/'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(phase=phase,argv=argv,env={k:os.environ.get(k) for k in ('MAKEFLAGS','MFLAGS','GNUMAKEFLAGS')},**extra))+'\n')
def cpp():
    child=obj/'Vretained_rev8b_b';child.mkdir(exist_ok=True)
    (child/'Vretained_rev8b_b.cpp').write_text('// mock output; never compiled\n')
    (obj/'VHostBlockTop.mk').write_text('# mock top\n')
if name=='verilator':
    event('plan_started')
    (out/'parent.active').write_text('mock parent is alive\n')
    obj.mkdir(exist_ok=True)
    if scenario!='missing_plan':
        (obj/'VHostBlockTop_hier.mk').write_text('' if scenario=='empty_plan' else '# mock hierarchy\n')
    # Arg files are immutable sentinels. The harness hashes them before and after
    # phase 2; no stub edits these inputs after planning.
    (obj/'Vretained__hierMkArgs.f').write_text('--top-module retained_rev8b_b\n')
    if scenario=='top_mk':(obj/'VHostBlockTop.mk').write_text('# premature top\n')
    if scenario in ('child_cpp','root_cpp'):
        parent=obj/'nested'/'child' if scenario=='child_cpp' else obj
        parent.mkdir(parents=True,exist_ok=True)
        (parent/'unexpected.cpp').write_text('// premature output\n')
    if scenario=='signal9':
        # A marker models surviving descendants; no orphan process is launched.
        (out/'descendant.active').write_text('surviving mock descendant\n')
        print('%Error: Verilator threw signal 9. Suggest trying --debug --gdbbt')
    elif os.environ.get('MAKEFLAGS')!='-n':
        event('implicit_child_verilation',parent_active=True)
        cpp()
    code=255 if scenario=='signal9' else 41 if scenario=='planning_error' else 0
    (out/'parent.active').unlink()
    inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in obj.iterdir() if p.name.endswith(('hier.mk','hierMkArgs.f'))}
    event('plan_finished',exit_code=code,generated_inputs=inputs)
    sys.exit(code)
elif name=='make':
    event('make_started',parent_active=(out/'parent.active').exists(),surviving_descendant=(out/'descendant.active').exists())
    if scenario=='child_failure':
        event('make_finished',exit_code=47);sys.exit(47)
    cpp()
    event('make_finished',exit_code=0)
elif name=='python3':
    script=Path(argv[0]).name
    if script=='build_host_hierarchy_bounded.py':
        event('bounded_started')
        code=53 if scenario=='bounded_failure' else 0
        event('bounded_finished',exit_code=code)
        sys.exit(code)
    elif script=='host_bf16_v_toolchain.py':
        event('toolchain_verify')
        sys.exit(61 if scenario=='toolchain_failure' else 0)
    elif script=='production_source_identity.py':
        event('source_verify')
        sys.exit(63 if scenario=='source_drift' else 0)
    else:raise SystemExit('REFUSE unrecognized python invocation: '+repr(argv))
elif name=='mock_record_elf':
    event('record_elf')
    Path(argv[0]).write_text(json.dumps({'backend':'changed' if scenario=='elf_drift' else 'pinned5.032'})+'\n')
elif name=='find':
    event('plan_cpp_check')
    if scenario=='find_failure':sys.exit(72)
    sys.exit(subprocess.run([os.environ['REAL_FIND'],*argv],check=False).returncode)
else:raise SystemExit('REFUSE unrecognized mock tool: '+name)
'''


@unittest.skipUnless(SHELL_TOOLS, "Bash and standard POSIX shell tools are required")
class Orchestration(unittest.TestCase):
    def run_case(self, scenario='success'):
        with tempfile.TemporaryDirectory(prefix='host_qkv_orchestration_') as temp:
            case = Path(temp)
            out = case / 'fresh output'
            out.mkdir()
            binpath = case / 'stub bin'
            binpath.mkdir()
            for name in ['verilator','make','python3','mock_record_elf','find']:
                p = binpath/name
                p.write_text('#!'+sys.executable+'\n'+STUB)
                p.chmod(0o700)
            fake_root = case/'repo with spaces'
            fake_p = fake_root/'chisel/continuous_prefill'
            retained = [fake_root/'rtl/integration/qwen2_matrix_command_endpoint.sv',
                        fake_root/'rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv',
                        fake_root/'rtl/matrix/candidates/rev8b_b/retained_rev8b_b_candidate.sv',
                        fake_root/'pinned idma/tech_cells_generic/src/rtl/tc_clk.sv']
            (out/'idma.f').write_text('+incdir+/pinned/idma\n+define+PINNED_IDMA\n+incdir+/pinned/idma\n/pinned/idma/source.sv\n')
            (out/'actual_verilator_before.json').write_text(json.dumps({'backend':'pinned5.032'})+'\n')
            quote=shlex.quote
            harness = '''#!/usr/bin/env bash
set -euo pipefail
'''+f'ROOT={quote(str(fake_root))}\nP={quote(str(fake_p))}\nOUT={quote(str(out))}\nHARDFLOAT_SOURCE={quote(str(fake_root/"retained hardfloat"))}\nRETAINED_SOURCES=('+ ' '.join(quote(str(p)) for p in retained)+''')
trap 'c=$?;echo "$c" >"$OUT/build.exit";exit "$c"' EXIT
record_verilator_elf() { mock_record_elf "$1"; }
'''+BLOCK+'\n: > \"$OUT/mock_build_ready\"\n'
            script=case/'exercise.sh';script.write_text(harness)
            env=dict(os.environ,**FLAGS,PATH=str(binpath)+os.pathsep+os.environ.get('PATH',os.defpath),MOCK_OUT=str(out),MOCK_SCENARIO=scenario,REAL_FIND=FIND,BUILD_JOBS='1',BUILD_RESERVE_BYTES='123456789')
            result=subprocess.run([BASH,str(script)],env=env,text=True,capture_output=True,timeout=10)
            events=[json.loads(x) for x in (out/'events.jsonl').read_text().splitlines()]
            receipts={p.name:p.read_text() for p in out.iterdir() if p.is_file() and (p.suffix in ('.exit','.log') or p.name=='mock_build_ready')}
            planned=next(e for e in events if e['phase']=='plan_finished')['generated_inputs']
            retained_inputs={name:hashlib.sha256((out/'obj'/name).read_bytes()).hexdigest() for name in planned}
            self.assertEqual(retained_inputs,planned,'generated Makefile/child arguments changed')
            return result,events,receipts,str(out),str(fake_p),[str(p) for p in retained]

    def phases(self,events):return [e['phase'] for e in events]

    def test_01_success_orders_plan_check_children_bounded_and_identity(self):
        result,events,receipts,*_=self.run_case()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.phases(events),['plan_started','plan_finished','plan_cpp_check','make_started','make_finished','bounded_started','bounded_finished','toolchain_verify','record_elf','source_verify'])
        make=next(e for e in events if e['phase']=='make_started')
        self.assertFalse(make['parent_active'])
        self.assertFalse(make['surviving_descendant'])
        self.assertEqual(receipts['initial_verilation.exit'],'0\n')
        self.assertEqual(receipts['build.exit'],'0\n')
        self.assertIn('mock_build_ready',receipts)
        self.assertIn('hierarchy_verilation.log',receipts)
        self.assertNotIn('recovery_verilation.log',receipts)

    def test_02_plan_env_scoped_and_all_build_env_restored(self):
        result,events,*_=self.run_case()
        self.assertEqual(result.returncode,0)
        self.assertEqual(events[0]['env'],{'MAKEFLAGS':'-n','MFLAGS':None,'GNUMAKEFLAGS':None})
        make=next(e for e in events if e['phase']=='make_started')
        self.assertEqual(make['env'],dict.fromkeys(FLAGS))
        bounded=next(e for e in events if e['phase']=='bounded_started')
        self.assertEqual(bounded['env'],FLAGS)

    def test_03_verilator_argv_and_retained_paths_preserved(self):
        result,events,_,out,p,retained=self.run_case()
        expected=['--cc','--exe','--assert','--comp-limit-parens','16','--output-split','3000','--output-split-cfuncs','200','-Wno-fatal','--top-module','HostBlockTop','-CFLAGS','-O2 -std=c++17 -ffp-contract=off -fno-fast-math','-j','1','--Mdir',out+'/obj','--hierarchical',p+'/tests/native_weight_hierarchy.vlt',*retained,'+define+PINNED_IDMA','+incdir+/pinned/idma','-f',out+'/idma.f',out+'/generated/HostBlockTop.sv',str(Path(p).parents[1]/'rtl/integration/idma_backend_rw_axi_flat_wrap.sv'),p+'/tests/host_bf16_qkv.cpp']
        self.assertEqual(result.returncode,0)
        self.assertEqual(events[0]['argv'],expected)

    def test_04_explicit_serial_make_target_and_bounded_reserve(self):
        result,events,_,out,p,_=self.run_case()
        self.assertEqual(result.returncode,0)
        self.assertIn('make_started',self.phases(events))
        self.assertEqual(next(e for e in events if e['phase']=='make_started')['argv'],['-C',out+'/obj','-f','VHostBlockTop_hier.mk','-j1','hier_verilation'])
        self.assertEqual(next(e for e in events if e['phase']=='bounded_started')['argv'],[p+'/scripts/build_host_hierarchy_bounded.py',out,'--reserve-bytes','123456789'])

    def assert_closed(self,scenario,code,absent):
        result,events,receipts,*_=self.run_case(scenario)
        self.assertEqual(result.returncode,code,result.stderr)
        for phase in absent:self.assertNotIn(phase,self.phases(events))
        self.assertEqual(receipts['build.exit'],str(code)+'\n')
        self.assertNotIn('mock_build_ready',receipts)
        return events,receipts

    def test_05_planning_error_never_generates_or_builds(self):
        _,receipts=self.assert_closed('planning_error',41,['make_started','bounded_started','source_verify'])
        self.assertEqual(receipts['initial_verilation.exit'],'41\n')

    def test_06_signal9_never_recovers_even_with_plan_and_surviving_descendant(self):
        events,receipts=self.assert_closed('signal9',255,['make_started','bounded_started','source_verify'])
        self.assertEqual(receipts['initial_verilation.exit'],'255\n')
        self.assertIn('Verilator threw signal 9',receipts['build.log'])
        self.assertNotIn('recovery_verilation.log',receipts)

    def test_07_missing_plan_stops(self):self.assert_closed('missing_plan',2,['make_started','bounded_started'])
    def test_08_empty_plan_stops(self):self.assert_closed('empty_plan',2,['make_started','bounded_started'])
    def test_09_premature_top_makefile_stops(self):self.assert_closed('top_mk',2,['make_started','bounded_started'])
    def test_10_nested_child_cpp_stops(self):self.assert_closed('child_cpp',2,['make_started','bounded_started'])
    def test_11_root_cpp_stops(self):self.assert_closed('root_cpp',2,['make_started','bounded_started'])
    def test_12_cpp_inspection_failure_stops(self):self.assert_closed('find_failure',2,['make_started','bounded_started'])

    def test_13_child_generation_failure_stops_compilation_and_identity(self):
        events,receipts=self.assert_closed('child_failure',47,['bounded_started','toolchain_verify','source_verify'])
        self.assertIn('make_started',self.phases(events))
        self.assertEqual(receipts['initial_verilation.exit'],'0\n')

    def test_14_bounded_failure_stops_acceptance(self):self.assert_closed('bounded_failure',53,['toolchain_verify','source_verify'])
    def test_15_toolchain_drift_stops_acceptance(self):self.assert_closed('toolchain_failure',61,['record_elf','source_verify'])
    def test_16_actual_elf_mismatch_stops_source_verification(self):self.assert_closed('elf_drift',1,['source_verify'])
    def test_17_source_drift_stops_success(self):self.assert_closed('source_drift',63,[])

    def test_18_syntax(self):
        result=subprocess.run([BASH,'-n',str(RECIPE_PATH)],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_19_full_recipe_retains_source_and_acceptance_contracts(self):
        # The mocked segment covers the downstream failures dynamically. These
        # checks bind it to the production entrypoint's preflight and receipt.
        for contract in (
            '[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT"',
            '[[ ${BUILD_JOBS:-1} = 1 ]]',
            'export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"',
            'export SOURCE_IDENTITY_SCOPE=full',
            'python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"',
            'python3 "$P/scripts/host_bf16_v_toolchain.py" before "$OUT/toolchain_before.json"',
            'record_verilator_elf "$OUT/actual_verilator_before.json"',
            'cmp "$OUT/actual_verilator_before.json" "$OUT/actual_verilator_after.json"',
            "status='BUILT_HOST_QKV_PROJECTIONS_ONLY_NOT_NUMERICAL_PASS',numerical_pass=False",
        ):
            self.assertIn(contract,TEXT)
        self.assertNotIn('recovery_verilation.log',TEXT)

if __name__=='__main__':
    unittest.main(verbosity=2)
