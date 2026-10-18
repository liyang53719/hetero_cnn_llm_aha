"""Fixed Verilator source quarantine and member verification. No build or execution.

CLI defaults to an offline plan. Actual acquisition requires a reviewed outer
supervisor and explicit guard. Archive SHA256 is an observation, not provenance.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import types
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
COMMIT = '4e194cc3ec8e27b18e17f80d7f99c15f984bbdae'
TREE = '3300b1cc13a3903fe3113ae65087ae75b2cdb2df'
API_URL = 'https://api.github.com/repos/verilator/verilator/tarball/' + COMMIT
REDIRECT_URL = 'https://codeload.github.com/verilator/verilator/legacy.tar.gz/' + COMMIT
# This exact literal is a fail-closed candidate, never inferred from response data.
# The plan must separately record its evidence and whether transport is reviewed.
PREFIX = 'verilator-verilator-4e194cc'
ARCHIVE_CAP = 64 * 1024 * 1024
EXPANDED_CAP = 128 * 1024 * 1024
ENTRY_CAP = 12000
MEMBER_CAP = 1024 * 1024
SELECTED_BYTES = 11747893
SELECTED_COUNT = 473
CHUNK = 64 * 1024
PLAN_BYTES = 2983
PLAN_SHA = 'c57d32c37413d3aaf252c674cfd5c51fda338b68a0823a264f220aaf3cdc336f'
BASE_BYTES = 19263
BASE_SHA = '4807fc702edfeb98d7eab9b86e727fe6d0d116ae7230200be7babb5a2c5b9b69'
MEMBERS_BYTES = 75898
MEMBERS_SHA = '4d21da6543c04411c19177752150eca0f1ba0c53dcd0db79aed1bb28d0f5573a'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed_raw(path, size, digest):
    path = Path(path)
    need(path.is_absolute() and str(path) == os.path.normpath(str(path)), 'normalized absolute source path required')
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'source symlink rejected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_size == size, 'fixed source size')
        raw = stream.read(size + 1)
    need(len(raw) == size and sha(raw) == digest, 'fixed source SHA256')
    return raw


def load_inputs():
    raw = fixed_raw(HERE / 'acquire_base.py', BASE_BYTES, BASE_SHA)
    base = types.ModuleType('fixed_original_acquirer')
    base.__file__ = str(HERE / 'acquire_base.py')
    exec(compile(raw, base.__file__, 'exec', dont_inherit=True), base.__dict__)
    plan = json.loads(fixed_raw(HERE / 'SOURCE_PLAN.json', PLAN_BYTES, PLAN_SHA))
    table = json.loads(fixed_raw(HERE / 'FIXED_CORE_MEMBERS.json', MEMBERS_BYTES, MEMBERS_SHA))
    need(table['revision'] == COMMIT and table['tree_sha'] == TREE, 'fixed commit/tree')
    need(table['count'] == SELECTED_COUNT and table['blob_bytes'] == SELECTED_BYTES, 'fixed totals')
    selected = {}
    for member in table['members']:
        path = str(base.relative_path(member['path']))
        need(path not in selected, 'duplicate selected path')
        need(member['mode'] in ('100644', '100755'), 'selected Git mode')
        need(type(member['bytes']) is int and 0 <= member['bytes'] <= MEMBER_CAP, 'selected size')
        need(re.fullmatch('[a-f0-9]{40}', member['git_blob_sha']) is not None, 'selected Git blob')
        selected[path] = member
    need(len(selected) == SELECTED_COUNT and sum(m['bytes'] for m in selected.values()) == SELECTED_BYTES,
         'selected member totals')
    for name in selected:
        need(not any('/'.join(name.split('/')[:n]) in selected for n in range(1, len(name.split('/')))),
             'selected file/directory collision')
    need(plan['commit'] == COMMIT and plan['tree'] == TREE and plan['archive_api_url'] == API_URL
         and plan['allowed_redirect_url'] == REDIRECT_URL and plan['exact_prefix'] == PREFIX, 'fixed transport plan')
    return base, plan, selected


def shared_budget(base, start, deadline, clock=time.monotonic):
    now = clock()
    need(all(type(x) in (int, float) and math.isfinite(x) for x in (start, deadline)), 'finite shared times')
    need(0 <= start <= now and now - start <= 410, 'shared start not current')
    need(now < deadline <= start + 410, 'deadline outside shared work window')
    budget = base.Budget({'total_transfer_bytes': ARCHIVE_CAP, 'elapsed_check_seconds': 400}, clock=clock)
    budget.deadline = min(deadline, now + 400)
    return budget


class FixedRedirect(urllib.request.HTTPRedirectHandler):
    """Return 302 unconsumed. Never invoke urllib's unbounded redirect drain."""
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('automatic redirect forbidden')

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def default_opener():
    # Retains default platform certificate verification and inherited proxy policy.
    # No credentials, tokens, proxy edits, direct fallback, retry or alternate URL.
    return urllib.request.build_opener(FixedRedirect())


