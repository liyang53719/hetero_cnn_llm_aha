"""Compose existing full-source gates and production stream modules; no loader ABI."""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys
import types

PACKAGE = '_production_component_bridge'
MODULES = ('bridge', 'service_trace', 'stream', 'cold_policy')
DEPENDENCY = None


def need(ok, message):
    if not ok: raise ValueError(message)


def pinned(path, config):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    pin = config['files'][str(path)]
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source drift: ' + str(path))
    return path


def create_production_namespace(config):
    root = Path(config['production_root']).resolve(strict=True)
    need(PACKAGE not in sys.modules and not any(n.startswith(PACKAGE + '.') for n in sys.modules), 'fresh production namespace')
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(root)]
    sys.modules[PACKAGE] = package
    return package


def load(config):
    """Existing ProjectCodeGate and load_runtime; no native load or constructor."""
    global DEPENDENCY
    path = pinned(config['project_code_gate_source'], config)
    name = '_production_existing_project_code_gate'
    need(name not in sys.modules, 'one production source gate load')
    spec = importlib.util.spec_from_file_location(name, path)
    gate_module = importlib.util.module_from_spec(spec)
    sys.modules[name] = gate_module
    spec.loader.exec_module(gate_module)
    root = Path(config['production_root']).resolve(strict=True)
    files = {m + '.py': config['files'][str(pinned(root / (m + '.py'), config))] for m in MODULES}
    create_production_namespace(config)
    with gate_module.ProjectCodeGate(root, files) as gate:
        modules = {m: importlib.import_module(PACKAGE + '.' + m) for m in MODULES}
    need({x['relative'] for x in gate.events} == set(files), 'complete production bridge module exec closure')
    dependency_root = Path(config['dependency_qualification_root']).resolve(strict=True)
    dependency_files = {n + '.py': config['files'][str(pinned(dependency_root / (n + '.py'), config))]
                        for n in ('initialization', 'safe_metadata')}
    helpers = {}
    with gate_module.ProjectCodeGate(dependency_root, dependency_files) as dependency_gate:
        for helper in ('initialization', 'safe_metadata'):
            helper_name = '_m16_existing_dependency_' + helper
            need(helper_name not in sys.modules, 'fresh existing dependency qualifier')
            helper_spec = importlib.util.spec_from_file_location(helper_name, dependency_root / (helper + '.py'))
            helpers[helper] = importlib.util.module_from_spec(helper_spec)
            sys.modules[helper_name] = helpers[helper]; helper_spec.loader.exec_module(helpers[helper])
    DEPENDENCY = dict(policy=modules['cold_policy'], initialization=helpers['initialization'],
                      safe=helpers['safe_metadata'], native_before=None, native_events=[])
    def watch(event, args):
        if event == 'import' and args and args[0] == 'yaml._yaml':
            if DEPENDENCY['native_before'] is None:
                DEPENDENCY['native_before'] = {n: n in sys.modules for n in helpers['initialization'].NAMES}
            DEPENDENCY['native_events'].append(dict(module=args[0], origin=args[1] if len(args) > 1 else None))
    sys.addaudithook(watch)
    runtime, receipt = gate_module.load_runtime(config['source_root'], config['source_manifest'], config['source_manifest_sha256'])
    source = __import__('json').loads(Path(config['source_manifest']).read_text())
    with gate_module.ProjectCodeGate(Path(config['source_root']), source['source_files']) as extra_gate:
        direct = importlib.import_module('candidates.qwen2_resident_matrix.production_qk16_model.direct_transport')
        ordered = importlib.import_module('candidates.qwen2_resident_matrix.production_qk16_model.ordered_work')
    inventory = gate_module.project_inventory(Path(config['source_root']), source['source_files'], sys.modules)
    return runtime, modules, direct, ordered, dict(runtime=receipt,
        production_module_exec_events=gate.events, late_module_exec_events=extra_gate.events,
        dependency_qualifier_exec_events=dependency_gate.events,
        dependency_native_before=DEPENDENCY['native_before'], dependency_native_events=DEPENDENCY['native_events'],
        final_project_inventory=inventory)
