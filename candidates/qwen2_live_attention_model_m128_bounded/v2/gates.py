"""V1 unchanged, plus the exact original ScalarService FENV initialization path."""
import ctypes
import json
from pathlib import Path
import sys
import types
from candidates.qwen2_live_attention_model_m128_bounded import gates as base

ROOT, OUTPUT_ROOT = base.ROOT, base.OUTPUT_ROOT
HERE = Path(__file__).resolve().parent
original = base.original
require, sha, manifest = base.require, base.sha, base.manifest
ROLES, REFERENCES = base.ROLES, base.REFERENCES
data_path, reference_path, fresh_output = base.data_path, base.reference_path, base.fresh_output
validate_inputs, validate_references = base.validate_inputs, base.validate_references
raw_identity, correspondence = base.raw_identity, base.correspondence


def pins():
    return json.loads((HERE / 'pins.json').read_text())


def verify_dependencies():
    p = pins()
    require(p['scope'] == 'M128_SOFTWARE_PC0_12_HELD_BOUNDED_V2' and type(p['rows']) is int and p['rows'] == 128 and
            p['actual_execution_authorized'] is False, 'v2 admission scope')
    parent = base.sources()
    require(parent == p['dependency_sha256'] and manifest(parent) == p['parent_source_manifest_sha256'],
            'frozen v1 source closure drift')
    runtime_path = Path(ctypes.__file__).resolve()
    require(str(runtime_path) == p['ctypes_runtime']['path'] and sha(runtime_path) == p['ctypes_runtime']['sha256'],
            'ctypes runtime identity drift')
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


def require_review(value):
    current = sources()
    require(isinstance(value, str) and len(value) == 64 and manifest(current) == value,
            'independent parent go and exact reviewed v2 manifest required')
    return current


def code_in(code, name):
    found = [c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == name]
    require(len(found) == 1, 'ambiguous source-bound code: ' + name)
    return found[0]


class OracleGate(base.OracleGate):
    def __init__(self, data, out, reference):
        super().__init__(data, out, reference)
        p = pins()
        self.scalar_path = ROOT / p['scalar_source']
        require(sha(self.scalar_path) == p['scalar_source_sha256'], 'Scalar source drift')
        scalar_code = code_in(compile(self.scalar_path.read_text(), str(self.scalar_path), 'exec',
                                      dont_inherit=True, optimize=sys.flags.optimize), 'ScalarService')
        self.expected_init = code_in(scalar_code, '__init__')
        self.expected_environment = code_in(scalar_code, '_check_environment')
        self.ctypes_path = Path(ctypes.__file__).resolve()
        require(str(self.ctypes_path) == p['ctypes_runtime']['path'] and
                sha(self.ctypes_path) == p['ctypes_runtime']['sha256'], 'ctypes runtime drift')
        ctypes_code = code_in(compile(self.ctypes_path.read_text(), str(self.ctypes_path), 'exec',
                                      dont_inherit=True, optimize=sys.flags.optimize), 'CDLL')
        self.expected_ctypes = {n: code_in(ctypes_code, n) for n in ('__init__', '__getitem__', '__getattr__')}
        self.environment_events = []
        self.environment_handle = None

    def _original_environment_frames(self, environment_frame):
        module = sys.modules.get('candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic')
        require(module is not None, 'original Scalar module not loaded')
        cls = module.ScalarService
        constructor = environment_frame.f_back if environment_frame is not None else None
        require(environment_frame is not None and constructor is not None and
                environment_frame.f_globals is module.__dict__ and constructor.f_globals is module.__dict__ and
                environment_frame.f_code is cls._check_environment.__code__ and
                constructor.f_code is cls.__init__.__code__ and
                environment_frame.f_code == self.expected_environment and constructor.f_code == self.expected_init and
                type(constructor.f_locals.get('self')) is cls,
                'current-process handle requires exact original Scalar constructor/environment code frames')
        p = pins()
        require(sha(self.scalar_path) == p['scalar_source_sha256'], 'Scalar source drift at FENV admission')

    def _ctypes_frame(self, frame, name):
        require(frame is not None and frame.f_globals is ctypes.__dict__ and
                frame.f_code is getattr(ctypes.CDLL, name).__code__ and
                frame.f_code == self.expected_ctypes[name], 'unapproved ctypes call frame')

    def audit(self, event, args):
        if event == 'ctypes.dlopen' and args[0] is None:
            require(not self.opened and self.environment_handle is None, 'FENV handle only once before seal')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__init__')
            self._original_environment_frames(frame.f_back)
            require(frame.f_locals.get('name') is None, 'FENV handle must target current process')
            self.environment_handle = id(frame.f_locals['self'])
            self.environment_events.append(dict(event=event, target=None,
                caller='ScalarService.__init__ -> ScalarService._check_environment -> ctypes.CDLL.__init__',
                source_sha256=pins()['scalar_source_sha256'], admitted=True))
            return
        if event == 'ctypes.dlsym' and getattr(args[0], '_name', 'not-current-process') is None:
            require(id(args[0]) == self.environment_handle and args[1] == 'fegetround',
                    'current-process symbol restricted to original fegetround probe')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__getitem__')
            self._ctypes_frame(frame.f_back, '__getattr__')
            self._original_environment_frames(frame.f_back.f_back)
            self.environment_events.append(dict(event=event, symbol='fegetround', admitted=True))
            return
        return super().audit(event, args)