def open_response(opener, budget, cleanup_errors):
    request = urllib.request.Request(API_URL, headers={'Accept-Encoding': 'identity'})
    timeout = lambda: min(30, max(0.001, budget.deadline - budget.clock()))
    def open_once(request):
        try:
            return opener.open(request, timeout=timeout())
        except urllib.error.HTTPError as error:
            cleanup_close(error, 'HTTP_error_response', cleanup_errors)
            raise
    budget.check()
    response = open_once(request)
    if response.status != 302:
        return response, API_URL
    try:
        need(response.geturl() == API_URL, 'redirect response URL changed')
        need(response.headers.get_all('Location', []) == [REDIRECT_URL],
             'redirect outside single fixed official route')
    except BaseException:
        cleanup_close(response, 'redirect_response', cleanup_errors)
        raise
    # No redirect body is read, so it cannot cause hidden unbounded transfer.
    cleanup_close(response, 'redirect_response', cleanup_errors)
    need(not cleanup_errors, 'redirect close failure')
    budget.check()
    request = urllib.request.Request(REDIRECT_URL, headers={'Accept-Encoding': 'identity'})
    return open_once(request), REDIRECT_URL


def check_response(response, expected_url=API_URL):
    need(response.status == 200 and response.geturl() == expected_url, 'unexpected final response')
    need(response.headers.get_all('Content-Encoding', []) in ([], ['identity']), 'encoded HTTP body rejected')
    lengths = response.headers.get_all('Content-Length', [])
    need(len(lengths) <= 1, 'ambiguous Content-Length')
    if lengths:
        need(re.fullmatch('[0-9]+', lengths[0]) is not None, 'invalid Content-Length')
        declared = int(lengths[0])
        need(0 < declared < ARCHIVE_CAP, 'Content-Length reaches archive cap')
        return declared
    return None


def transfer(stream, sink, budget, observation):
    """Derived from fixed acquire.copy_verified; unknown digest stays observational.

    Count received bytes before the deadline check. Rejected chunks are not
    written. The partial quarantine file is preserved on every failure.
    """
    digest = hashlib.sha256()
    read = getattr(stream, 'read1', stream.read)
    while True:
        allowance = budget.allowance(ARCHIVE_CAP - observation['received_bytes'])
        chunk = read(allowance)
        need(isinstance(chunk, bytes), 'stream returned nonbytes')
        observation['received_bytes'] += len(chunk)
        budget.bytes += len(chunk)
        need(len(chunk) <= allowance, 'stream violated bounded read')
        budget.check()
        if not chunk:
            break
        need(sink.write(chunk) == len(chunk), 'short quarantine write')
        digest.update(chunk)
        observation['retained_archive_bytes'] += len(chunk)
        observation['retained_archive_sha256'] = digest.hexdigest()
    need(observation['received_bytes'] > 0, 'empty source archive')
    observation['archive_complete'] = True
    observation['archive_sha256_observed'] = digest.hexdigest()


class ExpandedReader:
    """Count every decompressed byte, including rejected data, padding and suffix."""
    def __init__(self, stream, budget, observation):
        self.stream, self.budget, self.observation = stream, budget, observation

    def read(self, amount):
        need(0 < amount <= CHUNK, 'bounded expanded read required')
        self.budget.check()
        remaining = EXPANDED_CAP - self.observation['expanded_bytes']
        need(remaining > 0, 'expanded byte cap reached before EOF')
        amount = min(amount, remaining)
        data = self.stream.read(amount)
        need(isinstance(data, bytes), 'expanded stream returned nonbytes')
        self.observation['expanded_bytes'] += len(data)
        need(len(data) <= amount, 'expanded stream violated bounded read')
        self.budget.check()
        return data

    def exact(self, amount):
        data = bytearray()
        while len(data) < amount:
            chunk = self.read(min(CHUNK, amount - len(data)))
            need(chunk, 'truncated tar')
            data.extend(chunk)
        return bytes(data)

    def body(self, size, retain=False):
        chunks = []
        left = size
        while left:
            chunk = self.exact(min(CHUNK, left))
            if retain:
                chunks.append(chunk)
            left -= len(chunk)
        padding = (-size) % 512
        if padding:
            need(self.exact(padding) == b'\0' * padding, 'nonzero tar member padding')
        return b''.join(chunks) if retain else None


