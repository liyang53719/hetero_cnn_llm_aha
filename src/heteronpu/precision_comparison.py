"""C02.1 source-bound comparison formulas; not an official-model threshold.

The existing block_receipt v1 verifier remains bit-exact and unchanged. This
module registers independently supplied contracts for C02.2; a receipt cannot
select its own tolerance. Registration verifies bytes and formula semantics,
not whether the named source is authoritative. Callers must pin a trusted hash.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from pathlib import Path
import struct
from . import block_receipt as br
from .precision_policy import node_dtype

EQUATIONS = {
    'bit_exact': 'actual_bits == reference_bits; nonfinite forbidden',
    'abs_rel_elementwise_v1': 'forall i: abs(a[i]-r[i]) <= atol + rtol*abs(r[i])',
}
DISCRETE = frozenset({'route', 'index', 'selection', 'counter'})


@dataclass(frozen=True)
class Formula:
    name: str
    atol: float
    rtol: float
    source: Path
    digest: str
    evidence_class: str
    stamp: tuple[int, ...]


class FormulaRegistry:
    def __init__(self) -> None:
        self._formulas: dict[str, Formula] = {}

    def register(self, root: Path, source: str, expected_sha256: str) -> str:
        br.hash_text(expected_sha256, 64, 'formula source')
        path = br.safe_file(root, source)
        stamp = br.file_stamp(path)
        br.need(br.sha_file(path) == expected_sha256, 'formula source hash')
        spec = br.read_json(path)
        br.keys(spec, {'version', 'contract_id', 'formula', 'equation', 'parameters',
                       'source_revision', 'source_anchor', 'evidence_class'}, 'formula source')
        br.integer(spec['version'], 1, 1, 'formula version')
        br.hash_text(spec['source_revision'], 40, 'source revision')
        br.need(isinstance(spec['source_anchor'], str) and bool(spec['source_anchor'].strip()), 'missing source anchor')
        ident = spec['contract_id']
        br.need(isinstance(ident, str) and bool(ident.strip()) and ident not in self._formulas, 'duplicate/empty contract')
        name = spec['formula']
        if not isinstance(name, str) or name not in EQUATIONS:
            raise br.ComparisonUnavailable('unregistered formula: ' + str(name))
        br.need(spec['equation'] == EQUATIONS[name], 'formula definition mismatch')
        br.need(spec['evidence_class'] in ('synthetic_test', 'source_bound'), 'evidence class')
        params = spec['parameters']
        br.keys(params, set() if name == 'bit_exact' else {'atol', 'rtol'}, 'parameters')
        for value in params.values():
            br.need(type(value) in (float, int), 'tolerance must be numeric, not bool')
            try:
                br.need(math.isfinite(value) and value >= 0, 'nonfinite/negative tolerance')
            except OverflowError as error:
                raise br.ReceiptError('tolerance overflow') from error
        br.need(br.sha_file(path) == expected_sha256 and br.file_stamp(path) == stamp, 'formula source changed')
        self._formulas[ident] = Formula(name, float(params.get('atol', 0)), float(params.get('rtol', 0)),
                                       path, expected_sha256, spec['evidence_class'], stamp)
        return ident

    def get(self, ident: str) -> Formula:
        if not isinstance(ident, str) or ident not in self._formulas:
            raise br.ComparisonUnavailable('missing registered contract: ' + str(ident))
        formula = self._formulas[ident]
        br.need(br.file_stamp(formula.source) == formula.stamp and br.sha_file(formula.source) == formula.digest,
                'formula source changed after registration')
        return formula

    def compare(self, ident: str, actual: Path, reference: Path, tensor: dict,
                *, semantics: str, producer: dict | None = None,
                fp32_indices: frozenset[int] = frozenset()) -> dict:
        formula = self.get(ident)
        br.need(semantics in DISCRETE | {'continuous'}, 'unknown comparison semantics')
        dtype = tensor['dtype']
        size = br.tensor_bytes(tensor)
        if semantics in DISCRETE or dtype in ('u32le', 'i32le'):
            br.need(formula.name == 'bit_exact', 'discrete values require bit-exact comparison')
        else:
            br.need(producer is not None, 'continuous tensor requires producer dtype policy')
            expected = {'FP32': 'f32le', 'BF16': 'bf16le'}[node_dtype(producer, fp32_indices)]
            br.need(dtype == expected, 'producer precision policy mismatch')
        br.need(not actual.is_symlink() and not reference.is_symlink(), 'symlink tensor')
        stamps = {p: br.file_stamp(p) for p in (actual, reference)}
        # Shared full-byte validation: sizes, finite values, aliases, hashes and
        # exact differences. A numerical metric never skips an element.
        result = br.compare_files(actual, reference, dtype, size)
        failed = result['different_elements']
        first = result['first_difference']
        maximum = 0.0
        if formula.name != 'bit_exact':
            failed = checked = 0
            first = None
            width = br.WIDTHS[dtype]
            with actual.open('rb') as a, reference.open('rb') as r:
                while checked * width < size:
                    amount = min(1 << 20, size - checked * width)
                    x, y = a.read(amount), r.read(amount)
                    br.need(len(x) == len(y) == amount, 'tensor changed during metric')
                    br._finite(x, dtype); br._finite(y, dtype)
                    for i, (av, rv) in enumerate(zip(_values(x, dtype), _values(y, dtype), strict=True)):
                        delta = abs(av - rv)
                        limit = formula.atol + formula.rtol * abs(rv)
                        br.need(math.isfinite(delta) and math.isfinite(limit), 'metric arithmetic overflow')
                        maximum = max(maximum, delta)
                        if delta > limit:
                            failed += 1
                            if first is None:
                                first = checked + i
                    checked += amount // width
                br.need(a.read(1) == r.read(1) == b'', 'tensor grew during metric')
            br.need(checked == result['elements'], 'incomplete metric coverage')
        for p, stamp in stamps.items():
            br.need(br.file_stamp(p) == stamp, 'tensor changed during comparison')
        br.need(br.sha_file(actual) == result['actual_sha256'] and br.sha_file(reference) == result['reference_sha256'],
                'tensor changed after full-byte comparison')
        self.get(ident)
        return dict(result, passed=failed == 0, failed_elements=failed, first_failure=first,
                    max_absolute_error=maximum if formula.name != 'bit_exact' else None,
                    formula=formula.name, contract_id=ident, source_sha256=formula.digest,
                    evidence_class=formula.evidence_class, hardware_execution_verified=False,
                    official_model_accepted=False)


def _values(data: bytes, dtype: str):
    if dtype == 'f32le':
        return (v for (v,) in struct.iter_unpack('<f', data))
    br.need(dtype == 'bf16le', 'approximate metric requires floating tensor')
    return (struct.unpack('<f', struct.pack('<I', v << 16))[0] for (v,) in struct.iter_unpack('<H', data))
