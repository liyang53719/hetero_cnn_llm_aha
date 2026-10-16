"""Read-only monitoring transport for the exact profiled shared Matrix service.

All capture callbacks, causal fields, coverage, cleanup, and save behavior are
inherited unchanged. Only the constructor's exact service type and its source
closure are extended. No owner/service object, method, type, or result is
replaced. The reviewed old constructors and this narrow substitution are
checked by source hashes and AST equivalence before monitoring can start.

This remains software observation, not binary-build, native, or RTL acceptance.
The caller freezes the entire previous observer inventory plus this adapter,
its Matrix binding, and the explicit reduction profile.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import threading
import types

from ..official_bf16 import observation as original
from ..official_bf16 import observation_monitoring as monitoring
from ..official_bf16.observation import (
    ROOT, OWNER, base, require, _code, _same_code,
    verify_source_snapshot, verify_loaded_dependencies,
)
from ..official_bf16.observation_monitoring import verify_monitoring_dependencies
from . import matrix_binding, profile

ADAPTER = 'candidates/qwen2_resident_matrix/dense_block_reduce/observation.py'
BINDING = 'candidates/qwen2_resident_matrix/dense_block_reduce/matrix_binding.py'
PROFILE = 'candidates/qwen2_resident_matrix/dense_block_reduce/profile.py'
EXTRA_SOURCES = (ADAPTER, BINDING, PROFILE)
SOURCE_VERSION = 'qwen2-profiled-attention-observation-v4'
CAPTURE_SOURCE_VERSION = 'qwen2-official-bf16-attention-observation-v4'
CAPTURE_SHA256 = '13ec64d2f8985256d4bdf78595a628eb106a79117e62c728ac3e486d09e4f627'
MONITORING_SHA256 = '3c27ce71bd93937707c909ccd7507baff6a401c49b50e6a9753ab224a9d2a3c5'


def verify_constructor_delta():
    """Allow only the reviewed imports/service type and one closure check."""
    require(original.SOURCE_VERSION == CAPTURE_SOURCE_VERSION,
            'reviewed observer source version changed')
    paths = ((original.OBSERVER, CAPTURE_SHA256), (monitoring.MONITORING, MONITORING_SHA256))
    for relative, digest in paths:
        require(base.sha((ROOT / relative).read_bytes()) == digest,
                'reviewed observer constructor source drift: ' + relative)

    def constructor(relative, cls_name):
        tree = ast.parse((ROOT / relative).read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
        return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')

    expected = constructor(original.OBSERVER, 'OfficialAttentionObservation')
    # No general AST rewriter or dynamically compiled replacement is used.
    # These are the three explicit differences from the exact old init body.
    imports = [n for n in expected.body if isinstance(n, ast.ImportFrom)]
    require(len(imports) == 3, 'reviewed constructor import inventory drift')
    require(imports[0].module == 'owners' and imports[0].level == 1 and
            imports[1].module == 'dense_silu' and imports[1].level == 1,
            'reviewed constructor service imports drift')
    imports[0].module, imports[0].level = 'official_bf16.owners', 2
    imports[1].module = 'matrix_binding'
    imports[1].names[0].name = 'ProfiledMatrixService'
    for node in ast.walk(expected):
        if isinstance(node, ast.Name) and node.id == 'OfficialMatrixService':
            node.id = 'ProfiledMatrixService'
        elif isinstance(node, ast.Constant) and node.value == 'exact OfficialMatrixService and ScalarService required':
            node.value = 'exact ProfiledMatrixService and ScalarService required'
    transport = constructor(monitoring.MONITORING, 'OfficialAttentionMonitoringObservation')
    super_call = ast.dump(ast.parse('super().__init__(owner, source_sha256=source_sha256)').body[0], include_attributes=False)
    require(ast.dump(transport.body[0], include_attributes=False) == super_call,
            'reviewed monitoring constructor super call drift')
    expected.body.extend(transport.body[1:])
    expected.body.extend(ast.parse('self.profiled_loaded_functions_checked = verify_profiled_dependencies(owner, self.sources)').body)
    actual = constructor(ADAPTER, 'ProfiledAttentionMonitoringObservation')
    require(ast.dump(actual, include_attributes=False) == ast.dump(expected, include_attributes=False),
            'profiled observer constructor exceeded reviewed minimal delta')


def verify_profiled_dependencies(owner, sources):
    # Verify all old helpers/classes/imports/instance methods first; none of
    # their checks are bypassed by accepting the additional exact service type.
    count = verify_monitoring_dependencies(owner, sources)
    verify_source_snapshot(sources)
    require(all(name in sources for name in EXTRA_SOURCES),
            'snapshot must include profiled observer, Matrix binding and profile')
    from ..official_bf16.owners import OfficialAttentionOwner
    from ..ffn_public.prefix_arithmetic import ScalarService
    require(type(owner) is OfficialAttentionOwner and
            type(owner.matrix) is matrix_binding.ProfiledMatrixService and
            type(owner.scalar) is ScalarService,
            'exact OfficialAttentionOwner, ProfiledMatrixService and ScalarService required')
    for relative in EXTRA_SOURCES:
        module = sys.modules[relative[:-3].replace('/', '.')]
        count += original._verify_module(module, relative)
    policy = owner.matrix.profile
    require(type(policy) is profile.ReductionProfile and
            set(vars(policy)) == set(profile.ReductionProfile.__dataclass_fields__),
            'exact unpatched immutable ReductionProfile required')
    policy.validate(1536)
    verify_constructor_delta()
    return count


class ProfiledAttentionMonitoringObservation(monitoring.OfficialAttentionMonitoringObservation):
    """Exact existing capture with an explicitly checked profiled service."""

    def __init__(self, owner, *, source_sha256):
        from ..official_bf16.owners import OfficialAttentionOwner
        from .matrix_binding import ProfiledMatrixService
        from ..ffn_public.prefix_arithmetic import ScalarService
        require(type(owner) is OfficialAttentionOwner, 'exact OfficialAttentionOwner required')
        require(type(owner.matrix) is ProfiledMatrixService and type(owner.scalar) is ScalarService,
                'exact ProfiledMatrixService and ScalarService required')
        require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12)
                and not sys.flags.optimize, 'reviewed CPython 3.12 without -O required')
        self.owner, self.sources = owner, dict(source_sha256)
        self.execution_sources = verify_source_snapshot(self.sources)
        self.loaded_functions_checked = verify_loaded_dependencies(owner)
        self.instrumentation_sha256 = base.sha(Path(__file__).read_bytes())
        self.services = owner.matrix, owner.scalar
        self.codes, methods = {}, {}
        for name in ('_attention', '_matrix_step', 'tick'):
            method = getattr(owner, name)
            path = ROOT / (OWNER if name == '_attention' else base.OWNER)
            cls_name = 'OfficialAttentionOwner' if name == '_attention' else 'AttentionOwner'
            raw = path.read_text()
            code = _code(_code(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), cls_name), name)
            require(isinstance(method, types.MethodType) and _same_code(method.__func__.__code__, code),
                    'loaded observation target changed: ' + name)
            self.codes[name] = method.__func__.__code__
            cls = next(n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == cls_name)
            methods[name] = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)

        def point(method, statement):
            expected = ast.dump(ast.parse(statement).body[0], include_attributes=False)
            found = [n.lineno for n in ast.walk(methods[method]) if isinstance(n, ast.stmt)
                     and ast.dump(n, include_attributes=False) == expected]
            require(len(found) == 1, 'ambiguous observation statement: ' + statement)
            return found[0]

        self.points = dict(score=point('_attention', 'scores.append(score)'),
            exp=point('_attention', 'probabilities.append(probability)'),
            matrix=point('_matrix_step', 'return lanes'),
            store=point('_attention', 'yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)'))
        self.thread = threading.get_ident()
        self.active = self.closed = self.disarmed = False
        self.started = 0
        self.job = self.terminal = self.retirement = self.error = None
        self.fields = {}
        self._callback = self._trace
        self.loaded_functions_checked = verify_monitoring_dependencies(owner, self.sources)
        self.instrumentation_sha256 = original.base.sha(Path(__file__).read_bytes())
        self.tool_id = None
        self._tool_name = 'official-bf16-observation-' + str(id(self))
        self._registered = {}
        self._configured = {}
        self._line_callback = self._monitor_line
        self._return_callback = self._monitor_return
        self._target_lines = {
            self.codes['_attention']: frozenset(self.points[n] for n in ('score', 'exp', 'store')),
            self.codes['_matrix_step']: frozenset((self.points['matrix'],)),
        }
        self.profiled_loaded_functions_checked = verify_profiled_dependencies(owner, self.sources)

    def __enter__(self):
        require(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1],
                'participating services changed before entry')
        require(verify_profiled_dependencies(self.owner, self.sources) ==
                self.profiled_loaded_functions_checked,
                'profiled loaded dependencies changed before entry')
        return super().__enter__()

    def __exit__(self, kind, error, traceback):
        # Inherited cleanup always runs before an extra verification can fail.
        try:
            return super().__exit__(kind, error, traceback)
        finally:
            try:
                require(verify_profiled_dependencies(self.owner, self.sources) ==
                        self.profiled_loaded_functions_checked,
                        'profiled loaded dependency inventory changed')
            except Exception as failure:
                self.error = self.error or str(failure)
                raise

    def report(self):
        report = super().report()
        report['profiled_observation_source_version'] = SOURCE_VERSION
        report['profiled_observation_source_sha256'] = {name: self.sources[name] for name in EXTRA_SOURCES}
        report['profiled_loaded_python_functions_checked'] = self.profiled_loaded_functions_checked
        report['matrix_service_type'] = 'ProfiledMatrixService'
        return report
