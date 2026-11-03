#!/usr/bin/env python3
"""Fresh Qwen2-only AVX512 exact-wheel runtime under the external supervisor.

No reuse, retries, automatic ISA fallback, or arithmetic qualification. All logs
remain inside the owned output tree. The reference sets inter-op=1 before work.
"""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from weight_errors import WEIGHT_FAILURE_REASONS

CREATED_OUTPUT = None
BLOCK = 1 << 20
WHEEL_HOSTS = {'files.pythonhosted.org', 'download-r2.pytorch.org'}
TORCH_GIT = '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'


class StageFailure(ValueError):
    def __init__(self, reason, mismatch=False):
        super().__init__(reason)
        self.reason = reason
        self.mismatch = mismatch


def failure_receipt(output, exc, default_reason):
    # Never serialize exception strings, URLs, paths, headers, or response bodies.
    reason = exc.reason if isinstance(exc, StageFailure) else default_reason
    need(reason in ({'PRECHECK_PIN', 'INSTALL', 'WEIGHT_HASH'} | WEIGHT_FAILURE_REASONS), 'failure enum')
    if output.is_dir() and not output.is_symlink() and not (output / 'FAILURE.json').exists():
        write_json(output / 'FAILURE.json', {'schema': 'P0_STAGE_FAILURE_V1',
                   'status': 'FAIL', 'reason': reason})


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    out = {}
    for k, v in pairs:
        need(k not in out, 'duplicate JSON key')
        out[k] = v
    return out


def read_json(path):
    p = Path(path)
    need(not p.is_symlink() and p.is_file() and p.stat().st_size <= 2 * BLOCK, 'JSON file bound')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def safe_name(name):
    p = PurePosixPath(name)
    need(isinstance(name, str) and not p.is_absolute() and '..' not in p.parts
         and str(p) not in ('', '.') and '\\' not in name, 'unsafe relative name')
    return p


def allowed_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    need(p.scheme == 'https' and p.hostname in hosts and not p.username
         and not p.password and p.port in (None, 443), 'URL not allowlisted')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def clean_env():
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'PIP_CONFIG_FILE': '/dev/null', 'PIP_NO_INPUT': '1',
            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'ATEN_CPU_CAPABILITY': 'avx512', 'OMP_NUM_THREADS': '4',
            'MKL_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4', 'NUMEXPR_NUM_THREADS': '4'}


def verify_files(site, sidecar):
    for name, expected in sidecar['module_sha256'].items():
        rel = str(safe_name(sidecar['module_relative_paths'][name]))
        p = site / rel
        need(p.is_file() and not p.is_symlink() and sha(p) == expected, 'installed module hash')
    for rel, expected in sidecar['native_file_sha256'].items():
        p = site / str(safe_name(rel))
        need(p.is_file() and not p.is_symlink() and sha(p) == expected, 'installed native hash')