def text_field(raw):
    first, sep, rest = raw.partition(b'\0')
    need(not sep or not rest.strip(b'\0'), 'data after tar field terminator')
    return first.decode('utf-8', 'strict')


def octal_field(raw):
    need(not raw[0] & 128, 'base256 tar field rejected')
    value = raw.rstrip(b'\0 ').lstrip(b' ')
    need(not value or re.fullmatch(b'[0-7]+', value) is not None, 'invalid tar octal')
    return int(value or b'0', 8)


def safe_name(name, base, directory=False):
    need(not any(ord(c) < 32 or ord(c) == 127 for c in name), 'control character in tar path')
    if directory and name.endswith('/'):
        name = name[:-1]
    base.relative_path(name)
    return name


def parse_pax(data):
    result = {}
    while data:
        space = data.find(b' ')
        need(0 < space < 12 and re.fullmatch(b'[1-9][0-9]*', data[:space]) is not None, 'invalid pax length')
        size = int(data[:space])
        need(space + 3 <= size <= len(data) and data[size - 1:size] == b'\n', 'invalid pax record')
        key, equals, value = data[space + 1:size - 1].partition(b'=')
        need(equals and key and key not in result, 'invalid or duplicate pax key')
        need(key in (b'path', b'comment', b'mtime', b'atime', b'ctime'), 'unsupported pax key')
        result[key] = value.decode('utf-8', 'strict')
        data = data[size:]
    return result


def write_member(root, name, raw, base):
    target = root.joinpath(*base.relative_path(name).parts)
    base.no_symlink_path(target)
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    base.no_symlink_path(target)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as sink:
        need(sink.write(raw) == len(raw), 'short selected write')
        sink.flush()
        os.fsync(sink.fileno())
    need(stat.S_IMODE(target.stat().st_mode) == 0o600, 'selected file must be mode0600')


