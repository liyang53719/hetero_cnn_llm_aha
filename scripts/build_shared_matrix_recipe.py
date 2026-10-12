"""Build/verify the single host-only Matrix/SiLU test library; never use caches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

PREFIX = 'candidates/qwen2_resident_matrix/'
SOURCES = (PREFIX + 'ffn_attention/matrix_numeric.cpp',
           PREFIX + 'ffn_tiles/silu_recipe.cpp',
           PREFIX + 'transposed_down/numeric_smoke.cpp')
FLAGS = ('-shared', '-fPIC', '-O2', '-ffp-contract=off', '-fno-fast-math')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes(repo):
    return {name: sha(repo / name) for name in SOURCES}


def command(repo, compiler, library):
    return [str(compiler), *FLAGS, *(str(repo / name) for name in SOURCES[:2]),
            '-o', str(library)]


def validate(repo, library, receipt_path):
    repo, library, receipt_path = map(lambda p: Path(p).resolve(strict=True),
                                      (repo, library, receipt_path))
    r = json.loads(receipt_path.read_text())
    if r.get('schema') != 1 or r.get('status') != 'PASS_HOST_BUILD_ONLY':
        raise ValueError('shared recipe build status/schema')
    if r.get('repo') != str(repo) or r.get('library') != str(library):
        raise ValueError('shared recipe checkout/library path')
    current = source_hashes(repo)
    if r.get('sources_before') != current or r.get('sources_after') != current:
        raise ValueError('shared recipe source closure/hash')
    compiler = Path(r['compiler']).resolve(strict=True)
    if r.get('compiler_sha256') != sha(compiler):
        raise ValueError('shared recipe compiler identity')
    if r.get('argv') != command(repo, compiler, library) or r.get('returncode') != 0:
        raise ValueError('shared recipe strict compile command/exit')
    if r.get('library_bytes') != library.stat().st_size or r.get('library_sha256') != sha(library):
        raise ValueError('shared recipe library identity')
    return library


def from_environment(repo, environ=None):
    env = os.environ if environ is None else environ
    if not env.get('MATRIX_SERVICE_LIBRARY') or not env.get('MATRIX_SERVICE_COMPILE_RECEIPT'):
        raise ValueError('explicit MATRIX_SERVICE_LIBRARY and MATRIX_SERVICE_COMPILE_RECEIPT required')
    return validate(repo, env['MATRIX_SERVICE_LIBRARY'], env['MATRIX_SERVICE_COMPILE_RECEIPT'])


def build(repo, out):
    repo, out = Path(repo).resolve(strict=True), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler_name = shutil.which('g++')
    if compiler_name is None:
        raise ValueError('g++ is required for host recipe')
    compiler = Path(compiler_name).resolve(strict=True)
    library = out / 'matrix_silu_numeric.so'
    receipt = out / 'compile.json'
    before = source_hashes(repo)
    argv = command(repo, compiler, library)
    started = time.monotonic()
    result = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=60)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    r = dict(schema=1, status='PASS_HOST_BUILD_ONLY' if result.returncode == 0 else 'FAILED',
             repo=str(repo), library=str(library), compiler=str(compiler),
             compiler_sha256=sha(compiler), argv=argv, returncode=result.returncode,
             sources_before=before, sources_after=source_hashes(repo),
             seconds=time.monotonic() - started, rtl_generated=False)
    if library.is_file():
        r.update(library_bytes=library.stat().st_size, library_sha256=sha(library))
    receipt.write_text(json.dumps(r, indent=2) + '\n')
    validate(repo, library, receipt)
    return library, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    library, receipt = build(args.repo, args.out)
    values = dict(MATRIX_SERVICE_LIBRARY=library, MATRIX_SERVICE_COMPILE_RECEIPT=receipt,
                  MATRIX_SERVICE_EVIDENCE_DIR=library.parent)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as f:
            for key, value in values.items():
                f.write(f'{key}={value}\n')
    print(json.dumps({key: str(value) for key, value in values.items()}, sort_keys=True))


if __name__ == '__main__':
    main()
