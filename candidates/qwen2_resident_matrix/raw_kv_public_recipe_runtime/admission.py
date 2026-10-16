"""Hash-only admission of the fresh paired-recipe Public reference producer.

The frozen Public validator still owns the native geometry, original verdicts,
export layout and all 232 export records. This extension binds its producer to
both real strict-kernel receipts and fresh same-byte dispatch metadata. It does
not import a generated gate, load a library, decode arrays, or launch a producer.
"""
import hashlib
from pathlib import Path

from ..raw_kv_public_fresh import assets as files
from ..raw_kv_native_qk_run import phase, runtime as native_runtime
from ..raw_kv_native_qk_run import dispatch_diagnostic as diagnostic
from ..raw_kv_public_recipe_profile import dispatch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_runtime/admission.py'
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
GENERATED_MODULE = 'generated/qwen2_layer0_model_gate.py'
MAX_MODULE_BYTES = 1048576
MAX_LIBRARY_BYTES = 16 * 1024 * 1024
MAX_RECEIPT_BYTES = 131072
CASES = (('native16', 'native_m16', 16), ('native128', 'native', 128))


def need(ok, reason='fresh Public paired-recipe admission'):
    if not ok:
        raise ValueError(reason)


def validate_manifest_extension(value):
    """Validate only the new ``recipe`` value; never read referenced paths."""
    files.exact(value, ('generated_module', 'qk', 'qkv', 'native16', 'native128'),
                'exact fresh recipe schema required')
    files.record(value['generated_module'], expected=native_runtime.GENERATED_MODULE_SHA256)
    need(value['generated_module']['path'] == GENERATED_MODULE and
         0 < value['generated_module']['bytes'] <= MAX_MODULE_BYTES,
         'fresh generated recipe module path/size differs')
    for role, kernel in (('qk', phase.kernel), ('qkv', phase.qkv_kernel)):
        library = value[role]
        files.exact(library, ('binary', 'receipt'), 'exact recipe library schema required')
        for key, name, maximum in (('binary', kernel.LIBRARY, MAX_LIBRARY_BYTES),
                                   ('receipt', kernel.RECEIPT, MAX_RECEIPT_BYTES)):
            item = library[key]
            files.record(item)
            need(item['path'] == role + '_library/' + name and 0 < item['bytes'] <= maximum,
                 'fresh recipe library path/size differs')
    for name, _, _ in CASES:
        case = value[name]
        files.exact(case, ('report', 'diagnostics'), 'exact recipe case schema required')
        for key, suffix, maximum in (('report', '.json', phase.MAX_REPORT),
                                     ('diagnostics', '_diagnostics.json', phase.MAX_DIAGNOSTICS)):
            item = case[key]
            files.record(item)
            need(item['path'] == 'phase_' + name + suffix and 0 < item['bytes'] <= maximum,
                 'fresh recipe metadata path/size differs')
    return value


def _metadata(workspace, item, limit):
    """Parse exactly the bounded regular-file bytes whose digest was checked."""
    path = files.resolve_artifact(workspace, item)
    need(item['bytes'] <= limit, 'fresh recipe metadata bound')
    raw = native_runtime.read_bytes(path, limit)
    need(len(raw) == item['bytes'] and files.sha(raw) == item['sha256'],
         'fresh recipe metadata content drift')
    return files.json_bytes(raw, limit=limit)


def _library(workspace, recipe, role, kernel, sources):
    """Use the unchanged real verifier; it hashes ELF but never calls CDLL."""
    result = kernel.verify(workspace / (role + '_library'))
    declared = recipe[role]
    need(result['library_path'] == str(files.resolve_artifact(workspace, declared['binary'])) and
         result['receipt_path'] == str(files.resolve_artifact(workspace, declared['receipt'])) and
         result['library_sha256'] == declared['binary']['sha256'] and
         result['receipt_sha256'] == declared['receipt']['sha256'],
         'fresh recipe strict library receipt binding differs')
    need(type(result['source_sha256']) is dict and result['source_sha256'] and
         all(sources.get(name) == digest for name, digest in result['source_sha256'].items()),
         'fresh recipe library source closure differs')
    expected_pins = native_runtime.RECIPE_PINS_SHA256 if role == 'qk' else phase.kernel.OLD_PINS_SHA256
    need(result['pins_sha256'] == expected_pins, 'fresh recipe library pins differ')
    return result


def _trusted_context(runtime, workspace, manifest):
    """Establish expected identities from frozen sources and the setup context."""
    sources = runtime.source_snapshot()
    frozen = runtime.contract_snapshot(composed=True)
    raw, contract = runtime.contract_value()
    context, context_workspace = runtime.read_context(workspace / 'context.json', check_deadline=False)
    need(ROOT == runtime.ROOT == files.ROOT == phase.ROOT, 'fresh recipe source root differs')
    need(files.same(sources, frozen['sources']) and
         files.sha(raw) == frozen['contract_sha256'] == context['contract_sha256'] and
         files.same(sources, context['source_sha256']) and
         files.same(sources, manifest['source_sha256']) and
         manifest['source_manifest_sha256'] == files.sha(files.encoded(sources)),
         'fresh recipe source/contract identity differs')
    need(sources.get(SOURCE) == IMPORTED_SHA256 and
         sources.get(phase.kernel.ORIGINAL) == phase.qkv_kernel.FIXED[phase.kernel.ORIGINAL],
         'loaded recipe admission or original producer source drift')
    need(context_workspace == workspace and context['workspace'] == str(workspace) and
         context['generated_module'] == str(workspace / GENERATED_MODULE) and
         context['generated_module_sha256'] == native_runtime.GENERATED_MODULE_SHA256,
         'fresh recipe context workspace/generated module differs')
    return sources, frozen, raw, contract, context