def scan_tar(stream, selected, root, base, budget, observation, prefix=PREFIX):
    reader = ExpandedReader(stream, budget, observation)
    seen, kinds, verified = set(), {}, set()
    local_pax = None
    global_seen = False
    ended = False
    while True:
        header = reader.exact(512)
        if header == b'\0' * 512:
            need(reader.exact(512) == b'\0' * 512, 'tar needs two end blocks')
            need(local_pax is None, 'orphan local pax header')
            ended = True
            break
        observation['tar_entries'] += 1
        need(observation['tar_entries'] <= ENTRY_CAP, 'tar entry cap')
        expected = octal_field(header[148:156])
        need(sum(header[:148]) + 256 + sum(header[156:]) == expected, 'tar header checksum')
        need(header[257:265] == b'ustar\x0000', 'unsupported tar format')
        mode, size = octal_field(header[100:108]), octal_field(header[124:136])
        need(size < EXPANDED_CAP and mode <= 0o777, 'tar size/mode limit')
        name = text_field(header[:100])
        path_prefix = text_field(header[345:500])
        if path_prefix:
            name = path_prefix + '/' + name
        kind = header[156:157]
        need(kind in (b'0', b'\0', b'5', b'2', b'x', b'g'), 'unsupported tar type/link/device')
        name = safe_name(name, base, directory=kind == b'5')
        if kind in (b'x', b'g'):
            need(size <= CHUNK, 'pax payload cap')
            need(local_pax is None, 'nested local pax header')
            if kind == b'g':
                need(not global_seen and not seen and name == 'pax_global_header', 'unexpected global pax')
                global_seen = True
            else:
                need(name.startswith(prefix + '/'), 'local pax path outside fixed root')
            fields = parse_pax(reader.body(size, retain=True))
            if kind == b'g':
                need(set(fields) <= {b'comment', b'mtime', b'atime', b'ctime'}, 'global pax path rejected')
                need(fields.get(b'comment') == COMMIT, 'global pax commit mismatch')
            else:
                need(b'comment' not in fields, 'local pax comment rejected')
                local_pax = fields
            continue
        need(name == prefix or name.startswith(prefix + '/'), 'raw member outside unique fixed root')
        if local_pax is not None:
            name = safe_name(local_pax.get(b'path', name), base, directory=kind == b'5')
            local_pax = None
        need(name == prefix or name.startswith(prefix + '/'), 'member outside unique fixed root')
        need(name not in seen, 'duplicate tar path')
        seen.add(name)
        is_dir = kind == b'5'
        need(name != prefix or is_dir, 'root is not directory')
        components = name.split('/')
        for n in range(1, len(components)):
            parent = '/'.join(components[:n])
            need(kinds.get(parent) in (None, 'dir'), 'tar file/directory collision')
            kinds[parent] = 'dir'
        need(kinds.get(name) in (None, 'dir') if is_dir else kinds.get(name) is None,
             'tar file/directory collision')
        kinds[name] = 'dir' if is_dir else 'file'
        relative = name[len(prefix) + 1:] if name != prefix else ''
        wanted = selected.get(relative)
        if is_dir:
            need(size == 0 and wanted is None, 'nonempty or selected tar directory')
            continue
        if kind == b'2':
            need(size == 0 and wanted is None, 'selected or nonempty symlink rejected')
            link = safe_name(text_field(header[157:257]), base)
            # Conservative no-parent-link policy; unselected links never materialize.
            need(link and not link.startswith('/'), 'unsafe unselected symlink')
            observation['unselected_symlinks_skipped'] += 1
            continue
        need(text_field(header[157:257]) == '', 'regular entry has link target')
        if wanted is None:
            reader.body(size)
            continue
        need(size == wanted['bytes'] and size <= MEMBER_CAP, 'selected size mismatch')
        allowed_modes = (0o644, 0o664) if wanted['mode'] == '100644' else (0o755, 0o775)
        need(mode in allowed_modes, 'selected Git executable mode mismatch')
        data = reader.body(size, retain=True)
        git_sha = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
        need(git_sha == wanted['git_blob_sha'], 'selected Git blob mismatch')
        need(observation['selected_bytes'] + len(data) <= SELECTED_BYTES, 'selected total cap')
        write_member(root, relative, data, base)
        verified.add(relative)
        observation['selected_bytes'] += len(data)
        observation['verified_members'].append({'path': relative, 'bytes': len(data), 'git_blob_sha1': git_sha,
                                               'sha256_observed': sha(data), 'original_git_mode': wanted['mode'],
                                               'materialized_mode': '0600'})
    need(ended and prefix in seen, 'missing tar root or terminator')
    while True:
        suffix = reader.read(CHUNK)
        if not suffix:
            break
        need(not suffix.strip(b'\0'), 'nonzero data after tar terminator')
    need(verified == set(selected), 'missing selected members')
    need(observation['selected_bytes'] == sum(m['bytes'] for m in selected.values()), 'selected bytes mismatch')


def cleanup_close(stream, label, errors):
    if stream is not None:
        try:
            stream.close()
        except BaseException as error:
            errors.append({'resource': label, 'error_type': type(error).__name__})


