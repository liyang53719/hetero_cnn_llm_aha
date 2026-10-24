#!/usr/bin/env python3
"""Small synthetic-only tests. No production main, Git, native code or DUT."""
import ast
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_fixed_git as P

ORIGINAL_PROFILE = (Path(__file__).parent / 'fixture_original_git_profile.txt').read_bytes()


def fixture():
    root, git, output = '/synthetic/old_profile', '/synthetic/old_git', '/synthetic/new'
    head = 'a' * 40
    blobs = {'HEAD': (head + '\n').encode(), 'config': b'[core]\n bare=false\n',
             'shallow': (head + '\n').encode(),
             'objects/pack/pack-abc.idx': b'index', 'objects/pack/pack-abc.pack': b'pack',
             'objects/pack/pack-abc.rev': b'reverse'}
    artifacts = {f'object_{n}.bin': ('object' + str(n)).encode() for n in range(6)}
    artifacts['committed.cpp'] = b'int a;\n'
    env = {'GIT_DIR': git, 'GIT_NO_REPLACE_OBJECTS': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}
    lineage = {'schema': 1, 'head': head, 'git_dir': git,
               'git': {'path': '/usr/bin/git', **P.pin(b'git')},
               'git_metadata': [{'path': git + '/' + n, **P.pin(v)} for n, v in blobs.items()],
               'committed_cpp': {'path': root + '/committed.cpp', **P.pin(artifacts['committed.cpp'])},
               'mirror_cpp': {'path': '/unchanged/witness.cpp', **P.pin(artifacts['committed.cpp'])},
               'object_lineage': [{'oid': str(n) * 40, 'type': 'blob',
                                   'artifact': {'path': root + f'/object_{n}.bin', **P.pin(artifacts[f'object_{n}.bin'])}}
                                  for n in range(6)],
               'proposed_environment': env, 'non_path_note': git}
    raw_lineage = P.encode(lineage)
    source = P.patch_profile(ORIGINAL_PROFILE, P.ANCHORS['LINEAGE.json'], raw_lineage)
    artifacts.update({'LINEAGE.json': raw_lineage, 'git_profile.py': source,
                      'README.md': b'source-only', 'test_cold.py': b'pass\n'})
    manifest = {'schema': 1, 'files': {n: P.pin(data) for n, data in artifacts.items()}}
    raw_manifest = P.encode(manifest)
    artifacts['MANIFEST.json'] = raw_manifest
    files = {root + '/' + n: P.pin(data) for n, data in artifacts.items()}
    files.update({git + '/' + n: P.pin(data) for n, data in blobs.items()})
    files.update({'/unchanged/runtime/f' + str(n): P.pin(('r' + str(n)).encode()) for n in range(1620)})
    runtime = {'schema': 1, 'files': files, 'git_environment': copy.deepcopy(env),
               'git_profile_root': root, 'git_profile_manifest_sha256': P.pin(raw_manifest)['sha256'],
               'total_file_bytes': sum(v['bytes'] for v in files.values()),
               'python': {'path': '/unchanged/python', 'sha256': 'a' * 64},
               'numpy_root': '/unchanged/numpy', 'package_roots': {'yaml': '/unchanged/yaml'},
               'compiler': {'path': '/unchanged/compiler'}, 'prior_result_inherited': False}
    return runtime, raw_lineage, raw_manifest, source, output


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.args = fixture()
        self.result = P.transform(*self.args)

    def test_exact_inventory_and_1620_unchanged(self):
        old = self.args[0]
        new, mapping, _, _, _ = self.result
        self.assertEqual((len(new['files']), len(mapping)), (1638, 18))
        untouched = set(old['files']) - set(mapping)
        self.assertEqual(len(untouched), 1620)
        for key in untouched:
            self.assertEqual(P.encode(old['files'][key]), P.encode(new['files'][key]))
        self.assertTrue(set(mapping).isdisjoint(new['files']))
        self.assertEqual(new['total_file_bytes'], sum(x['bytes'] for x in new['files'].values()))
        for key in ('python', 'numpy_root', 'package_roots', 'compiler', 'prior_result_inherited'):
            self.assertEqual(old[key], new[key])

    def test_only_explicit_lineage_path_fields_change(self):
        old = P.parse(self.args[1])
        new = P.parse(self.result[3]['LINEAGE.json'])
        self.assertEqual(old['mirror_cpp'], new['mirror_cpp'])
        self.assertEqual(old['git'], new['git'])
        self.assertEqual(old['non_path_note'], new['non_path_note'])
        mapping = self.result[1]
        new['git_dir'] = old['git_dir']
        new['proposed_environment'] = old['proposed_environment']
        inverse = {v: k for k, v in mapping.items()}
        specs = [new['committed_cpp'], *new['git_metadata'], *(x['artifact'] for x in new['object_lineage'])]
        for spec in specs:
            spec['path'] = inverse[spec['path']]
        self.assertEqual(new, old)

    def test_real_profile_fixture_pin_and_ast_only_two_literals(self):
        self.assertEqual(P.pin(ORIGINAL_PROFILE), P.ANCHORS['git_profile.py'])
        new_bytes = self.result[3]['LINEAGE.json']
        # Independently compare the original genuine verifier, not just a toy AST.
        new_source = P.patch_profile(ORIGINAL_PROFILE, P.ANCHORS['LINEAGE.json'], new_bytes)
        old_ast, new_ast = ast.parse(ORIGINAL_PROFILE), ast.parse(new_source)
        changes = []
        for old, new in zip(ast.walk(old_ast), ast.walk(new_ast)):
            if isinstance(old, ast.Constant) and isinstance(new, ast.Constant) and old.value != new.value:
                changes.append((old.value, new.value))
                new.value = old.value
        self.assertCountEqual(changes, [(P.ANCHORS['LINEAGE.json']['sha256'], P.pin(new_bytes)['sha256']),
                                        (5231, len(new_bytes))])
        self.assertEqual(ast.dump(old_ast), ast.dump(new_ast))

    def test_manifest_and_runtime_close_new_hashes(self):
        new, _, _, generated, _ = self.result
        manifest = P.parse(generated['MANIFEST.json'])
        for name, data in generated.items():
            self.assertEqual(new['files'][self.args[-1] + '/profile/' + name], P.pin(data))
            if name != 'MANIFEST.json':
                self.assertEqual(manifest['files'][name], P.pin(data))
        self.assertNotIn('MANIFEST.json', manifest['files'])

    def test_fixed_head_not_mutable_source(self):
        self.assertEqual(self.result[4], b'a' * 40 + b'\n')

    def test_wrong_fixed_head_rejected(self):
        args = list(self.args)
        lineage = P.parse(args[1])
        lineage['head'] = 'b' * 40
        # Rebind local metadata to isolate the actual fixed-HEAD check.
        args = rebind_lineage(args, lineage)
        with self.assertRaisesRegex(ValueError, 'fixed HEAD'):
            P.transform(*args)

    def test_one_old_pin_mixed_rejected(self):
        args = list(copy.deepcopy(self.args))
        key = next(iter(self.result[1]))
        args[0]['files'][key]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'all 18'):
            P.transform(*args)

    def test_unknown_extra_git_file_rejected(self):
        args = list(copy.deepcopy(self.args))
        v = args[0]
        removed = v['files'].pop('/unchanged/runtime/f0')
        v['files'][v['git_environment']['GIT_DIR'] + '/objects/ab/extra'] = removed
        with self.assertRaisesRegex(ValueError, 'missing or extra'):
            P.transform(*args)

    def delta(self, changed):
        old = self.args[0]
        _, mapping, _, generated, _ = self.result
        replacement = {old['git_profile_root'] + '/' + n: P.pin(data) for n, data in generated.items()}
        P.validate_runtime_delta(old, changed, mapping, replacement)

    def test_removed_unknown_runtime_item_rejected(self):
        changed = copy.deepcopy(self.result[0])
        changed['files'].pop('/unchanged/runtime/f3')
        with self.assertRaises(ValueError):
            self.delta(changed)

    def test_same_count_unknown_item_swap_rejected(self):
        changed = copy.deepcopy(self.result[0])
        changed['files']['/unknown/extra'] = changed['files'].pop('/unchanged/runtime/f3')
        with self.assertRaisesRegex(ValueError, 'no removed'):
            self.delta(changed)

    def test_one_old_path_restored_rejected(self):
        changed = copy.deepcopy(self.result[0])
        old, new = next(iter(self.result[1].items()))
        changed['files'][old] = changed['files'].pop(new)
        with self.assertRaisesRegex(ValueError, 'no removed'):
            self.delta(changed)

    def test_other_runtime_metadata_rejected(self):
        changed = copy.deepcopy(self.result[0])
        changed['python']['path'] = '/mixed/python'
        with self.assertRaisesRegex(ValueError, 'outside allowed'):
            self.delta(changed)

    def test_one_git_environment_path_mixed_rejected(self):
        changed = copy.deepcopy(self.result[0])
        changed['git_environment']['GIT_DIR'] = self.args[0]['git_environment']['GIT_DIR']
        with self.assertRaisesRegex(ValueError, 'outside allowed'):
            self.delta(changed)

    def test_one_profile_manifest_hash_mixed_rejected(self):
        changed = copy.deepcopy(self.result[0])
        changed['git_profile_manifest_sha256'] = self.args[0]['git_profile_manifest_sha256']
        with self.assertRaisesRegex(ValueError, 'outside allowed'):
            self.delta(changed)

    def test_source_output_overlap_rejected(self):
        args = list(self.args)
        args[-1] = args[0]['git_profile_root'] + '/child'
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            P.transform(*args)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            P.parse(b'{"x":1,"x":2}')


