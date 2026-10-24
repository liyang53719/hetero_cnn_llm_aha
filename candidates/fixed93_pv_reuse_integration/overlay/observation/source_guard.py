"""Read-only identity checks for the TEMP PV normalization reuse candidate.

Import is stdlib-only and never imports/constructs the runtime or loads a DSO.
Construct after the caller has independently admitted and constructed services.
No reference values, arithmetic replacement, monkeypatch, or native acceptance.
"""
from array import array
import ast
import builtins
from dataclasses import asdict, fields, is_dataclass
import hashlib
import inspect
import json
from pathlib import Path
import sys
import threading
import types

PROFILE_MODULE = 'candidates.qwen2_resident_matrix.dense_block_reduce.profile'
PROFILED_MODULE = 'candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding'
OFFICIAL_MATRIX_MODULE = 'candidates.qwen2_resident_matrix.official_bf16.dense_silu'

PREDECESSOR_REVIEWED_MANIFEST_SHA256 = '26928f829488600765cefa2d836f4afe32413e03798ae0eb958bfd016994e13d'
REVIEWED_MANIFEST_SHA256 = None  # Candidate does not inherit the predecessor's review.
CANDIDATE_IDENTITY = 'fixed93-pv-normalization-reuse-source-candidate-v1'
OWNER_MODULE = 'candidates.qwen2_fixed93_attention.owner'
CLIENT_MODULE = 'candidates.qwen2_fixed93_attention.client'
BASE_MODULE = 'candidates.qwen2_resident_matrix.ffn_attention.attention_owner'
PREFIX_MODULE = 'candidates.qwen2_resident_matrix.ffn_public.prefix_owners'
ARITHMETIC_MODULE = 'candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic'
MATRIX_MODULE = 'candidates.qwen2_resident_matrix.ffn_attention.matrix_service'
PINS = {
    OWNER_MODULE: 'b18172eb9af3f047eaed5aa3d6e40741e57add5b0b856c6817017cc16693bc0e',
    CLIENT_MODULE: '5d23d47f51b2db59d435f47d073314921988e3079e69422acc3746d541afadaa',
    'candidates.qwen2_resident_matrix.official_bf16.owners': '0256c3ad3a90874bb032e39b5bdf28014a05f4ab08960c5bcf952cd5fdd5d05a',
    BASE_MODULE: '65d823ebebdb50cae98c0ff8c9c1c5631ebc298595cc5c28c71ba7a22890f6d8',
    MATRIX_MODULE: 'd3cc6f8ddbe08617c1c476d3b15e2033031e3e42b121233baa9c1b5835250698',
    'candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe': 'a58c7e32d509a368a5127a87165f0a9c8a4f0df6a58a0c78f031d4e337ef580d',
    ARITHMETIC_MODULE: '5391f807b8164511d6e3e5af156f1fb3dd5f298bb0dca66504c6b818d135f880',
    PREFIX_MODULE: '9001c58559d10a0f72aea1c00f85a0da6508a3c729dd2469433f831a0da5ea8b',
}
PINS['candidates.qwen2_resident_matrix.dense_block_reduce.profile'] = '1b2b558317d18f3e5218ad83368556628aec7c0012211050c91888ac563514f2'
PINS['candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding'] = '33ea0786d537aa7de59b19ff55cb515f2afeaee780f4a9f1faeb42402da19593'
PINS['candidates.qwen2_resident_matrix.official_bf16.dense_silu'] = 'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699'
REQUIRED_NATIVE_SOURCES = {
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp': '0d8790446c1d4b30c06dfcfd35fcc21faf6a8cd63e415412444f4e38a95f8fcb',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp': 'bdd7513bd788c03ac92be1d7c2f3553d3d7e0723ce1ac2892e93dcef58782ef1',
}
SELECTED = {
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockTop.scala': '15cc34f041228f38d69b15868a9f9c45fb3f9ea53a9275ec6a6d9fd70b4b0c25',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala': '94e6198a060044ae58a90328394ec8d11fe3311647fef62c1a1b975f2504ff4a',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala': 'f14c7f27f65d9679ea1241607eede3bc26903ece4385e62317bf40d6dce963e3',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala': '3b7f25537da7492d3c706c55129ca5ed0a18d9c2e0ec4f5d9e6e43b1ae2210d4',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/PackedAttentionStreamClient.scala': '58fb22a6f78a224241b9b0368e3108e5c403a9ea7106527061b140ff5d83b8c0',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala': '83516358916a6bb4a4816d700f056aae028c62dd0cc8891ea97f0cb9fea958cc',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala': '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala': '3d0afaff91e8cc8915e99ad3276339bda7d044404b39cd1c2a77c621b990f5ff',
    'candidates/qwen2_resident_matrix/host93_source_recovery/source/EmitCanonicalHost93.scala': 'ebc35a597dc3be2374efa7408ea152ff954f37483132b1d03e0d8c902628705d',
}
SENTINEL = 0xa5963cc3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_path(root, relative):
    require(type(relative) is str and relative and not Path(relative).is_absolute(), 'invalid closure path')
    root = Path(root).resolve()
    p = (root / relative).resolve()
    require(p.is_relative_to(root), 'closure path escaped source root')
    return p


