"""Self-contained text-only source proof. No Scala, model, compiler or RTL run."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parent
LOGICAL = {
    'Qwen2Block.scala': 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
    'VectorSilu.scala': 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/VectorSilu.scala',
    'FfnTileSiluBridge.scala': 'candidates/qwen2_resident_matrix/ffn_group/FfnTileSiluBridge.scala',
}
WIDTHS = {
    'Qwen2Block.scala': {
        'canonicalScoreTap': 117, 'canonicalProbTap': 113,
        'canonicalCosTap': 593, 'canonicalSinTap': 593,
        'canonicalPvRequestTap': 81, 'canonicalPvAckTap': 1,
    },
    'VectorSilu.scala': {'canonicalSiluTap': 513, 'canonicalLoanContextTap': 3},
    'FfnTileSiluBridge.scala': {'canonicalTileTap': 590},
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def files(name):
    return ((ROOT / 'baseline' / name).read_bytes(),
            (ROOT / 'candidate' / name).read_bytes(),
            (ROOT / 'patches' / (name + '.patch')).read_bytes())


def parse_patch(name, patch):
    """Parse only the exact single-file unified-diff form retained in this set."""
    lines = patch.splitlines(keepends=True)
    logical = LOGICAL[name].encode()
    require(lines[:2] == [b'--- a/' + logical + b'\n', b'+++ b/' + logical + b'\n'],
            'exact project patch paths')
    i, hunks = 2, []
    while i < len(lines):
        match = re.fullmatch(rb'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n', lines[i])
        require(match is not None, 'exact unified hunk header')
        old_start, old_count, new_start, new_count = match.groups()
        old_start, new_start = int(old_start), int(new_start)
        old_count, new_count = int(old_count or 1), int(new_count or 1)
        require(old_start > 0 and new_start > 0, 'positive source line positions')
        i += 1
        old, new = [], []
        while i < len(lines) and not lines[i].startswith(b'@@ '):
            line = lines[i]
            require(line[:1] in (b' ', b'-', b'+') and line.endswith(b'\n'), 'patch body')
            if line[:1] != b'+':
                old.append(line[1:])
            if line[:1] != b'-':
                new.append(line[1:])
            i += 1
        require(len(old) == old_count and len(new) == new_count, 'hunk line counts')
        hunks.append((old_start - 1, new_start - 1, old, new))
    require(bool(hunks), 'nonempty source patch')
    return hunks


def insertions_only(old, new):
    """Return inserted text and recover old bytes by deleting only insertions."""
    kept, added = [], []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        require(tag in ('equal', 'insert'), 'observation edit must only insert bytes')
        if tag == 'equal':
            require(old[a0:a1] == new[b0:b1], 'equal source span')
            kept.append(new[b0:b1])
        else:
            added.append(new[b0:b1])
    require(b''.join(kept) == old, 'deleting observation text reproduces original')
    return b''.join(added)


def replay(name, source, patch, reverse=False):
    """Apply/reverse the fixed patch with exact context, positions and suffix."""
    source_lines, out, cursor = source.splitlines(keepends=True), [], 0
    for old_pos, new_pos, old, new in parse_patch(name, patch):
        insertions_only(b''.join(old), b''.join(new))
        pos, target_pos, before, after = ((new_pos, old_pos, new, old) if reverse
                                        else (old_pos, new_pos, old, new))
        require(cursor <= pos <= len(source_lines), 'ordered source hunks')
        out.extend(source_lines[cursor:pos])
        require(len(out) == target_pos, 'exact projected line position')
        require(source_lines[pos:pos + len(before)] == before, 'exact pinned hunk context')
        out.extend(after)
        cursor = pos + len(before)
    out.extend(source_lines[cursor:])
    return b''.join(out)


def validate_text(name, baseline, candidate, patch):
    require(replay(name, baseline, patch) == candidate, 'exact forward replay')
    require(replay(name, candidate, patch, reverse=True) == baseline, 'exact backprojection')


class ProjectionCold(unittest.TestCase):
    def test_01_exact_project_file_hashes(self):
        records = json.loads((ROOT / 'PROJECT_SOURCE_HASHES.json').read_text())['files']
        expected = {kind + '/' + n for kind in ('baseline', 'candidate') for n in LOGICAL}
        expected |= {'patches/' + n + '.patch' for n in LOGICAL}
        expected.add('test_projection_cold.py')
        self.assertEqual(set(records), expected)
        for name, row in records.items():
            data = (ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'], name)
            self.assertEqual(len(data), row['bytes'], name)

    def test_02_three_exact_forward_replays(self):
        for name in LOGICAL:
            baseline, candidate, patch = files(name)
            self.assertEqual(replay(name, baseline, patch), candidate, name)

    def test_03_three_exact_deletion_backprojections(self):
        for name in LOGICAL:
            baseline, candidate, patch = files(name)
            self.assertEqual(replay(name, candidate, patch, reverse=True), baseline, name)

    def test_04_no_deleted_or_replaced_baseline_bytes(self):
        for name in LOGICAL:
            for _, _, old, new in parse_patch(name, files(name)[2]):
                self.assertTrue(insertions_only(b''.join(old), b''.join(new)))

    def test_05_modified_original_text_rejected(self):
        for name in LOGICAL:
            baseline, candidate, patch = files(name)
            with self.assertRaises(ValueError):
                validate_text(name, baseline + b'\n', candidate, patch)
            with self.assertRaises(ValueError):
                validate_text(name, baseline, candidate + b'\n', patch)

    def test_06_wrong_observation_event_rejected(self):
        mutations = {
            'Qwen2Block.scala': (b'when(matrixRequest.fire && state===st("attPVCompute"))',
                                 b'when(matrixRequest.valid && state===st("attPVCompute"))'),
            'VectorSilu.scala': (b'canonicalSiluTap.value:=value',
                                  b'canonicalSiluTap.value:=io.result.bits.value'),
            'FfnTileSiluBridge.scala': (b'canonicalTileTap.valid:=io.tiles.response.fire',
                                       b'canonicalTileTap.valid:=io.tiles.response.valid'),
        }
        for name, (old, new) in mutations.items():
            baseline, candidate, patch = files(name)
            self.assertEqual(candidate.count(old), 1)
            with self.assertRaises(ValueError):
                validate_text(name, baseline, candidate.replace(old, new), patch)

    def test_07_patch_header_change_rejected(self):
        for name in LOGICAL:
            patch = files(name)[2]
            with self.assertRaises(ValueError):
                parse_patch(name, patch.replace(b'--- a/', b'--- elsewhere/', 1))

    def test_08_replacement_cannot_be_called_additive(self):
        with self.assertRaises(ValueError):
            insertions_only(b'original', b'origXnal')
        with self.assertRaises(ValueError):
            insertions_only(b'original', b'origin')

    def test_09_declared_nine_bundles_and_2604_bits(self):
        measured = {}
        for name, expected in WIDTHS.items():
            text = files(name)[1].decode()
            for tap, width in expected.items():
                match = re.search(r'val ' + tap + r'\s*=.*?Wire\(new Bundle \{(.*?)\}\)', text, re.S)
                self.assertIsNotNone(match, tap)
                body = match.group(1)
                vectors = re.findall(r'Vec\((\d+),\s*UInt\((\d+)\.W\)\)', body)
                bits = sum(int(count) * int(size) for count, size in vectors)
                body = re.sub(r'Vec\(\d+,\s*UInt\(\d+\.W\)\)', '', body)
                bits += sum(map(int, re.findall(r'UInt\((\d+)\.W\)', body)))
                bits += len(re.findall(r'Bool\(\)', body))
                self.assertEqual(bits, width, tap)
                measured[tap] = bits
        self.assertEqual(len(measured), 9)
        self.assertEqual(sum(measured.values()), 2604)

    def test_10_no_added_state_storage_modules_or_ports_in_source(self):
        patterns = (rb'\bReg\s*\(', rb'\bRegInit\s*\(', rb'\bModule\s*\(',
                    rb'\bSyncReadMem\s*\(', rb'\bMem\s*\(', rb'\bIO\s*\(',
                    rb'\bDecoupled\s*\(', rb'\bstate\s*:=', rb'\bphase\s*:=',
                    rb'\.ready\s*:=', rb'\bmaterialize\s*\(', rb'\bF32\.')
        for name in LOGICAL:
            baseline, candidate, _ = files(name)
            for pattern in patterns:
                self.assertEqual(len(re.findall(pattern, baseline)),
                                 len(re.findall(pattern, candidate)), (name, pattern))

    def test_11_scala_source_provenance_and_no_binary(self):
        for name in LOGICAL:
            for data in files(name):
                data.decode('utf8')
                self.assertNotIn(b'\x00', data)
            self.assertTrue(files(name)[0].startswith(b'// SPDX-License-Identifier: Apache-2.0\n'))
            self.assertTrue(files(name)[1].startswith(b'// SPDX-License-Identifier: Apache-2.0\n'))

    def test_12_incomplete_patch_cannot_reproduce_candidate(self):
        for name in LOGICAL:
            baseline, candidate, patch = files(name)
            with self.assertRaises(ValueError):
                validate_text(name, baseline, candidate, patch[:-1])


if __name__ == '__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
            'run with -I -S -B; optional -O')
    unittest.main(verbosity=2)