def verify_recipe(workspace, manifest):
    """Revalidate fresh files and dispatch evidence without numerical execution.

    Reports and diagnostics may be read before the terminal fence because they
    contain bounded metadata only. Every tensor/ELF is streamed as opaque bytes.
    The returned dispatch summary remains a numerical prerequisite, not a Public
    chain verdict or a claim of backend-order equivalence.
    """
    from . import runtime

    need(type(manifest) is dict, 'fresh recipe manifest required')
    recipe = validate_manifest_extension(manifest['recipe'])
    workspace = files.safe_path(workspace, directory=True)
    captured_manifest = files.encoded(manifest)
    before = _trusted_context(runtime, workspace, manifest)
    sources, frozen, contract_raw, contract, context = before
    declared = list(files.records(manifest))
    for item in declared:
        files.checked_artifact(workspace, item)
    files.reject_aliases(workspace, {name: list(files.records(value)) for name, value in manifest.items()})
    need(files.resolve_artifact(workspace, recipe['generated_module']) == workspace / GENERATED_MODULE,
         'fresh generated recipe path differs')
    library = _library(workspace, recipe, 'qk', phase.kernel, sources)
    qkv_library = _library(workspace, recipe, 'qkv', phase.qkv_kernel, sources)
    payload = _metadata(workspace, manifest['payload']['manifest'], files.MAX_METADATA_BYTES)
    payload_hashes = diagnostic.payload_hashes(payload)
    files.exact(manifest['payload']['tensors'], files.TENSOR_PINS, 'exact recipe payload inventory')
    for name, pin in files.TENSOR_PINS.items():
        files.record(manifest['payload']['tensors'][name], size=pin['bytes'], expected=pin['sha256'])
    need(files.same(payload_hashes, {name: item['sha256'] for name, item in manifest['payload']['tensors'].items()}),
         'fresh recipe payload metadata/hash binding differs')
    shared = dict(source_manifest_sha256=files.sha(files.encoded(sources)),
        contract_sha256=frozen['contract_sha256'],
        original_module_sha256=phase.qkv_kernel.FIXED[phase.kernel.ORIGINAL],
        generated_module_sha256=recipe['generated_module']['sha256'],
        library_sha256=library['library_sha256'], library_receipt_sha256=library['receipt_sha256'],
        recipe_pins_sha256=library['pins_sha256'], qkv_library_sha256=qkv_library['library_sha256'],
        qkv_library_receipt_sha256=qkv_library['receipt_sha256'], qkv_recipe_pins_sha256=qkv_library['pins_sha256'],
        payload_manifest_sha256=manifest['payload']['manifest']['sha256'],
        payload_tensor_map_sha256=files.sha(files.encoded(payload_hashes)))
    trusted = dict(schema=1, profile=dispatch.PROFILE, shared=shared)
    pair = []
    for name, role, tokens in CASES:
        result_record = manifest[role]['result']
        files.record(result_record)
        need(result_record['path'] == role + '/RESULT.json', 'fresh recipe result path differs')
        result = _metadata(workspace, result_record, files.MAX_METADATA_BYTES)
        report = _metadata(workspace, recipe[name]['report'], phase.MAX_REPORT)
        observed = _metadata(workspace, recipe[name]['diagnostics'], phase.MAX_DIAGNOSTICS)
        projected = phase.project_result(result, tokens=tokens, result_sha256=result_record['sha256'],
            source_sha256=sources, contract_sha256=frozen['contract_sha256'],
            generated_module_sha256=shared['generated_module_sha256'], library=library, qkv_library=qkv_library,
            payload_manifest_sha256=shared['payload_manifest_sha256'],
            m16_result_sha256=None if tokens == 16 else manifest['native_m16']['result']['sha256'])
        need(files.same(report, projected), 'fresh recipe report differs from native result')
        need(files.same(observed['stage_sha256'], diagnostic.stage_hashes(result, tokens=tokens)) and
             files.same(observed['payload_sha256'], payload_hashes) and
             files.same(observed['backend_build'], phase.backend_build(result['identity'])),
             'fresh recipe diagnostics differ from result/payload hashes')
        trusted[name] = dict(result_sha256=result_record['sha256'],
            source_manifest_sha256=shared['source_manifest_sha256'],
            report_sha256=recipe[name]['report']['sha256'], diagnostics_sha256=recipe[name]['diagnostics']['sha256'])
        pair.extend((report, observed))
    prerequisite = dispatch.validate_pair(*pair, context=trusted)
    need(files.same(_library(workspace, recipe, 'qk', phase.kernel, sources), library) and
         files.same(_library(workspace, recipe, 'qkv', phase.qkv_kernel, sources), qkv_library),
         'fresh recipe library changed during admission')
    need(files.same(_trusted_context(runtime, workspace, manifest), before),
         'fresh recipe source/context changed during admission')
    need(files.encoded(manifest) == captured_manifest, 'fresh recipe manifest changed during admission')
    for item in declared:
        files.checked_artifact(workspace, item)
    return dict(identity=phase.combined_identity(library, qkv_library),
        generated_module_sha256=shared['generated_module_sha256'], prerequisite=prerequisite)


def identity(native, workspace, manifest):
    """Adapt only the two explicit producer identity fields for Public admission."""
    _, original = native.runtime_identity(ROOT)
    value = files.json_bytes(files.encoded(original))
    need(type(value) is dict and value.get('runner_sha256') == phase.qkv_kernel.FIXED[phase.kernel.ORIGINAL] and
         'independent_qkv_recipe' not in value, 'original native runtime identity required')
    verified = verify_recipe(workspace, manifest)
    value['runner_sha256'] = verified['generated_module_sha256']
    value['independent_qkv_recipe'] = verified['identity']
    return value