def verify_closure(source_root, closure_manifest, manifest_sha256):
    """Only inspect bytes; never call historical guards or build/load helpers."""
    root, manifest = Path(source_root).resolve(), Path(closure_manifest).resolve()
    raw = manifest.read_bytes()
    require(sha(raw) == manifest_sha256, 'unverified/changed closure manifest')
    data = json.loads(raw)
    require(data.get('schema') == 'fixed93-pv-reuse-source-manifest-v1' and
            data.get('candidate_identity') == CANDIDATE_IDENTITY and
            data.get('evidence_contract') == 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1' and
            data.get('reviewed_manifest_sha256', 'missing') is None and
            data.get('predecessor_reviewed_manifest_sha256') == PREDECESSOR_REVIEWED_MANIFEST_SHA256 and
            data.get('candidate_review_status') == 'SOURCE_PREPARED_REVIEW_SEPARATE',
            'candidate identity required; predecessor R3 review cannot authorize changed sources')
    sources, sizes = data.get('source_sha256'), data.get('source_bytes')
    require(isinstance(sources, dict) and isinstance(sizes, dict) and sources.keys() == sizes.keys(), 'closure hash/size inventory mismatch')
    for module, digest in PINS.items():
        require(sources.get(module.replace('.', '/') + '.py') == digest, 'required source not pinned: ' + module)
    for relative, digest in REQUIRED_NATIVE_SOURCES.items():
        require(sources.get(relative) == digest, 'required native source not pinned: ' + relative)
    for relative, digest in sources.items():
        content = relative_path(root, relative).read_bytes()
        require(len(content) == sizes[relative] and sha(content) == digest, 'source closure drift: ' + relative)
    require(data.get('selected_source_sha256') == SELECTED, 'selected fixed93 witness identity mismatch')
    for relative, digest in SELECTED.items():
        require(sha(relative_path(manifest.parent / 'selected', relative).read_bytes()) == digest,
                'selected fixed93 witness drift: ' + relative)
    return sha(raw), dict(sources)


def code_child(code, name):
    found = [x for x in code.co_consts if isinstance(x, types.CodeType) and x.co_name == name]
    require(len(found) == 1, 'ambiguous compiled function: ' + name)
    return found[0]


def same_code(a, b):
    if not (a == b and a.co_filename == b.co_filename and a.co_firstlineno == b.co_firstlineno
            and a.co_linetable == b.co_linetable and a.co_exceptiontable == b.co_exceptiontable):
        return False
    return all(same_code(x, y) for x, y in zip(a.co_consts, b.co_consts) if isinstance(x, types.CodeType))