def derive_sidecar(cache, wheels, expected):
    archives = {x['name']: cache / x['filename'] for x in wheels}
    module_order = ('transformers.models.qwen2.modeling_qwen2',
                    'transformers.models.qwen2.configuration_qwen2',
                    'transformers.activations', 'transformers.cache_utils',
                    'torch.nn.functional', 'torch._C')
    actual = {}
    modules = {}
    natives = {}
    with zipfile.ZipFile(archives['torch']) as t, zipfile.ZipFile(archives['transformers']) as f:
        for archive in (t, f):
            need(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate archive member')
            for info in archive.infolist():
                safe_name(info.filename)
                need(stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK, 'archive symlink')
        def member_hash(archive, rel):
            with archive.open(rel) as src:
                h = hashlib.sha256()
                for b in iter(lambda: src.read(BLOCK), b''):
                    h.update(b)
                return h.hexdigest()
        for name in module_order:
            rel = expected['module_relative_paths'][name]
            modules[name] = member_hash(t if rel.startswith('torch/') else f, rel)
        names = sorted(n for n in t.namelist() if n.startswith('torch/')
                       and (n.endswith('.so') or '.so.' in n) and not n.endswith('/'))
        for name in names:
            natives[name] = member_hash(t, name)
    actual = {
        'framework_revision': expected['framework_revision'],
        'module_sha256': modules,
        'module_relative_paths': {name: expected['module_relative_paths'][name] for name in module_order},
        'native_file_sha256': natives,
        'artifact_sha256': {name: expected['artifact_sha256'][name] for name in ('framework', 'torch')},
        'identity': expected['identity'], 'limits': expected['limits']} 
    need(actual == expected, 'archive-derived sidecar mismatch')
    return actual


def probe(site, frozen, output):
    manifest = read_json(frozen)
    sidecar = manifest['runtime_sidecar']['content']
    need(os.environ.get('ATEN_CPU_CAPABILITY') == 'avx512', 'dispatch environment')
    need(all(os.environ.get(k) == '4' for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS',
         'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS')), 'thread environment')
    verify_files(site, sidecar)
    import torch
    import transformers
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    observed_torch_git = torch.version.git_version
    need(torch.__version__ == '2.10.0+cpu' and observed_torch_git == TORCH_GIT,
         'Torch version')
    need(transformers.__version__ == '4.40.1', 'Transformers version')
    observed_capability = torch.backends.cpu.get_cpu_capability()
    observed_threads = torch.get_num_threads()
    observed_interop_threads = torch.get_num_interop_threads()
    need(observed_capability == 'AVX512', 'actual dispatch')
    need(observed_threads == 4 and observed_interop_threads == 1, 'actual threads')
    imported = {}
    for name, expected in sidecar['module_sha256'].items():
        mod = importlib.import_module(name)
        path = Path(mod.__file__).resolve()
        need(path == (site / sidecar['module_relative_paths'][name]).resolve(),
             'actual imported source')
        observed_hash = sha(path)
        need(observed_hash == expected, 'actual imported source')
        imported[name] = observed_hash
    versions = {}
    for x in manifest['wheels']:
        if x['role'] == 'runtime':
            dist = importlib.metadata.distribution(x['name'])
            need(dist.version == x['version'] and Path(dist.locate_file('')).resolve() == site.resolve(),
                 'installed distribution version/location')
            versions[x['name']] = dist.version
    verify_files(site, sidecar)
    write_json(output, {'observed_capability': observed_capability, 'threads': observed_threads,
                       'interop_threads': observed_interop_threads, 'imported_modules': imported,
                       'versions': versions, 'torch_git': observed_torch_git})


