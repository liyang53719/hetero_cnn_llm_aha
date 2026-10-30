"""Read-only FP32 SRAM evidence comparator. TEMP, never a block-PASS authority."""
import hashlib,struct
MARKER='HOST_RESIDENT_OBSERVATION_V1 profile=0 beats=143360 values=2293760 dtype=FP32 source=SEALED_SRAM_RESPONSE terminal=CLEAN coverage=EXACT_ONCE'
def expand_bf16_bits(reference):
    if len(reference)%2: raise ValueError('BF16 reference size')
    # Representation extension only, not floating-point math or actual rounding.
    return b''.join(struct.pack('<I',x<<16) for (x,) in struct.iter_unpack('<H',reference))
def compare_fp32_bits(actual,reference):
    expected=expand_bf16_bits(reference)
    if len(actual)!=len(expected):raise ValueError('resident actual size')
    mismatches=sum(a!=e for a,e in zip(actual,expected))
    first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),None)
    return dict(bytes=len(actual),byte_mismatches=mismatches,first_mismatch_byte=first,
        actual_sha256=hashlib.sha256(actual).hexdigest(),expected_layout_sha256=hashlib.sha256(expected).hexdigest(),
        observation='SEALED_SRAM_RESPONSE_FP32',reference_conversion='BF16_BITS_LEFT_SHIFT_16',actual_conversion='NONE',
        status='EXACT_STAGE_MATCH_ONLY' if mismatches==0 else 'STAGE_MISMATCH')
def compare_full128(directory,log,reference_bytes):
    if not directory.is_dir() or directory.is_symlink():raise ValueError('regular fresh resident observation directory')
    if log.count(MARKER)!=1:raise ValueError('missing unique clean resident terminal coverage receipt')
    out={}
    for name in ('gate','up'):
        ref=reference_bytes[name]
        if len(ref)!=128*8960*2:raise ValueError('full128 gate/up reference size')
        p=directory/('resident_'+name+'.fp32.actual.bin')
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=128*8960*4:raise ValueError('missing full128 actual SRAM '+name)
        before=p.stat();actual=p.read_bytes();after=p.stat()
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('resident observation changed while reading')
        if hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(actual).digest():raise ValueError('resident observation changed after reading')
        out['resident_'+name]=compare_fp32_bits(actual,ref)
        out['resident_'+name].update(shape=[128,8960],dtype='FP32_LE',coverage='EXACT_ONCE_FULL128')
    return out
