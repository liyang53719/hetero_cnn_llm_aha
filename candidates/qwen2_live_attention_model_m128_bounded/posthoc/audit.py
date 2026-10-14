"""Standalone comparison-only read gate; never installed into a DUT execution."""
import os
from pathlib import Path
from . import validation as v


def is_write(mode, flags):
    return (isinstance(mode, str) and any(c in mode for c in 'wa+x')) or \
        bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))


class ImportGuard:
    """Bootstrap pinned comparison modules without Torch, DUT imports, or old writes."""
    def __init__(self, out): self.out = Path(out)
    def audit(self, event, args):
        if event == 'import' and (args[0] == 'torch' or args[0].startswith('torch.') or
                                  args[0].startswith('candidates.qwen2_resident_matrix')):
            raise ValueError('posthoc Torch/DUT module import forbidden: ' + args[0])
        if event == 'subprocess.Popen': raise ValueError('posthoc subprocess forbidden')
        if event == 'open' and isinstance(args[0], (str, bytes)) and is_write(args[1], args[2]):
            name = args[0].decode() if isinstance(args[0], bytes) else args[0]
            if not Path(name).resolve().is_relative_to(self.out):
                raise ValueError('posthoc bootstrap write outside new output: ' + name)


class ReadOnlyGate:
    def __init__(self, out, receipt, review):
        p = v.pins(); self.out = Path(out); self.opened = False
        self.reference_reads = []; self.runtime_reads = []; self.blocked = []
        self.run = v.ROOT / p['run_path']; self.data = v.ROOT / p['data_path']; self.reference = v.ROOT / p['reference_path']
        self.runtime = {Path(spec['path']) if Path(spec['path']).is_absolute() else v.ROOT / spec['path']
                        for spec in p['runtime_native_files'].values()}
        from candidates.qwen2_live_attention_model_m128 import gates as original
        self.oracles = {self.reference / (n + '.f32le') for n in original.REFERENCES} | {self.reference / 'mask.bf16le'}
        self.allowed_payloads = {self.run / n for n in review['all_original_run_files']}
        self.allowed_payloads |= {self.data / 'inputs' / (n + '.bin') for n in original.ROLES}
        self.allowed_payloads |= {self.data / 'raw' / n for n in original.pins()['raw_files']}
        self.allowed_payloads |= {v.ROOT / n for n in p['dependency_sha256']}
        self.tools = {Path(spec['path']) for spec in receipt['tools_before'].values()}
        self.tools |= {Path(spec['path']) for spec in receipt['native_artifact_reuse']['artifact_identity_before'].values()}

    def reject(self, reason, path):
        self.blocked.append(dict(reason=reason, path=str(path)))
        raise ValueError(reason + ': ' + str(path))

    def audit(self, event, args):
        if event == 'ctypes.dlopen': self.reject('posthoc native loading forbidden', args[0])
        if event == 'subprocess.Popen': self.reject('posthoc process execution forbidden', args[0])
        if event == 'import' and (args[0] == 'torch' or args[0].startswith('torch.')):
            self.reject('posthoc Torch import forbidden', args[0])
        if event != 'open' or not isinstance(args[0], (str, bytes)): return
        name = args[0].decode() if isinstance(args[0], bytes) else args[0]
        path = Path(name).resolve(); mode, flags = args[1], args[2]
        if is_write(mode, flags):
            if not path.is_relative_to(self.out): self.reject('posthoc write outside new output', path)
            return
        if path in self.oracles:
            if not self.opened: self.reject('oracle before verified seal and identities', path)
            self.reference_reads.append(str(path.relative_to(v.ROOT))); return
        if path in self.runtime:
            self.runtime_reads.append(str(path)); return
        if path in self.tools or path in self.allowed_payloads or path.is_relative_to(self.out): return
        native = path.name.endswith('.so') or '.so.' in path.name
        payload = path.suffix in ('.bin', '.f32le', '.bf16le', '.npy', '.npz', '.u32le', '.u16le', '.presence')
        if path.is_relative_to(v.ROOT / 'work') and (native or payload):
            self.reject('unapproved prior-run payload/native read', path)
        if payload: self.reject('unapproved payload read', path)