def prepare(output, frozen):
    global CREATED_OUTPUT
    manifest = read_json(frozen)
    wheels = manifest['wheels']
    need(len(wheels) == 26 and len({x['filename'] for x in wheels}) == 26
         and len({x['name'] for x in wheels}) == 26, '26 unique exact wheels')
    need(sum(x['size_bytes'] for x in wheels) == 238463458, 'whole wheel budget')
    need(sum(x['role'] == 'runtime' for x in wheels) == 25, '25 runtime wheels')
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64'
         and platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 12), 'wheel ABI')
    need(not output.exists() and not output.is_symlink(), 'new runtime root required')
    output.mkdir()
    CREATED_OUTPUT = output.resolve()
    output = output.resolve()
    cache = output / 'artifacts'
    cache.mkdir()
    started = time.monotonic()
    received = 0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect(WHEEL_HOSTS))
    for x in wheels:
        name = str(safe_name(x['filename']))
        need('/' not in name, 'single wheel filename')
        allowed_url(x['url'], WHEEL_HOSTS)
        partial = cache / (name + '.partial')
        size = x['size_bytes']
        need(type(size) is int and 0 < size < 350 * BLOCK, 'wheel size')
        count = 0
        h = hashlib.sha256()
        request = urllib.request.Request(x['url'], headers={'Accept-Encoding': 'identity'})
        with opener.open(request, timeout=60) as response, partial.open('xb') as dst:
            allowed_url(response.geturl(), WHEEL_HOSTS)
            need(response.status == 200 and response.headers.get('Content-Encoding', 'identity') == 'identity', 'wheel response')
            need(response.headers.get('Content-Length') in (None, str(size)), 'wheel length')
            while True:
                need(time.monotonic() - started < 1500, 'download wall limit')
                block = response.read(min(BLOCK, size - count + 1))
                if not block:
                    break
                count += len(block)
                received += len(block)
                need(count <= size and received <= 238463458, 'download byte limit')
                h.update(block)
                dst.write(block)
        need(count == size and h.hexdigest() == x['sha256'], 'exact wheel mismatch')
        partial.rename(cache / name)
    sidecar = derive_sidecar(cache, wheels, manifest['runtime_sidecar']['content'])
    write_json(output / 'SOURCE_SIDECAR.json', sidecar)
    need(sha(output / 'SOURCE_SIDECAR.json') == manifest['runtime_sidecar']['sha256'], 'sidecar byte identity')
    boot = output / 'bootstrap-pip'
    boot.mkdir()
    pip = next(x for x in wheels if x['name'] == 'pip')
    with zipfile.ZipFile(cache / pip['filename']) as z:
        need(len(z.infolist()) < 16000 and sum(i.file_size for i in z.infolist()) < 64 * BLOCK,
             'pip extraction bounds')
        need(len(z.namelist()) == len(set(z.namelist())), 'duplicate pip member')
        for info in z.infolist():
            target = boot / str(safe_name(info.filename))
            need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR), 'regular pip member')
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst, BLOCK)
    site = output / 'site-packages'
    site.mkdir()
    tmp = output / 'tmp'
    tmp.mkdir()
    env = clean_env()
    env.update(HOME=str(output), TMPDIR=str(tmp), PYTHONPATH=str(boot))
    command = [sys.executable, '-S', '-B', '-m', 'pip', 'install', '--no-index', '--no-deps',
               '--no-compile', '--disable-pip-version-check', '--target', str(site)]
    command.extend(str(cache / x['filename']) for x in wheels if x['role'] == 'runtime')
    # Inherit the external lossless-log supervisor pipe; never create an unbounded log file.
    subprocess.run(command, env=env, check=True, timeout=max(1, 1800 - (time.monotonic() - started)))
    verify_files(site, sidecar)
    wrapper = output / 'python'
    wrapper.write_text('#!/bin/sh\nset -eu\nRUNTIME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
                       'unset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE LD_PRELOAD LD_LIBRARY_PATH\n'
                       'export PYTHONPATH="$RUNTIME/site-packages"\n'
                       'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\n'
                       'export ATEN_CPU_CAPABILITY=avx512 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4\n'
                       'exec ' + shlex.quote(sys.executable) + ' -S -B "$@"\n', encoding='utf-8')
    wrapper.chmod(0o755)
    result = output / 'IMPORT_PROBE.json'
    subprocess.run([str(wrapper), str(Path(__file__).resolve()), '--probe', '--site', str(site),
                    '--frozen', str(frozen.resolve()), '--output', str(result)],
                   env={**clean_env(), 'HOME':str(output), 'TMPDIR':str(tmp),
                        'XDG_CACHE_HOME':str(output/'cache'), 'HF_HOME':str(output/'cache/huggingface'),
                        'TORCH_HOME':str(output/'cache/torch')}, check=True, timeout=120)
    observed = read_json(result)
    receipt = {'schema': 'P0_AVX512_FRESH_RUNTIME_V1', 'status': 'FRESH_VERIFIED_NOT_REFERENCE_QUALIFIED',
               'site': str(site), 'wrapper': str(wrapper), 'wrapper_sha256': sha(wrapper),
               'source_sha256': sha(__file__), 'frozen_sha256': sha(frozen),
               'sidecar_sha256': sha(output / 'SOURCE_SIDECAR.json'),
               'python_executable_sha256': sha(sys.executable), 'python_version': platform.python_version(),
               'installed_wheels': [{'name': x['name'], 'version': x['version'], 'sha256': x['sha256'],
                                     'bytes': x['size_bytes']} for x in wheels],
               'network_bytes': received, 'historical_reference_pass_transferred': False, **observed}
    write_json(output / 'RUNTIME_RECEIPT.json', receipt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--site', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        need(args.site is not None, 'probe site required')
        probe(args.site, args.frozen, args.output)
    else:
        try:
            prepare(args.output, args.frozen)
        except Exception as exc:
            if CREATED_OUTPUT is not None:
                failure_receipt(CREATED_OUTPUT, exc, 'INSTALL')
            raise SystemExit(1) from None


if __name__ == '__main__':
    main()
