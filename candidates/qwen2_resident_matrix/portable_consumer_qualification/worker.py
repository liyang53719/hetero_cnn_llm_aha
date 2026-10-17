"""Unexecuted future fixed-case worker; all real arithmetic is opt-in here."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as c

HERE = Path(__file__).resolve().parent

def save(path, value):
    c.atomic(path, value)

def identity(root, library, compiler):
    import numpy as np
    import numpy._core._multiarray_umath as extension
    c.need(sys.version_info[:2] == (3, 12) and np.__version__ == '2.3.5', 'actual Python/NumPy version')
    c.need(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'reviewed runtime platform')
    loader = c.loader(os.environ, sys.executable)
    runner = {name: os.environ.get(key, '') for name, key in (
        ('os', 'RUNNER_OS'), ('arch', 'RUNNER_ARCH'), ('environment', 'RUNNER_ENVIRONMENT'),
        ('image_os', 'ImageOS'), ('image_version', 'ImageVersion'))}
    c.need(runner['environment'] == 'github-hosted', 'observed GitHub-hosted qualification runner')
    def item(path):
        path = Path(path).resolve(strict=True)
        return dict(name=path.name, bytes=path.stat().st_size, sha256=c.sha(path))
    loaded = {}
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith('/'):
            path = Path(fields[5])
            if path.is_file():
                with path.open('rb') as stream:
                    if stream.read(4) == b'\x7fELF':
                        loaded[str(path.resolve())] = item(path)
    libm = [v for k, v in loaded.items() if Path(k).name == 'libm.so.6']
    c.need(len(libm) == 1, 'one actual loaded system libm identity')
    libpython = [v for k, v in loaded.items() if Path(k).name.startswith('libpython3.12.so') and
                 Path(k).parent == Path(loader['LD_LIBRARY_PATH'])]
    c.need(len(libpython) == 1, 'one actual mapped libpython from validated interpreter lib directory')
    native = item(library)
    c.need(native in loaded.values(), 'fresh combined ELF actually mapped in this process')
    numpy_native = item(extension.__file__)
    c.need(numpy_native in loaded.values(), 'actual NumPy arithmetic extension is mapped')
    cpu_sets = [set(line.partition(':')[2].split()) for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('flags')]
    c.need(cpu_sets, 'observed CPU capability inventory')
    python_sources = []
    trees = {'origin': HERE.parents[2], 'generated': Path(library).parent.parent / 'source'}
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            for tree, base in trees.items():
                if path.is_relative_to(base):
                    python_sources.append(dict(module=name, tree=tree, path=str(path.relative_to(base)), sha256=c.sha(path)))
                    break
    return dict(interpreter=item(sys.executable), python_version=platform.python_version(),
                numpy_version=np.__version__, numpy_extension=numpy_native,
                compiler={k: compiler[k] for k in ('sha256', 'version')},
                compiler_name=Path(compiler['path']).name, libm=libm[0], combined_elf=native,
                loaded_elfs=sorted(loaded.values(), key=lambda x: (x['name'], x['sha256'])),
                system=platform.system(), machine=platform.machine(), kernel=platform.release(),
                runner=runner,
                loader=dict(policy='setup-python-single-lib', toolcache_relative=loader['toolcache_relative'], libpython=libpython[0]),
                python_sources=python_sources,
                cpu_flags_common=sorted(set.intersection(*cpu_sets)),
                committed_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                                       text=True, timeout=5).strip())

def build(root, out):
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as d
    c.need(Path(d.__file__).resolve() == root / (c.PREFIX + 'official_bf16/dense_silu.py'), 'actual strict builder tree')
    library, receipt = d.build_library(out / 'build')
    d.verify_library(receipt)
    c.need(set(receipt['source_sha256']) == set(c.ARITHMETIC), 'four-source compile closure')
    save(out / 'build-stage.json', dict(library_sha256=receipt['library_sha256'],
         identity=identity(root, receipt['library'], receipt['compiler'])))

def profile2(root, out):
    # Origin stays untouched: the original helper validates its own historical
    # source pins and the two exact generated files before calling the fresh ELF.
    from candidates.qwen2_resident_matrix.attention_packed_native import check_native
    receipt = c.read(out / 'build/official_bf16_compile.json')
    before = c.sha(receipt['library'])
    c.need(before == receipt['library_sha256'], 'new ELF before profile2 load')
    result = check_native.run(out / 'source', receipt['library'])
    c.need(result['status'] == 'PASS_TINY_PACKED_NATIVE_MODEL' and result['library_sha256'] == before,
           'actual original profile2 result and current ELF')
    c.need(result['selected_fault_timing_qualified'] is False and result['rtl_execution'] is False
           and result['full_public_admission'] is False, 'original profile2 scope remains explicit')
    c.need(result['generated_sha256'] == c.read(HERE / 'input-contract.json')['generated_sha256'],
           'profile2 actual generated-source identity')
    # check_native does not return its CDLL handle. Hold the same verified ELF
    # while collecting this process's actual mapped-library identity.
    import ctypes
    held = ctypes.CDLL(receipt['library'])
    save(out / 'profile2-stage.json', dict(library_sha256=before,
         identity=identity(root, receipt['library'], receipt['compiler']),
         checks=result['checks'], generated_sha256=result['generated_sha256']))
    c.need(c.sha(receipt['library']) == before and held is not None, 'ELF unchanged after profile2')

def scalar_silu(root, out):
    import ctypes as C
    import unittest
    from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as a
    from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import ArithmeticTests, ref_add, ref_div, ref_mul, ref_bf
    from candidates.qwen2_resident_matrix.ffn_attention.test_scalar_recipe import ScalarRecipeTests, reference_exp
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as d
    c.need(Path(a.__file__).resolve() == root / (c.PREFIX + 'ffn_public/prefix_arithmetic.py'), 'actual ScalarService tree')
    # Genuine .git/committed-source and FE_TONEAREST/gradual-underflow probes
    # remain unchanged. No identity stub, ExactScalar substitute or FTZ repair.
    scalar = a.ScalarService()
    c.need(scalar.identity['recipe']['git_head'] == os.environ['GITHUB_SHA'], 'actual committed ScalarService source')
    cases = [ArithmeticTests('test_original_scalar_policy_preserves_underflow_and_inexact_distinction'),
             ArithmeticTests('test_every_primitive_matches_independent_exact_rounding')]
    cases.extend(ScalarRecipeTests(name) for name in unittest.defaultTestLoader.getTestCaseNames(ScalarRecipeTests))
    c.need(len(cases) == 7, 'exact original scalar tests')
    tested = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(cases))
    c.need(tested.wasSuccessful() and tested.testsRun == 7, 'actual ScalarService exact/Fraction checks')
    receipt = d.verify_library(out / 'build/official_bf16_compile.json')
    library = d.configure_silu_library(d.configure_library(C.CDLL(receipt['library'])))
    c.need(library.sf_reset_bf16_v1() == 0, 'unchanged SiLU floating environment')
    def call(gates, ups):
        arrays = ((C.c_uint32 * 16)(*gates), (C.c_uint32 * 16)(*ups), (C.c_uint32 * 16)(),
                  (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)())
        code = library.sf_vector_bf16_v1(*arrays)
        return code, tuple(map(tuple, arrays[2:]))
    outputs = []
    # Finite +/- values, both zeros, exact BF16 subnormal output, BF16 ties,
    # and phase5 consuming the already materialized phase4 result.
    vectors = (
        ((0, 0x80000000, 0x3f800000, 0xbf800000, 0x3f008000, 0xbf008000, 0x3f818000, 0xbf818000) * 2,
         (0x3f808000, 0xbf808000, 0x3f800000, 0x3f000000) * 4),
        ((0x00020000, 0x80020000, 0x00800000, 0x80800000, 0x42a00000, 0xc2a00000, 0, 0x80000000) * 2,
         (0x3f800000,) * 16),
    )
    for gates, ups in vectors:
        code, (actual, phases, flags, errors) = call(gates, ups)
        c.need(code == 0 and errors == (0,) * 16, 'SiLU successful vector/fault policy')
        expected = [0] * 96
        for lane, (gate, up) in enumerate(zip(gates, ups)):
            e = reference_exp(gate)
            p = [e, ref_add(0x3f800000, e)]
            p.append(ref_div(0x3f800000, p[-1]))
            p.append(ref_mul(p[-1], e if gate >> 31 else 0x3f800000))
            p.append(ref_bf(ref_mul(p[-1], gate)))
            p.append(ref_bf(ref_mul(p[-1], up)))
            for phase, word in enumerate(p):
                expected[phase * 16 + lane] = word
        c.need(phases == tuple(expected) and actual == tuple(expected[80:]), 'six exact SiLU phase words')
        c.need(all((flag & 30) == 0 for flag in flags[16:]), 'no fatal FP32 phase flags')
        outputs.append(hashlib.sha256(b''.join(x.to_bytes(4, 'little') for x in phases)).hexdigest())
    for gate, up, expected_code, error_bit in (
            (0x7fc00001, 0x3f800000, -1, 64),
            (1, 0x3f800000, 5, 16),
            (0x7f7fffff, 0x3f800000, 5, 16)):
        code, (actual, phases, flags, errors) = call((gate,) * 16, (up,) * 16)
        c.need(code == expected_code and all(x & error_bit for x in errors), 'SiLU exact original fault phase')
    c.need(library.sf_bf16_v1_calls() == 5 and library.sf_bf16_v1_failures() == 3, 'actual SiLU call/failure counters')
    d.verify_library(receipt)
    save(out / 'scalar-silu-stage.json', dict(library_sha256=receipt['library_sha256'],
         identity=identity(root, receipt['library'], receipt['compiler']),
         scalar_source=scalar.identity, silu_phase_sha256=outputs))

def all_cases(origin, out):
    contract = c.validate(origin, HERE)
    from candidates.qwen2_resident_matrix.attention_packed_native import prepare
    composition = prepare.compose(out / 'composed')
    c.need(composition['generated_sha256'] == contract['generated_sha256'], 'original exact profile2 composition')
    subprocess.run(['git', 'worktree', 'add', '--detach', str(out / 'source'), os.environ['GITHUB_SHA']],
                   cwd=origin, check=True, timeout=20)
    source = out / 'source'
    for name, expected in contract['generated_sha256'].items():
        c.need(c.sha(out / 'composed' / name) == expected, 'composed generated source')
        shutil.copyfile(out / 'composed' / name, source / name)
    def stage(name, root):
        subprocess.run([sys.executable, '-I', '-B', str(HERE / 'worker.py'), name, str(root), str(out)],
                       cwd=root, check=True, timeout=120)
    stage('build', source)
    stage('profile2', origin)
    stage('scalar_silu', source)
    d = {name: c.read(out / file) for name, file in (
        ('build', 'build-stage.json'), ('profile2', 'profile2-stage.json'), ('scalar_silu', 'scalar-silu-stage.json'))}
    hashes = {value['library_sha256'] for value in d.values()}
    c.need(len(hashes) == 1 and c.sha(out / 'build/official_bf16_matrix_silu.so') in hashes,
           'one fresh ELF across all actual stages')
    for name, expected in contract['source_sha256'].items():
        c.need(c.sha(c.safe(source, name)) == contract['generated_sha256'].get(name, expected),
               'generated worktree source closure unchanged')
    c.validate(origin, HERE)
    save(out / 'result.json', dict(profile=c.PROFILE, status='PASS_FIXED_ACTUAL_CASES',
         library_sha256=next(iter(hashes)), identities={k: v['identity'] for k, v in d.items()},
         observations={'profile2_cases': d['profile2']['checks'],
                       'silu_phase_sha256': d['scalar_silu']['silu_phase_sha256']},
         checks={'profile2_original_suite': True, 'scalar_original_tests': 7,
                 'silu_success_vectors': 2, 'silu_fault_vectors': 3}))

if __name__ == '__main__':
    if sys.argv[1:] == ['--cold-import-check']:
        c.need('numpy' not in sys.modules and 'ctypes' not in sys.modules, 'cold isolated import')
        print('PASS_COLD_ISOLATED_IMPORT')
        raise SystemExit(0)
    c.need(len(sys.argv) == 4 and sys.argv[1] in ('all', 'build', 'profile2', 'scalar_silu'), 'fixed worker command')
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    mode, root, out = sys.argv[1], Path(sys.argv[2]).resolve(strict=True), Path(sys.argv[3]).resolve(strict=True)
    sys.path.insert(0, str(root))
    {'all': all_cases, 'build': build, 'profile2': profile2, 'scalar_silu': scalar_silu}[mode](root, out)
