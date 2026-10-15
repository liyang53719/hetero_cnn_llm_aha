"""Local-only native output snapshots at a failed capture; never acceptance.

The guard must verify its disabled backend policy before calling write().
Only already-computed outputs are observed. Metadata and payloads stay local.
"""
import json
import math
import os
from pathlib import Path
from types import ModuleType
if __package__:
    from . import all_comparisons as A
else:
    import all_comparisons as A

DIRECTORY='REPEAT_OBSERVATION_LOCAL'
META='METADATA.json'
FILES=tuple(node+'.bin' for node in A.NODES)
SHAPES={name:([1,128,8960] if name in ('act','gate','silu','up') else
    [1,128,1536] if name in ('att','down','n0','n1','o','qr','r','x','y') else
    [1,128,256] if name in ('kr','v') else [128,128] if name in ('cos','sin') else
    [1,1,128,128] if name=='mask' else [1,2,128,128] if name in ('cache_k','cache_v','k') else
    [1,12,128,128]) for name in A.NAMES}


def _need(ok):
    if not ok:raise ValueError('invalid local repeat observation')


def _path(value):
    p=Path(value)
    _need(p.is_absolute() and p.resolve()==p and all(not q.is_symlink() for q in (p,*p.parents)))
    return p


def _keys(value,keys):
    return type(value) is dict and all(type(k) is str for k in value) and set(value)==set(keys)


def _digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _identity(value,native=False):
    _need(_keys(value,('bytes','sha256','path') if native else ('bytes','sha256')))
    _need(type(value['bytes']) is int and 0<value['bytes']<2**40 and _digest(value['sha256']))
    if native:_need(type(value['path']) is str and 0<len(value['path'])<=1024)


def _boundary(value,certificate):
    keys={'source_closure_sha256','source_manifest','pins','effective_pins_sha256',
          'sources','raw13','native_files','input_proofs','raw_support','historical_receipts_revalidated'}
    if certificate:keys.add('external_certificate_sha256')
    _need(_keys(value,keys))
    for key in ('source_closure_sha256','effective_pins_sha256'):_need(_digest(value[key]))
    if certificate:_need(_digest(value['external_certificate_sha256']))
    _identity(value['source_manifest']);_identity(value['pins'])
    _need(value['historical_receipts_revalidated'] is False and type(value['raw_support']) is dict and not value['raw_support'])
    for field in ('sources','raw13','native_files','input_proofs'):
        items=value[field]
        _need(type(items) is dict and 0<len(items)<=1000 and all(type(k) is str and 0<len(k)<=1024 for k in items))
        for spec in items.values():_identity(spec,native=field=='native_files')
    _need(len(value['raw13'])==13 and len(value['native_files'])==6)
    # Only this precise per-invocation certificate field is intentionally absent
    # from the shared boundary. Every other identity must match across repeats.
    return {key:item for key,item in value.items() if key!='external_certificate_sha256'}


def _metadata(value):
    _need(_keys(value,('schema','status','boundary','records')))
    _need(type(value['schema']) is int and value['schema']==1 and type(value['status']) is str and
          value['status']=='LOCAL_FAILURE_OUTPUTS_ONLY' and type(value['records']) is list and len(value['records'])==29)
    _boundary(value['boundary'],False)
    for i,record in enumerate(value['records']):
        _need(_keys(record,('node','file','dtype','shape','native_stride','storage_offset','is_contiguous','bytes')))
        name=A.NAMES[i];dtype='torch.float32' if name=='softmax_fp32' else 'torch.bfloat16'
        _need(type(record['node']) is str and record['node']==A.NODES[i] and
            type(record['file']) is str and record['file']==FILES[i] and type(record['dtype']) is str and record['dtype']==dtype)
        _need(type(record['shape']) is list and all(type(n) is int for n in record['shape']) and record['shape']==SHAPES[name])
        _need(type(record['native_stride']) is list and len(record['native_stride'])==len(record['shape']) and
            all(type(n) is int and 0<=n<2**40 for n in record['native_stride']))
        _need(type(record['storage_offset']) is int and 0<=record['storage_offset']<2**40 and type(record['is_contiguous']) is bool)
        _need(type(record['bytes']) is int and record['bytes']==math.prod(SHAPES[name])*(4 if name=='softmax_fp32' else 2))
    return value


def _new(path,data):
    _need(type(data) is bytes)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data)


