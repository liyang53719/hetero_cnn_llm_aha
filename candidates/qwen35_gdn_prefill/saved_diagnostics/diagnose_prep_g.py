"""Saved-word Prep-g diagnosis only: stdlib rational recipe, no owner execution."""
import argparse
import ast
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import struct
import time

OUT = ROOT = OLD = PAYLOAD = None
SOURCE_PINS = {
 'candidates/qwen35_gdn_prefill/prep/model.py':'10c282860dbc63ba3937a03b1c334bd7908fbc0af9fe7064e835b58f716eef11',
 'candidates/qwen35_gdn_prefill/prep/scalar.py':'bd869a645eab426f2fbd374c742c0ae725ac727b67bed1edb532b8c1a5ac73b1',
 'candidates/qwen35_gdn_prefill/conv/scalar.py':'3131064d058a2262a059469f61b4830f0ec24ed74afd6b84745a2ada026fb132',
 'candidates/qwen35_35b_exp/scalar.py':'5e8f44c7a9ab95d9b18fff2fe443b4cc8742b0f037b61ff12121f6ba12c2e8c5',
 'candidates/qwen35_gdn_prefill/prep/test_model.py':'bf0d7123a903b203f79e38d4d07cb0943a481e0454ac4d025013dd18effe1c62',
 'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py':'daf80d7d6273e9818e63aa030be8ec1ead07324ddcafc82ef8d165ed55065d4e',
 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py':'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18',
}
PINS = {}
def need(ok, message):
    if not ok: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def signature(s): return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def snapshot(path, name, digest, extent=None):
    path=Path(path)
    need(not path.is_symlink(), 'symlink input')
    with path.open('rb') as f:
        before=os.fstat(f.fileno()); need(stat.S_ISREG(before.st_mode) and before.st_size<=16<<20,'regular bounded input'); raw=f.read(); after=os.fstat(f.fileno())
    need(stat.S_ISREG(before.st_mode) and len(raw)<=16<<20,'regular bounded input')
    need(signature(before)==signature(after)==signature(path.stat()),'changing input')
    need(sha(raw)==digest and (extent is None or len(raw)==extent),'input pin/extent: '+str(path))
    target=OUT/'snapshot'/name; target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    need(sha(target.read_bytes())==digest,'snapshot hash')
    PINS[str(path)]={'sha256':digest,'bytes':len(raw),'stat':signature(before),'snapshot':str(target.relative_to(OUT))}
    return raw
def word(value): return struct.unpack('<I',struct.pack('<f',value))[0]
def floating(bits): return struct.unpack('<f',struct.pack('<I',bits))[0]
@lru_cache(maxsize=16384)
def exact(bits):
    exponent,mantissa=(bits>>23)&255,bits&0x7fffff
    need(exponent!=255,'nonfinite word')
    shift=-149 if exponent==0 else exponent-150
    mantissa+=0 if exponent==0 else 1<<23
    if bits>>31: mantissa=-mantissa
    return Fraction(mantissa<<max(shift,0),1<<max(-shift,0))
def rn(number, negative_zero=False):
    sign=0x80000000 if number<0 or (not number and negative_zero) else 0
    if not number: return sign
    number=abs(number); numerator,denominator=number.numerator,number.denominator
    exponent=numerator.bit_length()-denominator.bit_length()
    if number<Fraction(1<<max(exponent,0),1<<max(-exponent,0)): exponent-=1
    shift=149 if exponent < -126 else 23-exponent
    numerator<<=max(shift,0); denominator<<=max(-shift,0)
    quotient,remainder=divmod(numerator,denominator)
    quotient+=2*remainder>denominator or (2*remainder==denominator and quotient&1)
    if exponent < -126: return sign|quotient
    if quotient>=1<<24: quotient>>=1; exponent+=1
    need(exponent<=127,'rational overflow')
    return sign|((exponent+127)<<23)|(quotient&0x7fffff)
def add(a,b): return rn(exact(a)+exact(b),a==b==0x80000000)
def mul(a,b): return rn(exact(a)*exact(b),bool((a^b)>>31))
def div(a,b): return rn(exact(a)/exact(b),bool((a^b)>>31))
EXP=tuple(word(math.pow(-math.log(2),i)/math.factorial(i)) for i in range(8))
SOFT=tuple(word(1/(2*i+1)) for i in range(8))
LOG2=word(1/math.log(2))
@lru_cache(maxsize=4096)
def recipe_exp(a):
    magnitude=a&0x7fffffff
    if exact(magnitude)>=80: return 0
    z=mul(magnitude,LOG2); k=int(exact(z)); fraction=add(z,word(float(k))^0x80000000)
    value=EXP[-1]
    for coefficient in reversed(EXP[:-1]): value=add(mul(value,fraction),coefficient)
    return mul(value,(127-k)<<23)
