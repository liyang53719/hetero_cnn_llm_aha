"""Import-anchored identity guards for the existing shared software Scalars.

No arithmetic, source reads, native loads or policy selection happen in checks.
These detect persistent rebinding at checked boundaries, not arbitrary Python
code, a mutate/use/restore callback, or modifications made before this module
was imported. Checks do not revalidate the host FP environment or establish
source-to-loaded-bytecode equivalence, arbitrary owner-method integrity or
native execution correctness. File identity is a separate pre/post snapshot.
DecayScalar is guarded for standalone tests; this does NOT admit it into the
full-block coordinator or widen any exp/layout policy.
"""
from dataclasses import dataclass
from types import FunctionType, MethodType

from . import rms_owner as rms
from .conv import scalar as conv
from .prep import scalar as prep
from ..qwen35_35b_exp import scalar as decay
from .chunk import exp_policy


SCALAR_SOURCE_FILES = (
    'candidates/qwen35_gdn_prefill/scalar_identity.py',
    'candidates/qwen35_gdn_prefill/rms_owner.py',
    'candidates/qwen35_gdn_prefill/conv/scalar.py',
    'candidates/qwen35_gdn_prefill/prep/scalar.py',
    'candidates/qwen35_35b_exp/scalar.py',
)
SCHEMA = 'shared_scalar_callable_identity_v1'


def _changed(detail):
    raise ValueError('Scalar arithmetic binding changed: ' + detail)


@dataclass(frozen=True)
class _Binding:
    owner: object
    name: str
    value: object
    code: object = None
    defaults: object = None
    kwdefaults: object = None
    closure: tuple = ()

    @classmethod
    def capture(cls, owner, name):
        value = vars(owner)[name]
        if type(value) is FunctionType:
            return cls(owner, name, value, value.__code__, value.__defaults__,
                       None if value.__kwdefaults__ is None else tuple((k, type(v), v) for k, v in value.__kwdefaults__.items()),
                       tuple(cell.cell_contents for cell in value.__closure__ or ()))
        return cls(owner, name, value)

    def check(self):
        if vars(self.owner).get(self.name) is not self.value:
            _changed(self.name)
        if self.code is not None:
            fn = self.value
            if (fn.__code__ is not self.code or fn.__defaults__ is not self.defaults or
                    (None if fn.__kwdefaults__ is None else tuple((k, type(v), v) for k, v in fn.__kwdefaults__.items())) != self.kwdefaults or
                    len(fn.__closure__ or ()) != len(self.closure) or
                    any(cell.cell_contents is not value for cell, value in
                        zip(fn.__closure__ or (), self.closure))):
                _changed(self.name + ' code/defaults/closure')


# Retain original class definitions AND every defining op in the super() chain.
# Capturing only scalar.op would miss a replaced inherited implementation.
_CLASSES = (rms.SharedScalar, conv.ConvScalar, prep.PrepScalar, decay.DecayScalar)
_METHODS = (('acquire', 'release', 'op'), ('_exp_node', 'op'),
            ('_soft_node', 'op'), ('_node', 'op', '_evaluate_exp'))
_CLASS_PINS = tuple((cls, cls.__mro__, cls.__bases__, tuple(_Binding.capture(cls, name) for name in names))
                    for cls, names in zip(_CLASSES, _METHODS))
_COMMON = ('ArithmeticFault', 'finite', 'value', 'word', 'require', 'np')
_MODULE_PINS = (
    (rms, (*_COMMON, '_tiny_inexact', 'struct', 'SharedScalar')),
    (conv, (*_COMMON, 'EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'SharedScalar', 'ConvScalar')),
    (prep, (*_COMMON, 'EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'SOFT_COEFFICIENTS', 'ConvScalar', 'PrepScalar')),
    (decay, (*_COMMON, 'EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'LN2_HI', 'LN2_LO',
             'MIN_NORMAL', 'OPERATION', 'POLICY', 'PrepScalar', 'DecayScalar')),
)
_MODULE_PINS = tuple(tuple(_Binding.capture(module, name) for name in names)
                     for module, names in _MODULE_PINS)
_NUMPY_PINS = tuple(_Binding.capture(rms.np, name) for name in
                    ('add', 'multiply', 'divide', 'sqrt', 'float32', 'errstate'))
_DECAY_NUMPY_PIN = _Binding.capture(rms.np, 'rint')
_STRUCT_PINS = tuple(_Binding.capture(rms.struct, name) for name in ('pack', 'unpack'))
_RESOLVED = tuple({name: getattr(cls, name) for name in
                  ('acquire', 'release', 'op', '_exp_node', '_soft_node') +
                  (('_node', '_evaluate_exp') if cls is decay.DecayScalar else ())}
                 for cls in (prep.PrepScalar, decay.DecayScalar))

_ROUTE_PINS = tuple(_Binding.capture(exp_policy, name) for name in
                    ('operation', 'LEGACY_EXP', 'CANDIDATE_POLICIES', 'OPERATION'))


def legacy_exp_routing_identity(policy_module):
    """Keep the existing coordinator's operation selection import-anchored."""
    if policy_module is not _ROUTE_PINS[0].owner:
        _changed('chunk exp_policy module alias')
    for pin in _ROUTE_PINS:
        pin.check()
    return tuple(pin.value for pin in _ROUTE_PINS)


class ScalarIdentityGuard:
    """Validate canonical imported callables and freeze this instance's flags."""
    def __init__(self, scalar):
        if type(scalar) not in (_CLASSES[2], _CLASSES[3]):
            _changed('exact PrepScalar or DecayScalar required')
        self._scalar = scalar
        self._decay = type(scalar) is _CLASSES[3]
        self._flags = self._configuration(scalar)
        self.check(scalar)

    def _configuration(self, scalar):
        names = ('enable_softplus',) + (('enable_ieee_exp',) if self._decay else ())
        values = tuple(getattr(scalar, name, None) for name in names)
        if any(type(value) is not bool for value in values):
            _changed('literal boolean enable flags required')
        return values

    def check(self, scalar):
        expected_type = _CLASSES[3 if self._decay else 2]
        if scalar is not self._scalar or type(scalar) is not expected_type:
            _changed('shared instance/type')
        for cls, mro, bases, pins in _CLASS_PINS[:4 if self._decay else 3]:
            if cls.__mro__ != mro or cls.__bases__ != bases or '__getattribute__' in vars(cls) or '__getattr__' in vars(cls):
                _changed('class resolution/MRO')
            for pin in pins:
                pin.check()
        for pins in _MODULE_PINS[:4 if self._decay else 3]:
            for pin in pins:
                pin.check()
        for pin in (*_NUMPY_PINS, *_STRUCT_PINS, *((_DECAY_NUMPY_PIN,) if self._decay else ())):
            pin.check()
        for name, expected in _RESOLVED[self._decay].items():
            bound = getattr(scalar, name)
            if (name in vars(scalar) or type(bound) is not MethodType or
                    bound.__self__ is not scalar or bound.__func__ is not expected):
                _changed('resolved ' + name)
        flags = self._configuration(scalar)
        if flags != self._flags:
            _changed('enable flags')
        return (id(scalar), expected_type, flags)

    def report(self, scalar):
        self.check(scalar)
        return dict(schema=SCHEMA, implementation=type(scalar).__name__,
                    enable_softplus=self._flags[0],
                    enable_ieee_exp=self._flags[1] if self._decay else None,
                    guarded_methods=sorted(_RESOLVED[self._decay]),
                    boundary_integrity_only=True, numerical_acceptance=None,
                    production_new_opcode_bound=False)
