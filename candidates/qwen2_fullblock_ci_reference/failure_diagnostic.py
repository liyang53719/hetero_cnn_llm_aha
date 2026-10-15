"""Bounded public failure projection; exception messages and paths stay private."""
from pathlib import PurePosixPath

MODULES = {
    'candidates/qwen2_fullblock_reference_m128/capture.py': 'ORIGINAL_CAPTURE',
    'candidates/qwen2_fullblock_reference_m128/guard.py': 'ORIGINAL_GUARD',
    'candidates/qwen2_fullblock_reference_m128/lifecycle.py': 'ORIGINAL_LIFECYCLE',
    'candidates/qwen2_fullblock_reference_m128/recipe.py': 'ORIGINAL_RECIPE',
    'candidates/qwen2_fullblock_ci_reference/guard.py': 'CI_GUARD',
    'candidates/qwen2_fullblock_ci_reference/recipe.py': 'CI_RECIPE',
    'candidates/qwen2_fullblock_ci_reference/issuer.py': 'CI_ISSUER',
    'candidates/qwen2_fullblock_ci_reference/lifecycle.py': 'CI_LIFECYCLE',
}
ERROR_TYPES = (
    (FileNotFoundError, 'FILE_NOT_FOUND'), (PermissionError, 'PERMISSION_ERROR'),
    (TimeoutError, 'TIMEOUT'), (MemoryError, 'MEMORY_ERROR'),
    (AssertionError, 'ASSERTION_ERROR'), (ValueError, 'VALUE_ERROR'),
    (TypeError, 'TYPE_ERROR'), (KeyError, 'KEY_ERROR'),
    (ImportError, 'IMPORT_ERROR'), (OSError, 'OS_ERROR'),
    (RuntimeError, 'RUNTIME_ERROR'),
)
ERRORS = frozenset(label for _, label in ERROR_TYPES) | {'OTHER'}
MAX_LINE = 100000


def checked(record):
    """Return a fresh exact-schema record or reject without echoing input."""
    if type(record) is not dict or set(record) != {'schema','status','origin','error','module','line'}:
        raise ValueError('invalid failure diagnostic schema')
    if (type(record['schema']) is not int or record['schema'] != 1 or
        type(record['status']) is not str or record['status'] != 'CI_REFERENCE_FAILURE' or
        type(record['origin']) is not str or record['origin'] not in ('WORKER','SUPERVISOR') or
        type(record['error']) is not str or record['error'] not in ERRORS or
        type(record['module']) is not str or record['module'] not in set(MODULES.values()) | {'OTHER'} or
        type(record['line']) is not int or not 0 <= record['line'] <= MAX_LINE or
        (record['module'] == 'OTHER') != (record['line'] == 0)):
        raise ValueError('invalid failure diagnostic values')
    return dict(record)


def project(error, origin, root):
    """Project trusted traceback code locations, never exception str/repr/args."""
    if not isinstance(error, BaseException):
        raise TypeError('exception required')
    if type(origin) is not str or origin not in ('WORKER','SUPERVISOR'):
        raise ValueError('invalid failure origin')
    if not isinstance(root, (str, PurePosixPath)):
        raise TypeError('explicit absolute root required')
    root_text = str(root)
    path = PurePosixPath(root_text)
    if not path.is_absolute() or str(path) != root_text or '..' in path.parts or root_text == '/':
        raise ValueError('explicit canonical root required')
    approved = {root_text+'/'+relative: label for relative,label in MODULES.items()}
    result = dict(schema=1,status='CI_REFERENCE_FAILURE',origin=origin,
                  error='OTHER',module='OTHER',line=0)
    for kind,label in ERROR_TYPES:
        if isinstance(error,kind):
            result['error'] = label
            break
    trace = BaseException.__traceback__.__get__(error)
    while trace is not None:
        code = trace.tb_frame.f_code
        label = approved.get(code.co_filename)
        if label is not None and code.co_name not in ('need','require') and 1 <= trace.tb_lineno <= MAX_LINE:
            result.update(module=label,line=trace.tb_lineno)
        trace = trace.tb_next
    return checked(result)
