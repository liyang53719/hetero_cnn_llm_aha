#!/usr/bin/env python3
"""Verify fixed published archive members, never recreate the historical ZIP.

The fixed publication pins were authenticated separately by the coordinator.
No caller-provided digests, Git/network operations, model execution or private
bodies are admitted. This route is distinct from verify_artifact.py's ZIP route.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import types

HERE = Path(__file__).absolute().parent
BUILDER_SHA = 'd5471b74ce8dbd7d92195505231b67c76b544e55ab90be401989ad960816f05e'
VERIFIER_SHA = '21a29376b04bfa0e83dc05108dbd00b5122188f6dbaeea18a01f6e770c90a5b3'
PUBLICATION_SHA = '97a014341a9d1dda97f8e081e4532303ed298c908bc0fe611e6294e1e5b4bd7e'
MEMBER_MAP_SHA = 'c8c8938bdecae81df68bf08509d9fd729c5e24c4f54ab63e28922e06e335abd8'
PREFIX = 'reports/execution/QWEN2_SAME_HOST_M128_REPLAY_IDENTITY_20261017'
ORIGINAL_ZIP_SHA = '0c25aa1453f5b9f099fdc470933e3074462bd2f92ca08c191a1cfb9adf22b21a'


def checked_builder():
    # Bootstrap a fixed helper from source bytes, never import a cached module.
    path = HERE / 'build_source_view.py'
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('BUILDER_ALIAS')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= 1024 * 1024:
            raise ValueError('BUILDER_TYPE_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(before.st_size + 1)
        after = os.fstat(fd)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) != signature(after) or signature(before) != signature(path.stat(follow_symlinks=False)):
            raise ValueError('BUILDER_DRIFT')
        if hashlib.sha256(raw).hexdigest() != BUILDER_SHA:
            raise ValueError('BUILDER_PIN')
        module = types.ModuleType('checked_source_builder')
        module.__file__ = str(path)
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        return module
    finally:
        os.close(fd)


B = checked_builder()


def load_publication(package=HERE):
    package_fd = B.open_directory(package)
    try:
        raw, _ = B.read_checked(package_fd, 'archive_publication.json')
        B.need(B.sha(raw) == PUBLICATION_SHA, 'PUBLICATION_PIN')
        publication = B.strict(raw)
        B.need(publication['status'] == 'AUTHENTICATED_FIXED_PUBLICATION' and
               all(type(publication[key]) is str and re.fullmatch('[0-9a-f]{40}', publication[key])
                   for key in ('publication_commit', 'publication_tree')), 'PUBLICATION_NOT_AUTHENTICATED')
        B.need(publication['archive_member_map_sha256'] == MEMBER_MAP_SHA and
               publication['archive_prefix'] == PREFIX and
               publication['original_zip_sha256'] == ORIGINAL_ZIP_SHA, 'PUBLICATION_SCOPE')
        map_raw, _ = B.read_checked(package_fd, 'ARCHIVED_MEMBER_HASHES.json')
        B.need(B.sha(map_raw) == MEMBER_MAP_SHA, 'ARCHIVE_MAP_PIN')
        members = B.strict(map_raw)
        B.source_map(members, 10)
        B.need(all(name.startswith(PREFIX + '/') and '/' not in name[len(PREFIX) + 1:]
                   for name in members), 'ARCHIVE_MAP_SCOPE')
        return publication, members
    finally:
        os.close(package_fd)


def load_verifier(package=HERE):
    package_fd = B.open_directory(package)
    try:
        raw, _ = B.read_checked(package_fd, 'verify_artifact.py')
        B.need(B.sha(raw) == VERIFIER_SHA, 'VERIFIER_PIN')
        module = types.ModuleType('checked_unchanged_artifact_verifier')
        module.__file__ = str(Path(package) / 'verify_artifact.py')
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        return module
    finally:
        os.close(package_fd)


def verify(archive_checkout, freeze, package=HERE):
    publication, full_members = load_publication(package)
    verifier = load_verifier(package)
    expected = {name[len(PREFIX) + 1:]: digest for name, digest in full_members.items()}
    B.need(set(expected) == set(verifier.FILES) | {'MANIFEST.json', 'README.md'}, 'ARCHIVE_MEMBER_NAMES')
    checkout = B.absolute(archive_checkout)
    archive_path = checkout / PREFIX
    archive_fd = B.open_directory(archive_path)
    root_identity = B.dir_identity(os.fstat(archive_fd))
    try:
        B.need(set(os.listdir(archive_fd)) == set(expected), 'ARCHIVE_INVENTORY')
        bodies = {}
        snapshots = {}
        for name, digest in expected.items():
            raw, snapshot = B.read_checked(archive_fd, name)
            B.need(B.sha(raw) == digest, 'ARCHIVE_MEMBER_PIN')
            bodies[name] = raw
            snapshots[name] = snapshot
        B.need(sum(map(len, bodies.values())) <= 4 * 1024 * 1024, 'ARCHIVE_TOTAL_SIZE')
        # No manifest claim is used to bypass receipt/schema/provenance validation.
        manifest = verifier.strict(bodies['MANIFEST.json'])
        ci = dict(commit=verifier.COMMIT, run_id=verifier.RUN_ID, run_attempt='1')
        verifier.exact(manifest['ci'], ci, 'ARCHIVE_CI')
        B.need(manifest['job_id'] == publication['job_id'] == verifier.JOB_ID and
               manifest['artifact_id'] == publication['artifact_id'] and
               manifest['original_artifact']['sha256'] == ORIGINAL_ZIP_SHA, 'ARCHIVE_HISTORICAL_BINDING')
        full, pins = verifier.load_sources(freeze)
        compiled = verifier.derive_compile_sources(freeze, full, pins)
        raws = {name: bodies[name] for name in verifier.FILES}
        values, chains = verifier.validate_receipts(raws, ci, pins)
        inventory = verifier.load_identity_schema().validate_manifest(
            values['replay_identity.json'], pins[128]['inputs'], compile_sources=compiled)
        verifier.validate_provenance(values, raws, chains, full)
        for name, digest in expected.items():
            raw, snapshot = B.read_checked(archive_fd, name)
            B.need(B.sha(raw) == digest and snapshot == snapshots[name], 'ARCHIVE_DRIFT')
        B.need(set(os.listdir(archive_fd)) == set(expected), 'ARCHIVE_INVENTORY_DRIFT')
        current_fd = B.open_directory(archive_path)
        try:
            B.need(B.dir_identity(os.fstat(current_fd)) == root_identity, 'ARCHIVE_ROOT_DRIFT')
        finally:
            os.close(current_fd)
        return dict(schema=1, status='PASS_ARCHIVED_MEMBER_BINDING', verification_route='ARCHIVED_MEMBER_BINDING',
                    ci=ci, publication=publication, archive_member_map_sha256=MEMBER_MAP_SHA,
                    archive_members={name: dict(bytes=len(raw), sha256=B.sha(raw)) for name, raw in bodies.items()},
                    receipt_files={name: dict(bytes=len(raw), sha256=B.sha(raw)) for name, raw in raws.items()},
                    original_zip_sha256_recorded=ORIGINAL_ZIP_SHA, original_zip_bytes_read=False,
                    original_zip_digest_recomputed=False, zip_container_recovered=False,
                    publication_content_matches_fixed_authenticated_pins=True,
                    local_git_head_authenticated=False, actual_git_publication_proof_replayed=False,
                    github_metadata_independently_fetched=False, full_source_map_sha256=B.MAP_SHA,
                    raw_source_files=465, source_chains=chains, inventory=inventory,
                    combined_compile_source_map_sha256=B.sha(B.encoded(compiled)),
                    stable_identity_sha256=values['replay_identity.json']['identity_sha256'],
                    replay_identity_sha256=B.sha(raws['replay_identity.json']),
                    program_reported_replay_identity_ready=True, source_bound_strict_cleanup_required=True,
                    numerical_execution_performed=False, private_tensor_bytes_replayed=False,
                    private_qualification_bytes_replayed=False, private_process_proofs_replayed=False,
                    future_job_admission_authority=False, full_29_node_acceptance=False,
                    rtl_execution=False, hardware_acceptance=False)
    finally:
        os.close(archive_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-checkout', required=True, type=Path)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        output = B.absolute(args.out)
        for source in (B.absolute(args.archive_checkout) / PREFIX, B.absolute(args.freeze), HERE):
            B.need(source != output and source not in output.parents, 'OUTPUT_INPUT_OVERLAP')
        parent_fd = B.open_directory(output.parent)
        try:
            try:
                os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise B.SourceViewError('OUTPUT_EXISTS')
            report = verify(args.archive_checkout, args.freeze)
            B.write_exclusive(parent_fd, output.name, B.encoded(report))
        finally:
            os.close(parent_fd)
        print(B.encoded(dict(status=report['status'], zip_container_recovered=False,
                             stable_identity_sha256=report['stable_identity_sha256'])).decode(), end='')
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'archived-member verification rejected: {error}\n')


if __name__ == '__main__':
    main()