@lru_cache(maxsize=4096)
def recipe_softplus(a):
    need(exact(a)>-80,'softplus domain')
    if exact(a)>20: return a
    e=recipe_exp(a); y=div(e,add(word(2),e)); square=mul(y,y); value=SOFT[-1]
    for coefficient in reversed(SOFT[:-1]): value=add(mul(value,square),coefficient)
    return add(0 if a>>31 else a,mul(mul(word(2),y),value))
@lru_cache(maxsize=8192)
def mathematical(kind,bits):
    answers=[]
    for precision in (70,100):
        with localcontext() as ctx:
            ctx.prec=precision; f=exact(bits); d=Decimal(f.numerator)/Decimal(f.denominator)
            value=d.exp() if kind=='exp' else (Decimal(1)+d.exp()).ln()
            answers.append(rn(Fraction(value)))
    need(answers[0]==answers[1],'Decimal precision stability')
    return answers[0]
def order(w): return 0x80000000-(w&0x7fffffff) if w>>31 else 0x80000000+w
def metric(actual,reference):
    need(len(actual)==len(reference)>0,'metric extent')
    errors=[abs(floating(a)-floating(b)) for a,b in zip(actual,reference)]
    ulps=[abs(order(a)-order(b)) for a,b in zip(actual,reference)]
    worst=max(range(len(errors)),key=errors.__getitem__)
    return {'elements':len(actual),'bit_mismatches':sum(a!=b for a,b in zip(actual,reference)),
      'max_abs':max(errors),'mean_abs':math.fsum(errors)/len(errors),'max_ulp':max(ulps),
      'ulp_histogram':dict(sorted(Counter(ulps).items())),
      'signed_mean_actual_minus_reference':math.fsum(floating(a)-floating(b) for a,b in zip(actual,reference))/len(actual),
      'worst_index':worst,'thresholds':None,'passed':None}
