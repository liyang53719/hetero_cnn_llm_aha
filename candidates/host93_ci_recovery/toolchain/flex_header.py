"""Pinned single-header SOURCE acquisition; import performs no application I/O.

stage() is for an independently pinned, isolated Python child supervised by a
120 s wall / 40 s CPU / 512 MiB AS / 4 MiB FSIZE / 64 KiB captured-log parent.
It uses only the verified parser's pure validate_package(), not its obsolete
five-package staging or identity-review entrypoints. No package is installed,
no downloaded code is executed, and no archive path is used as an output path.
The caller owns cleanup of any partially created fresh destination on failure.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import urllib.request

PURPOSE = 'PINNED_HEADER_ONLY_FOR_PUBLIC_SOURCE_CI'
SCHEMA = 'SINGLE_FLEX_HEADER_ACQUISITION_V1'
PACKAGE_URL = 'https://deb.debian.org/debian/pool/main/f/flex/libfl-dev_2.6.4-8.2+b4_amd64.deb'
PACKAGE_FILENAME = 'libfl-dev_2.6.4-8.2+b4_amd64.deb'
PACKAGE_BYTES = 85600
PACKAGE_SHA256 = '1b40033660656acd5c2f85d2c45a4e02bf57a0facc5e0623327474cb911b3136'
HEADER_SOURCE_PATH = 'usr/include/FlexLexer.h'
HEADER_OUTPUT_PATH = 'include/FlexLexer.h'
HEADER_BYTES = 6893
HEADER_SHA256 = 'ee9859d6b3027ed565f98f42744e438ab31b2cd2e9f797ddf870029ca2021686'
PARSER_BYTES = 20634
PARSER_SHA256 = '3f56c0b6ce0f41f245abf8d37ff55fa5257d71ead395f49410a2746924682a79'
PLAN_SHA256 = '84ba3f04c62bca43cc277c3a5acdaf8e108feefa2c307db21f593964a5b40f55'
PACKAGE_PIN_SHA256 = '8f1af8c3766157adfd85824ef36f19c76f265669129196f7f18aea2e45db81e8'
DEADLINE_SECONDS = 90
SOCKET_TIMEOUT_SECONDS = 30
MAX_RECEIPT_BYTES = 4096
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class AcquisitionError(ValueError):
    """Only fixed, non-network-derived messages leave this module."""


def require(ok, reason):
    if not ok:
        raise AcquisitionError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii'))


def _checked_config(plan, package_pin):
    require(type(plan) is dict and type(package_pin) is dict, 'configuration type')
    try:
        require(canonical_sha(plan) == PLAN_SHA256, 'plan identity')
        require(canonical_sha(package_pin) == PACKAGE_PIN_SHA256, 'package pin identity')
        items = [p for p in plan['artifacts'] if p['package'] == 'libfl-dev']
        require(len(items) == 1, 'single package plan')
        p = items[0]
        require(p['url'] == PACKAGE_URL and p['relative_destination'] == PACKAGE_FILENAME
                and type(p['known_size_bytes']) is int and p['known_size_bytes'] == PACKAGE_BYTES
                and type(p['max_transfer_bytes']) is int and p['max_transfer_bytes'] == PACKAGE_BYTES + 1
                and p['sha256'] == PACKAGE_SHA256 and p['architecture'] == 'amd64',
                'package plan contract')
        require(plan['transport'] == 'https-no-redirect', 'transport contract')
        require(package_pin['package'] == 'libfl-dev'
                and package_pin['deb_filename'] == PACKAGE_FILENAME
                and type(package_pin['deb_bytes']) is int and package_pin['deb_bytes'] == PACKAGE_BYTES
                and package_pin['deb_sha256'] == PACKAGE_SHA256
                and package_pin['control_fields'] == {'Package': 'libfl-dev',
                    'Version': '2.6.4-8.2+b4', 'Architecture': 'amd64'}, 'package pin contract')
        selected = {'path': HEADER_SOURCE_PATH, 'raw_tar_path': './' + HEADER_SOURCE_PATH,
                    'kind': 'regular', 'tar_type': '0', 'mode': '0o644',
                    'bytes': HEADER_BYTES, 'sha256': HEADER_SHA256}
        require(package_pin['selected'] == [selected], 'single selected header contract')
        rows = [r for r in package_pin['members'] if r['name'] == './' + HEADER_SOURCE_PATH]
        require(rows == [{'name': './' + HEADER_SOURCE_PATH, 'type': '0', 'mode': '0o644',
                          'bytes': HEADER_BYTES, 'sha256': HEADER_SHA256, 'linkname': ''}],
                'header member contract')
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('configuration malformed') from None


def _load_parser(parser_raw, parser_path):
    require(type(parser_raw) is bytes and len(parser_raw) == PARSER_BYTES
            and sha(parser_raw) == PARSER_SHA256, 'parser buffer identity')
    require(type(parser_path) is str and 0 < len(parser_path) <= 4096
            and '\x00' not in parser_path, 'parser label')
    namespace = {'__name__': '_verified_flex_header_parser', '__file__': parser_path}
    try:
        # Compile this exact already hashed buffer. Never reopen parser_path.
        exec(compile(parser_raw, parser_path, 'exec', dont_inherit=True), namespace)
        validator = namespace.get('validate_package')
        require(callable(validator), 'parser callable')
        return validator
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('parser load failed') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AcquisitionError('redirect refused')

    # Reject before urllib resolves or examines a Location target.
    def http_error_302(self, req, fp, code, msg, headers):
        raise AcquisitionError('redirect refused')

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'acquisition deadline')
    return remaining


def _download(deadline):
    try:
        # Retain urllib's platform proxy/CA defaults; never install an opener
        # globally or forward arbitrary request headers from configuration.
        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(PACKAGE_URL, headers={'Accept-Encoding': 'identity'}, method='GET')
        timeout = min(SOCKET_TIMEOUT_SECONDS, _remaining(deadline))
        with opener.open(request, timeout=timeout) as response:
            _remaining(deadline)
            require(response.getcode() == 200, 'HTTP status refused')
            require(response.geturl() == PACKAGE_URL, 'response URL refused')
            lengths = response.headers.get_all('Content-Length', [])
            encodings = response.headers.get_all('Content-Encoding', [])
            require(len(lengths) <= 1, 'content length refused')
            if lengths:
                length = lengths[0].strip()
                require(length.isascii() and length.isdecimal()
                        and len(length) <= 12 and int(length) == PACKAGE_BYTES, 'content length refused')
            require(not encodings or (len(encodings) == 1 and encodings[0].strip().lower() == 'identity'),
                    'content encoding refused')
            chunks, total = [], 0
            while total <= PACKAGE_BYTES:
                _remaining(deadline)
                # One extra byte is sufficient to prove oversize. The outer
                # supervisor bounds blocking DNS/TLS/body calls as well.
                chunk = response.read(min(16384, PACKAGE_BYTES + 1 - total))
                _remaining(deadline)
                require(type(chunk) is bytes, 'response body type')
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                require(total <= PACKAGE_BYTES, 'package size exceeded')
            raw = b''.join(chunks)
            require(len(raw) == PACKAGE_BYTES and sha(raw) == PACKAGE_SHA256, 'package identity')
            return raw
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('transport failed') from None


def _open_parent(output_dir):
    require(isinstance(output_dir, Path) and output_dir.is_absolute(), 'absolute output directory required')
    parts = output_dir.parts
    require(len(parts) >= 3 and all(p not in ('', '.', '..') for p in parts[1:])
            and len(str(output_dir)) <= 4096, 'output directory syntax')
    fd = os.open('/', DIRECTORY_FLAGS)
    try:
        for part in parts[1:-1]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        st = os.fstat(fd)
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                and stat.S_IMODE(st.st_mode) == 0o700, 'output parent must be private')
        try:
            os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise AcquisitionError('output destination exists')
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _write_at(parent_fd, name, raw):
    require(name in ('FlexLexer.h', 'RECEIPT.json'), 'output filename')
    fd = os.open(name, WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    try:
        offset = 0
        while offset < len(raw):
            n = os.write(fd, raw[offset:])
            require(n > 0, 'output short write')
            offset += n
        os.fsync(fd)
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600
                and st.st_uid == os.geteuid() and st.st_nlink == 1 and st.st_size == len(raw),
                'output inode identity')
    finally:
        os.close(fd)
    check_fd = os.open(name, READ_FLAGS, dir_fd=parent_fd)
    try:
        after = os.fstat(check_fd)
        require((after.st_dev, after.st_ino, after.st_mode, after.st_nlink, after.st_size)
                == (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size), 'output path replaced')
        parts, count = [], 0
        while count <= len(raw):
            chunk = os.read(check_fd, len(raw) + 1 - count)
            if not chunk:
                break
            parts.append(chunk)
            count += len(chunk)
        require(b''.join(parts) == raw, 'output readback')
    finally:
        os.close(check_fd)


def _receipt():
    return {'schema': SCHEMA, 'purpose': PURPOSE,
            'package': {'filename': PACKAGE_FILENAME, 'bytes': PACKAGE_BYTES, 'sha256': PACKAGE_SHA256},
            'header': {'path': HEADER_OUTPUT_PATH, 'source_path': HEADER_SOURCE_PATH,
                       'bytes': HEADER_BYTES, 'sha256': HEADER_SHA256, 'mode': '0o600'},
            'parser': {'bytes': PARSER_BYTES, 'sha256': PARSER_SHA256},
            'plan_sha256': PLAN_SHA256, 'package_pin_sha256': PACKAGE_PIN_SHA256}


def stage(output_dir: Path, plan: dict, package_pin: dict,
          parser_raw: bytes, parser_path: str) -> dict:
    """Validate one fixed package and publish only its exact pinned header.

    plan is the full unchanged DEPENDENCY_PLAN.json; package_pin is the full
    libfl-dev row of PINS.json. parser_path is a diagnostic label, never read.
    The existing destination parent must be private, owned, mode 0700; the
    destination leaf must not exist. All path traversal and writes are nofollow.
    Return the same small receipt written to RECEIPT.json. Never return network
    headers, environment/proxy settings, transport exception text, or paths from
    the caller. All checks remain effective under Python -O.
    """
    deadline = time.monotonic() + DEADLINE_SECONDS
    parent_fd = root_fd = include_fd = None
    try:
        _checked_config(plan, package_pin)
        validator = _load_parser(parser_raw, parser_path)
        parent_fd, leaf = _open_parent(output_dir)
        raw = _download(deadline)
        try:
            selected, _unused_report = validator(raw, package_pin)
        except Exception:
            raise AcquisitionError('package parser rejected') from None
        _remaining(deadline)
        require(type(selected) is dict and set(selected) == {HEADER_SOURCE_PATH}, 'selected header set')
        header = selected[HEADER_SOURCE_PATH]
        require(type(header) is bytes and len(header) == HEADER_BYTES
                and sha(header) == HEADER_SHA256, 'selected header identity')
        receipt = _receipt()
        receipt_raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode('ascii')
        require(len(receipt_raw) <= MAX_RECEIPT_BYTES, 'receipt size')
        # There is no output creation until transport and every byte check pass.
        os.mkdir(leaf, 0o700, dir_fd=parent_fd)
        root_fd = os.open(leaf, DIRECTORY_FLAGS, dir_fd=parent_fd)
        os.mkdir('include', 0o700, dir_fd=root_fd)
        include_fd = os.open('include', DIRECTORY_FLAGS, dir_fd=root_fd)
        for fd in (root_fd, include_fd):
            st = os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                    and stat.S_IMODE(st.st_mode) == 0o700, 'output directory mode')
        _write_at(include_fd, 'FlexLexer.h', header)
        _write_at(root_fd, 'RECEIPT.json', receipt_raw)
        require(sorted(os.listdir(root_fd)) == ['RECEIPT.json', 'include']
                and os.listdir(include_fd) == ['FlexLexer.h'], 'output inventory')
        os.fsync(include_fd)
        os.fsync(root_fd)
        os.fsync(parent_fd)
        _remaining(deadline)
        return receipt
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('acquisition failed') from None
    finally:
        for fd in (include_fd, root_fd, parent_fd):
            if fd is not None:
                os.close(fd)
