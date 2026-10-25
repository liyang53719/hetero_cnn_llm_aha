"""Narrow runtime prohibitions for the reviewed metadata-only cold action.

This is not a general Python sandbox. Full source/module/map gates and the
unchanged oracle path gate are independent. Pinned dependency initialization
may load its own native extensions; Matrix/task native loading never may.
"""
import os
import sys
from pathlib import Path
from common import need

FORBIDDEN_CALLS = frozenset((
    'configure_library', 'configure_silu_library', 'selected_library', 'load_library', 'build_library',
    'compile_fresh', 'td_reset', 'sf_reset', 'reset', 'run_actual', 'make_dispatch',
    'run', 'op', '_op', 'tick', '_matrix_step', 'run_owner',
    'execute_public_prefix', 'execute_public_suffix', 'execute_attention_owner',
    'execute_windows', 'run_recipe', 'capture_reference', 'load_inputs',
    'load_exact', 'pack_words', 'fp32_from_bf16', 'rope_bytes', 'pattern_bytes',
    'prepare', 'make_comparator', 'compare_after_live_terminal',
    'acquire', 'accept_group', 'accept_step', 'retire_result', 'retire_done',
    'retire_legacy_reply', 'retire_owner_response', 'release', 'abort',
))
FORBIDDEN_CLASSES = frozenset((
    'PhysicalMemory', 'FullGraphMemory', 'DenseReductionOwner', 'MatrixService',
    'OfficialMatrixService', 'ProfiledMatrixService', 'ScalarService',
    'ReducedPublicExecution', 'PublicFrontend', 'HostControl',
    'OfficialPrefixOwner', 'OfficialAttentionOwner', 'ObservedSiluLibrary',
    'RopeOperandCapture', 'PrefixOwner', 'AttentionOwner', 'PackedClient',
    'ProductionQk16Schedule', 'OrderedFoldAdapter', 'OrderedFoldWork',
    'ServiceTrace', 'PackedFields', 'Fields', 'SelectedSiluLibrary',
    'OfficialDenseLibraryAdapter', 'DenseLibraryAdapter', 'PrefixWorkspace',
))

class MetadataOnlyGuard:
    def __init__(self, config):
        self.config = config
        self.denied = []
        self.active_profile = False
        self.post_normal = False
        self.matrix = str(Path(config['elf']).resolve())
        stat = Path(self.matrix).stat()
        self.matrix_inode = (stat.st_dev, stat.st_ino)
        self.roots = tuple(str(Path(config[key]).resolve()) + os.sep
                           for key in ('source_root', 'candidate_root', 'observer_root', 'cold_helper_root'))
        self.buffer = config['buffer_source']

    def reject(self, kind, detail):
        self.denied.append(dict(kind=kind, detail=str(detail)))
        raise PermissionError(kind + ': ' + str(detail))

    def audit(self, event, args):
        if event in ('shutil.rmtree', 'os.remove', 'os.rmdir'):
            self.reject('metadata_evidence_deletion_forbidden', args[0] if args else event)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0]))
            if str(path.resolve()) == self.matrix:
                self.reject('matrix_elf_read_forbidden', args[0])
            try:
                stat = path.stat()
            except OSError:
                pass
            else:
                if (stat.st_dev, stat.st_ino) == self.matrix_inode:
                    self.reject('matrix_elf_alias_read_forbidden', args[0])
        if event == 'ctypes.dlopen' and args:
            raw = args[0]
            if self.post_normal:
                self.reject('post_normal_native_load_forbidden', raw)
            if raw is not None:
                path = Path(os.fsdecode(raw))
                if str(path.resolve()) == self.matrix:
                    self.reject('matrix_native_load_forbidden', raw)
                try:
                    stat = path.stat()
                except OSError:
                    return
                if (stat.st_dev, stat.st_ino) == self.matrix_inode:
                    self.reject('matrix_native_alias_load_forbidden', raw)
        if event == 'ctypes.dlsym' and self.post_normal:
            self.reject('post_normal_native_symbol_forbidden', args[1] if len(args) > 1 else event)

    def is_target_frame(self, frame):
        return any(type(raw) is str and (raw == self.buffer or raw.startswith(self.roots))
                   for raw in (frame.f_code.co_filename, frame.f_globals.get('__file__')))

    def profile(self, frame, event, arg):
        if event != 'call' or not self.is_target_frame(frame):
            return
        code = frame.f_code
        # Class/module definition bodies are not an invocation. Generated
        # dataclass constructors retain their source module globals.
        if not code.co_flags & 0x02:
            return
        if code.co_name in FORBIDDEN_CALLS:
            self.reject('metadata_task_call_forbidden', code.co_filename + ':' + code.co_qualname)
        if code.co_name in ('__init__', '__new__'):
            obj = frame.f_locals.get('self')
            cls = type(obj) if obj is not None else frame.f_locals.get('cls')
            if isinstance(cls, type) and cls.__name__ in FORBIDDEN_CLASSES:
                self.reject('metadata_task_construction_forbidden', cls.__name__)

    def install_audit(self):
        sys.addaudithook(self.audit)

    def enter_metadata(self):
        need(not self.post_normal and sys.getprofile() is None, 'one clean metadata transition')
        self.post_normal = True
        self.active_profile = True
        sys.setprofile(self.profile)

    def finish_profile(self):
        if self.active_profile:
            current = sys.getprofile()
            sys.setprofile(None)
            self.active_profile = False
            need(getattr(current, '__self__', None) is self and
                 getattr(current, '__func__', None) is MetadataOnlyGuard.profile,
                 'metadata profile was replaced or disabled')

    def require_clean(self):
        need(not self.denied, 'sticky metadata-only prohibition violation')

    def report(self):
        return dict(denied=list(self.denied), post_normal=self.post_normal,
                    scope='Explicit targeted task/native/delete prohibitions; not a general Python sandbox',
                    matrix_native_allowed=False, task_arithmetic_allowed=False,
                    oracle_values_allowed=False, persistent_metadata_only=True)
