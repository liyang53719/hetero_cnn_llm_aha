"""Reuse only pinned native code, never old data, state, or numerical acceptance."""
from pathlib import Path
from . import gates


def identity():
    result = {}
    for name, expected in gates.pins()['native_artifact'].items():
        path = gates.ROOT / expected['path']
        gates.require(path.resolve() == path and not path.is_symlink(), 'aliased native artifact')
        digest = gates.sha(path)
        gates.require(digest == expected['sha256'], 'native artifact drift: ' + name)
        result[name] = dict(path=str(path), sha256=digest, bytes=path.stat().st_size)
    return result


def load(dense):
    before = identity()
    receipt = dense.verify_library(before['receipt']['path'])
    gates.require(Path(receipt['library']) == Path(before['library']['path']), 'native receipt library path mismatch')
    gates.require(receipt['library_sha256'] == before['library']['sha256'], 'native receipt ELF hash mismatch')
    library = dense.configure_silu_library(dense.configure_library(dense.C.CDLL(receipt['library'])))
    gates.require(identity() == before, 'native artifact drift during load')
    reuse = dict(status='VERIFIED_NATIVE_CODE_REUSE', compile_executed=False,
        old_numeric_state_reused=False, old_pass_inherited=False,
        previous_compile_receipt=receipt, artifact_identity_before=before,
        provenance='Unchanged strict native C++ Matrix/SILU .so only; fresh process and explicit td_reset follow')
    return library, receipt, reuse
