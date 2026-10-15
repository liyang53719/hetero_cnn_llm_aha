"""Bounded comparison of already-computed outputs; never a numerical acceptance."""
import hashlib
from pathlib import PurePosixPath, PosixPath
from types import ModuleType
if __package__:
    from . import comparison_diagnostic as C
else:
    import comparison_diagnostic as C

NAMES=('act','att','cache_k','cache_v','cos','down','gate','k','kr','logits','mask','n0','n1',
       'o','prob','pv','q','qr','r','repeat_k','repeat_v','scores','silu','sin','softmax_fp32','up','v','x','y')
NODES=tuple('OUTPUT_%02d'%i for i in range(29))
TOKEN_MAJOR=frozenset(('q','k','repeat_k','repeat_v','pv','cache_k','cache_v'))


def checked(record):
    if type(record) is not dict or any(type(k) is not str for k in record) or set(record)!={
        'schema','status','scope','compared_count','numeric_acceptance_claimed','records'}:
        raise ValueError('invalid all-comparison schema')
    if (type(record['schema']) is not int or record['schema']!=1 or
        type(record['status']) is not str or record['status']!='CI_REFERENCE_ALL_COMPARISONS' or
        type(record['scope']) is not str or record['scope']!='EXISTING_OUTPUTS_ONLY' or
        type(record['compared_count']) is not int or record['compared_count']!=29 or
        record['numeric_acceptance_claimed'] is not False or
        type(record['records']) is not list or len(record['records'])!=29):
        raise ValueError('invalid all-comparison values')
    rows=[]
    for index,row in enumerate(record['records']):
        if (type(row) is not dict or any(type(k) is not str for k in row) or
            set(row)!={'node','categories','mismatch_count'} or type(row['node']) is not str or row['node']!=NODES[index]):
            raise ValueError('invalid all-comparison row')
        safe=C.checked(dict(schema=1,status='CI_REFERENCE_COMPARISON',node='NODE_00',
            categories=row['categories'],mismatch_count=row['mismatch_count']))
        rows.append(dict(node=NODES[index],categories=safe['categories'],mismatch_count=safe['mismatch_count']))
    return {**record,'records':rows}


def _mapping(value,names):
    return type(value) is dict and all(type(k) is str for k in value) and set(value)==set(names)


def _observe(value,name,torch,hook,expected):
    # Identical observation expressions to original capture.py:253-262. No
    # forward, softmax, arithmetic chain, tensor writes or input reads occur.
    data=value.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
    native=value.contiguous().view(torch.uint8).numpy().tobytes()
    token=value.transpose(1,2).reshape(1,128,-1) if name in TOKEN_MAJOR else value
    token_data=token.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
    layout=hook.get(name,dict(native_stride=list(value.stride()),
        storage_offset=value.storage_offset(),is_contiguous=value.is_contiguous()))
    layout_keys=('native_stride','storage_offset','is_contiguous')
    if name in hook:
        if not _mapping(layout,(*layout_keys,'shape','native_dtype')):
            raise ValueError('invalid original hook record')
        if (type(layout['shape']) is not list or any(type(n) is not int for n in layout['shape']) or
            type(layout['native_dtype']) is not str or layout['native_dtype'] not in ('torch.bfloat16','torch.float32')):
            raise ValueError('invalid original hook metadata')
    elif not _mapping(layout,layout_keys):
        raise ValueError('invalid observation layout')
    layout={key:layout[key] for key in layout_keys}
    result=dict(shape=list(value.shape),bytes=len(data),native_dtype=str(value.dtype),
        export_dtype=('FP32 unchanged' if name=='softmax_fp32' else 'FP32 exact BF16 widening'),native_bytes=len(native),sha256=hashlib.sha256(data).hexdigest(),
        native_sha256=hashlib.sha256(native).hexdigest(),token_major_sha256=hashlib.sha256(token_data).hexdigest(),
        **layout)
    if not C._record(result):raise ValueError('invalid observed metadata')
    return result


def project(error,root,expected):
    if not isinstance(error,BaseException) or type(root) not in (str,PurePosixPath,PosixPath):return None
    root_text=str(root);path=PurePosixPath(root_text)
    if not path.is_absolute() or str(path)!=root_text or '..' in path.parts or root_text=='/':return None
    trace=BaseException.__traceback__.__get__(error)
    while trace is not None:
        frame=trace.tb_frame;code=frame.f_code
        if code.co_filename==root_text+'/'+C.SOURCE and code.co_name=='capture' and trace.tb_lineno==265:
            local=frame.f_locals;outputs=local.get('outputs');hook=local.get('hook_records');torch=local.get('torch')
            if not _mapping(outputs,NAMES) or not _mapping(expected,NAMES):return None
            if type(hook) is not dict or any(type(k) is not str or k not in NAMES for k in hook):return None
            if type(torch) is not ModuleType or torch.__name__!='torch':return None
            tensor_type=torch.Tensor
            if any(type(value) is not tensor_type for value in outputs.values()):return None
            normalized={}
            for name in NAMES:
                spec=expected[name]
                if not _mapping(spec,set(C.FIELDS)|{'file'}) or type(spec['file']) is not str or spec['file']!=name+'.f32le':return None
                meta={key:spec[key] for key in C.FIELDS}
                if not C._record(meta):return None
                normalized[name]=meta
            # Validate all contracts before observing any tensor.
            rows=[]
            for index,name in enumerate(NAMES):
                actual=_observe(outputs[name],name,torch,hook,normalized[name])
                differing=[key for key in C.FIELDS if type(actual[key]) is not type(normalized[name][key]) or actual[key]!=normalized[name][key]]
                rows.append(dict(node=NODES[index],categories=sorted({C.FIELDS[key] for key in differing}),mismatch_count=len(differing)))
            return checked(dict(schema=1,status='CI_REFERENCE_ALL_COMPARISONS',scope='EXISTING_OUTPUTS_ONLY',
                compared_count=29,numeric_acceptance_claimed=False,records=rows))
        trace=trace.tb_next
    return None
