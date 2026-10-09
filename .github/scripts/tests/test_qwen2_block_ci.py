"""Exercise CI orchestration with real fixture packers and mocked build tools.

No Scala compilation, RTL build, or numerical simulation runs in these tests.
The production block body is also compared verbatim with its original gate.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path('.github/scripts/run_qwen2_block_ci.sh')
WORKFLOW = Path('.github/workflows/chisel-qwen2-continuous-block.yml')
PROJECT = Path('chisel/continuous_prefill')
ORIGINAL = PROJECT / 'scripts/run_qwen2_block_verified.sh'

# The same tool stand-in records orchestration and emits clearly mocked logs.
# All fixture generation, suite discovery, source hashing and result validation
# still run through the unchanged production Python and shell implementations.
MOCK_TOOL = r'''
import json, os
from pathlib import Path
import shutil, sys
name=Path(sys.argv[0]).name; args=sys.argv[1:]
root=Path(os.environ['MOCK_ROOT'])
with (root/'calls.jsonl').open('a') as f:
    f.write(json.dumps({'tool':name,'args':args,
        'fixture':os.environ.get('OWNER_FIXTURE'),
        'makeflags':os.environ.get('MAKEFLAGS','')})+'\n')
if name=='git':
    base=root
    if args[:1]==['-C']: base=Path(args[1]);args=args[2:]
    if args[:2]==['rev-parse','HEAD']:
        print('c1105e6ac6a0dd90fc80893efc4830ab609005d3' if base.name=='hardfloat' else '1'*40)
    elif args[:1]==['status']: pass
    elif args[:2]==['ls-files','-z']:
        files=set()
        for arg in args[2:]:
            p=base/arg
            files.update([p] if p.is_file() else (q for q in p.rglob('*') if q.is_file()))
        sys.stdout.buffer.write(b''.join(str(p.relative_to(base)).encode()+b'\0' for p in sorted(files)))
    else: raise RuntimeError('unexpected git call: '+repr(args))
elif name in ('java','g++'): print('mock tool; no compilation')
elif name=='sbt':
    assert 'VK_PCH_I_FAST=' in os.environ['MAKEFLAGS']
    assert 'VK_PCH_I_SLOW=' in os.environ['MAKEFLAGS']
    assert 'CFG_CXXFLAGS_PCH_I' not in os.environ['MAKEFLAGS']
    if args==['-batch','compile','Test/compile']: pass
    elif len(args)==2 and args[1].startswith('testOnly '):
        suites=args[1].split()[1:]
        fixture=Path(os.environ['OWNER_FIXTURE'])
        m=json.loads((fixture/'manifest.json').read_text())
        group=next((g for g,s in [('tiny','HostBlockCommandsSpec'),
            ('real','HostBlockCommandsRealLayersSpec'),('native','HostBlockCommandsNativeWeightsSpec')]
            if 'heteronpu.continuous.'+s in suites),'general')
        assert fixture.name=={'general':'tiny_fixture','tiny':'tiny_fixture',
            'real':'real_fixture','native':'native_fixture'}[group]
        assert m['shape']['H']==(64 if group in ('general','tiny') else 1536)
        if group in ('real','native'):
            assert m['layers']==2 and m['tokens']==16 and m['commands']==42 and m['descriptors']==430
        assert m.get('weight_storage','fp32')==('bf16' if group=='native' else 'fp32')
        if os.environ.get('MOCK_FAIL_GROUP')==group: sys.exit(19)
        for suite in suites:
            if suite!=os.environ.get('MOCK_OMIT_SUITE'): print(suite.rsplit('.',1)[-1]+':')
        print('Tests: succeeded '+str({'general':101,'tiny':8,'real':10,'native':10}[group])+', failed 0, canceled 0, ignored 0, pending 0')
        print('All tests passed.')
    elif len(args)==2 and args[1].startswith('runMain '):
        _,main,out,*flags=args[1].split();out=Path(out);out.mkdir()
        if main=='heteronpu.continuous.EmitContinuous':
            assert flags==['--small-fabric']
            (out/'ContinuousElementwiseTop.sv').write_text('// MOCK EMISSION\n')
        elif main=='heteronpu.continuous.EmitQwenBlock':
            for file in ['Qwen2ContinuousBlock.sv','block_layout.h','layout.json']:
                (out/file).write_text('// MOCK EMISSION\n')
        else: raise RuntimeError(main)
    else: raise RuntimeError('unscoped or unexpected sbt call: '+repr(args))
elif name=='verilator':
    if args==['--version']: print('Verilator MOCK; no simulation')
    elif args==['-V']: print('VERILATOR_ROOT = '+str(root/'verilator-runtime'))
    elif '--build' in args:
        top=args[args.index('--top-module')+1]
        out=Path(args[args.index('--Mdir')+1]);out.mkdir()
        shutil.copy2(root/'tools/mock_tool',out/('V'+top))
    else: raise RuntimeError('unexpected Verilator call: '+repr(args))
elif name=='VContinuousElementwiseTop':
    print('MOCK_CONTINUOUS_PAYLOAD '+repr(args))
elif name=='VQwen2ContinuousBlock':
    if os.environ.get('MOCK_SOURCE_DRIFT'):
        with (root/'chisel/continuous_prefill/tests/qwen2_block.cpp').open('a') as f:
            f.write('// mock source drift\n')
    if args[1] in ('repeat','write-error','tag-error'):
        if os.environ.get('MOCK_FAIL_FAULT')==args[1]: sys.exit(21)
        print('MOCK_FAULT_CHECK '+args[1])
    else:
        for phase in range(14 if os.environ.get('MOCK_BAD_PHASE') else 15):
            print('STAGE_CHECK phase='+str(phase))
else: raise RuntimeError('unexpected mock executable: '+name)
'''


class Qwen2BlockCiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        workflow = yaml.safe_load((ROOT / WORKFLOW).read_text())
        scopes = workflow['jobs']['block']['steps'][0]['with']['sparse-checkout'].split()
        files = subprocess.check_output(['git', 'ls-files', '-z', '--', *scopes], cwd=ROOT).decode().split('\0')
        for name in set(filter(None, files)) | {str(RUNNER), str(WORKFLOW)}:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        tools = self.root / 'tools'
        tools.mkdir()
        mock = tools / 'mock_tool'
        mock.write_text('#!' + sys.executable + '\n' + MOCK_TOOL)
        mock.chmod(0o755)
        for name in ('java', 'sbt', 'verilator', 'g++', 'git'):
            (tools / name).symlink_to(mock)
        runtime = self.root / 'verilator-runtime'
        (runtime / 'include').mkdir(parents=True)
        (runtime / 'verilator_bin').symlink_to(mock)
        hardfloat = self.root / 'hardfloat'
        (hardfloat / '.git').mkdir(parents=True)
        (hardfloat / 'hardfloat/src/main/scala').mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('MAKEFLAGS', 'OFFLINE_TOOLS', 'VERILATOR_ROOT', 'SOURCE_IDENTITY_SCOPE')}
        self.env.update(PATH=str(tools) + os.pathsep + os.environ['PATH'],
                        MOCK_ROOT=str(self.root), HARDFLOAT_SOURCE=str(hardfloat),
                        PYTHONDONTWRITEBYTECODE='1')

    def run_gate(self, mode='tiny', **env):
        out = self.root / 'evidence'
        result = subprocess.run(['bash', str(self.root / RUNNER), mode, str(out), '16'],
                                env={**self.env, **env}, text=True, capture_output=True, timeout=45)
        calls = [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]
        return result, out, calls

    def assert_no_block(self, out, calls):
        self.assertFalse((out / 'RESULT.json').exists())
        self.assertFalse(any('EmitQwenBlock' in ' '.join(c['args']) for c in calls))

    def test_numerical_body_is_unchanged(self):
        marker = "EXTRA='';"
        original = (ROOT / ORIGINAL).read_text().split(marker, 1)[1]
        self.assertEqual((ROOT / RUNNER).read_text().split(marker, 1)[1], original)

    def test_control_oracles_are_checked_out_and_bound(self):
        oracles = ('scripts/qk_norm256_reference.c', 'scripts/rope_bf16_candidate_reference.c')
        continuous = ROOT / '.github/workflows/chisel-continuous-prefill.yml'
        for workflow_path, job in ((ROOT / WORKFLOW, 'block'), (continuous, 'continuous')):
            workflow = yaml.safe_load(workflow_path.read_text())
            scopes = workflow['jobs'][job]['steps'][0]['with']['sparse-checkout'].split()
            for name in oracles:
                self.assertTrue(any(Path(scope) in Path(name).parents for scope in scopes),
                                f'{workflow_path.name}: missing {name}')
                self.assertIn(name, (ROOT / RUNNER).read_text() if job == 'block' else workflow_path.read_text())
                self.assertTrue((ROOT / name).is_file())

    def test_tiny_covers_every_suite_fixture_payload_and_fault(self):
        result, out, calls = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads((out / 'control/suite_plan.json').read_text())
        invocations = [c for c in calls if c['tool'] == 'sbt' and c['args'][1].startswith('testOnly ')]
        self.assertEqual([c['args'][1].split()[1:] for c in invocations], list(plan.values()))
        expected = sorted('heteronpu.continuous.' + p.stem for p in
                          (ROOT / PROJECT / 'src/test/scala/heteronpu/continuous').glob('*Spec.scala'))
        self.assertEqual(sorted(s for suites in plan.values() for s in suites), expected)
        self.assertEqual([c['args'] for c in calls if c['tool'] == 'VQwen2ContinuousBlock'],
                         [[str(n), 'synthetic'] for n in (1, 2, 17, 33)] +
                         [['2', case] for case in ('repeat', 'write-error', 'tag-error')])
        self.assertEqual([c['args'] for c in calls if c['tool'] == 'VContinuousElementwiseTop'],
                         [[str(n)] for n in (1, 17, 33, 1025, 32768, 1572864, 2097152, 2621440)] +
                         [['1025', 'fail']])
        report = json.loads((out / 'RESULT.json').read_text())
        self.assertEqual(report['tokens'], [1, 2, 17, 33])
        self.assertTrue(all(run['phases'] == list(range(15)) for run in report['runs'].values()))
        self.assertIn(str(RUNNER), (out / 'sources.sha256').read_text())
        self.assertIn('SOURCE_IMMUTABILITY_PASS', (out / 'control/source_verify.log').read_text())

    def test_real_keeps_original_sixteen_token_numerical_run(self):
        result, out, calls = self.run_gate('real')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c['args'] for c in calls if c['tool'] == 'VQwen2ContinuousBlock'], [['16', 'synthetic']])
        self.assertEqual(json.loads((out / 'RESULT.json').read_text())['tokens'], 16)

    def test_fixture_suite_failure_stops_before_block_emission(self):
        result, out, calls = self.run_gate(MOCK_FAIL_GROUP='native')
        self.assertEqual(result.returncode, 19, result.stderr)
        self.assert_no_block(out, calls)
        self.assertIn('FAILED_PREFLIGHT_LOG:', result.stderr)
        self.assertEqual((out / 'control/gate.exit').read_text().strip(), '19')

    def test_omitted_suite_cannot_pass_preflight(self):
        result, out, calls = self.run_gate(MOCK_OMIT_SUITE='heteronpu.continuous.BlockAxiAdapterSpec')
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_block(out, calls)
        self.assertIn('MISSING_SUITE:general', result.stderr)

    def test_incomplete_block_stages_cannot_pass(self):
        result, out, _ = self.run_gate(MOCK_BAD_PHASE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((out / 'RESULT.json').exists())
        self.assertIn('incomplete or duplicate stage coverage', result.stderr)

    def test_fault_failure_cannot_pass(self):
        result, out, _ = self.run_gate(MOCK_FAIL_FAULT='tag-error')
        self.assertEqual(result.returncode, 21)
        self.assertFalse((out / 'RESULT.json').exists())

    def test_source_drift_cannot_pass(self):
        result, out, _ = self.run_gate(MOCK_SOURCE_DRIFT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((out / 'RESULT.json').exists())
        self.assertIn('FAILED', (out / 'source_immutability.log').read_text())


if __name__ == '__main__':
    unittest.main()