def execute(base, plan, selected, root, budget, opener=None):
    """Synthetic callers may inject a mock opener; CLI only uses fixed inputs."""
    need(plan['transport_reviewed'] is True, 'transport/prefix evidence remains HOLD')
    root.mkdir(mode=0o700)
    source = root / 'verilator'
    source.mkdir(mode=0o700)
    observation = {'received_bytes': 0, 'retained_archive_bytes': 0, 'archive_complete': False,
                   'expanded_bytes': 0, 'tar_entries': 0, 'selected_bytes': 0,
                   'verified_members': [], 'unselected_symlinks_skipped': 0}
    errors = []
    response = sink = raw = expanded = None
    primary = None
    try:
        budget.check()
        response, expected_url = open_response(opener if opener is not None else default_opener(), budget, errors)
        declared = check_response(response, expected_url)
        fd = os.open(root / 'source.tar.gz.part', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        sink = os.fdopen(fd, 'wb', buffering=0)
        transfer(response, sink, budget, observation)
        sink.flush()
        os.fsync(sink.fileno())
        need(declared in (None, observation['received_bytes']), 'body differs from Content-Length')
        cleanup_close(sink, 'archive_sink', errors)
        sink = None
        cleanup_close(response, 'HTTP_response', errors)
        response = None
        need(not errors, 'pre-scan close failure')
        os.link(root / 'source.tar.gz.part', root / 'source.tar.gz')
        # Never delete retained archive bytes, even on a later parse/hash failure.
        try:
            (root / 'source.tar.gz.part').unlink()
        except BaseException as error:
            errors.append({'resource': 'archive_partial_link', 'error_type': type(error).__name__})
        raw = base.open_regular(root / 'source.tar.gz')
        need(os.fstat(raw.fileno()).st_size == observation['received_bytes'], 'archive changed size')
        # Rehash the same open file before scanning; seek does not substitute a new path.
        digest = hashlib.sha256()
        while True:
            budget.check()
            block = raw.read(CHUNK)
            if not block:
                break
            digest.update(block)
        need(digest.hexdigest() == observation['archive_sha256_observed'], 'archive changed after transfer')
        raw.seek(0)
        expanded = gzip.GzipFile(fileobj=raw, mode='rb')
        scan_tar(expanded, selected, source, base, budget, observation)
        budget.check()
    except BaseException as error:
        primary = error
    finally:
        cleanup_close(expanded, 'gzip_reader', errors)
        cleanup_close(raw, 'archive_reader', errors)
        cleanup_close(sink, 'archive_sink', errors)
        cleanup_close(response, 'HTTP_response', errors)
    if primary is None and errors:
        primary = ValueError('cleanup failed; retained bytes need review')
    result = {'schema': 'fixed-official-source-acquisition-v1', 'commit': COMMIT, 'tree': TREE,
              'fixed_members_sha256': MEMBERS_SHA, 'fixed_plan_sha256': PLAN_SHA,
              'archive_sha256_is_independent_provenance': False,
              'selected_identity_basis': 'pre-fixed Git tree path, mode, size and Git blob SHA1',
              'transport': 'default-platform-HTTPS-one-exact-official-302-no-retry',
              'archive_api_url': API_URL, 'exact_archive_prefix': PREFIX,
              'installed': False, 'source_executed': False, 'native_executed': False,
              'host_compilation_or_rtl_evidence': False, 'terminal_success': False,
              'cleanup_errors': errors, **observation}
    if primary is None:
        result['status'] = 'SELECTED_SOURCE_PREPARED_PENDING_OUTER_EXIT0_AND_REVIEW'
        destination = root / 'SOURCE.json'
    else:
        result['status'] = 'INCOMPLETE_NO_SOURCE_SUCCESS'
        result['error_type'] = type(primary).__name__
        result['failure_reason'] = str(primary) if isinstance(primary, (ValueError, base.AcquisitionError)) else type(primary).__name__
        result['partial_archive_preserved'] = True
        destination = root / 'FAILED.json'
    try:
        warning = base.write_json(destination, result)
        if warning is not None:
            result['receipt_postcommit_cleanup_warning'] = warning
    except BaseException as receipt_error:
        if primary is not None:
            primary.add_note('failure receipt publication error: ' + type(receipt_error).__name__)
            raise primary
        raise
    if primary is not None:
        raise primary
    return result


def checked_output_root(base, output, repository):
    # The original acquirer's SOURCE_CANDIDATE is location-relative. Do not use
    # that boundary after copying it: retain explicit checkout and current
    # candidate/source exclusions instead of accidentally excluding all workspace.
    root = base.no_symlink_path(output)
    checkout = base.no_symlink_path(repository).resolve()
    need(checkout.is_dir() and (checkout / '.git').exists(), 'explicit checkout root required')
    resolved = root.resolve()
    for protected in (checkout, HERE):
        need(resolved != protected and protected not in resolved.parents, 'output inside protected source')
    need(root.parent.is_dir() and not root.exists(), 'fresh output with existing parent required')
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--shared-start-monotonic', type=float)
    parser.add_argument('--work-deadline-monotonic', type=float)
    parser.add_argument('--execute-reviewed-acquisition', action='store_true')
    args = parser.parse_args(argv)
    base, plan, selected = load_inputs()
    if not args.execute_reviewed_acquisition:
        print(json.dumps({'status': 'SOURCE_PLAN_ONLY_NO_NETWORK_NO_BUILD', 'plan': plan}, sort_keys=True))
        return 0
    need(args.repository is not None and args.output_root is not None, 'explicit repository/output required')
    need(args.shared_start_monotonic is not None and args.work_deadline_monotonic is not None, 'outer absolute budget required')
    root = checked_output_root(base, args.output_root, args.repository)
    budget = shared_budget(base, args.shared_start_monotonic, args.work_deadline_monotonic)
    result = execute(base, plan, selected, root, budget)
    print(json.dumps({k: v for k, v in result.items() if k != 'verified_members'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use Python -I -S -B')
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print('Source acquisition stopped: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
