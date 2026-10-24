"""Metadata-only regression: extracts the real guard AST; imports no model/native."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


def require(ok, why):
    if not ok:
        raise ValueError(why)


def extract(raw):
    tree = ast.parse(raw)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FullBlockCoordinator'))
    fn = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_check_resources'))
    allocation = fn.body[1].value.args[0]
    ns = {'require': require}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), 'extracted_guard', 'exec'), ns)
    e = ast.Expression(ast.Lambda(
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self')],
                           kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=allocation,
    ))
    return (ns['_check_resources'], eval(compile(ast.fix_missing_locations(e), 'allocation_expression', 'eval')))


def fixture(n):
    regions = {1048576 + 64 * i: object() for i in range(n)}
    scalar = object()
    vector = object()
    trace = []

    def identity():
        trace.append('identity')
        return ('stable',)

    def address():
        trace.append('matrix_address')
        return 123
    f = NS(
        memory=NS(regions=regions),
        allocations=dict(regions),
        resource_identity=('stable',),
        _resource_identity=identity,
        matrix=NS(resource_address=123, lib=NS(matrix_accumulator_address=address)),
        scalar=scalar,
        vector=vector,
        trace=trace,
    )
    for name in ('rms', 'conv', 'prep', 'chunk', 'norm', 'elementwise'):
        setattr(f, name, NS(scalar=scalar))
    f.chunk.vector = vector
    f.chunk.host_batch = True
    f.chunk.geometry = (16, 128, 128)
    return f
mutations = {
    'valid': lambda f: None,
    'delete': lambda f: f.memory.regions.pop(next(iter(f.memory.regions))),
    'extra': lambda f: f.memory.regions.update({-1: object()}),
    'wrong_same_count': lambda f: (f.memory.regions.pop(next(iter(f.memory.regions))), f.memory.regions.update({-1: object()})),
    'replace_region': lambda f: f.memory.regions.update({next(iter(f.memory.regions)): object()}),
    'expected_deleted': lambda f: f.allocations.pop(next(iter(f.allocations))),
    'expected_added': lambda f: f.allocations.update({-1: object()}),
    'expected_replaced': lambda f: f.allocations.update({next(iter(f.allocations)): object()}),
    'resource_changed': lambda f: setattr(f, 'resource_identity', ('changed',)),
    'matrix_address': lambda f: setattr(f.matrix, 'resource_address', 999),
    'scalar_route': lambda f: setattr(f.prep, 'scalar', object()),
    'vector_route': lambda f: setattr(f.chunk, 'vector', object()),
    'batch_off': lambda f: setattr(f.chunk, 'host_batch', False),
    'geometry': lambda f: setattr(f.chunk, 'geometry', (16, 64, 128)),
}


def outcome(fn, f):
    try:
        fn(f)
        return ('pass', list(f.trace))
    except Exception as e:
        return (type(e).__name__, str(e), list(f.trace))


def cases(original, changed):
    tests = 0
    for n in (1, 16, 57, 128):
        for name, mutate in mutations.items():
            results = []
            for fn in (original, changed):
                f = fixture(n)
                mutate(f)
                results.append(outcome(fn, f))
            require(results[0] == results[1], (n, name, results))
            require((results[0][0] == 'pass') == (name == 'valid'), name)
            tests += 1
    for target in ('memory', 'expected'):
        for fn in (original, changed):
            f = fixture(57)
            alias = f.memory.regions if target == 'memory' else f.allocations
            fn(f)
            key = next(iter(alias))
            saved = alias[key]
            alias[key] = object()
            require(outcome(fn, f)[0] == 'ValueError', 'mutation must fail closed')
            alias[key] = saved
            fn(f)
        tests += 1
    for n in (0, 1, 16, 57, 128):
        for fn in (original, changed):
            f = fixture(n)
            f.memory.regions = dict(reversed(list(f.memory.regions.items())))
            fn(f)
        tests += 1

    class Equal:

        def __eq__(self, other):
            return True
    for value in (None, False, 0, Equal()):
        for fn in (original, changed):
            f = fixture(1)
            key = next(iter(f.allocations))
            f.allocations[key] = value
            f.memory.regions = {key: value}
            fn(f)
            f.memory.regions = {key + 64: value}
            require(outcome(fn, f)[0] == 'ValueError', 'mutation must fail closed')
        tests += 1
    for fn in (original, changed):
        f = fixture(1)
        key = next(iter(f.allocations))
        f.allocations[key] = Equal()
        f.memory.regions[key] = Equal()
        require(outcome(fn, f)[0] == 'ValueError', 'mutation must fail closed')
    tests += 1
    from types import MappingProxyType

    class LyingKeys(dict):

        def keys(self):
            return {k for k in super().keys() if k >= 0}

    class EmptyKeys(dict):

        def keys(self):
            return set()

    class ChangedIteration(dict):

        def __iter__(self):
            return iter([-999])
    for factory in (dict, LyingKeys, EmptyKeys, ChangedIteration, MappingProxyType):
        for side in ('regions', 'allocations'):
            for mutate_extra in (False, True):
                values = []
                for fn in (original, changed):
                    f = fixture(16)
                    mapping = f.memory.regions if side == 'regions' else f.allocations
                    if mutate_extra:
                        mapping[-1] = object()
                    if side == 'regions':
                        f.memory.regions = factory(mapping)
                    else:
                        f.allocations = factory(mapping)
                    values.append(outcome(fn, f))
                require(values[0] == values[1], (factory, side, mutate_extra, values))
                tests += 1
    for fn in (original, changed):
        f = fixture(16)
        fn(f)
        f.memory.regions = LyingKeys(f.memory.regions)
        f.memory.regions[-1] = object()
        require(outcome(fn, f)[0] == 'ValueError', 'mutation must fail closed')
    tests += 1
    return tests


class AllocationGuardColdTests(unittest.TestCase):

    def test_equivalence_and_mutation_cases(self):
        candidate = Path(__file__).with_name('full_driver.py').read_bytes()
        new = b'(self.memory.regions.keys() == self.allocations.keys()\n                 if type(self.memory.regions) is dict and type(self.allocations) is dict\n                 else set(self.memory.regions) == set(self.allocations))'
        old = b'set(self.memory.regions) == set(self.allocations)'
        self.assertEqual(candidate.count(new), 1)
        base = candidate.replace(new, old)
        original, _ = extract(base)
        changed, _ = extract(candidate)
        self.assertEqual(cases(original, changed), 89)
if __name__ == '__main__':
    unittest.main(verbosity=2)
