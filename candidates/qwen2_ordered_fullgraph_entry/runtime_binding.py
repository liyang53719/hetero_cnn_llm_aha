"""Normal source-bound fullgraph imports, without constructing an execution.

This is a project-source/code gate, not a replacement for the independently
pinned interpreter, NumPy DT_NEEDED/maps gate. Only a disposable cold worker
should call load_runtime. No old runtime(), prepare(), CDLL or job is called.
"""
import hashlib
import importlib
import json
import marshal
from pathlib import Path
import sys
from types import SimpleNamespace

PREFIX = 'candidates.qwen2_resident_matrix.'
MODULES = {
    'base': PREFIX + 'ffn_public.check_prefix_numeric',
    'original': PREFIX + 'ffn_public.execute_numeric',
    'fixtures': PREFIX + 'ffn_public.fixture',
    'public': PREFIX + 'ffn_public.model',
    'prefix': PREFIX + 'ffn_public.prefix_execution',
    'scalar': PREFIX + 'ffn_public.prefix_arithmetic',
    'suffix': PREFIX + 'ffn_public.fullgraph_execution',
    'physical_adapter': PREFIX + 'ffn_public.fullgraph_memory',
    'owner_module': PREFIX + 'dense_block_reduce.dense_drain',
    'binding': PREFIX + 'dense_block_reduce.matrix_binding',
    'profiles': PREFIX + 'dense_block_reduce.profile',
    'execution': PREFIX + 'dense_block_reduce.public_execution',
    'policy': PREFIX + 'official_bf16.execution',
    'dense': PREFIX + 'official_bf16.dense_silu',
    'matrix': PREFIX + 'ffn_attention.matrix_service',
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_sources(root, manifest, manifest_sha256):
    root, manifest = Path(root).resolve(strict=True), Path(manifest).resolve(strict=True)
    raw = manifest.read_bytes()
    need(digest(raw) == manifest_sha256, 'source manifest hash')
    data = json.loads(raw)
    need(data['schema'] == 'qwen2-ordered-fullgraph-source-manifest-v1', 'source manifest schema')
    files = data['source_files']
    need(data['source_file_count'] == len(files), 'source manifest count')
    for rel, pin in files.items():
        path = root / rel
        need(not Path(rel).is_absolute() and '..' not in Path(rel).parts and
             path.resolve().is_relative_to(root) and not path.is_symlink(), 'source path escape')
        content = path.read_bytes()
        need(len(content) == pin['bytes'] and digest(content) == pin['sha256'], 'source drift: ' + rel)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    need(actual == set(files), 'unmanifested or missing source')
    return root, files


def project_inventory(root, files, modules):
    """Include path-loaded legacy aliases as well as named packages."""
    found = {}
    for name, module in list(modules.items()):
        origin = getattr(module, '__file__', None)
        path = Path(origin).resolve() if origin else None
        project_name = name == 'candidates' or name.startswith('candidates.') or name == 'scripts' or name.startswith('scripts.')
        if path is None:
            if project_name:
                locations = list(getattr(module, '__path__', ()))
                need(locations and all(Path(p).resolve().is_relative_to(root) for p in locations),
                     'foreign project namespace: ' + name)
            continue
        if not path.is_relative_to(root):
            need(not project_name, 'foreign project module: ' + name)
            continue
        rel = str(path.relative_to(root))
        need(rel in files and path.suffix == '.py', 'unmanifested project module: ' + name)
        content = path.read_bytes()
        need(digest(content) == files[rel]['sha256'], 'loaded project source drift: ' + name)
        found[name] = {'relative': rel, 'sha256': files[rel]['sha256']}
    return found


class ProjectCodeGate:
    """Attest every project module exec against its complete exact source.

    The hook is dormant after context exit; it neither blocks nor labels
    dependency/dataclass code as project source. Runtime inventory is a separate
    required gate, not implicitly approved by this class.
    """
    def __init__(self, root, files):
        self.root, self.files = root, files
        self.active, self.events = False, []

    def hook(self, event, args):
        if not self.active or event != 'exec':
            return
        code = args[0]
        filename = code.co_filename
        if filename.startswith('<'):
            return
        path = Path(filename).resolve()
        if not path.is_relative_to(self.root):
            return
        rel = str(path.relative_to(self.root))
        need(rel in self.files and code.co_name == '<module>', 'foreign project execution code')
        raw = path.read_bytes()
        need(digest(raw) == self.files[rel]['sha256'], 'project exec source changed')
        expected = compile(raw, str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize)
        need(marshal.dumps(code) == marshal.dumps(expected), 'project module code differs: ' + rel)
        self.events.append({'relative': rel, 'source_sha256': self.files[rel]['sha256'],
                            'code_sha256': digest(marshal.dumps(code))})

    def __enter__(self):
        sys.addaudithook(self.hook)
        self.active = True
        return self

    def __exit__(self, *unused):
        self.active = False


def load_runtime(source_root, source_manifest, source_manifest_sha256):
    """Normal imports only. library and selected are intentionally absent."""
    root, files = verify_sources(source_root, source_manifest, source_manifest_sha256)
    before = project_inventory(root, files, sys.modules)
    need(not before, 'cold project namespace required; preloaded code cannot be attested')
    sys.path.insert(0, str(root))
    with ProjectCodeGate(root, files) as gate:
        loaded = {role: importlib.import_module(name) for role, name in MODULES.items()}
    inventory = project_inventory(root, files, sys.modules)
    for role, name in MODULES.items():
        need(name in inventory and loaded[role] is sys.modules[name], 'runtime module binding identity')
    executed = {e['relative'] for e in gate.events}
    need(all(v['relative'] in executed for v in inventory.values()), 'loaded module lacks full code attestation')
    verify_sources(root, source_manifest, source_manifest_sha256)
    receipt = dict(status='NORMAL_PROJECT_IMPORT_CODE_BINDING_ONLY', modules=inventory,
                   module_exec_events=gate.events, module_targets=MODULES,
                   services_constructed=False, library_configured=False, jobs_submitted=False,
                   task_tensor_read=False, numerical_status='TEMP_NOT_EXECUTED',
                   external_runtime_maps_status='REQUIRES_SEPARATE_PINNED_GATE')
    return SimpleNamespace(**loaded), receipt
