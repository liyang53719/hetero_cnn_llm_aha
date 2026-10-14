"""Fresh entry closure/admission; all original numerical and payload gates reused."""
import hashlib
import json
import os
from pathlib import Path
import re
from candidates.qwen2_live_attention_model_m128 import gates as original

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / 'work/qwen2_live_attention_numeric_m128_bounded_20261014'
require, sha = original.require, original.sha
ROLES, REFERENCES = original.ROLES, original.REFERENCES
data_path, reference_path = original.data_path, original.reference_path
validate_inputs, validate_references = original.validate_inputs, original.validate_references
raw_identity, correspondence = original.raw_identity, original.correspondence


def pins():
    return json.loads((HERE / 'pins.json').read_text())


def verify_dependencies():
    p = pins()
    require(p['scope'] == 'M128_SOFTWARE_PC0_12_HELD_BOUNDED_V1' and type(p['rows']) is int and p['rows'] == 128,
            'bounded entry scope/rows')
    require(p['actual_execution_authorized'] is False, 'stored approval bit cannot authorize this entry')
    require((p['inner_wall_seconds'], p['outer_wall_seconds'], p['progress_loop_interval']) == (900, 930, 131072),
            'unreviewed bounded timing contract')
    for name, digest in p['dependency_sha256'].items():
        require(sha(ROOT / name) == digest, 'bounded dependency drift: ' + name)
    original.verify_dependencies()
    return p


def require_final_reference():
    verify_dependencies()
    return original.require_final_reference()


def sources():
    result = dict(verify_dependencies()['dependency_sha256'])
    for path in HERE.iterdir():
        if path.is_file() and (path.suffix in ('.py', '.md') or path.name == 'pins.json'):
            result[str(path.relative_to(ROOT))] = sha(path)
    return result


def manifest(sources_):
    return hashlib.sha256(json.dumps(sources_, sort_keys=True).encode()).hexdigest()


def require_review(reviewed_source_manifest):
    require(isinstance(reviewed_source_manifest, str) and re.fullmatch(r'[0-9a-f]{64}', reviewed_source_manifest),
            'independent parent go and exact reviewed source manifest required')
    current = sources()
    require(manifest(current) == reviewed_source_manifest, 'reviewed source manifest drift')
    return current


def fresh_output(path, data):
    path = Path(path).absolute()
    require(path.resolve() == path and path.parent == OUTPUT_ROOT and
            re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', path.name),
            'output must be a fresh direct child of bounded numeric work directory')
    require(not path.exists() and not path.is_relative_to(data) and not data.is_relative_to(path),
            'output exists/overlaps inputs')


class OracleGate(original.OracleGate):
    """Original payload rules plus exact old native-code artifact admission.

    Original gate ignores .so/.json and ctypes.dlopen. This additional guard
    narrows old-run reads to the two pinned code artifacts. It grants no new
    tensor path and independently restricts ctypes loading to that exact ELF.
    """
    def __init__(self, data, out, reference):
        super().__init__(data, out, reference)
        self.artifacts = {name: ROOT / spec['path'] for name, spec in pins()['native_artifact'].items()}
        self.artifact_reads = []

    def audit(self, event, args):
        if event == 'ctypes.dlopen':
            name = args[0]
            require(isinstance(name, (str, bytes)), 'unapproved native dlopen handle')
            path = Path(name.decode() if isinstance(name, bytes) else name).resolve()
            require(path == self.artifacts['library'], 'unapproved native dlopen path')
            self.artifact_reads.append(dict(event=event, path=str(path.relative_to(ROOT))))
            return
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = args[0].decode() if isinstance(args[0], bytes) else args[0]
            path = Path(name).resolve()
            prior_run = self.artifacts['library'].parent.parent
            work_native = path.is_relative_to(ROOT / 'work') and (path.name.endswith('.so') or '.so.' in path.name)
            if path.is_relative_to(prior_run) or work_native:
                require(path in self.artifacts.values(), 'unapproved prior-run artifact read')
                mode, flags = args[1], args[2]
                require((mode is None or all(c not in mode for c in 'wa+x')) and
                        isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC) == 0,
                        'native artifact must remain read-only')
                self.artifact_reads.append(dict(event=event, path=str(path.relative_to(ROOT))))
                return
        return super().audit(event, args)