def constants(source):
    result={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('EXP_COEFFICIENTS','SOFT_COEFFICIENTS','LOG2_RECIPROCAL'):
                    result[target.id]=ast.literal_eval(node.value)
    return result
def main():
    global OUT, ROOT, OLD, PAYLOAD
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('repository', 'saved-snapshot', 'payload', 'output'):
        parser.add_argument('--' + option, required=True, type=Path)
    args = parser.parse_args()
    ROOT = args.repository.resolve(strict=True)
    OLD = args.saved_snapshot.resolve(strict=True)
    PAYLOAD = args.payload.resolve(strict=True)
    OUT = args.output.resolve()
    for protected in (ROOT, OLD, PAYLOAD, Path(__file__).resolve().parents[3]):
        need(OUT != protected and protected not in OUT.parents, 'output must be independent')
    need(not OUT.exists(), 'fresh output directory required')
    started=time.monotonic(); os.umask(0o077); OUT.mkdir(mode=0o700)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    for limit,value in ((resource.RLIMIT_AS,256<<20),(resource.RLIMIT_CPU,45),(resource.RLIMIT_FSIZE,16<<20),(resource.RLIMIT_CORE,0)):
        resource.setrlimit(limit,(value,value))
    def expired(*unused): raise TimeoutError('55-second diagnostic deadline')
    signal.signal(signal.SIGALRM,expired); signal.alarm(55)
    report={'scope':'SAVED_COLD_PREP_G_INDEPENDENT_RATIONAL_DIAGNOSTIC',
      'status':'RUNNING','full_block_acceptance':False,'original_execution_status':'UNKNOWN',
      'owner_executed':False,'native_arithmetic_executed':False,'full_replay_executed':False,
      'thresholds':None,'passed':None,'source_or_head_changed':False,
      'bounds':{'cpu_count':1,'address_space_bytes':256<<20,'cpu_seconds':45,'wall_seconds':55}}
    try:
        for name,digest in SOURCE_PINS.items():
            source=snapshot(ROOT/name,'sources/'+name,digest)
            found=constants(source) if name.endswith('/scalar.py') else {}
            for key,value in found.items(): need(value=={'EXP_COEFFICIENTS':EXP,'SOFT_COEFFICIENTS':SOFT,'LOG2_RECIPROCAL':LOG2}[key],'independently derived coefficient mismatch')
        snapshot(Path(__file__),'sources/diagnose.py',sha(Path(__file__).read_bytes()))
        savedpins=json.loads(snapshot(OLD/'pins.json','metadata/prior_pins.json','cb66d5b5525a7288dc14a910f8e7e7fcb8c345b7abaef4aa861269893e90a3f7'))
        lookup={v['snapshot']:v for v in savedpins.values()}
        def saved(relative):
            p=lookup[relative]; return snapshot(OLD/relative,relative.removeprefix('snapshot/'),p['sha256'],p['bytes'])
        identity=json.loads(saved('snapshot/metadata/actual_identity.json'))
        progress=json.loads(saved('snapshot/metadata/actual_progress.json'))
        for name in SOURCE_PINS:
            if name in identity['source_sha256']: need(identity['source_sha256'][name]==SOURCE_PINS[name],'run source pin')
        need(identity['scalar_arithmetic_binding']['implementation']=='DecayScalar' and identity['scalar_arithmetic_binding']['enable_softplus'] is True,'scalar route')
        need([(c['phase'],c['role']) for c in progress['commands']]==[('cold128',r) for r in ('input_norm','qkv','z','ab','conv_silu','prep')],'six original terminals')
        need(all(c['terminal_accepted'] is True and c['complete'] is True and c['status'] is None for c in progress['commands']),'terminal success')
        prep=saved('snapshot/actual/cold128.prep.actual.fp32le'); ab=saved('snapshot/actual/cold128.ab.actual.bf16le')
        native=saved('snapshot/native/0018.f32le')
        need(len(prep)==128*6400*4 and len(ab)==128*32*2 and len(native)==2048*4,'tensor extents')
        logs=struct.unpack('<16I',snapshot(PAYLOAD/'linear_attn.A_log.bin','inputs/A_log.bin',identity['parameter_sha256']['linear_attn.A_log'],64))
        bias=struct.unpack('<16H',snapshot(PAYLOAD/'linear_attn.dt_bias.bin','inputs/dt_bias.bin',identity['parameter_sha256']['linear_attn.dt_bias'],32))
        actual=[struct.unpack_from('<I',prep,(r*6400+6144+h*16)*4)[0] for r in range(128) for h in range(16)]
        official=list(struct.unpack('<2048I',native)); recipe=[]; soft=[]; ideal_soft=[]; exponent=[]; ideal_exp=[]; replacement_e=[]; replacement_s=[]; replacement_both=[]; biased=[]
        for i in range(2048):
            row,head=divmod(i,16); a=struct.unpack_from('<H',ab,(row*32+head)*2)[0]<<16
            x=add(a,bias[head]<<16); s=recipe_softplus(x); e=recipe_exp(logs[head])
            if not logs[head]>>31: e=div(word(1),e)
            im_s=mathematical('softplus',x); im_e=mathematical('exp',logs[head])
            biased.append(x); soft.append(s); ideal_soft.append(im_s); exponent.append(e); ideal_exp.append(im_e)
            recipe.append(mul(e^0x80000000,s)); replacement_e.append(mul(im_e^0x80000000,s))
            replacement_s.append(mul(e^0x80000000,im_s)); replacement_both.append(mul(im_e^0x80000000,im_s))
        report['saved_vs_independent_recipe']=metric(actual,recipe)
        report['saved_vs_official']=metric(actual,official)
        report['recipe_factor_vs_precision_stable_mathematics']={'softplus':metric(soft,ideal_soft),'exp_A_log':metric(exponent[0:16],ideal_exp[0:16])}
        report['counterfactual_vs_official']={'replace_exp_only':metric(replacement_e,official),'replace_softplus_only':metric(replacement_s,official),'replace_both':metric(replacement_both,official)}
        worst=report['saved_vs_official']['worst_index']; row,head=divmod(worst,16)
        report['worst_official_difference']={'token':row,'head':head}
        report['recipe']='Legacy Prep ExpNegative magnitude/floor P7 plus Softplus7; experimental split-ln2 chunk exp does not replace Prep op4/op7.'
        report['arithmetic_reference']='Copied independent Fraction binary32 RNE Add/Mul/Div helper semantics; constants independently derived and checked against pinned source literals.'
        report['mathematical_reference']='Decimal exp/ln at 70 and 100 decimal digits; rounded FP32 words required identical; diagnostic, not proof of correctly rounded transcendental library behavior.'
        report['attribution_limit']='Official exp/softplus factors were not captured. Factor replacements are counterfactual sensitivity diagnostics, not observed official operation attribution or a complete flags oracle.'
        for original,pin in PINS.items():
            p=Path(original); need(signature(p.stat())==tuple(pin['stat']) and sha(p.read_bytes())==pin['sha256'],'original changed after analysis')
            need(sha((OUT/pin['snapshot']).read_bytes())==pin['sha256'],'snapshot changed after analysis')
        report['before_after_pins_match']=True
        report['status']='DIAGNOSTIC_COMPLETE'
    except BaseException as error:
        report['status']='DIAGNOSTIC_FAILED'; report['error']=repr(error)
        raise
    finally:
        report['elapsed_seconds']=time.monotonic()-started
        report['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        for filename,data in (('pins.json',PINS),('report.json',report)):
            with (OUT/filename).open('x') as f: json.dump(data,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')
        signal.alarm(0)
    print(json.dumps(report,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