def write(error,root,out):
    """Return a new local directory, or None for a nonmatching failure site."""
    if not isinstance(error,BaseException):return None
    root=_path(root);out=_path(out)
    _need(out.is_dir() and out.is_relative_to(root/'work'))
    trace=BaseException.__traceback__.__get__(error)
    while trace is not None:
        frame=trace.tb_frame;code=frame.f_code
        if code.co_filename==str(root/A.C.SOURCE) and code.co_name=='capture' and trace.tb_lineno==265:
            outputs=frame.f_locals.get('outputs');torch=frame.f_locals.get('torch')
            _need(_keys(outputs,A.NAMES) and type(torch) is ModuleType and torch.__name__=='torch')
            _need(all(type(value) is torch.Tensor for value in outputs.values()))
            _need(torch.backends.mkldnn.enabled is False)
            R=frame.f_locals.get('R');L=frame.f_locals.get('L')
            pins=frame.f_locals.get('pins');before=frame.f_locals.get('before')
            _need(type(R) is ModuleType and type(L) is ModuleType and type(pins) is dict and type(before) is dict)
            common=_boundary(before,True)
            _need(R.same(L.snapshot(R,pins),before))
            hooks=frame.f_locals.get('hook_records')
            _need(_keys(hooks,('gate','silu','up','act','down')))
            records=[]
            for i,name in enumerate(A.NAMES):
                value=outputs[name]
                layout=dict(native_stride=list(value.stride()),storage_offset=value.storage_offset(),
                    is_contiguous=value.is_contiguous())
                if name in hooks:
                    hook=hooks[name]
                    _need(_keys(hook,('shape','native_dtype','native_stride','storage_offset','is_contiguous')))
                    _need(type(hook['shape']) is list and all(type(n) is int for n in hook['shape']) and
                        hook['shape']==SHAPES[name] and type(hook['native_dtype']) is str and hook['native_dtype']==str(value.dtype))
                    # Clone storage may differ; preserve original returned layout,
                    # exactly as capture.py does, while observing clone bytes.
                    layout={key:hook[key] for key in ('native_stride','storage_offset','is_contiguous')}
                records.append(dict(node=A.NODES[i],file=FILES[i],dtype=str(value.dtype),shape=list(value.shape),
                    **layout,bytes=math.prod(SHAPES[name])*(4 if name=='softmax_fp32' else 2)))
            metadata=_metadata(dict(schema=1,status='LOCAL_FAILURE_OUTPUTS_ONLY',boundary=common,records=records))
            _need(sum(row['bytes'] for row in records)<=33*1024*1024)
            directory=_path(out/DIRECTORY);directory.mkdir(exist_ok=False)
            for i,name in enumerate(A.NAMES):
                # Same native observation as capture, with no widening/forward.
                raw=outputs[name].contiguous().view(torch.uint8).numpy().tobytes()
                _need(type(raw) is bytes and len(raw)==records[i]['bytes'])
                _new(directory/FILES[i],raw)
                _need(_read(directory/FILES[i],len(raw))==raw)
            _need(torch.backends.mkldnn.enabled is False and R.same(L.snapshot(R,pins),before))
            # Completion marker is last; interrupted/partial directories reject.
            _new(directory/META,json.dumps(metadata,sort_keys=True,separators=(',',':')).encode())
            _inventory(directory)
            return directory
        trace=trace.tb_next
    return None


def _inventory(directory):
    directory=_path(directory)
    _need(directory.name==DIRECTORY and directory.is_dir() and {p.name for p in directory.iterdir()}==set(FILES)|{META})
    for name in (*FILES,META):
        path=_path(directory/name);_need(path.is_file() and path.stat().st_nlink==1)
    _need(sum((directory/name).stat().st_size for name in (*FILES,META))<=34*1024*1024)
    return directory


def _read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        _need(os.fstat(stream.fileno()).st_size<=limit)
        data=stream.read(limit+1)
    _need(len(data)<=limit)
    return data


def _unique(pairs):
    value={}
    for key,item in pairs:
        _need(key not in value);value[key]=item
    return value


def checked(value):
    _need(_keys(value,('schema','status','compared_count','same_count','diff_count','records')))
    _need(type(value['schema']) is int and value['schema']==1 and type(value['status']) is str and value['status']=='DIAGNOSTIC_ONLY')
    _need(all(type(value[k]) is int for k in ('compared_count','same_count','diff_count')) and
        value['compared_count']==29 and 0<=value['same_count']<=29 and value['diff_count']==29-value['same_count'])
    _need(type(value['records']) is list and len(value['records'])==29)
    for node,row in zip(A.NODES,value['records']):
        _need(_keys(row,('node','equal')) and type(row['node']) is str and row['node']==node and type(row['equal']) is bool)
    _need(sum(row['equal'] for row in value['records'])==value['same_count'])
    return {**value,'records':[dict(row) for row in value['records']]}


def compare(first,second):
    """Validate two complete local snapshots and compare metadata and all bytes."""
    directories=(_inventory(first),_inventory(second))
    _need(sum(sum(p.stat().st_size for p in d.iterdir()) for d in directories)<=69*1024*1024)
    metadata=[_metadata(json.loads(_read(d/META,1024*1024),object_pairs_hook=_unique)) for d in directories]
    _need(metadata[0]['boundary']==metadata[1]['boundary'])
    rows=[]
    for i,node in enumerate(A.NODES):
        records=[m['records'][i] for m in metadata]
        raw=[_read(d/FILES[i],r['bytes']) for d,r in zip(directories,records)]
        _need(all(len(data)==r['bytes'] for data,r in zip(raw,records)))
        rows.append(dict(node=node,equal=records[0]==records[1] and raw[0]==raw[1]))
    for directory in directories:_inventory(directory)
    same=sum(row['equal'] for row in rows)
    return checked(dict(schema=1,status='DIAGNOSTIC_ONLY',compared_count=29,same_count=same,diff_count=29-same,records=rows))