def literal(node, namespace, root, path):
    """Restricted source constants only. Never execute source expressions."""
    if isinstance(node, ast.Name):
        require(node.id in namespace, 'unknown source constant: ' + node.id)
        return namespace[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.LShift, ast.Sub, ast.Add)):
        a, b = literal(node.left, namespace, root, path), literal(node.right, namespace, root, path)
        if isinstance(node.op, ast.LShift):
            return a << b
        return a - b if isinstance(node.op, ast.Sub) else a + b
    if isinstance(node, ast.Tuple):
        return tuple(literal(x, namespace, root, path) for x in node.elts)
    if isinstance(node, ast.Dict):
        return {literal(k, namespace, root, path): literal(v, namespace, root, path)
                for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == 'MappingProxyType':
            require(len(node.args) == 1 and not node.keywords, 'mapping constant expression drift')
            return types.MappingProxyType(literal(node.args[0], namespace, root, path))
        if node.func.id == 'ReductionProfile':
            # Return a tagged description. Do not call a model constructor.
            require(not node.keywords, 'profile constant expression drift')
            return ('__profile_literal__', tuple(literal(x, namespace, root, path) for x in node.args))
    return ast.literal_eval(node)


def module_reference(node, namespace):
    if isinstance(node, ast.Name):
        return namespace[node.id] if node.id in namespace else vars(builtins)[node.id]
    require(isinstance(node, ast.Attribute), 'unsupported class base expression')
    return getattr(module_reference(node.value, namespace), node.attr)


def _constant_equal(actual, expected):
    if type(expected) is tuple and len(expected) == 2 and expected[0] == '__profile_literal__':
        return (is_dataclass(actual) and tuple(getattr(actual, f.name) for f in fields(actual)) == expected[1])
    if isinstance(expected, types.MappingProxyType):
        return type(actual) is types.MappingProxyType and dict(actual) == dict(expected)
    return actual == expected


def _method_function(item):
    if isinstance(item, (classmethod, staticmethod)):
        return item.__func__
    if isinstance(item, property):
        require(item.fset is None and item.fdel is None, 'unexpected property mutation accessor')
        return item.fget
    return item


def verify_loaded(owner, root):
    """Inspect existing loaded modules; never import a DUT or invoke a DUT method."""
    require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12)
            and not sys.flags.optimize, 'CPython 3.12 without -O is required')
    modules = {name: sys.modules.get(name) for name in PINS}
    require(all(isinstance(x, types.ModuleType) for x in modules.values()), 'required loaded dependency missing')
    require(type(owner) is modules[OWNER_MODULE].Fixed93AttentionOwner, 'exact Fixed93AttentionOwner required')
    expected_owner_mro = (modules[OWNER_MODULE].Fixed93AttentionOwner,
        modules['candidates.qwen2_resident_matrix.official_bf16.owners'].OfficialAttentionOwner,
        modules[BASE_MODULE].AttentionOwner, modules[PREFIX_MODULE].PrefixOwner, object)
    require(type(owner).__mro__ == expected_owner_mro, 'exact owner MRO required')
    expected_matrix_mro = (modules[PROFILED_MODULE].ProfiledMatrixService,
        modules[OFFICIAL_MATRIX_MODULE].OfficialMatrixService, modules[MATRIX_MODULE].MatrixService, object)
    require(type(owner.matrix).__mro__ == expected_matrix_mro, 'exact Profiled/Official/Matrix MRO required')
    require(type(owner.scalar) is modules[ARITHMETIC_MODULE].ScalarService, 'exact ScalarService required')
    profile = owner.matrix.profile
    require(type(profile) is modules[PROFILE_MODULE].ReductionProfile and
        getattr(type(profile), '__dataclass_params__').frozen and
        profile is modules[PROFILE_MODULE].QWEN2_QKV_PROFILE and
        (profile.identity, profile.ranges, profile.pair_reverse, profile.source_sha256) == (
            'torch210cpu_onednn371_avx512_core_bf16_4t_qkv_k1536',
            ((0, 1024), (1024, 1536)), True,
            '07008af966dbe4d64b10f75c37e4d19e17159e3708543982a70c8ec996f1d5a5'),
        'immutable exact original QKV profile required')
    checked = 0
    for name, module in modules.items():
        path = root / (name.replace('.', '/') + '.py')
        require(Path(module.__file__).resolve() == path, 'loaded dependency outside source closure: ' + name)
        text = path.read_text()
        compiled, tree = compile(text, str(path), 'exec', dont_inherit=True, optimize=0), ast.parse(text)
        # Build a separate source-literal environment in declaration order.
        constants = {'ROOT': root, 'HERE': path.parent}
        def function(actual, node, expected):
            nonlocal checked
            actual = _method_function(actual)
            require(isinstance(actual, types.FunctionType) and same_code(actual.__code__, expected),
                    'loaded function code changed: ' + name + '.' + node.name)
            args = tuple(literal(x, constants, root, path) for x in node.args.defaults) or None
            kw = {a.arg: literal(v, constants, root, path) for a, v in zip(node.args.kwonlyargs, node.args.kw_defaults) if v is not None} or None
            require(actual.__defaults__ == args and actual.__kwdefaults__ == kw and actual.__globals__ is module.__dict__,
                    'loaded defaults/globals changed: ' + name + '.' + node.name)
            checked += 1
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                function(getattr(module, node.name), node, code_child(compiled, node.name))
            elif isinstance(node, ast.ClassDef):
                cls = getattr(module, node.name)
                require(isinstance(cls, type) and cls.__module__ == name, 'loaded class identity changed')
                expected_bases = tuple(module_reference(x, module.__dict__) for x in node.bases) or (object,)
                require(cls.__bases__ == expected_bases, 'loaded inheritance changed: ' + node.name)
                class_code = code_child(compiled, node.name)
                for method in node.body:
                    if isinstance(method, ast.FunctionDef):
                        function(vars(cls).get(method.name), method, code_child(class_code, method.name))
                    elif isinstance(method, ast.Assign) and all(isinstance(x, ast.Name) for x in method.targets):
                        expected = literal(method.value, constants, root, path)
                        for target in method.targets:
                            require(_constant_equal(getattr(cls, target.id), expected), 'loaded class constant changed')
            elif isinstance(node, ast.Assign):
                names = [x.id for x in node.targets if isinstance(x, ast.Name)]
                if 'ROOT' in names or 'HERE' in names:
                    expected = root if 'ROOT' in names else path.parent
                else:
                    expected = literal(node.value, constants, root, path)
                for target in node.targets:
                    pairs = zip(target.elts, expected) if isinstance(target, ast.Tuple) else [(target, expected)]
                    for variable, val in pairs:
                        require(isinstance(variable, ast.Name) and _constant_equal(getattr(module, variable.id), val),
                                'loaded constant changed: ' + name)
                        constants[variable.id] = val
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = module.__package__.split('.')
                    imported = '.'.join(parts[:len(parts)-node.level+1] + ([node.module] if node.module else []))
                else:
                    imported = node.module
                dependency = sys.modules.get(imported)
                require(dependency is not None, 'loaded imported module missing: ' + str(imported))
                for alias in node.names:
                    require(getattr(module, alias.asname or alias.name) is getattr(dependency, alias.name),
                            'loaded imported dependency changed: ' + name + '.' + alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    require(getattr(module, alias.asname or alias.name.split('.')[0]) is sys.modules[alias.name if alias.asname else alias.name.split('.')[0]],
                            'loaded module import changed: ' + name)
    for instance in (owner, owner.scalar, owner.matrix):
        names = {n for cls in type(instance).__mro__ for n in vars(cls)}
        for name in names:
            item = inspect.getattr_static(type(instance), name)
            if isinstance(item, types.FunctionType):
                bound = getattr(instance, name)
                require(isinstance(bound, types.MethodType) and bound.__func__ is item, 'instance method replacement: ' + name)
            elif isinstance(item, staticmethod):
                require(getattr(instance, name) is item.__func__, 'instance staticmethod replacement: ' + name)
            elif isinstance(item, property):
                require(name not in vars(instance), 'instance property shadow: ' + name)
    # Resolve inherited property deliberately without executing its native getter.
    ticket = inspect.getattr_static(type(owner.matrix), 'ticket')
    require(ticket is vars(modules[MATRIX_MODULE].MatrixService)['ticket'] and
            isinstance(ticket, property), 'inherited ticket property changed/omitted')
    bindings = vars(owner.matrix).get('_bindings')
    require(type(bindings) is dict, 'exact original Dense binding storage required')
    binding_type = modules[OFFICIAL_MATRIX_MODULE].DenseBinding
    for tag, binding in bindings.items():
        require(type(binding) is binding_type and type(tag) is int and dict(binding.job_fields)['tag'] == tag and
                getattr(binding_type, '__dataclass_params__').frozen, 'Dense binding type/identity drift')
    return checked
