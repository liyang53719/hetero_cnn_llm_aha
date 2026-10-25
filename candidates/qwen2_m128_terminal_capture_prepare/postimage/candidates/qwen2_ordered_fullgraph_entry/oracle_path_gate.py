"""Draft narrow oracle-file guard, not an execution authority or OS sandbox.

Only a future exact-reviewed worker may install it. That worker must finish
opaque oracle identity hashing in a different/preflight phase, close all such
handles, keep payload bytes out of DUT state, and attest pinned source/modules/
maps. The trusted runner must pass the ORIGINAL live-terminal verifier, not a
boolean/report. This file does not load a model, oracle, provider, or native ELF.

CPython open audit covers Python open/io.FileIO/os.open. Direct os.read/pread/
readv on an existing fd have no audit event: inherited oracle fds and mappings
must be rejected before activation. Native syscalls/ctypes, racing alias changes,
fd transfer and another process are NOT isolated by this helper.
Sealed-phase open names must be absolute because audit omits dir_fd. Normal
dependency initialization must finish before this isolation phase begins. They remain
source/closure restrictions, not a kernel sandbox guarantee.
"""
import os
from pathlib import Path
import sys


class OracleAccessDenied(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise OracleAccessDenied(message)


class ExactOraclePathGate:
    def __init__(self, roots, payload_paths):
        need(type(roots) in (list, tuple) and bool(roots), 'exact oracle roots required')
        self.roots = tuple(Path(p).resolve(strict=True) for p in roots)
        need(all(p.is_dir() for p in self.roots), 'oracle root must be a directory')
        need(type(payload_paths) in (list, tuple) and bool(payload_paths),
             'complete sealed oracle file path list required')
        # Include every sealed file under each oracle root, not merely one
        # sentinel. This list must also be bound to the exact external manifest
        # by the preflight worker; enumeration here is metadata only.
        present = set()
        for root in self.roots:
            for child in root.rglob('*'):
                need(not child.is_symlink(), 'symlink inside sealed oracle tree')
                if child.is_file():present.add(child.resolve(strict=True))
        declared = {Path(name).resolve(strict=True) for name in payload_paths}
        need(len(declared) == len(payload_paths) and declared == present,
             'complete exact oracle-root file enumeration required')
        self.inodes = set()
        for name in payload_paths:
            path = Path(name).resolve(strict=True)
            need(any(path.is_relative_to(root) for root in self.roots), 'payload outside oracle roots')
            st = path.stat()
            need(path.is_file(), 'oracle payload must be a regular file')
            self.inodes.add((st.st_dev, st.st_ino))
        self.state = 'SEALED'
        self.installed = False
        self.comparison_attempted = False
        self.denied = []

    def _oracle(self, target):
        if type(target) is int:
            need(target >= 0, 'invalid file descriptor')
            try:
                st = os.fstat(target)
                name = os.readlink('/proc/self/fd/' + str(target))
            except OSError as error:
                raise OracleAccessDenied('unresolved file descriptor') from error
            if (st.st_dev, st.st_ino) in self.inodes:
                return True
            target = name.removesuffix(' (deleted)')
            if not target.startswith('/'):
                return False  # pipe/socket/etc., never an oracle file
        need(isinstance(target, (str, bytes, os.PathLike)), 'unresolved open target')
        path = Path(os.fsdecode(target)).resolve()
        if any(path.is_relative_to(root) for root in self.roots):
            return True
        try:
            st = path.stat()
        except FileNotFoundError:
            return False
        return (st.st_dev, st.st_ino) in self.inodes

    def audit(self, event, args):
        if self.state == 'COMPARING':
            return
        target = None
        if event == 'open':
            target = args[0]
        elif event == 'mmap.__new__' and args[0] != -1:
            target = args[0]
        if target is None:
            return
        try:
            if isinstance(target, (str, bytes, os.PathLike)):
                # open audit omits dir_fd. Never guess cwd for a relative name.
                need(Path(os.fsdecode(target)).is_absolute(),
                     'relative open forbidden while oracle is sealed; dir_fd is not audited')
            need(not self._oracle(target),
                 'oracle file is sealed before/after terminal comparison')
        except OracleAccessDenied as error:
            self.denied.append({'event': event, 'target': os.fsdecode(target) if isinstance(target, bytes) else str(target),
                                'reason': str(error), 'state': self.state})
            raise

    def require_clean(self):
        need(not self.denied, 'sticky oracle isolation violation; comparison/acceptance forbidden')

    def report(self):
        return dict(state=self.state, installed=self.installed,
                    comparison_attempted=self.comparison_attempted,
                    denied=[dict(row) for row in self.denied],
                    acceptance_eligible=not self.denied)

    def assert_no_inherited_oracle(self, fd_targets, maps_text):
        """Caller persists full raw fd/maps snapshot before invoking this check."""
        need(type(fd_targets) is dict and type(maps_text) is str, 'raw fd/maps inventory required')
        for fd, target in fd_targets.items():
            need(type(fd) is int and fd >= 0, 'fd inventory type')
            need(not self._oracle(target), 'preexisting oracle fd')
            # Check current fd identity as well as the persisted path spelling.
            need(not self._oracle(fd), 'current inherited oracle fd identity')
        for line in maps_text.splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith('/'):
                need(not self._oracle(fields[5].removesuffix(' (deleted)')), 'preexisting oracle mmap')

    def install(self, fd_targets, maps_text):
        need(not self.installed and self.state == 'SEALED', 'one installation only')
        self.assert_no_inherited_oracle(fd_targets, maps_text)
        sys.addaudithook(self.audit)
        self.installed = True

    def compare_after_live_terminal(self, verify_live_terminal, callback, *args, **kwargs):
        """Scope oracle reads to one callback after original live terminal check.

        Source admission MUST bind verify_live_terminal to registry._live_terminal
        with the original x/physical/memory/report. An arbitrary callable here is
        not authenticated. This control seam alone grants NO launch permission.
        """
        need(self.installed and self.state == 'SEALED' and not self.comparison_attempted,
             'fresh installed terminal comparison gate required')
        need(callable(verify_live_terminal) and callable(callback), 'source-bound callbacks required')
        self.require_clean()
        self.comparison_attempted = True
        # Existing verifier returns None after checking live original objects.
        # A boolean/dict supplied as proof is explicitly not accepted.
        need(verify_live_terminal() is None, 'live verifier must succeed, not supply a boolean proof')
        self.require_clean()
        self.state = 'COMPARING'
        try:
            return callback(*args, **kwargs)
        finally:
            self.state = 'CLOSED'