def rebind_lineage(args, lineage):
    old_raw = args[1]
    args[1] = P.encode(lineage)
    args[3] = P.patch_profile(args[3], P.pin(old_raw), args[1])
    manifest = P.parse(args[2])
    manifest['files']['LINEAGE.json'] = P.pin(args[1])
    manifest['files']['git_profile.py'] = P.pin(args[3])
    args[2] = P.encode(manifest)
    r = args[0] = copy.deepcopy(args[0])
    for name, data in zip(('LINEAGE.json', 'MANIFEST.json', 'git_profile.py'), (args[1], args[2], args[3])):
        r['files'][r['git_profile_root'] + '/' + name] = P.pin(data)
    r['git_profile_manifest_sha256'] = P.pin(args[2])['sha256']
    r['total_file_bytes'] = sum(x['bytes'] for x in r['files'].values())
    return args


class SmallIOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.data = b'small synthetic bytes\n'
        self.source.write_bytes(self.data)
        self.spec = P.pin(self.data)
        self.dest = self.root / 'copy'

    def test_same_fd_stream_copy_preserves_source(self):
        before = P.stamp(self.source.stat())
        P.stream_checked(self.source, self.spec, self.dest)
        self.assertEqual(self.dest.read_bytes(), self.data)
        self.assertEqual(P.stamp(self.source.stat()), before)
        self.assertNotEqual(self.source.stat().st_ino, self.dest.stat().st_ino)
        self.assertEqual(self.dest.stat().st_nlink, 1)

    def test_wrong_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'content pin'):
            P.stream_checked(self.source, dict(self.spec, sha256='0' * 64), self.dest)

    def test_wrong_size_rejected(self):
        with self.assertRaisesRegex(ValueError, 'size pin'):
            P.stream_checked(self.source, dict(self.spec, bytes=123))

    def test_source_symlink_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'non-aliased'):
            P.stream_checked(link, self.spec)

    def test_ancestor_symlink_rejected(self):
        link = self.root / 'dirlink'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'ancestors'):
            P.stream_checked(link / 'source', self.spec)

    def test_source_hardlink_rejected(self):
        os.link(self.source, self.root / 'hardlink')
        with self.assertRaisesRegex(ValueError, 'nlink=1'):
            P.stream_checked(self.source, self.spec)

    def test_existing_output_rejected(self):
        self.dest.write_bytes(b'unchanged')
        with self.assertRaises(FileExistsError):
            P.stream_checked(self.source, self.spec, self.dest)
        self.assertEqual(self.dest.read_bytes(), b'unchanged')

    def test_output_symlink_rejected_without_target_change(self):
        self.dest.symlink_to(self.source)
        with self.assertRaises(FileExistsError):
            P.stream_checked(self.source, self.spec, self.dest)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_duplicate_inode_rejected(self):
        seen = set()
        P.stream_checked(self.source, self.spec, seen=seen)
        with self.assertRaisesRegex(ValueError, 'duplicate source inode'):
            P.stream_checked(self.source, self.spec, seen=seen)

    def test_toctou_before_open_rejected(self):
        original_open = P.os.open
        def swapped(path, flags, *args, **kwargs):
            replacement = self.root / 'replacement'
            replacement.write_bytes(self.data)
            replacement.replace(self.source)
            return original_open(path, flags, *args, **kwargs)
        with patch.object(P.os, 'open', side_effect=swapped):
            with self.assertRaisesRegex(ValueError, 'replaced before open'):
                P.stream_checked(self.source, self.spec, self.dest)

    def test_toctou_during_read_rejected(self):
        original = P.os.fstat
        calls = 0
        def mutate(fd):
            nonlocal calls
            calls += 1
            if calls == 2:  # after the tiny read, before the final FD/path stamps
                self.source.write_bytes(b'x' * len(self.data))
            return original(fd)
        with patch.object(P.os, 'fstat', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during read'):
                P.stream_checked(self.source, self.spec)

    def test_retained_metadata_limit(self):
        with self.assertRaisesRegex(ValueError, 'limited to 1 MiB'):
            P.stream_checked(self.source, dict(self.spec, bytes=P.CHUNK + 1))

    def test_small_multichunk_copy(self):
        with patch.object(P, 'CHUNK', 3):
            P.stream_checked(self.source, self.spec, self.dest)
        self.assertEqual(self.dest.read_bytes(), self.data)

    def test_fresh_write_rejects_overwrite(self):
        P.write_new(self.dest, b'first')
        with self.assertRaises(FileExistsError):
            P.write_new(self.dest, b'second')
        self.assertEqual(self.dest.read_bytes(), b'first')


if __name__ == '__main__':
    unittest.main(verbosity=2)
