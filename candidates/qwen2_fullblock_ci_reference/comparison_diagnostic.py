"""Project only bounded prior18 comparison categories from one exact failure site."""
from pathlib import PurePosixPath, PosixPath

SOURCE = 'candidates/qwen2_fullblock_reference_m128/capture.py'
NODES = ('att','cos','k','kr','logits','mask','n0','prob','pv','q','qr',
         'repeat_k','repeat_v','scores','sin','softmax_fp32','v','x')
NODE_ENUMS = tuple('NODE_%02d' % n for n in range(18))
FIELDS = {
    'sha256':'HASH','native_sha256':'HASH','token_major_sha256':'HASH',
    'storage_offset':'LAYOUT','is_contiguous':'LAYOUT',
    'native_dtype':'DTYPE','export_dtype':'DTYPE','shape':'SHAPE',
    'native_stride':'STRIDE','bytes':'BYTES','native_bytes':'BYTES',
}
CATEGORIES = ('BYTES','DTYPE','HASH','LAYOUT','SHAPE','STRIDE')


def _record(value):
    if type(value) is not dict or any(type(k) is not str for k in value) or set(value) != set(FIELDS):
        return False
    for key,item in value.items():
        if key in ('shape','native_stride'):
            if type(item) is not list or not 1 <= len(item) <= 4:
                return False
            if any(type(n) is not int or not 0 <= n < 2**63 for n in item):
                return False
        elif key in ('bytes','native_bytes','storage_offset'):
            if type(item) is not int or not 0 <= item < 2**63:
                return False
        elif key == 'is_contiguous':
            if type(item) is not bool:
                return False
        elif key == 'native_dtype':
            if type(item) is not str or item not in ('torch.bfloat16','torch.float32'):
                return False
        elif key == 'export_dtype':
            if type(item) is not str or item not in ('FP32 exact BF16 widening','FP32 unchanged'):
                return False
        elif type(item) is not str or len(item) != 64 or any(c not in '0123456789abcdef' for c in item):
            return False
    return len(value['shape']) == len(value['native_stride'])


def checked(record):
    if (type(record) is not dict or any(type(k) is not str for k in record) or
        set(record) != {'schema','status','node','categories','mismatch_count'}):
        raise ValueError('invalid comparison diagnostic schema')
    if (type(record['schema']) is not int or record['schema'] != 1 or
        type(record['status']) is not str or record['status'] != 'CI_REFERENCE_COMPARISON' or
        type(record['node']) is not str or record['node'] not in NODE_ENUMS or
        type(record['categories']) is not list or
        any(type(c) is not str or c not in CATEGORIES for c in record['categories']) or
        record['categories'] != sorted(set(record['categories'])) or
        type(record['mismatch_count']) is not int or not 0 <= record['mismatch_count'] <= len(FIELDS)):
        raise ValueError('invalid comparison diagnostic values')
    categories=record['categories'];count=record['mismatch_count']
    if not len(categories) <= count <= sum(c in categories for c in FIELDS.values()):
        raise ValueError('invalid comparison diagnostic count')
    return {**record,'categories':list(categories)}


def project(error, root):
    """Return None unless the exact site and entirely native records are present."""
    if not isinstance(error,BaseException) or type(root) not in (str,PurePosixPath,PosixPath):
        return None
    root_text=str(root);path=PurePosixPath(root_text)
    if not path.is_absolute() or str(path) != root_text or '..' in path.parts or root_text == '/':
        return None
    trace=BaseException.__traceback__.__get__(error)
    while trace is not None:
        frame=trace.tb_frame;code=frame.f_code
        if code.co_filename == root_text+'/'+SOURCE and code.co_name == 'capture' and trace.tb_lineno == 265:
            local=frame.f_locals
            actual=local.get('actual');pins=local.get('pins');name=local.get('name')
            if type(name) is not str or name not in NODES or type(pins) is not dict:
                return None
            if any(type(k) is not str for k in pins):
                return None
            prior=pins.get('prior18_expectations')
            if (type(prior) is not dict or any(type(k) is not str for k in prior) or
                set(prior) != set(NODES)):
                return None
            expected=prior[name]
            if not _record(actual) or not _record(expected):
                return None
            differing=[key for key in FIELDS if type(actual[key]) is not type(expected[key]) or actual[key] != expected[key]]
            return checked(dict(schema=1,status='CI_REFERENCE_COMPARISON',node=NODE_ENUMS[NODES.index(name)],
                categories=sorted({FIELDS[key] for key in differing}),mismatch_count=len(differing)))
        trace=trace.tb_next
    return None
