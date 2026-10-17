"""Bounded stdlib-only replay identity projection. Never runs numerical code.

The live parent owns numerical qualification and publication. Prepared objects
are private in-process state, never portable acceptance receipts. This module
neither writes files nor grants numerical, RTL, hardware, or freeze acceptance.
All errors are fixed codes; private paths and raw runtime strings stay private.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

SCHEMA = 'qwen2-same-host-replay-identity-v1'
BASE = 'candidates/qwen2_resident_matrix/'
MODEL = 'Qwen/Qwen2-1.5B-Instruct'
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
FORWARD = '9fe3f585bb4ea29f209dc705d269fbe292e1128f'
POLICY_SHA = '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'
LEDGER = 'config/payload_pins/qwen2_layer0.json'
LEDGER_SHA = '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'
CONFIG = 'config/upstream/weight_headers/qwen2_1p5b/config.json'
CONFIG_SHA = 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136'
TABLE_SHA = '5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045'
RUNNER_SHA = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
MAX_JSON = 16 * 1024 * 1024
MAX_FILE = 188043264
MAX_CAPTURE = 32 * 1024 * 1024
MAX_TOTAL = 8 * 1024**3
MAX_RECORDS = 4096
CHUNK = 1024 * 1024
WIDTHS = dict(zip(('n0','qr','kr','v','q','k','att','o','r','n1','gate','up','act','down','y'),
                 (1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536)))
ACTUAL_WIDTHS = dict(WIDTHS, qraw=1536, kraw=256, vraw=256, kv=512, silu=8960)
STAGES = tuple(sorted((*WIDTHS, 'x','cache_k','cache_v','repeat_k','repeat_v','scores','logits',
                       'prob','pv','silu','cos','sin','mask','softmax_fp32')))
METHODS = ('official_self_cache','independent_self_cache')
MODES = ('bf16','fp32')
FIELDS = ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp',
          'softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
CAUSAL_FIELDS = FIELDS[:7]
OBSERVED_STAGES = tuple(n for n in STAGES if n != 'mask')
SCALAR_FLAGS = ('-O2','-std=c++17','-ffp-contract=off','-fno-fast-math')
LIBRARY_FLAGS = ('-shared','-fPIC','-O2','-ffp-contract=off','-fno-fast-math')
RECIPE_FLAGS = ('-shared','-fPIC','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math','-fno-builtin-fmaf')
PAYLOAD_NAMES = ('embed_tokens.rows_0_255','input_layernorm.weight','mlp.down_proj.weight',
 'mlp.gate_proj.weight','mlp.up_proj.weight','post_attention_layernorm.weight','self_attn.k_proj.bias',
 'self_attn.k_proj.weight','self_attn.o_proj.weight','self_attn.q_proj.bias','self_attn.q_proj.weight',
 'self_attn.v_proj.bias','self_attn.v_proj.weight')
INPUT_PINS = {
 16:('271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c',
     '0a94ea142c28a6c1ce4b8ad928caecee9c5721bb6e4bc0eb097eebd8202aabf8'),
 128:('ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df',
      'e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7')}
PROVIDERS = {
 'gamma0':([1,1536],'float32','input_layernorm.weight','BF16_EXPAND_F32'),
 'gamma1':([1,1536],'float32','post_attention_layernorm.weight','BF16_EXPAND_F32'),
 'bq':([1,1536],'float32','self_attn.q_proj.bias','BF16_EXPAND_F32'),
 'bk':([1,256],'float32','self_attn.k_proj.bias','BF16_EXPAND_F32'),
 'bv':([1,256],'float32','self_attn.v_proj.bias','BF16_EXPAND_F32'),
 'wq':([1536,1536],'bfloat16','self_attn.q_proj.weight','BF16_TRANSPOSE_2D'),
 'wk':([1536,256],'bfloat16','self_attn.k_proj.weight','BF16_TRANSPOSE_2D'),
 'wv':([1536,256],'bfloat16','self_attn.v_proj.weight','BF16_TRANSPOSE_2D'),
 'wo':([1536,1536],'bfloat16','self_attn.o_proj.weight','BF16_TRANSPOSE_2D'),
 'wg':([1536,8960],'bfloat16','mlp.gate_proj.weight','BF16_TRANSPOSE_2D'),
 'wu':([1536,8960],'bfloat16','mlp.up_proj.weight','BF16_TRANSPOSE_2D'),
 'wd':([8960,1536],'bfloat16','mlp.down_proj.weight','BF16_TRANSPOSE_2D')}
RECIPE_SOURCES = {
 'payload_loader':'scripts/qwen2_layer0_payload.py',
 'native_gate':'scripts/qwen2_layer0_model_gate.py',
 'scalar_layout':'scripts/qwen2_block_recipe_model.py',
 'scalar_materialization':'scripts/qwen2_bf16_materialization_candidate.py',
 'input_and_tables':'scripts/qwen2_rms_rope_prefill_candidate.py',
 'loaded_provider_recipe':BASE+'official_bf16/check_numeric.py',
 'actual_persistence':BASE+'ffn_public/fullgraph_execution.py',
 'scalar_inventory':BASE+'dense_block_reduce/reference/workload.py',
 'm16_capture':BASE+'attention_packed_observation/capture.py',
 'm128_capture':BASE+'attention_packed_tiled_observation/capture.py'}


class IdentityError(ValueError):
    """Constant, path-free failure code; parent must keep readiness false."""

ERROR_CODES = frozenset((
    'ABSOLUTE_PATH',
    'ACTUAL_COUNT',
    'ACTUAL_FIELDS',
    'ACTUAL_SET',
    'ACTUAL_SIZE',
    'ACTUAL_STAGE_SET',
    'ATTEMPT_BINDING',
    'BLAS_ENVIRONMENT',
    'BYTE_CAP',
    'CAPTURE_COVERAGE',
    'CAPTURE_FIELD',
    'CAPTURE_LIMIT',
    'CAPTURE_METADATA',
    'CAPTURE_OBSERVED_COUNT',
    'CAPTURE_SENTINEL',
    'CAPTURE_SIZE',
    'CAUSAL_REFERENCE_SIZE',
    'CI_FIELDS',
    'CI_IDENTITY',
    'COMBINED_BINARY_FIELDS',
    'COMBINED_BINARY_TARGET',
    'COMBINED_BUILD',
    'COMPARISON_SCOPE',
    'COMPILER_HASH',
    'COMPILER_VERSION',
    'COMPILER_VERSION_ALLOWLIST',
    'DEADLINE_TYPE',
    'DERIVED_SIZE',
    'DIAGNOSTIC_VERDICT',
    'DIRECTORY_DRIFT',
    'EXPECTED_HASH',
    'EXPECTED_SIZE',
    'EXPORT_FIELDS',
    'EXPORT_METADATA',
    'FIELDS',
    'FILE_ACCESS',
    'FILE_CLOSE',
    'FILE_ALIAS',
    'FILE_DRIFT',
    'FILE_HASH',
    'FILE_SIZE',
    'FILE_TYPE_SIZE_ALIAS',
    'FINAL_CHILD_BINDING',
    'FINAL_RECEIPT_BINDING',
    'FINAL_SOURCE_BINDING',
    'FINAL_SOURCE_DIGEST',
    'FIXED_OBSERVED_HASH',
    'FIXED_OBSERVED_SET',
    'FIXED_OUTPUT_HASH',
    'FIXED_OUTPUT_SET',
    'FULL_SNAPSHOT_BINDING',
    'FULL_STATUS',
    'GATE_CONTENT_BINDING',
    'GATE_METHODS',
    'GATE_STAGES',
    'GATE_VERDICT',
    'INDEPENDENT_VERIFIER',
    'INTERNAL_STAGE_SET',
    'JSON_ARRAY',
    'JSON_COMPLEXITY',
    'JSON_DUPLICATE',
    'JSON_INTEGER',
    'JSON_INVALID',
    'JSON_NONFINITE',
    'JSON_OBJECT',
    'JSON_SIZE',
    'JSON_STRING',
    'JSON_TYPE',
    'LIBC_HASH',
    'LIBC_SET',
    'LIBRARY_FIELDS',
    'LIVE_CONTEXT',
    'LOADED_PROVIDER_SET',
    'LOADED_X_BINDING',
    'LOGICAL_ID',
    'LOGICAL_REFERENCE',
    'M128_CONTEXT_BINDING',
    'M16_FULL_BINDING',
    'M16_QUALIFICATION',
    'M16_SOURCE_MAP',
    'NATIVE_BINDING',
    'NATIVE_CONTEXT',
    'NATIVE_COUNT',
    'NATIVE_FIELDS',
    'NATIVE_LOGICAL_HASH',
    'NATIVE_METHODS',
    'NATIVE_MODES',
    'NATIVE_OUTPUT_SET',
    'NATIVE_PHASES',
    'NATIVE_PRODUCER',
    'NATIVE_STAGES',
    'NATIVE_STIMULUS',
    'NATIVE_STORAGE',
    'OBSERVATION_SET',
    'PARENT_COMPLETION',
    'PARENT_VALIDATION',
    'PAYLOAD_FIELDS',
    'PAYLOAD_LEDGER',
    'PAYLOAD_METADATA_ORDER',
    'PAYLOAD_METADATA_SET',
    'PAYLOAD_PIN',
    'PAYLOAD_SET',
    'PERMUTATION_GEOMETRY',
    'POINTER_FIELDS',
    'POINTER_TARGET',
    'POLICY_THRESHOLDS',
    'PREPARED_DRIFT',
    'PREPARED_STATE',
    'PREREQUISITE_RECORDS',
    'PRODUCER_ROOTS',
    'PRODUCER_SOURCES',
    'PRODUCER_STATUS',
    'PROVIDER_FIELDS',
    'PROVIDER_GEOMETRY',
    'PUBLIC_SIZE',
    'PV_ACK_BINDING',
    'PYTHON_HASH',
    'QUALIFICATION_STATE',
    'QUALIFIED_OFFICIAL_GATE',
    'QUALIFIED_PRODUCER_BINDING',
    'READONLY_FIELDS',
    'READONLY_PIN',
    'READ_LIMIT',
    'RECIPE_LIBRARY_BUILD',
    'RECIPE_LIBRARY_SET',
    'RECIPE_SOURCE_HASH',
    'RECIPE_SOURCE_PINS',
    'RECORD',
    'RECORD_CAP',
    'RECORD_GEOMETRY',
    'RECORD_IDENTITY',
    'RECORD_ROOT',
    'RECORD_TARGET',
    'REFERENCE_DEADLINE',
    'RELATIVE_PATH',
    'RESULT_MODES',
    'ROOTED_RECORD',
    'ROWS',
    'RUNTIME_BUILD',
    'RUNTIME_HASH',
    'RUNTIME_PROFILE',
    'RUNTIME_SETTINGS',
    'SCALAR_BUILD',
    'SCALAR_COUNT',
    'SCALAR_OUTPUT_SET',
    'SCALAR_RUN',
    'SEQUENTIAL_EXPORT_ORDER',
    'SEQUENTIAL_EXPORT_SET',
    'SHARED_PAYLOAD',
    'SHARED_RUNTIME',
    'SOURCE_OUTPUT_OVERLAP',
    'SOURCE_SET',
    'TENSOR_DTYPE_ENCODING',
    'TENSOR_HASH',
    'TENSOR_SHAPE',
    'TENSOR_SIZE',
    'WHOLE_CHECKPOINT_SCOPE',
) )


def error_code(error):
    """Whitelist a fixed IdentityError code; never stringify an exception."""
    if type(error) is IdentityError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in ERROR_CODES:
        return error.args[0]
    return 'UNKNOWN'


def need(value, code):
    if not value:
        raise IdentityError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def digest(value, length=64):
    return type(value) is str and len(value)==length and all(c in '0123456789abcdef' for c in value)


def exact(value, keys, code='FIELDS'):
    need(type(value) is dict and set(value)==set(keys), code)


def positive(value, maximum=MAX_FILE):
    return type(value) is int and 0 < value <= maximum


def strict(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_JSON, 'JSON_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'JSON_DUPLICATE')
            result[key] = value
        return result
    def bad(_):
        raise IdentityError('JSON_NONFINITE')
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
        stack, count = [(result,0)], 0
        while stack:
            value, depth = stack.pop(); count += 1
            need(depth <= 48 and count <= 250000, 'JSON_COMPLEXITY')
            if type(value) is dict:
                need(len(value)<=4096 and all(type(k) is str and len(k)<=2048 for k in value), 'JSON_OBJECT')
                stack.extend((v,depth+1) for v in value.values())
            elif type(value) is list:
                need(len(value)<=32768, 'JSON_ARRAY');stack.extend((v,depth+1) for v in value)
            elif type(value) is str:
                need(len(value.encode('utf-8'))<=131072, 'JSON_STRING')
            elif type(value) is float:
                need(math.isfinite(value), 'JSON_NONFINITE')
            else:
                need(value is None or type(value) in (bool,int), 'JSON_TYPE')
                if type(value) is int: need(abs(value)<2**128, 'JSON_INTEGER')
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise IdentityError('JSON_INVALID') from None


def remaining(deadline):
    need(type(deadline) in (int,float) and math.isfinite(deadline) and deadline>0, 'DEADLINE_TYPE')
    if time.monotonic() >= deadline:
        raise TimeoutError('REPLAY_IDENTITY_DEADLINE')


def relative(value):
    need(type(value) is str and 0<len(value)<=2048 and '\\' not in value and '\x00' not in value and
         all(x not in ('','.','..') for x in value.split('/')), 'RELATIVE_PATH')
    return value


def absolute(value):
    value = str(value) if isinstance(value, Path) else value
    need(type(value) is str and value.startswith('/') and len(value)<=4096 and '\\' not in value and
         '\x00' not in value and str(Path(value))==value and '..' not in value.split('/'), 'ABSOLUTE_PATH')
    return Path(value)


def signature(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


class Reader:
    """No-follow descriptor traversal; fixed byte, unique-file and read caps."""
    def __init__(self, deadline):
        remaining(deadline)
        self.deadline=deadline;self.files={};self.inodes={};self.total=0

    def read(self, path, expected, *, size=None, capture=False, limit=MAX_FILE):
        remaining(self.deadline);path=absolute(path)
        need(digest(expected), 'EXPECTED_HASH')
        need(type(limit) is int and 0<limit<=MAX_FILE, 'READ_LIMIT')
        if size is not None: need(positive(size,limit), 'EXPECTED_SIZE')
        if capture: need(limit<=MAX_CAPTURE, 'CAPTURE_LIMIT')
        descriptors=[];failed=False
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY);descriptors.append(fd)
            for part in path.parts[1:-1]:
                fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);descriptors.append(fd)
            parent=fd
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);descriptors.append(fd)
            before=os.fstat(fd);sig=signature(before)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and positive(before.st_size,limit), 'FILE_TYPE_SIZE_ALIAS')
            need(size is None or size==before.st_size, 'FILE_SIZE')
            key=str(path);inode=(before.st_dev,before.st_ino)
            need(inode not in self.inodes or self.inodes[inode]==key, 'FILE_ALIAS')
            if key in self.files:
                need(self.files[key]==(expected,sig), 'FILE_DRIFT')
            else:
                need(len(self.files)<MAX_RECORDS, 'RECORD_CAP')
            need(self.total+before.st_size<=MAX_TOTAL, 'BYTE_CAP')
            hasher=hashlib.sha256();chunks=[];count=0
            while count<before.st_size:
                remaining(self.deadline)
                block=os.read(fd,min(CHUNK,before.st_size-count))
                if not block:break
                count+=len(block);self.total+=len(block)
                need(count<=before.st_size and self.total<=MAX_TOTAL, 'BYTE_CAP');hasher.update(block)
                if capture:chunks.append(block)
            after=os.fstat(fd);named=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            need(count==before.st_size and signature(after)==sig and signature(named)==sig,'FILE_DRIFT')
            need(hasher.hexdigest()==expected, 'FILE_HASH')
            # Verify directory descriptors still identify their original absolute names.
            for index,opened in enumerate(descriptors[:-1]):
                check=Path('/') if index==0 else Path(*path.parts[:index+1])
                current=os.stat(check,follow_symlinks=False)
                opened_info=os.fstat(opened)
                need(stat.S_ISDIR(current.st_mode) and (current.st_dev,current.st_ino)==
                     (opened_info.st_dev,opened_info.st_ino), 'DIRECTORY_DRIFT')
            self.files[key]=(expected,sig);self.inodes[inode]=key
            remaining(self.deadline)
            return b''.join(chunks) if capture else before.st_size
        except TimeoutError:
            failed=True;raise
        except OSError:
            failed=True;raise IdentityError('FILE_ACCESS') from None
        except BaseException:
            failed=True;raise
        finally:
            close_failed=False
            for fd in reversed(descriptors):
                try:os.close(fd)
                except OSError:close_failed=True
            if not failed:
                need(not close_failed,'FILE_CLOSE')
                remaining(self.deadline)

    def json(self, path, expected):
        return strict(self.read(path,expected,capture=True,limit=MAX_JSON))

    def pointer(self, item, expected_path=None):
        exact(item,('path','sha256'),'POINTER_FIELDS')
        path=absolute(item['path'])
        need(expected_path is None or path==absolute(expected_path),'POINTER_TARGET')
        return self.json(path,item['sha256'])

    def verify(self):
        for path,(expected,sig) in tuple(self.files.items()):
            self.read(path,expected,size=sig[4])
        remaining(self.deadline)


def shapes(rows):
    need(type(rows) is int and rows in (16,128), 'ROWS')
    result={name:[1,rows,width] for name,width in WIDTHS.items()}
    result.update(x=[1,rows,1536],silu=[1,rows,8960])
    for name,heads in (('q',12),('k',2),('cache_k',2),('cache_v',2),('repeat_k',12),('repeat_v',12),('pv',12)):
        result[name]=[1,heads,rows,128]
    for name in ('scores','logits','prob','softmax_fp32'):result[name]=[1,12,rows,rows]
    result.update(mask=[1,1,rows,rows],cos=[rows,128],sin=[rows,128])
    need(set(result)==set(STAGES) and len(result)==29,'INTERNAL_STAGE_SET')
    return result


def export_shape(rows,name):
    return [1,rows,1536 if name=='q' else 256] if name in ('q','k') else shapes(rows)[name]


def token_to_head(raw, rows, heads, dim=128):
    """Byte permutation only: [1,M,H,D] -> [1,H,M,D], no FP decode."""
    need(type(raw) is bytes and type(rows) is int and type(heads) is int and type(dim) is int and
         0<rows<=128 and 0<heads<=12 and 0<dim<=128 and len(raw)==rows*heads*dim*4,'PERMUTATION_GEOMETRY')
    width=dim*4
    return b''.join(raw[(m*heads+h)*width:(m*heads+h+1)*width] for h in range(heads) for m in range(rows))


def descriptor(raw_hash, content_hash, stored, logical, *, dtype='bfloat16', encoding='float32_le',
               mapping='IDENTITY_C_ORDER', verification='DIRECT_FILE_REHASH', size=None, origin='REFERENCE_EXPORT'):
    need(digest(raw_hash) and digest(content_hash),'TENSOR_HASH')
    need(all(type(s) is list and 1<=len(s)<=5 and all(positive(x,MAX_FILE) for x in s) for s in (stored,logical)), 'TENSOR_SHAPE')
    need(dtype in ('bfloat16','float32','uint32','uint16','uint8') and
         encoding in ('bfloat16_le','float32_le','uint32_le','uint16_le','uint8'),'TENSOR_DTYPE_ENCODING')
    itemsize=2 if encoding in ('bfloat16_le','uint16_le') else 1 if encoding=='uint8' else 4
    count=math.prod(stored)*itemsize
    need(count==math.prod(logical)*itemsize and positive(count) and (size is None or size==count),'TENSOR_SIZE')
    return dict(stored_shape=stored,logical_shape=logical,logical_dtype=dtype,storage_encoding=encoding,
                bytes=count,file_sha256=raw_hash,content_sha256=content_hash,canonical_mapping=mapping,
                verification=verification,origin=origin)


def record_path(item, rows, out, expected):
    root=out/'m16/setup/producer' if rows==16 else out/'producer128'
    if rows==128:
        exact(item,('root','path','bytes','sha256'),'ROOTED_RECORD')
        need(item['root'] in ('current','upstream'),'RECORD_ROOT')
        if item['root']=='upstream':root=out/'m16/setup/producer'
    else:exact(item,('path','bytes','sha256'),'RECORD')
    name=relative(item['path']);need(name==expected,'RECORD_TARGET')
    need(positive(item['bytes']) and digest(item['sha256']),'RECORD_IDENTITY')
    return root/name


def read_record(reader,item,rows,out,expected,*,size=None,capture=False):
    path=record_path(item,rows,out,expected)
    need(size is None or item['bytes']==size,'RECORD_GEOMETRY')
    return reader.read(path,item['sha256'],size=item['bytes'],capture=capture,limit=MAX_CAPTURE if capture else MAX_FILE)


def tensor(reader,item,rows,out,path,name,*,mode='bf16',raw_cache=False):
    logical=shapes(rows)[name]
    stored=[1,rows,2,128] if raw_cache else export_shape(rows,name)
    raw=read_record(reader,item,rows,out,path,size=math.prod(stored)*4,capture=True)
    transpose=name in ('q','k') or raw_cache
    canon=token_to_head(raw,rows,12 if name=='q' else 2) if transpose else raw
    result=descriptor(item['sha256'],sha(canon),stored,logical,
                      dtype='float32' if mode=='fp32' or name=='softmax_fp32' else 'bfloat16',
                      mapping='TOKEN_HEAD_BYTE_PERMUTATION' if transpose else 'IDENTITY_C_ORDER')
    return result


def source_map(reader,root,sources):
    need(type(sources) is dict and 1<=len(sources)<=512,'SOURCE_SET')
    for name,expected in sorted(sources.items()):
        reader.read(root/relative(name),expected,limit=8*1024*1024)
    return sha(encoded(sources))


def validate_ci(ci):
    exact(ci,('commit','run_id','run_attempt'),'CI_FIELDS')
    need(digest(ci['commit'],40) and type(ci['run_id']) is str and ci['run_id'].isascii() and
         ci['run_id'].isdecimal() and 0<int(ci['run_id'])<10**24 and ci['run_attempt']=='1','CI_IDENTITY')
    return dict(ci)


def compiler_projection(compiler):
    need(type(compiler) is dict and digest(compiler.get('sha256')),'COMPILER_HASH')
    version=compiler.get('version');need(type(version) is str and 0<len(version)<=4096,'COMPILER_VERSION')
    match=re.fullmatch(r'(?:x86_64-linux-gnu-)?g\+\+(?:-[0-9]{1,2})? (?:\((?:Ubuntu|Debian) [0-9A-Za-z.+~ -]{1,80}\) )?([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{1,2})',version)
    need(match is not None,'COMPILER_VERSION_ALLOWLIST')
    return dict(family='GNU_GXX',version_components=[int(v) for v in match.groups()],
                version_text_sha256=sha(version.encode()),executable_sha256=compiler['sha256'],
                verification='QUALIFIED_METADATA_ONLY')


def runtime_projection(producer):
    identity,observed=producer['runtime_identity'],producer['runtime_observation']
    fixed=dict(python='3.12.15',torch='2.10.0+cpu',numpy='2.3.5',transformers='4.40.1',
        device='cpu',attention='eager',model_revision=REVISION,forward_revision=FORWARD,
        installed_sources_verified_exact=True,runner_sha256=RUNNER_SHA)
    need(all(type(identity.get(k)) is type(v) and identity[k]==v for k,v in fixed.items()),'RUNTIME_PROFILE')
    hashes={}
    for name in ('cache_utils_sha256','mask_utils_sha256','activations_sha256'):
        need(digest(identity.get(name)),'RUNTIME_HASH');hashes[name]=identity[name]
    for name in ('torch_build','numpy_build'):
        value=identity[name];need(type(value) is str and 0<len(value.encode())<=65536,'RUNTIME_BUILD')
        hashes[name+'_sha256']=sha(value.encode())
    fenv=dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False)
    need(observed.get('fenv')==fenv and observed.get('mkldnn_enabled') is True and
         observed.get('torch_commit')=='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0','RUNTIME_SETTINGS')
    need(observed.get('blas_environment')==dict(OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4'),
         'BLAS_ENVIRONMENT')
    need(digest(observed.get('python_executable_sha256')),'PYTHON_HASH')
    libc=observed['runtime_libc_sha256'];exact(libc,('libm.so.6','libc.so.6'),'LIBC_SET')
    need(all(digest(v) for v in libc.values()),'LIBC_HASH')
    return dict(packages={k:fixed[k] for k in ('python','torch','numpy','transformers')},
        compiler=compiler_projection(observed['compiler']),torch_commit=observed['torch_commit'],
        runtime_files=dict(python=observed['python_executable_sha256'],libc=libc['libc.so.6'],libm=libc['libm.so.6']),
        runtime_files_verification='QUALIFIED_METADATA_ONLY',fenv=fenv,mkldnn_enabled=True,
        threads=4,interop_threads=1,deterministic_algorithms=True,device='cpu',attention='eager',
        settings_basis=dict(threads='QUALIFIED_NATIVE_METADATA',interop_threads='SOURCE_ENFORCED_CONFIGURATION',
                            deterministic_algorithms='SOURCE_ENFORCED_CONFIGURATION'),
        blas_environment=dict(OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4'),
        build_hashes=hashes,dispatch_metadata_sha256=sha(encoded(producer['dispatch'])),
        cpu_metadata_sha256=sha(encoded(observed['cpu'])))


def producer_projection(reader,producer,rows,out,ledger):
    need(producer.get('rows')==rows and type(producer['rows']) is int and producer.get('past_tokens')==0 and
         type(producer['past_tokens']) is int and producer.get('status')==f'COMPLETE_FRESH_M{rows}_REFERENCE_OUTPUTS' and
         producer.get('original_small_gate_revalidated') is True,'PRODUCER_STATUS')
    need(digest(producer.get('driver_sha256')) and digest(producer.get('source_lock_sha256')) and
         producer['source_manifest_sha256']==sha(encoded(producer['source_sha256'])),'PRODUCER_SOURCES')
    if rows==128:
        need(producer['roots']==dict(current=str(out/'producer128'),upstream=str(out/'m16/setup/producer')),'PRODUCER_ROOTS')
    native=producer['native'];exact(native,('producer','result','outputs'),'NATIVE_FIELDS')
    need(native['producer']=='generated-paired-qkv-qk.run_gate','NATIVE_PRODUCER')
    native_path=f'native{rows}/RESULT.json'
    result=strict(read_record(reader,native['result'],rows,out,native_path,capture=True))
    need(result.get('tokens')==rows and result.get('carried') is False and result.get('layer')==0 and
         result.get('torch_threads')==4 and result.get('official_framework_forward') is True and
         result.get('model_id')==MODEL and result.get('manifest_whole_checkpoint_hash_verified') is False and
         result.get('identity')==producer['runtime_identity'] and
         result.get('blas_environment')==producer['runtime_observation']['blas_environment'],'NATIVE_CONTEXT')
    exact(native['outputs'],MODES,'NATIVE_MODES');exact(result['modes'],MODES,'RESULT_MODES')
    records={};native_raw={}
    for mode in MODES:
        exact(native['outputs'][mode],METHODS,'NATIVE_METHODS')
        phases=result['modes'][mode]['phases'];need(type(phases) is list and len(phases)==1,'NATIVE_PHASES')
        phase=phases[0]
        need(type(phase['phase']) is int and phase['phase']==0 and type(phase['past_tokens']) is int and
             phase['past_tokens']==0 and phase['token_ids']==list(range(rows)) and
             phase['position_ids']==list(range(rows)),'NATIVE_STIMULUS')
        exact(phase['stages'],STAGES,'NATIVE_STAGES')
        for method,prefix in zip(METHODS,('native','independent')):
            exact(native['outputs'][mode][method],STAGES,'NATIVE_OUTPUT_SET')
            for name in STAGES:
                entry=phase['stages'][name];item=native['outputs'][mode][method][name]
                relative_file=f'{mode}/phase_0/{prefix}_{name}.f32le'
                need(entry[prefix+'_file']==relative_file and entry[prefix+'_export_shape']==export_shape(rows,name) and
                     entry['shape']==shapes(rows)[name] and entry[prefix+'_file_sha256']==item['sha256'],'NATIVE_BINDING')
                record=tensor(reader,item,rows,out,f'native{rows}/'+relative_file,name,mode=mode)
                expected=entry['actual_f32_sha256' if prefix=='native' else 'reference_f32_sha256']
                need(record['content_sha256']==expected,'NATIVE_LOGICAL_HASH')
                storage='torch.bfloat16' if mode=='bf16' and name!='softmax_fp32' else 'torch.float32'
                need(entry.get('actual_storage_dtype')==storage and digest(entry.get('actual_storage_sha256')),'NATIVE_STORAGE')
                record['native_storage']=dict(verification='QUALIFIED_METADATA_ONLY',dtype=storage,
                    content_sha256=entry['actual_storage_sha256'],logical_shape=shapes(rows)[name]) if prefix=='native' else dict(
                    verification='NOT_EMITTED_BY_PRODUCER',dtype=None,content_sha256=None)
                record['acceptance_scope']='BF16_REFERENCE' if mode=='bf16' else 'FP32_DIAGNOSTIC_ONLY'
                records[f'{mode}.{method}.{name}']=record
                native_raw[(mode,method,name)]=item
    need(len(records)==116,'NATIVE_COUNT')
    payload=producer['payload'];exact(payload,('manifest','tensors'),'PAYLOAD_FIELDS')
    exact(payload['tensors'],PAYLOAD_NAMES,'PAYLOAD_SET')
    actual_payload=strict(read_record(reader,payload['manifest'],rows,out,'payload/manifest.json',capture=True))
    need(actual_payload.get('full_checkpoint_sha256_verified') is False,'WHOLE_CHECKPOINT_SCOPE')
    items=actual_payload['tensors'];need(type(items) is list and len(items)==13,'PAYLOAD_METADATA_SET')
    need([v['local_name'] for v in items]==list(PAYLOAD_NAMES),'PAYLOAD_METADATA_ORDER')
    payload_records={}
    for pin,meta in zip(ledger['tensors'],items):
        name=pin['local_name'];item=payload['tensors'][name]
        need(all(meta.get(k)==pin[k] for k in ('local_name','dtype','shape','source_shape','bytes','sha256')) and
             meta['file']==name+'.bin' and item['sha256']==pin['sha256'],'PAYLOAD_PIN')
        read_record(reader,item,rows,out,'payload/'+name+'.bin',size=pin['bytes'])
        d=descriptor(item['sha256'],item['sha256'],pin['shape'],pin['shape'],encoding='bfloat16_le',origin='SELECTED_CHECKPOINT_RANGE')
        d.update(source_shape=pin['source_shape'],selected_rows=[0,256] if name==PAYLOAD_NAMES[0] else None)
        payload_records[name]=d
    ro=producer['readonly'];exact(ro,('arena','table','input_x','input_x_sha256','intermediate_preloads'),'READONLY_FIELDS')
    need(type(ro['intermediate_preloads']) is int and ro['intermediate_preloads']==0 and
         ro['input_x_sha256']==ro['input_x']['sha256']==INPUT_PINS[rows][0] and
         ro['arena']['sha256']==INPUT_PINS[rows][1] and ro['table']['sha256']==TABLE_SHA,'READONLY_PIN')
    readonly={}
    for name,path,shape in (('arena','readonly_arena.f32le',[188043264//4]),
                            ('table','tables.f32le',[192+5*16384]),('input_x','input_x.f32le',[1,rows,1536])):
        item=ro[name];read_record(reader,item,rows,out,'readonly/'+path,size=math.prod(shape)*4)
        readonly[name]=descriptor(item['sha256'],item['sha256'],shape,shape,
            dtype='float32' if name!='input_x' else 'bfloat16',origin='COLD_READONLY_INPUT',
            mapping={'arena':'SOURCE_BOUND_ARENA_V1','table':'PREFIX192_THEN_5X256X64','input_x':'IDENTITY_C_ORDER'}[name])
    scalars={};builds={}
    raw_names={f'phase_{i}_{n}_recipe.f32le':n for i,n in enumerate(WIDTHS)}
    raw_names.update({n+'.f32le':n for n in ('cache_k','cache_v','scores','logits','softmax_fp32','prob','silu')})
    for role in ('sequential','reduced'):
        p=producer[role]
        exact(p['outputs'],raw_names,'SCALAR_OUTPUT_SET')
        scalars[role]={}
        for filename,name in raw_names.items():
            scalars[role][name]=tensor(reader,p['outputs'][filename],rows,out,role+'/raw_stages/'+filename,name,
                raw_cache=name in ('cache_k','cache_v'))
        need(len(scalars[role])==22,'SCALAR_COUNT')
        for key,file in (('cpp','candidate.cpp'),('header','block_layout.h'),('executable','candidate'),('compile','compile.json'),('run','run.json')):
            read_record(reader,p[key],rows,out,role+'/'+file)
        compile_record=strict(read_record(reader,p['compile'],rows,out,role+'/compile.json',capture=True))
        run=strict(read_record(reader,p['run'],rows,out,role+'/run.json',capture=True))
        need(compile_record['returncode']==0 and type(compile_record['returncode']) is int and
             compile_record['argv'][1:-3]==list(SCALAR_FLAGS) and
             compile_record['compiler']==producer['runtime_observation']['compiler'] and
             all(compile_record[k]==p[f]['sha256'] for k,f in
                 (('cpp_sha256','cpp'),('header_sha256','header'),('binary_sha256','executable'))),'SCALAR_BUILD')
        need(run['status']=='COMPLETE_REFERENCE_ONLY' and run['returncode']==0 and
             run['output_sha256']=={n:v['sha256'] for n,v in p['outputs'].items()} and
             run['readonly_sha256']==ro['arena']['sha256'] and run['input_x_sha256']==ro['input_x']['sha256'] and
             run['table_sha256']==TABLE_SHA and run['actual_chain_executed'] is False,'SCALAR_RUN')
        builds[role]=dict(cpp_sha256=p['cpp']['sha256'],header_sha256=p['header']['sha256'],
                          executable_sha256=p['executable']['sha256'],flags=list(SCALAR_FLAGS))
    seq=producer['sequential'];exact(seq['tensors'],STAGES,'SEQUENTIAL_EXPORT_SET')
    exports=strict(read_record(reader,seq['export_receipt'],rows,out,'sequential/exports.json',capture=True))
    need(type(exports) is list and [x['name'] for x in exports]==list(STAGES),'SEQUENTIAL_EXPORT_ORDER')
    sequential={}
    for e in exports:
        exact(e,('name','path','shape','export_shape','sha256'),'EXPORT_FIELDS');name=e['name']
        need(e['path']=='candidate_'+name+'.f32le' and e['shape']==shapes(rows)[name] and
             e['export_shape']==export_shape(rows,name) and e['sha256']==seq['tensors'][name]['sha256'],'EXPORT_METADATA')
        sequential[name]=tensor(reader,seq['tensors'][name],rows,out,'sequential/tensors/'+e['path'],name)
    libraries={};exact(producer['libraries'],('qkv','qk'),'RECIPE_LIBRARY_SET')
    for role in ('qkv','qk'):
        lib=producer['libraries'][role];exact(lib,('binary','receipt'),'LIBRARY_FIELDS')
        read_record(reader,lib['binary'],rows,out,f'{role}_library/{role}_pair.so')
        receipt=strict(read_record(reader,lib['receipt'],rows,out,f'{role}_library/{role}_pair_compile.json',capture=True))
        need(receipt['argv'][1:-3]==list(RECIPE_FLAGS) and receipt['library_sha256']==lib['binary']['sha256'] and
             receipt['returncode']==0 and type(receipt['returncode']) is int and
             digest(receipt['cpp_sha256']) and digest(receipt['generated_module_sha256']) and
             receipt['compiler']['sha256']==producer['runtime_observation']['compiler']['sha256'],'RECIPE_LIBRARY_BUILD')
        cpp_path=record_path(lib['binary'],rows,out,f'{role}_library/{role}_pair.so').with_suffix('.cpp')
        reader.read(cpp_path,receipt['cpp_sha256'],limit=8*1024*1024)
        libraries[role]=dict(library_sha256=lib['binary']['sha256'],cpp_sha256=receipt['cpp_sha256'],
            generated_module_sha256=receipt['generated_module_sha256'],flags=list(RECIPE_FLAGS),
            compiler_executable_sha256=receipt['compiler']['sha256'])
    return dict(payload=payload_records,readonly=readonly,native=records,scalar_raw=scalars,
                sequential_exports=sequential),dict(scalar_builds=builds,recipe_libraries=libraries),native_raw


def loaded_providers(snapshot,producer_identity,rows):
    loaded=snapshot['loaded_inputs'];exact(loaded,(*PROVIDERS,'x','rope'),'LOADED_PROVIDER_SET')
    result={}
    for name in (*PROVIDERS,'x','rope'):
        item=loaded[name];exact(item,('bytes','sha256'),'PROVIDER_FIELDS')
        if name=='x':shape,dtype,source,recipe=[1,rows,1536],'float32','embed_tokens.rows_0_255','EMBEDDING_ROWS_BF16_EXPAND_F32'
        elif name=='rope':shape,dtype,source,recipe=[2,1024,64],'float32','table','COS_SIN_FP32_FIRST_M_ZERO_PAD1024'
        else:shape,dtype,source,recipe=PROVIDERS[name]
        encoding='bfloat16_le' if dtype=='bfloat16' else 'float32_le'
        need(item['bytes']==math.prod(shape)*(2 if dtype=='bfloat16' else 4) and digest(item['sha256']),'PROVIDER_GEOMETRY')
        source_hash=producer_identity['readonly']['table']['content_sha256'] if name=='rope' else producer_identity['payload'][source]['content_sha256']
        direct=name=='x'
        if direct:need(item['sha256']==producer_identity['readonly']['input_x']['file_sha256'],'LOADED_X_BINDING')
        result[name]=dict(logical_shape=shape,logical_dtype='bfloat16' if name=='x' else dtype,storage_encoding=encoding,
            bytes=item['bytes'],content_sha256=item['sha256'],file_sha256=item['sha256'] if direct else None,
            verification='DIRECT_FILE_REHASH' if direct else 'QUALIFIED_METADATA_ONLY',
            qualified_origin='SNAPSHOT_LOADED_INPUTS',qualified_snapshot_rows=rows,
            reconstruction=dict(recipe=recipe,source_tensor=('readonly:table' if name=='rope' else 'payload:'+source),source_content_sha256=source_hash,
                                rows=rows if name in ('x','rope') else None))
    return result


def capture_shape(rows,name):
    need(name in FIELDS,'CAPTURE_FIELD')
    return [12,rows,rows,16] if name=='dot_parts' else [12,rows,3] if name=='normalizer' else [12,rows,128] if name in ('pv_raw','pv_bf16') else [12,rows,rows]


def present_bytes(raw,presence,frequency,rows,name):
    shape=capture_shape(rows,name);count=math.prod(shape)
    need(type(raw) is bytes and type(presence) is bytes and type(frequency) is bytes and
         len(raw)==count*4 and len(presence)==count and len(frequency)==count*2,'CAPTURE_SIZE')
    selected=[];width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
    causal=name in CAUSAL_FIELDS
    for h in range(12):
        for query in range(rows):
            for key in range(rows) if causal else (0,):
                start=((h*rows+query)*rows+key)*width if causal else (h*rows+query)*width
                end=start+width;observed=not causal or key<=query
                need(presence[start:end]==bytes([int(observed)])*width and
                     frequency[start*2:end*2]==(b'\x01\x00' if observed else b'\x00\x00')*width,'CAPTURE_COVERAGE')
                block=raw[start*4:end*4]
                if observed:selected.append(block)
                else:need(block==bytes.fromhex('c33c96a5')*width,'CAPTURE_SENTINEL')
    return b''.join(selected)


def derived_descriptor(raw,shape,*,dtype='bfloat16',recipe,source_ids):
    need(len(raw)==math.prod(shape)*4,'DERIVED_SIZE')
    return dict(logical_shape=shape,logical_dtype=dtype,storage_encoding='float32_le',bytes=len(raw),
                file_sha256=None,content_sha256=sha(raw),verification='DERIVED_BYTE_MAPPING',
                reconstruction=dict(recipe=recipe,source_tensors=source_ids))


def select_causal(raw,rows):
    need(type(raw) is bytes and len(raw)==12*rows*rows*4,'CAUSAL_REFERENCE_SIZE')
    return b''.join(raw[(h*rows*rows+q*rows)*4:(h*rows*rows+q*rows+q+1)*4]
                    for h in range(12) for q in range(rows))


def full_projection(reader,summary,snapshot,rows,out,producer,producer_identity,native_raw,combined_hash):
    need(type(summary.get('rows')) is int and summary['rows']==rows and snapshot['rows']==rows and
         summary.get('actual_dataflow_pass') is True and summary.get('native_acceptance')=='PASS_OBSERVED_ONLY' and
         summary.get('full_29_node_acceptance') is False and summary.get('rtl_executed') is False and
         summary.get('old_pass_inherited') is False,'FULL_STATUS')
    need(summary['loaded_inputs']==snapshot['loaded_inputs'] and summary['binaries']==snapshot['binaries'] and
         summary['binaries']['library_sha256']==combined_hash,'FULL_SNAPSHOT_BINDING')
    root=out/('m16/full_m16/actual' if rows==16 else 'full_m128/actual')
    actual=summary['sealed_actual_outputs'];exact(actual,tuple(n for n in ACTUAL_WIDTHS if n!='silu'),'ACTUAL_SET')
    records={};raw_actual={}
    for name,width in ACTUAL_WIDTHS.items():
        item=dict(bytes=rows*width*4,sha256=summary['sealed_silu_sha256']) if name=='silu' else actual[name]
        exact(item,('bytes','sha256'),'ACTUAL_FIELDS');need(item['bytes']==rows*width*4,'ACTUAL_SIZE')
        raw=reader.read(root/('actual_'+name+'.f32le'),item['sha256'],size=item['bytes'],capture=True,limit=MAX_CAPTURE)
        stored=[2,rows,2,128] if name=='kv' else [1,rows,width]
        logical=shapes(rows)[name] if name in STAGES else stored
        canonical=token_to_head(raw,rows,12 if name=='q' else 2) if name in ('q','k') else raw
        origin='ACTUAL_FFN_TILE_READ_AUDIT' if name in ('gate','up') else 'OBSERVED_SILU_SEAL' if name=='silu' else 'ACKED_PHYSICAL_OUTPUT'
        records[name]=descriptor(item['sha256'],sha(canonical),stored,logical,
            dtype='float32' if name in ('qraw','kraw','vraw') else 'bfloat16',origin=origin,
            mapping='TOKEN_HEAD_BYTE_PERMUTATION' if name in ('q','k') else 'K_PLANE_THEN_V_PLANE' if name=='kv' else 'IDENTITY_C_ORDER')
        if name in ('kv','att'):raw_actual[name]=raw
    need(len(records)==20,'ACTUAL_COUNT')
    observed=summary['observation']['fields'];exact(observed,FIELDS,'OBSERVATION_SET')
    captures={};selected={}
    for name in FIELDS:
        meta=observed[name];shape=capture_shape(rows,name);count=math.prod(shape)
        need(meta['shape']==shape and type(meta['words']) is int and meta['words']==count and
             type(meta['identical_repeats']) is int and meta['identical_repeats']==0,'CAPTURE_METADATA')
        parts={}
        for kind,suffix,key,encoding,width in (
            ('raw','.u32le','raw_sha256','uint32_le',4),
            ('presence','.presence','presence_sha256','uint8',1),
            ('frequency','.count.u16le','frequency_sha256','uint16_le',2)):
            raw=reader.read(root/'attention_observation'/(name+suffix),meta[key],size=count*width,capture=True,limit=MAX_CAPTURE)
            parts[kind]=raw
        present=present_bytes(parts['raw'],parts['presence'],parts['frequency'],rows,name)
        need(meta['observed_words']==meta['writes']==len(present)//4 and type(meta['writes']) is int,'CAPTURE_OBSERVED_COUNT')
        entry={}
        for kind,key,encoding,dtype in (('raw','raw_sha256','uint32_le','uint32'),
            ('presence','presence_sha256','uint8','uint8'),('frequency','frequency_sha256','uint16_le','uint16')):
            entry[kind]=descriptor(meta[key],meta[key],shape,shape,dtype=dtype,encoding=encoding,origin='ACTUAL_ATTENTION_CAPTURE')
        entry.update(present_content_sha256=sha(present),observed_elements=len(present)//4,
            unobserved_elements=count-len(present)//4,coverage='CAUSAL_KEY_LE_QUERY' if name in CAUSAL_FIELDS else 'COMPLETE',
            absent_word_hex='a5963cc3' if name in CAUSAL_FIELDS else None,
            semantic_value_dtype='bfloat16' if name in ('dot_bf16','scores_bf16','prob_bf16','pv_bf16') else 'float32',
            raw_hash_scope='FULL_STORAGE_INCLUDING_UNOBSERVED_SENTINELS' if name in CAUSAL_FIELDS else 'COMPLETE_OBSERVED_STORAGE',
            present_hash_scope='OBSERVED_LOGICAL_VALUES_ONLY',
            present_mapping='PRESENCE1_WORDS_IN_C_ORDER',future_positions_observed=False if name in CAUSAL_FIELDS else None)
        captures[name]=entry
        if name in ('scores_bf16','softmax_fp32','prob_bf16','pv_bf16'):selected[name]=present
    need(sha(token_to_head(raw_actual['att'],rows,12))==captures['pv_bf16']['raw']['file_sha256'],'PV_ACK_BINDING')
    stages={name:records[name] for name in WIDTHS}
    stages['silu']=records['silu']
    for index,name in enumerate(('cache_k','cache_v')):
        plane_size=rows*2*128*4;raw=raw_actual['kv'][index*plane_size:(index+1)*plane_size]
        cache=token_to_head(raw,rows,2)
        stages[name]=derived_descriptor(cache,[1,2,rows,128],recipe='KV_PLANE_TOKEN_TO_HEAD',source_ids=['full.persisted_actual:kv'])
        head_size=rows*128*4
        repeated=b''.join(cache[h*head_size:(h+1)*head_size]*6 for h in range(2))
        repeat='repeat_k' if index==0 else 'repeat_v'
        stages[repeat]=derived_descriptor(repeated,[1,12,rows,128],recipe='REPEAT_EACH_KV_HEAD6',source_ids=['full.actual_stages:'+name])
    ro=producer['readonly']
    x=read_record(reader,ro['input_x'],rows,out,'readonly/input_x.f32le',capture=True)
    stages['x']=derived_descriptor(x,[1,rows,1536],recipe='LOADED_INPUT_X',source_ids=['readonly:input_x'])
    table=read_record(reader,ro['table'],rows,out,'readonly/tables.f32le',capture=True)
    for index,name in ((3,'cos'),(4,'sin')):
        start=(192+index*16384)*4;part=table[start:start+rows*64*4]
        expanded=b''.join(part[q*256:(q+1)*256]*2 for q in range(rows))
        stages[name]=derived_descriptor(expanded,[rows,128],recipe='TABLE_BF16_SLICE_DUPLICATE_HALF',source_ids=['readonly:table'])
        stages[name]['origin']='REFERENCE_TABLE_DATA_NOT_ENGINE_OUTPUT'
    mapping=dict(scores='scores_bf16',logits='scores_bf16',softmax_fp32='softmax_fp32',prob='prob_bf16',pv='pv_bf16')
    for name,field in mapping.items():
        value=captures[field]
        stages[name]=dict(logical_shape=shapes(rows)[name],logical_dtype='float32' if name=='softmax_fp32' else 'bfloat16',
            storage_encoding='uint32_le_fp32_bits',file_sha256=value['raw']['file_sha256'],
            content_sha256=value['raw']['content_sha256'],present_content_sha256=value['present_content_sha256'],
            verification='DIRECT_FILE_REHASH',origin='ACTUAL_ATTENTION_CAPTURE',
            content_hash_scope=value['raw_hash_scope'],present_hash_scope='OBSERVED_LOGICAL_VALUES_ONLY',
            coverage=value['coverage'],observed_elements=value['observed_elements'],
            unobserved_elements=value['unobserved_elements'],capture_field=field)
    exact(stages,OBSERVED_STAGES,'ACTUAL_STAGE_SET')
    comparison=summary['comparison']
    need(comparison['fixed_arithmetic_pass'] is True and comparison['official_target']=='official_self_cache' and
         comparison['missing_nodes']==['explicit_mask_tensor'] and comparison['full_29_node_acceptance'] is False and
         comparison['future_score_materialization'] is False and comparison['partially_observed_nodes']==['scores','logits','prob','softmax_fp32'] and
         comparison['independent_self_cache_is_auxiliary'] is True and comparison['old_sequential_producer_is_auxiliary'] is True,'COMPARISON_SCOPE')
    thresholds=comparison['thresholds']
    need(thresholds['sha256']==POLICY_SHA and thresholds['operator']==dict(max_abs=0.03125,mean_abs=0.005) and
         thresholds['block']==dict(max_abs=0.05,mean_abs=0.01),'POLICY_THRESHOLDS')
    exact(comparison['methods'],METHODS,'GATE_METHODS')
    gates={}
    for method in METHODS:
        entries=comparison['methods'][method]['stages'];exact(entries,OBSERVED_STAGES,'GATE_STAGES')
        gate_records={}
        for name in OBSERVED_STAGES:
            entry=entries[name];metric=entry['metrics'];verdict=entry['verdict'];record=stages[name]
            actual_sha=record.get('present_content_sha256',record['content_sha256'])
            item=native_raw[('bf16',method,name)]
            ref=producer_identity['native']['bf16.'+method+'.'+name]
            reference_sha=ref['content_sha256']
            if name in ('scores','logits','prob','softmax_fp32'):
                raw=read_record(reader,item,rows,out,f'native{rows}/bf16/phase_0/'+('native' if method==METHODS[0] else 'independent')+'_'+name+'.f32le',capture=True)
                reference_sha=sha(select_causal(raw,rows))
            need(metric['actual_f32_sha256']==actual_sha and metric['reference_f32_sha256']==reference_sha and
                 entry['original_shape']==shapes(rows)[name] and metric['finite'] is True,'GATE_CONTENT_BINDING')
            diagnostic=name=='softmax_fp32';limit='block' if name=='y' else 'operator'
            if diagnostic:need(verdict['passed'] is None and verdict['contract'] is None,'DIAGNOSTIC_VERDICT')
            else:need(type(verdict['passed']) is bool and verdict['limits']==thresholds[limit],'GATE_VERDICT')
            if method==METHODS[0] and not diagnostic:need(verdict['passed'] is True,'QUALIFIED_OFFICIAL_GATE')
            gate_records[name]=dict(actual_tensor='full.actual_stages:'+name,reference_tensor='native:bf16.'+method+'.'+name,
                actual_comparison_sha256=actual_sha,reference_comparison_sha256=reference_sha,
                comparison_mapping='CAUSAL_PRESENT_ONLY' if name in ('scores','logits','prob','softmax_fp32') else 'LOGICAL_C_ORDER',
                policy='DIAGNOSTIC_NO_FP32_TOLERANCE' if diagnostic else 'BF16_BLOCK' if name=='y' else 'BF16_OPERATOR',
                qualified_verdict=verdict['passed'],assigned=method==METHODS[0] and not diagnostic)
        gates[method]=gate_records
    fixed={};exact(comparison['whole_outputs'],WIDTHS,'FIXED_OUTPUT_SET')
    for index,name in enumerate(WIDTHS):
        metric=comparison['whole_outputs'][name]
        expected=producer_identity['scalar_raw']['reduced'][name]['file_sha256']
        need(metric['actual_f32_sha256']==records[name]['file_sha256'] and metric['reference_f32_sha256']==expected and
             metric['bit_exact'] is True,'FIXED_OUTPUT_HASH')
        fixed[name]=dict(actual_tensor='full.persisted_actual:'+name,reference_tensor='scalar_raw.reduced:'+name,
            comparison_mapping='STORED_C_ORDER',actual_comparison_sha256=metric['actual_f32_sha256'],
            reference_comparison_sha256=expected,qualified_bit_exact=True)
    exact(comparison['actual_observed_nodes'],('scores','logits','softmax_fp32','prob','pv','silu'),'FIXED_OBSERVED_SET')
    for name in ('scores','logits','softmax_fp32','prob','pv','silu'):
        metric=comparison['actual_observed_nodes'][name]
        expected_actual=stages[name].get('present_content_sha256',stages[name]['content_sha256'])
        refname='att' if name=='pv' else name
        filename='phase_6_att_recipe.f32le' if name=='pv' else name+'.f32le'
        raw=read_record(reader,producer['reduced']['outputs'][filename],rows,out,'reduced/raw_stages/'+filename,capture=True)
        if name=='pv':raw=token_to_head(raw,rows,12)
        elif name in ('scores','logits','softmax_fp32','prob'):raw=select_causal(raw,rows)
        expected=sha(raw)
        need(metric['actual_f32_sha256']==expected_actual and metric['reference_f32_sha256']==expected and
             metric['bit_exact'] is True,'FIXED_OBSERVED_HASH')
        fixed[name]=dict(actual_tensor='full.actual_stages:'+name,reference_tensor='scalar_raw.reduced:'+refname,
            comparison_mapping='TOKEN_HEAD_BYTE_PERMUTATION' if name=='pv' else 'CAUSAL_PRESENT_ONLY' if name!='silu' else 'LOGICAL_C_ORDER',
            actual_comparison_sha256=expected_actual,reference_comparison_sha256=expected,qualified_bit_exact=True)
    return dict(persisted_actual=records,attention_captures=captures,actual_stages=stages,
                loaded_providers=loaded_providers(snapshot,producer_identity,rows),gate_bindings=gates,
                fixed_arithmetic_bindings=fixed)


def validate_logical_references(run):
    namespaces={'payload':run['payload'],'readonly':run['readonly'],'native':run['native'],
        'scalar_raw.sequential':run['scalar_raw']['sequential'],'scalar_raw.reduced':run['scalar_raw']['reduced'],
        'sequential_exports':run['sequential_exports']}
    if 'full' not in run:return
    full=run['full']
    namespaces.update({'full.persisted_actual':full['persisted_actual'],'full.actual_stages':full['actual_stages'],
                       'full.loaded_providers':full['loaded_providers']})
    def resolve(logical_id):
        need(type(logical_id) is str and logical_id.count(':')==1,'LOGICAL_ID')
        namespace,name=logical_id.split(':')
        need(namespace in namespaces and name in namespaces[namespace],'LOGICAL_REFERENCE')
        return namespaces[namespace][name]
    for table in (full['actual_stages'],full['loaded_providers']):
        for item in table.values():
            recipe=item.get('reconstruction',{})
            for logical_id in recipe.get('source_tensors',[]):resolve(logical_id)
            if 'source_tensor' in recipe:
                source=resolve(recipe['source_tensor'])
                need(source['content_sha256']==recipe['source_content_sha256'],'RECIPE_SOURCE_HASH')
    for table in (*full['gate_bindings'].values(),full['fixed_arithmetic_bindings']):
        for gate in table.values():
            resolve(gate['actual_tensor']);resolve(gate['reference_tensor'])


def validation_binding(receipt,rows,summary_hash,snapshot_hash):
    need(receipt.get('status')==f'PASS_FRESH_SAME_HOST_M{rows}_ASSIGNED27' and
         type(receipt.get('child_exit_code')) is int and receipt['child_exit_code']==0 and
         receipt.get('owned_group_cleanup_complete') is True,'PARENT_COMPLETION')
    value=receipt['validation']
    need(value['rows']==rows and type(value['rows']) is int and value['summary_sha256']==summary_hash and
         value['snapshot_sha256']==snapshot_hash and value['official_observed_stages']==28 and
         value['assigned_official_gates']==27 and value['diagnostic_fp32_stages']==1 and
         value['fixed_arithmetic_pass'] is True and value['observed_official_gates_pass'] is True and
         value['full_29_node_acceptance'] is False and value['rtl_acceptance'] is False and
         value['hardware_acceptance'] is False,'PARENT_VALIDATION')


class Prepared:
    """Private state sealed by canonical content and byte-binding signatures."""
    __slots__=('root','out','reader','identity','provenance','producers','native_raw','ci','nonce',
               'qualification_sha256','prerequisite_sha256','combined_hash','seal','used')


def _prepared_seal(prepared):
    return sha(encoded(dict(identity=prepared.identity,provenance=prepared.provenance,
        producers=prepared.producers,native_raw={str(rows):{'.'.join(k):v for k,v in records.items()} for rows,records in prepared.native_raw.items()},
        ci=prepared.ci,nonce=prepared.nonce,qualification=prepared.qualification_sha256,
        prerequisite=prepared.prerequisite_sha256,combined=prepared.combined_hash,
        root=str(prepared.root),out=str(prepared.out),files=prepared.reader.files)))


def prepare(*,root,out,source_pins,qualification_sha256,m16_prerequisite_sha256,context_sha256,deadline):
    """Called after current producer/verifier zero exit and strict cleanup.

    deadline is the existing reference receipt monotonic-seconds stop. No timer
    is changed, and no later deadline is created. Only private state is returned.
    """
    reader=Reader(deadline);root,out=absolute(root),absolute(out)
    need(not root.is_relative_to(out) and not out.is_relative_to(root),'SOURCE_OUTPUT_OVERLAP')
    raw_sources=source_map(reader,root,source_pins)
    need(source_pins.get(LEDGER)==LEDGER_SHA and source_pins.get(CONFIG)==CONFIG_SHA and
         source_pins.get('spec/numerical_contract.md')==POLICY_SHA,'RECIPE_SOURCE_PINS')
    ledger=reader.json(root/LEDGER,LEDGER_SHA)
    need(ledger['model_id']==MODEL and ledger['revision']==REVISION and ledger['layer_id']==0 and
         ledger['payload_bytes']==94382080 and [x['local_name'] for x in ledger['tensors']]==list(PAYLOAD_NAMES),'PAYLOAD_LEDGER')
    q=reader.json(out/'M128_QUALIFICATION.json',qualification_sha256)
    prerequisite=reader.json(out/'M16_PREREQUISITE.json',m16_prerequisite_sha256)
    context=reader.json(out/'M128_CONTEXT.json',context_sha256)
    ci=validate_ci(q['ci']);nonce=q['attempt_nonce'];need(digest(nonce),'ATTEMPT_BINDING')
    need(q['status']=='PASS_FRESH_M128_PRODUCER' and q['owned_group_cleanup_complete'] is True and
         type(q['child_exit_code']) is int and q['child_exit_code']==0 and q['original_array_gate_revalidated'] is True and
         q['parent_context_sha256']==context_sha256,'QUALIFICATION_STATE')
    need(prerequisite['status']=='VERIFIED_CURRENT_JOB_FULL_M16_SAME_ELF' and
         prerequisite['parent_pid']==context['parent_pid']==os.getpid() and
         prerequisite['ci']==context['ci']==ci and prerequisite['attempt_nonce']==context['attempt_nonce']==nonce and
         context['root']==str(root) and context['workspace']==str(out/'producer128') and
         prerequisite['m16_root']==str(out/'m16'),'LIVE_CONTEXT')
    need(type(context['receipt_deadline_ns']) is int and abs(deadline-context['receipt_deadline_ns']/1e9)<1e-6,'REFERENCE_DEADLINE')
    expected_records=dict(producer_manifest='setup/producer/PRODUCER_M16.json',producer_qualification='setup/QUALIFICATION.json',
        actual='full_m16/actual/summary.json',snapshot='full_m16/snapshot/SNAPSHOT.json',
        child_result='full_m16/CHILD_RESULT.json',full_receipt='evidence/full_m16_summary.json')
    exact(prerequisite['records'],expected_records,'PREREQUISITE_RECORDS')
    old={name:reader.pointer(prerequisite['records'][name],out/'m16'/path) for name,path in expected_records.items()}
    p16=old['producer_manifest'];p128=reader.json(out/'producer128/PRODUCER_M128.json',q['producer_manifest_sha256'])
    q16=old['producer_qualification']
    need(q16['status']=='PASS_FRESH_M16_PRODUCER' and q16['producer_native_gate_validated'] is True and
         q16['owned_group_cleanup_complete'] is True and type(q16['child_exit_code']) is int and q16['child_exit_code']==0 and
         q16['producer_manifest_sha256']==prerequisite['records']['producer_manifest']['sha256'],'M16_QUALIFICATION')
    for producer,qualified in ((p16,q16),(p128,q)):
        need(producer['ci']==qualified['ci']==ci and producer['attempt_nonce']==qualified['attempt_nonce']==nonce and
             qualified['producer_source_manifest_sha256']==producer['source_manifest_sha256'] and
             qualified['runtime_identity_sha256']==sha(encoded(producer['runtime_identity'])) and
             qualified['host_sha256']==sha(encoded(producer['host'])),'QUALIFIED_PRODUCER_BINDING')
    need(p16['runtime_identity']==p128['runtime_identity'] and p16['runtime_observation']==p128['runtime_observation'],
         'SHARED_RUNTIME')
    need(p128['parent_context_sha256']==context_sha256 and p128['upstream']==context['upstream'],'M128_CONTEXT_BINDING')
    verifier=reader.json(out/'VERIFIED_M128_PRODUCER.json',q['verifier_receipt_sha256'])
    need(verifier['status']=='PASS_ORIGINAL_M128_NATIVE_AND_SCALAR_GATES' and verifier['producer_manifest_sha256']==q['producer_manifest_sha256'] and
         verifier['parent_context_sha256']==context_sha256 and verifier['original_array_gate_revalidated'] is True and
         verifier['native_exports']==116 and verifier['scalar_outputs_each']==22,'INDEPENDENT_VERIFIER')
    m16_source_hash=source_map(reader,out/'m16/source',prerequisite['source_sha256'])
    need(m16_source_hash==prerequisite['source_manifest_sha256'],'M16_SOURCE_MAP')
    lib=prerequisite['library'];binary=lib['binary'];exact(binary,('path','bytes','sha256'),'COMBINED_BINARY_FIELDS')
    need(absolute(binary['path'])==out/'m16/setup/tiny/build/official_bf16_matrix_silu.so','COMBINED_BINARY_TARGET')
    reader.read(binary['path'],binary['sha256'],size=binary['bytes'])
    build=reader.pointer(lib['receipt'],out/'m16/setup/tiny/build/official_bf16_compile.json')
    need(build['library_sha256']==binary['sha256'] and build['argv'][1:6]==list(LIBRARY_FLAGS) and
         build['returncode']==0 and type(build['returncode']) is int and
         build['compiler']['sha256']==p16['runtime_observation']['compiler']['sha256'],'COMBINED_BUILD')
    old_receipt=old['full_receipt'];r16=prerequisite['records']
    validation_binding(old_receipt,16,r16['actual']['sha256'],r16['snapshot']['sha256'])
    need(old['actual']['snapshot_sha256']==r16['snapshot']['sha256'] and old['actual']['source_sha256']==prerequisite['source_sha256'] and
         old['snapshot']['source_sha256']==prerequisite['source_sha256'],'M16_FULL_BINDING')
    identities={};builds={};native_raw={}
    for rows,producer in ((16,p16),(128,p128)):
        identities[str(rows)],builds[str(rows)],native_raw[rows]=producer_projection(reader,producer,rows,out,ledger)
    need(identities['16']['payload']==identities['128']['payload'],'SHARED_PAYLOAD')
    identities['16']['full']=full_projection(reader,old['actual'],old['snapshot'],16,out,p16,identities['16'],native_raw[16],binary['sha256'])
    recipe_sources={name:source_pins[path] for name,path in RECIPE_SOURCES.items()}
    identity=dict(model=dict(model_id=MODEL,revision=REVISION,layer=0,selected_embedding_rows=[0,256],
        whole_checkpoint_hash_verified=False,config_sha256=CONFIG_SHA,payload_ledger_sha256=LEDGER_SHA),
        serialization=dict(schema=1,hash='SHA256',byte_order='LITTLE_ENDIAN',canonical_tensor_order='LOGICAL_C_ORDER',
                           numeric_conversion_performed=False,logical_id_scope='PER_ROWS_RUN',logical_id_separator='COLON'),
        stimulus=dict(batch=1,past_tokens=0,carried=False,rows=[16,128],token_ids='RANGE_ZERO_TO_ROWS_EXCLUSIVE',
            position_ids='RANGE_ZERO_TO_ROWS_EXCLUSIVE',tokenizer_or_template=False,intermediate_preloads=0,
            input_source='SELECTED_CHECKPOINT_EMBEDDINGS',stimulus_random_draw=False,stimulus_seed=None,
            framework_construction_rng_claim=False,eval=True,dropout=False),
        recipe_sources=recipe_sources,policy=dict(numerical_contract_sha256=POLICY_SHA,operator=dict(max_abs=0.03125,mean_abs=0.005),
            block=dict(max_abs=0.05,mean_abs=0.01),assigned_official_gates=27,observed_stages=28,
            diagnostic_stages=['softmax_fp32'],missing_stages=['explicit_mask_tensor'],
            partially_observed_stages=['scores','logits','prob','softmax_fp32'],
            fixed_arithmetic_reference='REDUCED_BLOCK_PAIR_SCALAR',official_reference='OFFICIAL_SELF_CACHE',
            auxiliary_references=['INDEPENDENT_SELF_CACHE','SEQUENTIAL_SCALAR'],new_tolerances=False),runs=identities)
    validate_logical_references(identities['16'])
    provenance=dict(ci=ci,raw_source_map_sha256=raw_sources,m16_composed_source_map_sha256=m16_source_hash,
        qualification_sha256=qualification_sha256,m16_prerequisite_sha256=m16_prerequisite_sha256,
        producer_context_sha256=context_sha256,producer_manifest_sha256={'16':r16['producer_manifest']['sha256'],'128':q['producer_manifest_sha256']},
        native_result_sha256={'16':p16['native']['result']['sha256'],'128':p128['native']['result']['sha256']},
        m16_summary_sha256=r16['actual']['sha256'],m16_snapshot_sha256=r16['snapshot']['sha256'],
        m16_full_receipt_sha256=r16['full_receipt']['sha256'],verifier_receipt_sha256=q['verifier_receipt_sha256'],
        runtime=runtime_projection(p16),builds=builds,
        combined_library=dict(content_sha256=binary['sha256'],flags=list(LIBRARY_FLAGS),
            compiler_executable_sha256=build['compiler']['sha256'],source_map_sha256=sha(encoded(build['source_sha256'])),
            shared_m16_m128=True,verification='DIRECT_FILE_REHASH'),
        driver_sha256={'16':p16['driver_sha256'],'128':p128['driver_sha256']},
        package_scope='FOUR_QUALIFIED_RUNTIME_VERSIONS_PLUS_PINNED_COMPLETE_WHEEL_LOCK',
        wheel_lock_sha256=source_pins[BASE+'portable_official_producer_launch/wheel-lock.json'],
        emitter_sha256=source_pins[BASE+'portable_same_host_m128_launch/replay_identity.py'])
    prepared=Prepared();prepared.root=root;prepared.out=out;prepared.reader=reader
    prepared.identity=identity;prepared.provenance=provenance;prepared.producers={16:p16,128:p128};prepared.native_raw=native_raw
    prepared.ci=ci;prepared.nonce=nonce;prepared.qualification_sha256=qualification_sha256
    prepared.prerequisite_sha256=m16_prerequisite_sha256;prepared.combined_hash=binary['sha256'];prepared.used=False
    reader.verify();prepared.seal=_prepared_seal(prepared);remaining(deadline)
    return prepared


def finalize(*,prepared,full_receipt_sha256,sources,deadline):
    """Return (path-free manifest, exact canonical SHA256), without publication.

    Caller first persists its original numerical receipt. The same existing full
    receipt stop applies. Caller must exclusively write canonical bytes and
    check that stop again before setting its separate replay_identity_ready.
    """
    need(type(prepared) is Prepared and prepared.used is False,'PREPARED_STATE')
    remaining(deadline);need(_prepared_seal(prepared)==prepared.seal,'PREPARED_DRIFT')
    prepared.used=True
    reader=prepared.reader;reader.deadline=deadline;reader.total=0;reader.verify()
    out=prepared.out
    receipt=reader.json(out/'evidence/full_m128_summary.json',full_receipt_sha256)
    need(receipt['ci']==prepared.ci and receipt['attempt_nonce']==prepared.nonce and
         receipt['producer_receipt_sha256']==prepared.qualification_sha256 and
         receipt['m16_prerequisite_sha256']==prepared.prerequisite_sha256,'FINAL_RECEIPT_BINDING')
    validation=receipt['validation'];summary_hash=validation['summary_sha256'];snapshot_hash=validation['snapshot_sha256']
    validation_binding(receipt,128,summary_hash,snapshot_hash)
    # The parent source-bound run context is indirectly bound by the qualified
    # child result and its existing postflight; final enforces its absolute stop
    # through the parent-supplied deadline and does not mint a replacement stop.
    summary=reader.json(out/'full_m128/actual/summary.json',summary_hash)
    snapshot=reader.json(out/'full_m128/snapshot/SNAPSHOT.json',snapshot_hash)
    need(summary['snapshot_sha256']==snapshot_hash and summary['source_sha256']==sources and
         summary['source_sha256_after']==sources and snapshot['source_sha256']==sources,'FINAL_SOURCE_BINDING')
    composed_hash=source_map(reader,out/'source128',sources)
    need(validation['source_manifest_sha256']==composed_hash,'FINAL_SOURCE_DIGEST')
    identity=strict(encoded(prepared.identity));provenance=strict(encoded(prepared.provenance))
    identity['runs']['128']['full']=full_projection(reader,summary,snapshot,128,out,prepared.producers[128],
        identity['runs']['128'],prepared.native_raw[128],prepared.combined_hash)
    validate_logical_references(identity['runs']['128'])
    child=reader.json(out/'full_m128/CHILD_RESULT.json',receipt['child_result_sha256'])
    need(child['summary_sha256']==summary_hash and child['snapshot_sha256']==snapshot_hash and
         child['validation']==validation and child['source_manifest_sha256']==composed_hash,'FINAL_CHILD_BINDING')
    provenance.update(m128_summary_sha256=summary_hash,m128_snapshot_sha256=snapshot_hash,
        m128_full_receipt_sha256=full_receipt_sha256,m128_child_result_sha256=receipt['child_result_sha256'],
        m128_composed_source_map_sha256=composed_hash)
    result=dict(schema=SCHEMA,status='IDENTITY_METADATA_REQUIRES_PARENT_COMPLETION',identity=identity,
        identity_sha256=sha(encoded(identity)),provenance=provenance,
        authority=dict(numerical_acceptance_granted=False,freeze_readiness_granted=False,
                       full_29_node_acceptance=False,rtl_acceptance=False,hardware_acceptance=False,
                       parent_postflight_required=True,parent_publication_and_deadline_check_required=True))
    raw=encoded(result);need(len(raw)<=2*1024*1024,'PUBLIC_SIZE')
    reader.verify();remaining(deadline)
    return result,sha(raw)
