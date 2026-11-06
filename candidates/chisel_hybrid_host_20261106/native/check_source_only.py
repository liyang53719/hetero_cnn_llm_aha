"""Check preserved native source bytes and quoted include names, without a build."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

D = Path(__file__).resolve().parent
EXTERNAL = {'Vqwen2_matrix_command_endpoint.h', 'Vtc_clk_gating.h',
            'Vidma_backend_rw_axi_flat_wrap.h', 'VOriginalIdmaAdapterProbe.h', 'verilated.h'}


def need(value, message):
    if not value:
        raise ValueError(message)


def validate(catalog, root=D):
    need(catalog['schema'] == 'TEMP_NATIVE_SOURCE_PRESERVATION_V1', 'source-only schema')
    need(catalog['status'] == 'EXACT_PREVIOUSLY_COMPILED_SOURCE_ONLY_NOT_A_PORTABLE_NATIVE_BUILD', 'source-only scope')
    rows = catalog['files']
    need(len(rows) == len({row['path'] for row in rows}) == 16, 'sixteen unique preserved sources')
    need(set(catalog['external_headers']) == EXTERNAL, 'explicit unresolved generated/runtime headers')
    need(sum(r['bytes'] for r in rows) == 56706, 'exact source byte count')
    need({group: sum(r['group'] == group for r in rows) for group in ('matrix_icg', 'idma')} == {'matrix_icg': 10, 'idma': 6}, 'exact source groups')
    paths = {row['path'] for row in rows}
    actual = {str(p.relative_to(root)) for group in ('matrix_icg', 'idma') for p in (root / group).iterdir()}
    need(actual == paths, 'no missing or extra native source entries')
    used_external = set()
    for row in rows:
        need(set(row) == {'path', 'bytes', 'sha256', 'group', 'quoted_includes'}, 'source row schema')
        rel = PurePosixPath(row['path'])
        need(not rel.is_absolute() and len(rel.parts) == 2 and rel.parts[0] == row['group'] and '..' not in rel.parts and str(rel) == row['path'], 'canonical group-relative source')
        need(rel.suffix in ('.cpp', '.h'), 'handwritten native source extension')
        path = root / rel
        need(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path, 'canonical regular source')
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(stamp(before) == stamp(after) and len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'exact stable source bytes')
        includes = re.findall(r'^\s*#include\s+"([^"\n]+)"', raw.decode('utf-8'), re.M)
        need(includes == row['quoted_includes'], 'complete ordered quoted include names')
        for name in includes:
            need(PurePosixPath(name).name == name and name not in ('.', '..'), 'basename-only quoted include')
            if name in EXTERNAL:
                used_external.add(name)
            else:
                need(str(rel.parent / name) in paths, 'local quoted header preserved')
    need(used_external == EXTERNAL, 'all explicitly missing model/runtime header roles observed')
    return dict(status='TEMP_NATIVE_SOURCE_IDENTITY_CHECK_ONLY', files=16, source_bytes=56706,
                unresolved_external_headers=sorted(EXTERNAL), native_compiled=False, native_executed=False)


if __name__ == '__main__':
    print(json.dumps(validate(json.loads((D / 'SOURCES.json').read_bytes())), sort_keys=True))
