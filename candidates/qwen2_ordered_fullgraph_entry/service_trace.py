"""Exact fullgraph service binding for unchanged passive component callbacks.

ProfiledMatrixService inherits OfficialMatrixService.acquire. In normal mode
that wrapper only returns super().acquire(owner, mode, tag). Observe the wrapper
return once, not both wrapper and base returns. The remaining eight lifecycle
methods still resolve directly to MatrixService. No service is constructed,
patched, called, or generalized by this module.
"""
import hashlib
from pathlib import Path
import sys
import threading


METHODS = ('acquire', 'accept_group', 'accept_step', 'retire_result',
           'retire_done', 'retire_legacy_reply', 'retire_owner_response',
           'release', 'abort')
ROOT_MODULE = 'candidates.qwen2_resident_matrix.'
CLASSES = (
    ('dense_block_reduce.matrix_binding', 'ProfiledMatrixService'),
    ('official_bf16.dense_silu', 'OfficialMatrixService'),
    ('ffn_attention.matrix_service', 'MatrixService'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def service_specs(service_class, profile):
    """Validate normal source class identities without constructing a service.

    Returned bindings retain the original monitor.bind contract. Caller must
    invoke that strict code binder, not treat source file hashing as code proof.
    """
    root = Path(profile['source_root']).resolve(strict=True) / 'candidates/qwen2_resident_matrix'
    classes, paths = [], []
    for module_name, class_name in CLASSES:
        fullname = ROOT_MODULE + module_name
        module = sys.modules.get(fullname)
        path = root / (module_name.replace('.', '/') + '.py')
        need(module is not None and Path(getattr(module, '__file__', '')).resolve() == path,
             'normal service module origin: ' + fullname)
        pin = profile['files'][str(path)]['sha256']
        need(hashlib.sha256(path.read_bytes()).hexdigest() == pin, 'service source pin: ' + fullname)
        cls = vars(module).get(class_name)
        need(isinstance(cls, type) and cls.__module__ == fullname and cls.__name__ == class_name,
             'normal service class identity: ' + fullname)
        classes.append(cls)
        paths.append(path)
    need(service_class is classes[0] and service_class.__mro__ == tuple(classes) + (object,),
         'exact Profiled/Official/Matrix service MRO required')
    specs = {}
    for name in METHODS:
        index = 1 if name == 'acquire' else 2
        owner, path = classes[index], paths[index]
        fn = owner.__dict__.get(name)
        need(fn is not None and getattr(service_class, name) is fn,
             'unexpected service method override: ' + name)
        specs[name] = (fn, path, profile['files'][str(path)]['sha256'], owner.__name__, name)
    return specs


def make_trace(runtime_observer, service, profile, bind):
    """Reuse old callback/monitoring/seal implementation with exact new bindings."""
    specs = service_specs(type(service), profile)
    need(runtime_observer.ServiceTrace.METHODS == METHODS, 'original trace method contract changed')

    class FullgraphServiceTrace(runtime_observer.ServiceTrace):
        def __init__(self):
            self.service = service
            self.events = []
            self.error = None
            self.tool = None
            self.closed = False
            self.thread = threading.get_ident()
            self.codes = {}
            for name, (fn, path, pin, cls, method) in specs.items():
                bound = getattr(service, name)
                need(getattr(bound, '__self__', None) is service and
                     getattr(bound, '__func__', None) is fn,
                     'instance service method substitution: ' + name)
                code = bind(bound, path, pin, cls, method, False)
                need(code not in self.codes, 'duplicate lifecycle code binding')
                self.codes[code] = name

    return FullgraphServiceTrace()
