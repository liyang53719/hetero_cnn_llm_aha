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


def capture_error(instance, error):
    if instance.error is None:
        instance.error = type(error).__name__ + ': ' + str(error)


def monitoring_enter(instance, label, slots, callbacks, codes, mask):
    """Install only our private monitor lease; never wrap a frame-sensitive callback."""
    mon = sys.monitoring
    need(not instance.closed and instance.tool is None, 'single-use monitor')
    instance._monitor_label = label + ':' + format(id(instance), 'x')
    instance._monitor_owned = instance._stop_attempted = instance._foreign_registration = False
    instance._monitor_callbacks = dict(callbacks)  # retain exact bound callback objects
    instance._monitor_codes = tuple(codes)
    instance._monitor_mask = mask
    instance._callback_attempted = set()
    instance._callback_installed = set()
    instance._stale_restored = set()
    instance._local_attempted = set()
    for tool in slots:
        if mon.get_tool(tool) is not None or mon.get_events(tool) or any(
                mon.get_local_events(tool, code) for code in instance._monitor_codes):
            continue
        try:
            mon.use_tool_id(tool, instance._monitor_label)
        except BaseException:
            # Resolve an uncertain claim before cleanup; never free foreign state.
            if mon.get_tool(tool) == instance._monitor_label:
                instance.tool, instance._monitor_owned = tool, True
            raise
        instance.tool, instance._monitor_owned = tool, True
        break
    need(instance.tool is not None, 'monitor tool busy or retains event masks')
    slot = instance.tool
    for event, callback in instance._monitor_callbacks.items():
        need(mon.get_tool(slot) == instance._monitor_label and not mon.get_events(slot), 'monitor lease changed')
        instance._callback_attempted.add(event)
        previous = mon.register_callback(slot, event, callback)
        if previous is not None:
            replaced = mon.register_callback(slot, event, previous)
            if replaced is not callback:
                mon.register_callback(slot, event, replaced)
                instance._foreign_registration = True
                raise ValueError('callback changed while restoring foreign registration')
            instance._stale_restored.add(event)
            raise ValueError('stale monitor callback restored; not used')
        instance._callback_installed.add(event)
    need(mon.get_tool(slot) == instance._monitor_label and not mon.get_events(slot) and
         not any(mon.get_local_events(slot, code) for code in instance._monitor_codes), 'monitor masks changed')
    for code in instance._monitor_codes:
        instance._local_attempted.add(code)
        mon.set_local_events(slot, code, mask)
    return instance


def monitoring_stop(instance, callbacks, codes):
    """Once-only cleanup; caller catches errors, never retry uncertain mutations.

    The callbacks/codes arguments name the adapter contract. Actual ownership is
    checked against exact callback objects and masks retained during installation.
    """
    if getattr(instance, '_stop_attempted', False):
        return
    instance._stop_attempted = True
    instance.closed = True
    if instance.tool is None or not getattr(instance, '_monitor_owned', False):
        return
    mon, slot = sys.monitoring, instance.tool
    need(mon.get_tool(slot) == instance._monitor_label, 'foreign monitor lease; not cleared')
    global_mask = mon.get_events(slot)
    local_masks = {code: mon.get_local_events(slot, code) for code in instance._monitor_codes}
    need(not global_mask and not instance._foreign_registration and all(
        value in ((0, instance._monitor_mask) if code in instance._local_attempted else (0,))
        for code, value in local_masks.items()), 'foreign monitor masks/registration; preserved')
    for event in instance._callback_attempted:
        if event in instance._stale_restored:
            continue
        previous = mon.register_callback(slot, event, None)
        own = previous is instance._monitor_callbacks[event]
        absent_failed_install = event not in instance._callback_installed and previous is None
        if not own and not absent_failed_install:
            displaced = mon.register_callback(slot, event, previous)
            if displaced is not None:
                mon.register_callback(slot, event, displaced)
            instance._foreign_registration = True
            raise ValueError('foreign monitor callback restored; masks and lease preserved')
    need(mon.get_tool(slot) == instance._monitor_label and mon.get_events(slot) == global_mask and all(
        mon.get_local_events(slot, code) == value for code, value in local_masks.items()),
        'monitor ownership changed during cleanup; masks and lease preserved')
    for code, value in local_masks.items():
        if value:
            mon.set_local_events(slot, code, 0)
    # CPython free_tool_id preserves any restored stale callback. No foreign
    # callback or foreign local/global event mask is cleared by this cleanup.
    mon.free_tool_id(slot)
    instance.tool = None
    instance._monitor_owned = False


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


def make_trace(runtime_observer, service, profile, bind, event_stream_path):
    """Reuse the exact old callback; replace only bounded storage and safe monitoring lifetime."""
    from .stream import EventWriter, profile_counts
    specs = service_specs(type(service), profile)
    need(runtime_observer.ServiceTrace.METHODS == METHODS, 'original trace method contract changed')

    class FullgraphServiceTrace(runtime_observer.ServiceTrace):
        def __init__(self):
            self.service = service
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
            groups, events = profile_counts(profile['rows'])
            self.events = EventWriter(event_stream_path, expected_groups=groups,
                expected_events=events, max_events=profile['event_stream_max_events'],
                max_bytes=profile['event_stream_max_bytes'])
            self.stream_receipt = None

        def __enter__(self):
            try:
                event = sys.monitoring.events.PY_RETURN
                return monitoring_enter(self, 'ordered-service-events', (4, 3),
                    ((event, self._return),), self.codes, event)
            except BaseException as error:
                capture_error(self, error)
                self.stop()
                self.events.close_incomplete()
                raise

        def stop(self):
            # Old _return calls this method on capture errors. It cannot throw
            # back into the original service frame or clear somebody else's slot.
            try:
                monitoring_stop(self, (sys.monitoring.events.PY_RETURN,), self.codes)
            except BaseException as error:
                capture_error(self, error)
                self.closed = True
                if isinstance(error, KeyboardInterrupt):
                    raise

        def __exit__(self, kind, value, traceback):
            self.stop()
            if kind is not None or self.error is not None:
                self.events.close_incomplete()
            else:
                try:
                    self.stream_receipt = self.events.seal()
                except BaseException as error:
                    # Evidence failure never substitutes a DUT result or ACK.
                    self.error = type(error).__name__ + ': ' + str(error)
                    self.events.close_incomplete()
                    if isinstance(error, KeyboardInterrupt):
                        raise
            return False

        def seal(self):
            need(self.closed and self.error is None and self.stream_receipt is not None,
                 'stream trace failed or still active: ' + str(self.error))
            return dict(self.stream_receipt)

        def raw_receipt(self):
            receipt = self.events.snapshot()
            receipt.update(monitor_error=self.error, monitor_residual_tool=self.tool, monitor_closed=self.closed)
            return receipt

    return FullgraphServiceTrace()
