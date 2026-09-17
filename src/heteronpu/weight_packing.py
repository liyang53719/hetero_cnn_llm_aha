"""Q21.1 raw weight -> BF16 row-major [K,N] packer with independent readback.

HF [N,K] uses transpose=True. IO tiles bound temporary RAM but DO NOT change
on-device storage into tile-major order. Pad columns to a declared multiple;
logical and physical shapes remain distinct. No official checkpoint loader,
GGUF dequantization, descriptor mutation, or NPU execution is claimed here.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import numpy as np


class PackingError(ValueError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise PackingError(why)


def positive(n: int, name: str) -> int:
    need(type(n) is int and 1 <= n < (1 << 32), 'invalid ' + name)
    return n


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


@dataclass(frozen=True)
class PackContract:
    source_rows: int
    source_columns: int
    transpose: bool
    input_dtype: str = 'f32le'
    column_multiple: int = 32
    chunk_rows: int = 64
    tile_columns: int = 256
    device_base: int = 0x100000000

    def layout(self) -> dict:
        positive(self.source_rows, 'rows'); positive(self.source_columns, 'columns')
        need(type(self.transpose) is bool, 'transpose must be boolean')
        need(self.input_dtype in ('f32le', 'bf16le'), 'explicit little-endian input dtype required')
        positive(self.column_multiple, 'column_multiple')
        need(self.column_multiple >= 32 and self.column_multiple <= 4096 and self.column_multiple & (self.column_multiple-1) == 0, 'column_multiple must be power-of-two 32..4096')
        need(1 <= positive(self.chunk_rows, 'chunk_rows') <= 4096, 'chunk_rows too large')
        need(1 <= positive(self.tile_columns, 'tile_columns') <= 4096, 'tile_columns too large')
        need(type(self.device_base) is int and 0 <= self.device_base < (1 << 56) and self.device_base % 64 == 0, 'invalid device base')
        k,n = (self.source_columns,self.source_rows) if self.transpose else (self.source_rows,self.source_columns)
        pn = (n+self.column_multiple-1)//self.column_multiple*self.column_multiple
        size = k*pn*2
        need(self.device_base+size <= 1 << 56, 'device extent overflows 56 bits')
        return dict(logical_kn=[k,n], storage_kn=[k,pn], row_stride_bytes=pn*2,
                    payload_bytes=size, source_bytes=self.source_rows*self.source_columns*(4 if self.input_dtype=='f32le' else 2))


def round_bf16(words: np.ndarray) -> np.ndarray:
    """Finite FP32 bit patterns, RNE; preserves representable subnormals/-0."""
    need(words.dtype.kind == 'u' and words.dtype.itemsize == 4, 'FP32 bit words must be uint32')
    need(not np.any((words & 0x7f800000) == 0x7f800000), 'nonfinite FP32 input')
    wide = words.astype(np.uint64)
    out = ((wide + 0x7fff + ((wide >> 16) & 1)) >> 16).astype('<u2')
    need(not np.any((out & 0x7f80) == 0x7f80), 'BF16 rounding overflow')
    return out


def _convert(words: np.ndarray, dtype: str) -> np.ndarray:
    if dtype == 'f32le':
        return round_bf16(words)
    need(not np.any((words & 0x7f80) == 0x7f80), 'nonfinite BF16 input')
    return words.astype('<u2', copy=False)


def _source(source: Path, c: PackContract, layout: dict) -> np.memmap:
    need(source.is_file() and source.stat().st_size == layout['source_bytes'], 'source byte length mismatch')
    return np.memmap(source, mode='r', dtype='<u4' if c.input_dtype=='f32le' else '<u2', shape=(c.source_rows,c.source_columns))


def _rows(k: int, chunk: int):
    for start in range(0,k,chunk):
        yield start,min(start+chunk,k)


def _chunks(payload: Path, layout: dict, c: PackContract) -> list[dict]:
    chunks=[]
    with payload.open('rb') as f:
        for first,end in _rows(layout['storage_kn'][0],c.chunk_rows):
            size=(end-first)*layout['row_stride_bytes']
            offset=first*layout['row_stride_bytes']; f.seek(offset)
            h=hashlib.sha256(); left=size
            while left:
                data=f.read(min(left,1<<20)); need(bool(data),'truncated payload chunk')
                h.update(data);left-=len(data)
            chunks.append(dict(first_k=first,rows=end-first,offset=offset,bytes=size,sha256=h.hexdigest()))
    return chunks


def pack_file(source: Path, output: Path, contract: PackContract) -> dict:
    layout=contract.layout()
    need(not output.exists() and not output.is_symlink(), 'output must be a new directory')
    raw=_source(source,contract,layout)
    before=digest(source)
    # Validate all source words before creating any apparently deliverable file.
    flat=raw.reshape(-1)
    for i in range(0,flat.size,1<<18): _convert(flat[i:i+(1<<18)],contract.input_dtype)
    b=raw.T if contract.transpose else raw
    k,n=layout['logical_kn']; pn=layout['storage_kn'][1]
    output.mkdir(parents=True,exist_ok=False)
    payload=output/'weights.bf16le'
    with payload.open('xb') as f:
        f.truncate(layout['payload_bytes'])  # zero padding, never uninitialized RAM
        for r0,r1 in _rows(k,contract.chunk_rows):
            for c0 in range(0,n,contract.tile_columns):
                c1=min(n,c0+contract.tile_columns)
                tile=_convert(np.asarray(b[r0:r1,c0:c1]),contract.input_dtype)
                for row in range(r1-r0):
                    f.seek(((r0+row)*pn+c0)*2)
                    f.write(tile[row].tobytes())
    need(digest(source)==before, 'source changed during packing; partial directory preserved')
    manifest=dict(schema=1,format='row_major_kn_bf16le',contract=asdict(contract),**layout,
                  source_sha256=before,payload_sha256=digest(payload),chunks=_chunks(payload,layout,contract),
                  rounding='RNE_finite_preserve_subnormal_reject_overflow',descriptor_patched=False)
    # Completion manifest is written last. A failed run leaves no success manifest.
    with (output/'manifest.json').open('x',encoding='utf-8') as f:
        json.dump(manifest,f,indent=2);f.write('\n')
    return manifest


def _independent_bf16(words: np.ndarray, dtype: str) -> np.ndarray:
    """Different tie decision than the add-bias encoder, used for full readback."""
    if dtype=='bf16le':
        need(not np.any((words & 0x7f80)==0x7f80),'nonfinite BF16 source')
        return words.astype('<u2',copy=False)
    need(not np.any((words & 0x7f800000)==0x7f800000),'nonfinite FP32 source')
    high=words.astype(np.uint64)>>16
    low=words & 0xffff
    increment=(low>0x8000)|((low==0x8000)&((high&1)!=0))
    value=(high+increment).astype('<u2')
    need(not np.any((value & 0x7f80)==0x7f80),'BF16 overflow in reference')
    return value


def verify_package(source: Path, output: Path, expected: PackContract) -> dict:
    layout=expected.layout()
    need(output.is_dir() and not output.is_symlink(), 'missing/aliased package')
    def unique(pairs):
        result={}
        for k,v in pairs:
            need(k not in result,'duplicate manifest key');result[k]=v
        return result
    manifest_path=output/'manifest.json';payload=output/'weights.bf16le'
    need(not manifest_path.is_symlink() and not payload.is_symlink(),'symlink package member')
    m=json.loads(manifest_path.read_text(),object_pairs_hook=unique)
    fields={'schema','format','contract',*layout,'source_sha256','payload_sha256','chunks','rounding','descriptor_patched'}
    need(isinstance(m,dict) and set(m)==fields, 'manifest fields')
    # JSON canonical equality distinguishes booleans from integer dimensions.
    need(type(m['schema']) is int and m['schema']==1 and m['format']=='row_major_kn_bf16le','schema/format')
    need(json.dumps(m['contract'],sort_keys=True)==json.dumps(asdict(expected),sort_keys=True),'packing contract drift')
    need(json.dumps({key:m[key] for key in layout},sort_keys=True)==json.dumps(layout,sort_keys=True),'layout drift')
    need(m['rounding']=='RNE_finite_preserve_subnormal_reject_overflow' and m['descriptor_patched'] is False,'precision/ABI policy drift')
    raw=_source(source,expected,layout);before=digest(source)
    need(m['source_sha256']==before,'source hash changed')
    need(payload.is_file() and not payload.samefile(source) and payload.stat().st_size==layout['payload_bytes'],'payload bytes/alias')
    need(m['payload_sha256']==digest(payload),'payload hash mismatch')
    need(json.dumps(m['chunks'],sort_keys=True)==json.dumps(_chunks(payload,layout,expected),sort_keys=True),'missing/duplicate/reordered chunk')
    b=raw.T if expected.transpose else raw
    packed=np.memmap(payload,mode='r',dtype='<u2',shape=tuple(layout['storage_kn']))
    k,n=layout['logical_kn'];checked=0
    for r0,r1 in _rows(k,expected.chunk_rows):
        for c0 in range(0,n,expected.tile_columns):
            c1=min(n,c0+expected.tile_columns)
            ref=_independent_bf16(np.asarray(b[r0:r1,c0:c1]),expected.input_dtype)
            need(np.array_equal(packed[r0:r1,c0:c1],ref),f'weight byte parity at k={r0},n={c0}')
            checked+=(r1-r0)*(c1-c0)
        need(not np.any(packed[r0:r1,n:]!=0),'nonzero padding')
    need(digest(source)==before and digest(payload)==m['payload_sha256'],'file changed during readback')
    return dict(status='PASS_WEIGHT_PACK_READBACK',elements=checked,padding_elements=k*(layout['storage_kn'][1]-n),
                payload_sha256=m['payload_sha256'],source_sha256=before,
                official_weights_verified=False,rtl_execution=False,**layout)
