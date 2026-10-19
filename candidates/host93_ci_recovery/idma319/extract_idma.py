"""Data-only iDMA ZIP subset extraction. Downloading and native execution are absent."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Python -I -S -B is required before local code loading.')
if __name__ == '__main__':
    raise SystemExit('Use the pinned same-buffer entry from ENTRY.json.')
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import shlex
import signal
import stat
import time
import zipfile

ARCHIVE_SIZE = 9926876
ARCHIVE_SHA = 'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'
PREFIX = 'idma_export/'
META = {
    'SHA256SUMS.json': (104165, 'a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19'),
    'SOURCE_CLOSURE.json': (73326, 'a3161f06be82894bbab48e3efae325e868385ea204d5f2aab47978ce9bd10aa1'),
}
PUBLISHED = {
    'COMMITS.json': '41b092ed490aca4bedfd4602fc93e7f6890d25aa918df4fa0e0721fe1f0c7d6e',
    'SOURCE_EXPORT_POLICY.json': 'f36cf6ed5868f9d50dd3a74253415cc6d99d22e2db2f240c32c61c0fa593ab95',
    'idma/Bender.lock': '9e6c33f898dad20fd1b29cf8b07647b7d55fe8b42c36bd5cd72586fc2606557e',
    'deps/tech_cells_generic/src/rtl/tc_clk.sv': '93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207',
}
EXTRAS = ('SHA256SUMS.json', 'SOURCE_CLOSURE.json', 'COMMITS.json',
          'SOURCE_EXPORT_POLICY.json', 'idma.f.in', 'idma/Bender.lock')
CLOCK = 'deps/tech_cells_generic/src/rtl/tc_clk.sv'
FIFO_PATH = 'deps/common_cells/src/cc_passthrough_stream_fifo.sv'
FIFO_BASE = (4411, '68de1c713e40d97950591111dccd37a7546025f7fe6750fa3092826422557352')
FIFO_DERIVED = (4536, 'd5482112dccd8a60bb142982fded05b64658b097b4227bf21a514f2da5d34e70')
DEFINES = {name: '' for name in ('TARGET_ASIC', 'TARGET_RTL', 'TARGET_SYNTHESIS', 'TARGET_VERILATOR')}
LIMITS = {'total_seconds': 60, 'work_seconds': 55, 'cpu_seconds': 40,
          'cpu_affinity_count': 1, 'as_bytes': 512 * 1024**2,
          'fsize_bytes': 4 * 1024**2, 'tree_bytes': 8 * 1024**2,
          'report_bytes': 512 * 1024}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def path_parts(name):
    need(type(name) is str and 0 < len(name) <= 1024 and
         not any(c in name for c in ('\\', '\x00', ':')) and not name.startswith('/'), 'unsafe path')
    parts = name.split('/')
    need(len(parts) <= 32 and all(p not in ('', '.', '..') and len(p) <= 255 for p in parts),
         'unsafe path component')
    return parts


def digest_ok(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def unique_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def identity(s):
    return {k: getattr(s, 'st_' + k) for k in ('dev', 'ino', 'mode', 'size', 'mtime_ns', 'ctime_ns')}


def parent_fd(path):
    text = os.fspath(path)
    need(text.startswith('/') and text != '/', 'absolute path required')
    parts = path_parts(text[1:])
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def checked_read(path, size, digest):
    need(type(size) is int and 0 <= size <= ARCHIVE_SIZE and digest_ok(digest), 'read identity bounds')
    parent, name = parent_fd(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = identity(os.fstat(fd))
            need(stat.S_ISREG(before['mode']) and before['size'] == size, 'read type/size mismatch')
            chunks, count = [], 0
            while count <= size:
                chunk = os.read(fd, min(65536, size + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
            raw = b''.join(chunks)
            after = identity(os.fstat(fd))
            current = identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
            need(len(raw) == size and sha(raw) == digest and before == after == current,
                 'read raw identity mismatch')
            return raw, {'bytes': size, 'sha256': digest, 'stat': before}
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def index_zip(z, count):
    infos = z.infolist()
    need(type(count) is int and 0 < count <= 929 and len(infos) == count, 'ZIP entry count')
    indexed = {}
    for info in infos:
        path_parts(info.filename)
        need(info.orig_filename == info.filename and info.filename not in indexed, 'ZIP duplicate/truncated name')
        need(not info.is_dir() and stat.S_ISREG(info.external_attr >> 16) and
             not (info.external_attr & 0x10), 'ZIP nonregular type')
        need(not (info.flag_bits & (1 | 0x40 | 0x2000)), 'ZIP encryption')
        need(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'ZIP compression')
        need(0 <= info.file_size <= 64 * 1024**2 and 0 <= info.compress_size <= ARCHIVE_SIZE,
             'ZIP metadata size bound')
        indexed[info.filename] = info
    return indexed


def member(z, indexed, name, size, digest):
    path_parts(name)
    need(type(size) is int and 0 <= size <= 907909 and digest_ok(digest), 'selected identity bound')
    need(name in indexed and indexed[name].file_size == size, 'selected metadata size mismatch')
    with z.open(indexed[name], 'r') as stream:
        raw = stream.read(size + 1)
        need(stream.read(1) == b'', 'selected stream exceeded bound')
    need(len(raw) == size and sha(raw) == digest, 'selected size/SHA mismatch')
    return raw


def filelist(raw):
    sources, includes, defines = [], [], {}
    for line in raw.decode('utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        for word in shlex.split(line):
            if word.startswith('+define+'):
                for definition in word[8:].split('+'):
                    name, unused, value = definition.partition('=')
                    need(name in DEFINES and value == '' and (name not in defines or defines[name] == value),
                         'unexpected filelist define')
                    defines[name] = value
                continue
            is_include = word.startswith('+incdir+')
            for name in (word[8:].split('+') if is_include else [word]):
                need(name.startswith('@ROOT@/'), 'unexpected filelist token')
                relative = name[7:]
                path_parts(relative)
                (includes if is_include else sources).append(relative)
    return sources, list(dict.fromkeys(includes)), defines


def derive_selection(manifest, closure, raw_filelist):
    """The new selection contract is data-derived from two separately pinned records."""
    need(type(manifest) is dict and len(manifest) == 927, '927-entry manifest required')
    for name, digest in manifest.items():
        path_parts(name)
        need(digest_ok(digest) and name != 'SHA256SUMS.json', 'manifest identity format')
    need(closure['schema'] == 2 and closure['source_files'] == 294 and closure['include_directories'] == 8,
         'closure schema/counts')
    admitted = closure['admitted_input_hashes']
    need(type(admitted) is dict and len(admitted) == 312, '312 admitted inputs required')
    for name, digest in admitted.items():
        path_parts(name)
        need(digest_ok(digest) and manifest.get(name) == digest, 'closure/manifest disagreement')
    sources, includes, defines = filelist(raw_filelist)
    need(len(sources) == len(set(sources)) == 294 and len(includes) == 8 and defines == DEFINES and
         closure['initial_filelist_defines'] == DEFINES, 'original filelist counts/defines')
    need(set(sources) <= set(admitted), 'filelist source absent from admitted inputs')
    headers = set(admitted) - set(sources)
    need(len(headers) == 18 and all(p.endswith(('.svh', '.vh')) for p in headers), '18 admitted headers')
    need(CLOCK not in admitted and not (set(EXTRAS) & set(admitted)), 'extra member collision')
    selected = sorted(set(admitted) | {CLOCK} | set(EXTRAS))
    need(len(selected) == 319, '319 selected names required')
    for name in selected:
        path_parts(name)
        parts = name.split('/')
        need(not any('/'.join(parts[:i]) in selected for i in range(1, len(parts))), 'file/parent collision')
    return selected, {'ordered_sources': sources, 'include_directories': includes,
                      'defines': defines, 'headers': sorted(headers)}


def prepare(raw):
    need(len(raw) == ARCHIVE_SIZE and sha(raw) == ARCHIVE_SHA, 'fixed archive bytes before ZIP parse')
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as z:
        indexed = index_zip(z, 929)
        need(sum(i.file_size for i in indexed.values()) == 33777372, 'whole ZIP uncompressed metadata total')
        metadata = {name: member(z, indexed, PREFIX + name, size, digest)
                    for name, (size, digest) in META.items()}
        manifest = unique_json(metadata['SHA256SUMS.json'])
        closure = unique_json(metadata['SOURCE_CLOSURE.json'])
        need(type(manifest) is dict and len(manifest) == 927, 'manifest shape')
        expected = {PREFIX + name for name in manifest} | {PREFIX + 'SHA256SUMS.json', 'SAFE_IDENTITY.json'}
        need(set(indexed) == expected and indexed['SAFE_IDENTITY.json'].file_size == 32889,
             'exact original ZIP member set')
        for name, digest in PUBLISHED.items():
            need(manifest.get(name) == digest, 'published metadata/source pin')
        need(manifest.get('SOURCE_CLOSURE.json') == META['SOURCE_CLOSURE.json'][1], 'closure manifest pin')
        f = PREFIX + 'idma.f.in'
        raw_filelist = member(z, indexed, f, indexed[f].file_size, manifest['idma.f.in'])
        selected, description = derive_selection(manifest, closure, raw_filelist)
        verified = []
        for name in selected:
            size = indexed[PREFIX + name].file_size
            digest = META['SHA256SUMS.json'][1] if name == 'SHA256SUMS.json' else manifest[name]
            content = member(z, indexed, PREFIX + name, size, digest)
            verified.append(({'zip_member': PREFIX + name, 'relative_destination': name,
                              'bytes': size, 'sha256': digest}, content))
        need(sum(e['bytes'] for e, b in verified) == 3072200 and
             max(e['bytes'] for e, b in verified) == 907909, 'selected exact size totals')
        return verified, description



def derive_fifo_valid_split(verified):
    """One fixed base-to-derived FIFO buffer after all original 319 pass prepare."""
    need(len(verified) == 319, 'FIFO split requires original 319 selection')
    names = [item['relative_destination'] for item, content in verified]
    need(len(set(names)) == 319 and names.count(FIFO_PATH) == 1,
         'FIFO split missing, extra or duplicate target/selection')
    need(sum(item['bytes'] for item, content in verified) == 3072200,
         'FIFO split original selected byte total')
    for item, content in verified:
        need(item['zip_member'] == PREFIX + item['relative_destination'] and
             len(content) == item['bytes'] and sha(content) == item['sha256'],
             'FIFO split original buffer identity')
    position = names.index(FIFO_PATH)
    item, original = verified[position]
    need((item['bytes'], item['sha256']) == FIFO_BASE and
         (len(original), sha(original)) == FIFO_BASE, 'FIFO split exact base identity')
    zero = b"            valid_o     = 1'b0;\n"
    compare = (b"            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]\n"
               b"                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1'b1;\n")
    anchor = b'    // Logic\n'
    need(original.count(zero) == original.count(compare) == original.count(anchor) == 1,
         'FIFO split exact unique transformation anchors')
    split = (b'    // Output validity\n    always_comb begin\n'
             b'        if (flush_i) begin // Flush\n' + zero +
             b'        end else begin\n' + compare + b'        end\n    end\n\n')
    derived = original.replace(zero, b'', 1).replace(compare, b'', 1).replace(anchor, split + anchor, 1)
    need((len(derived), sha(derived)) == FIFO_DERIVED, 'FIFO split exact derived identity')
    result = list(verified)
    result[position] = (dict(item, bytes=FIFO_DERIVED[0], sha256=FIFO_DERIVED[1]), derived)
    need([row['relative_destination'] for row, content in result] == names and
         sum(row['bytes'] for row, content in result) == 3072325, 'FIFO split exact output delta')
    return result, {'relative_destination': FIFO_PATH,
                    'original': {'bytes': FIFO_BASE[0], 'sha256': FIFO_BASE[1]},
                    'derived': {'bytes': FIFO_DERIVED[0], 'sha256': FIFO_DERIVED[1]},
                    'operation': 'exact_valid_o_combinational_block_split',
                    'original_manifest_unchanged': True, 'selected_file_count_delta': 0,
                    'selected_bytes_delta': 125}


def fresh(path):
    parent, name = parent_fd(path)
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        need(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, 'fresh root mode')
        return fd
    finally:
        os.close(parent)


def write(root, name, raw):
    need(len(raw) <= LIMITS['fsize_bytes'], 'output per-file bound')
    parts = path_parts(name)
    fd = os.dup(root)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            need(stat.S_IMODE(os.fstat(nxt).st_mode) == 0o700, 'output directory mode')
            os.close(fd)
            fd = nxt
        out = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            need(stat.S_IMODE(os.fstat(out).st_mode) == 0o600, 'output file mode')
            offset = 0
            while offset < len(raw):
                count = os.write(out, raw[offset:])
                need(count > 0, 'output write stalled')
                offset += count
        finally:
            os.close(out)
    finally:
        os.close(fd)


def tree(root):
    rows, total, count = [], 0, 0
    def visit(fd, prefix):
        nonlocal total, count
        for name in sorted(os.listdir(fd)):
            path_parts(name)
            count += 1
            need(count <= 1024, 'output entry bound')
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(s.st_mode):
                need(stat.S_IMODE(s.st_mode) == 0o700, 'inventory directory mode')
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    visit(child, prefix + name + '/')
                finally:
                    os.close(child)
            else:
                need(stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600, 'inventory file type/mode')
                total += s.st_size
                need(s.st_size <= LIMITS['fsize_bytes'] and total <= LIMITS['tree_bytes'], 'output tree bound')
                rows.append(prefix + name)
    visit(root, '')
    return sorted(rows), total


def expire(signum, frame):
    raise TimeoutError('iDMA extraction deadline')


def arm(deadline):
    left = deadline - time.monotonic()
    need(left > 0, 'total extraction deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL, left)


def limits(entry):
    for key, value in ((resource.RLIMIT_CPU, 40), (resource.RLIMIT_AS, 512 * 1024**2),
                       (resource.RLIMIT_FSIZE, 4 * 1024**2)):
        hard = resource.getrlimit(key)[1]
        need(hard == resource.RLIM_INFINITY or hard >= value, 'cannot raise resource limit')
        resource.setrlimit(key, (value, value))
    allowed = os.sched_getaffinity(0)
    need(bool(allowed), 'CPU affinity missing')
    os.sched_setaffinity(0, {min(allowed)})
    need(len(os.sched_getaffinity(0)) == 1, 'one CPU required')
    arm(entry + 55)


def extract(archive, out, entry, fifo_valid_split=False):
    need(type(fifo_valid_split) is bool, 'FIFO split option must be boolean')
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'fresh unblocked timer required')
    need(globals().get('__verified_source_pin__') is not None, 'verified source entry required')
    old_handler = signal.signal(signal.SIGALRM, expire)
    old_umask = os.umask(0o077)
    root, before, failed = None, None, None
    report = {'status': 'FAILED', 'complete': False, 'native_executed': False, 'network_used': False,
              'source_pin': globals()['__verified_source_pin__'], 'limits': dict(LIMITS),
              'subset_inventory': [], 'safe_identity_extracted': False,
              'manifest_scope': '927-entry original manifest is provenance, not a full extraction claim.',
              'new_contract': 'Pinned archive and embedded manifest/closure; no inherited selected-plan approval.',
              'independent_acceptance': 'PENDING'}
    try:
        limits(entry)
        root = fresh(out)
        raw, before = checked_read(archive, ARCHIVE_SIZE, ARCHIVE_SHA)
        report['archive_before'] = before
        verified, description = prepare(raw)
        report['selection_basis'] = description
        if fifo_valid_split:
            verified, derivation = derive_fifo_valid_split(verified)
            report['source_derivations'] = [derivation]
        expected_bytes = 3072325 if fifo_valid_split else 3072200
        for item, content in verified:
            need(len(content) == item['bytes'] and sha(content) == item['sha256'], 'buffer identity before write')
            relative = 'sources/' + item['relative_destination']
            write(root, relative, content)
            unused, observed = checked_read(Path(out) / relative, item['bytes'], item['sha256'])
            report['subset_inventory'].append(dict(item, mode='0600'))
        names, size = tree(root)
        need(names == sorted('sources/' + item['relative_destination'] for item, raw in verified) and
             len(names) == 319 and size == expected_bytes, 'exact extracted tree')
        unused, after = checked_read(archive, ARCHIVE_SIZE, ARCHIVE_SHA)
        report['archive_after'] = after
        need(before == after, 'archive changed')
        report.update(status='EXTRACTED_319_PENDING_REVIEW', complete=True,
                      archive_unchanged=True, selected_files=319, selected_bytes=size)
    except Exception as error:
        failed = error
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:2048]}
        arm(entry + 60)
        if before is not None:
            try:
                unused, after = checked_read(archive, ARCHIVE_SIZE, ARCHIVE_SHA)
                report['archive_after'] = after
                report['archive_unchanged'] = before == after
            except Exception as post_error:
                report['archive_unchanged'] = False
                report['archive_postcheck_error'] = str(post_error)[:2048]
    finally:
        try:
            if root is not None:
                arm(entry + 60)
                report['entry_to_report_seconds'] = time.monotonic() - entry
                raw_report = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
                need(len(raw_report) <= LIMITS['report_bytes'], 'report size limit')
                write(root, 'EXTRACTION_REPORT.json', raw_report)
                names, size = tree(root)
                need(size <= LIMITS['tree_bytes'] and time.monotonic() < entry + 60, 'final total bound')
        finally:
            if root is not None:
                os.close(root)
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
            os.umask(old_umask)
    if failed is not None:
        raise failed
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive')
    parser.add_argument('--out')
    parser.add_argument('--fifo-valid-split', action='store_true')
    args = parser.parse_args()
    if args.archive is None and args.out is None:
        print(json.dumps({'status': 'SOURCE_ONLY_NO_ARCHIVE_READ_NO_EXTRACTION'}))
        return
    need(args.archive is not None and args.out is not None, '--archive and --out are both required')
    result = extract(args.archive, args.out, globals()['__entry_monotonic__'], args.fifo_valid_split)
    print(json.dumps({key: result[key] for key in ('status', 'selected_files', 'selected_bytes',
                                                  'archive_unchanged', 'native_executed')}, sort_keys=True))
