"""SOURCE-only fixed11 wheel front door. Import/default CLI never accesses network.

The caller owns the original shared 6600s budget, 120s safety reserve, process-group
supervision, acquisition <=180s and total acquisition+install <=300s. Python setup
is also charged to that original shared budget. This module never launches pip.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import urllib.request

ACQUIRE_SECONDS = 180
INSTALL_SECONDS = 120
TOTAL_SECONDS = 300
WHEEL_BYTES = 215906086
MAX_WHEEL_BYTES = 188943803
INSTALLED_OBSERVATION_CAP = 1610612736
COMBINED_OBSERVATION_CAP = 1879048192
PYTHON_BYTES = 30894944
PYTHON_SHA256 = 'fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7'
PYTHON_VERSION = (3, 12)
SOURCE_PINS = {
    'WHEELS.json': (7947, 'ddfbba18f68182631118ba0108d0a8d5d51db1b32d07094fa00e4c83cd147caf'),
    'requirements-direct.lock': (2587, 'c49b3b6241845e0d68c60e96187a557418c96febd7fbbb15eb1d3bba24e6d3e1'),
    'requirements-runtime.txt': (1217, '9bd334944d52ae82a86ca89ac44612920270c028f29c15fde93ba4d656535a83'),
}
# name, version, filename, exact byte length, SHA-256, sole authorized HTTPS URL.
WHEELS = (('filelock', '4.2.0', 'filelock-4.2.0-py3-none-any.whl', 135032, '2ff5690882e8cdb00ef31fb3d01a3094c29f30985426c59495afb1733f3b7238', 'https://files.pythonhosted.org/packages/8e/a3/9bc26acff301fe1aaea1cc3d82a1d57e0a34df3e1cadbfa91ac2dbcdde5c/filelock-4.2.0-py3-none-any.whl'), ('fsspec', '2026.9.0', 'fsspec-2026.9.0-py3-none-any.whl', 221738, '8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f', 'https://files.pythonhosted.org/packages/6c/c0/a98505f18594f1bce828bb159cec0fcf9860562f1a2c85913409fc8f3d9e/fsspec-2026.9.0-py3-none-any.whl'), ('jinja2', '3.1.6', 'jinja2-3.1.6-py3-none-any.whl', 134899, '85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67', 'https://files.pythonhosted.org/packages/62/a1/3d680cbfd5f4b8f15abc1d571870c5fc3e594bb582bc3b64ea099db13e56/jinja2-3.1.6-py3-none-any.whl'), ('markupsafe', '3.0.4', 'markupsafe-3.0.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl', 22985, '8e124f974786f831d6043728e38296969d3579db8896fe004682f5758e613581', 'https://files.pythonhosted.org/packages/4f/a7/aeedb5140afa41fc74c225e9184ab96723a6e873b6ee1c9fede7283456d8/markupsafe-3.0.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl'), ('mpmath', '1.3.0', 'mpmath-1.3.0-py3-none-any.whl', 536198, 'a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c', 'https://files.pythonhosted.org/packages/43/e3/7d92a15f894aa0c9c4b49b8ee9ac9850d6e63b03c9c32c0367a13ae62209/mpmath-1.3.0-py3-none-any.whl'), ('networkx', '3.7', 'networkx-3.7-py3-none-any.whl', 2142205, 'e3fd2c13a7814cee3746340d8d7f8598a67f16a58bf47fb7f8793fab6efca1b0', 'https://files.pythonhosted.org/packages/7e/cd/fe58041e9011f307c490e3e17dd48cc516448f7c698a3f2d9d9d65d7e6a8/networkx-3.7-py3-none-any.whl'), ('numpy', '2.3.5', 'numpy-2.3.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl', 16606086, '0d8163f43acde9a73c2a33605353a4f1bc4798745a8b1d73183b28e5b435ae28', 'https://files.pythonhosted.org/packages/b6/23/2a1b231b8ff672b4c450dac27164a8b2ca7d9b7144f9c02d2396518352eb/numpy-2.3.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl'), ('setuptools', '84.0.0', 'setuptools-84.0.0-py3-none-any.whl', 818216, '51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670', 'https://files.pythonhosted.org/packages/95/9c/c510029fc6ef33a6275cd2c5d3cecd6613dfd6aa401d57c54f1c18852ccf/setuptools-84.0.0-py3-none-any.whl'), ('sympy', '1.14.0', 'sympy-1.14.0-py3-none-any.whl', 6299353, 'e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5', 'https://files.pythonhosted.org/packages/a2/09/77d55d46fd61b4a135c444fc97158ef34a095e5681d0a6c10b75bf356191/sympy-1.14.0-py3-none-any.whl'), ('torch', '2.10.0+cpu', 'torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl', 188943803, 'ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d', 'https://download-r2.pytorch.org/whl/cpu/torch-2.10.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl'), ('typing_extensions', '4.16.0', 'typing_extensions-4.16.0-py3-none-any.whl', 45571, '481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8', 'https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl'))
CODES = frozenset(('SOURCE_IDENTITY', 'FILESYSTEM', 'PYTHON_IDENTITY',
    'EXECUTION_DISABLED', 'DEADLINE', 'NETWORK', 'REDIRECT', 'RESPONSE',
    'WHEEL_SIZE', 'WHEEL_HASH', 'WHEEL_SET', 'TREE_LIMIT', 'OBSERVATION'))


class GateError(RuntimeError):
    """Only finite codes may cross the public error boundary."""
    def __init__(self, code):
        super().__init__(code if code in CODES else 'OBSERVATION')


def _regular_open(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            raise GateError('FILESYSTEM')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def _checked_bytes(path, size, digest, code):
    with _regular_open(path) as f:
        if os.fstat(f.fileno()).st_size != size:
            raise GateError(code)
        data = f.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise GateError(code)
        return data


def source_preflight(source_dir):
    """Offline, same-buffer identity+parse of the three immutable source inputs."""
    try:
        source = Path(source_dir)
        blobs = {n: _checked_bytes(source/n, *p, 'SOURCE_IDENTITY')
                 for n, p in SOURCE_PINS.items()}
        m = json.loads(blobs['WHEELS.json'])
        rows = tuple((p['name'], p['version'], p['filename'], p['bytes'],
                      p['sha256'], p['url']) for p in m['packages'])
        if rows != WHEELS or len(rows) != 11 or sum(x[3] for x in rows) != WHEEL_BYTES:
            raise GateError('SOURCE_IDENTITY')
        return {'status': 'SOURCE_ONLY', 'packages': 11, 'wheel_bytes': WHEEL_BYTES,
                'acquired': False, 'installed': False, 'native_executed': False}
    except GateError:
        raise
    except Exception:
        raise GateError('SOURCE_IDENTITY') from None


def _private_dir(path, *, fresh=False):
    p = Path(path).absolute()
    # Reject symlink components, including existing ancestors and the final path.
    if p != p.resolve(strict=False):
        raise GateError('FILESYSTEM')
    if fresh:
        p.mkdir(mode=0o700)
    s = p.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise GateError('FILESYSTEM')
    return p


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise GateError('DEADLINE')
    return remaining


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GateError('REDIRECT')


def _download_one(opener, row, directory, deadline):
    """Stream exact-sized content. No partial byte is ever trusted as a wheel."""
    name, version, filename, expected_size, expected_hash, url = row
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity',
                                                  'User-Agent': 'n0-fixed11/1'})
    with opener.open(request, timeout=min(10.0, _remaining(deadline))) as response:
        _remaining(deadline)
        if response.status != 200 or response.geturl() != url:
            raise GateError('RESPONSE')
        encoding = response.headers.get('Content-Encoding')
        lengths = response.headers.get_all('Content-Length', [])
        if encoding not in (None, 'identity') or len(lengths) > 1:
            raise GateError('RESPONSE')
        if lengths and (not lengths[0].isascii() or not lengths[0].isdecimal()
                        or int(lengths[0]) != expected_size):
            raise GateError('WHEEL_SIZE')
        fd = os.open(directory/filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW, 0o600)
        h, count = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as f:
            while True:
                _remaining(deadline)
                # read1 avoids aggregating many socket reads into one call where
                # supported. The outer process supervisor is the hard wall cap.
                read = getattr(response, 'read1', response.read)
                chunk = read(min(1024 * 1024, expected_size - count + 1))
                _remaining(deadline)
                if not chunk:
                    break
                count += len(chunk)
                if count > expected_size:
                    raise GateError('WHEEL_SIZE')
                h.update(chunk)
                f.write(chunk)
            if count != expected_size:
                raise GateError('WHEEL_SIZE')
            if h.hexdigest() != expected_hash:
                raise GateError('WHEEL_HASH')
            f.flush()
            os.fchmod(f.fileno(), 0o400)
        return count


def verify_wheels(wheel_dir):
    """Rehash exactly the fixed11; reject extra files, links and changed sizes."""
    try:
        d = _private_dir(wheel_dir)
        if set(os.listdir(d)) != {x[2] for x in WHEELS}:
            raise GateError('WHEEL_SET')
        total = 0
        for _, _, filename, size, digest, _ in WHEELS:
            with _regular_open(d/filename) as f:
                if os.fstat(f.fileno()).st_size != size:
                    raise GateError('WHEEL_SIZE')
                h, count = hashlib.sha256(), 0
                while True:
                    b = f.read(min(1024*1024, size-count+1))
                    if not b:
                        break
                    count += len(b)
                    if count > size:
                        raise GateError('WHEEL_SIZE')
                    h.update(b)
                if count != size:
                    raise GateError('WHEEL_SIZE')
                if h.hexdigest() != digest:
                    raise GateError('WHEEL_HASH')
            total += size
        if total != WHEEL_BYTES:
            raise GateError('WHEEL_SET')
        return {'packages': 11, 'wheel_bytes': total}
    except GateError:
        raise
    except Exception:
        raise GateError('FILESYSTEM') from None


def acquire_wheels(source_dir, fresh_wheel_dir, *, execute=False, deadline=None):
    """Explicit execution-only network entry. No retries, mirrors or redirects.

    Uses urllib's normal platform proxy and certificate trust configuration.
    Supplies no account credentials, cookies, custom CA, or authentication handlers.
    Caller MUST enforce an outer <=180s process-group deadline and shared budget.
    """
    if execute is not True:
        raise GateError('EXECUTION_DISABLED')
    try:
        source_preflight(source_dir)
        started = time.monotonic()
        if deadline is None:
            deadline = started + ACQUIRE_SECONDS
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise GateError('DEADLINE')
        deadline = min(deadline, started + ACQUIRE_SECONDS)
        _remaining(deadline)
        d = _private_dir(fresh_wheel_dir, fresh=True)
        # Default handlers retain normal environment proxy/CA behavior. The
        # explicit redirect handler replaces automatic HTTPRedirectHandler.
        opener = urllib.request.build_opener(_NoRedirect())
        total = 0
        for row in WHEELS:
            total += _download_one(opener, row, d, deadline)
        _remaining(deadline)
        if total != WHEEL_BYTES:
            raise GateError('WHEEL_SIZE')
        result = verify_wheels(d)
        _remaining(deadline)
        os.chmod(d, 0o500)
        return {'status': 'ACQUIRED_VERIFIED', **result, 'installed': False}
    except GateError:
        raise
    except Exception:
        raise GateError('NETWORK') from None


def require_current_python(python_path=None):
    """The caller must already run under the pinned historical CPython 3.12."""
    try:
        p = Path(sys.executable).resolve(strict=True)
        chosen = p if python_path is None else Path(python_path).resolve(strict=True)
        if (chosen != p or tuple(sys.version_info[:len(PYTHON_VERSION)]) != PYTHON_VERSION
                or sys.implementation.name != 'cpython' or sys.platform != 'linux'):
            raise GateError('PYTHON_IDENTITY')
        _checked_bytes(p, PYTHON_BYTES, PYTHON_SHA256, 'PYTHON_IDENTITY')
        if not os.access(p, os.X_OK):
            raise GateError('PYTHON_IDENTITY')
        return str(p)
    except GateError:
        raise
    except Exception:
        raise GateError('PYTHON_IDENTITY') from None


def install_argv(source_dir, wheel_dir, fresh_target_dir, python_path=None):
    """Prepare only: fixed direct LOCAL wheel URLs+hashes, return exact pip argv.

    The fresh target contains a private fixed11 lock. No package process starts
    here. The caller must supervise pip at <=120s AND remaining original 300s,
    with offline network policy, clean env, private TMPDIR, logs and tree sampling.
    """
    try:
        source_preflight(source_dir)
        python = require_current_python(python_path)
        verify_wheels(wheel_dir)
        wheels = _private_dir(wheel_dir)
        target = _private_dir(fresh_target_dir, fresh=True)
        lock = target/'.n0-fixed11.lock'
        content = ''.join((wheels/row[2]).as_uri() + ' --hash=sha256:' + row[4] + '\n'
                          for row in WHEELS).encode('ascii')
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        return [python, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                '--no-input', 'install', '--no-index', '--no-deps', '--only-binary=:all:',
                '--require-hashes', '--no-cache-dir', '--no-compile', '--retries', '0',
                '--target', str(target), '-r', str(lock)]
    except GateError:
        raise
    except Exception:
        raise GateError('FILESYSTEM') from None


def observe_installed_tree(target_dir, wheel_dir):
    """Post-install acceptance check, NOT an OS-enforced filesystem limit.

    Reports measured regular-file logical bytes including the tiny local lock;
    transient pip/temp/log space must also be sampled by the caller. No imported
    torch/numpy code, native identity claim, peak-space claim or numerical claim.
    """
    try:
        verify_wheels(wheel_dir)
        root = _private_dir(target_dir)
        count, total = 0, 0
        def reject_walk_error(_error):
            raise GateError('OBSERVATION') from None
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=reject_walk_error):
            for name in dirs:
                s = (Path(directory)/name).lstat()
                if not stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode):
                    raise GateError('OBSERVATION')
            for name in files:
                s = (Path(directory)/name).lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                    raise GateError('OBSERVATION')
                total += s.st_size
                count += 1
                if total > INSTALLED_OBSERVATION_CAP or total+WHEEL_BYTES > COMBINED_OBSERVATION_CAP:
                    raise GateError('TREE_LIMIT')
        return {'status': 'SIZE_ACCEPTED_ONLY', 'installed_tree_logical_bytes': total,
                'combined_wheels_tree_logical_bytes': total+WHEEL_BYTES,
                'installed_regular_files': count, 'os_hard_size_limit': False,
                'native_identity_checked': False, 'numeric_execution': False}
    except GateError:
        raise
    except Exception:
        raise GateError('OBSERVATION') from None


if __name__ == '__main__':
    # Intentionally no acquisition/install CLI: the integrating coordinator owns
    # execution authorization, original budgets and supervision.
    try:
        if len(sys.argv) != 1:
            raise GateError('EXECUTION_DISABLED')
        print(json.dumps(source_preflight(Path(__file__).parent), sort_keys=True))
    except GateError as e:
        print(json.dumps({'status': 'FAILED', 'code': str(e)}, sort_keys=True))
        raise SystemExit(1)
