"""Independent admission/provenance/metric checks; usable under normal Python and -O."""
import hashlib, importlib.util, json, shutil, subprocess, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from heteronpu.rope_rounding_ablation import trace_pair, compare_words, VARIANTS
spec=importlib.util.spec_from_file_location('ablation_review',ROOT/'scripts/run_rope_rounding_ablation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=0

def check(value, label):
    global checks
    if not value: raise RuntimeError(label)
    checks+=1

def reject(call,label):
    try: call()
    except (ValueError,TypeError,OSError): check(True,label)
    else: check(False,label+' did not reject')

# Byte identity of an independent extraction from pinned original sources.
for name,pin in m.FIXTURE_PINS.items():
    check(hashlib.sha256((OUT/'refrozen'/name).read_bytes()).hexdigest()==pin,'refreeze '+name)

# Independently vectorized native-to-pair mapping, using saved tensors only.
for name,audit in [('local','work/bf16_recovery/final_saved'),('remote','work/rope_rounding_ablation/remote_native/bf16')]:
    frozen,prov=m.load_corpus(name)
    with np.load(ROOT/audit/'all_bf16_producers.npz',allow_pickle=False) as full:
        for group in prov['groups']:
            case=group['case'];head=group['heads'];q=group['producer']=='q';pi=16 if q else 25;mi=27 if q else 30
            x=full[f'{case}_native_producer_{pi:02}'].view(np.uint32)[0]
            cos=full[f'{case}_native_cos'].view(np.uint32)[0,:,:32]
            sin=full[f'{case}_native_sin'].view(np.uint32)[0,:,:32]
            expected_inputs=np.stack((x[...,:32],x[...,32:64],np.broadcast_to(cos[:,None,:],(128,head,32)),np.broadcast_to(sin[:,None,:],(128,head,32))),axis=-1).reshape(-1,4)
            product=full[f'{case}_native_producer_{mi:02}'].view(np.uint32)[0].swapaxes(0,1)
            rotproduct=full[f'{case}_native_producer_{mi+1:02}'].view(np.uint32)[0].swapaxes(0,1)
            output=full[f'{case}_native_producer_{mi+2:02}'].view(np.uint32)[0].swapaxes(0,1)
            expected_products=np.stack((product[...,:32],rotproduct[...,:32]^0x80000000,rotproduct[...,32:64],product[...,32:64]),axis=-1).reshape(-1,4)
            expected_output=np.stack((output[...,:32],output[...,32:64]),axis=-1).reshape(-1,2)
            sl=slice(group['start'],group['start']+group['pairs'])
            for key,value in [('inputs',expected_inputs),('native_products',expected_products),('native_outputs',expected_output)]: check(np.array_equal(frozen[key][sl],value),name+' '+case+' '+group['producer']+' '+key)

# No assertion statements: these reject checks remain live under Python -O.
for pos in range(4):
    for word in (0x7f800000,0xff800000,0x7fc00000,0x7f800001,-1,2**32,True,1.0):
        for variant in VARIANTS:
            args=[0,0,0x3f800000,0];args[pos]=word
            reject(lambda:trace_pair(*args,variant),'invalid arithmetic admission')

# Each independent pin must reject corruption before any array is admitted.
corrupt=OUT/('corrupt_O' if sys.flags.optimize else 'corrupt')
corrupt.mkdir(exist_ok=True)
for name in m.FIXTURE_PINS: shutil.copyfile(m.FIXTURES/name,corrupt/name)
for name in m.FIXTURE_PINS:
    content=(corrupt/name).read_bytes();(corrupt/name).write_bytes(content+b'X')
    reject(lambda:m.load_corpus('local',corrupt),'digest admission '+name)
    (corrupt/name).write_bytes(content)

exe=OUT/'independent_run/fenv_reference'
malformed=[b'0 0 0\n',b'0 0 0 0 0\n',b'-1 0 0 0\n',b'+0 0 0 0\n',b'100000000 0 0 0\n',b'0x 0 0 0\n',b'gg 0 0 0\n',b'0 0 0 0\x00ignored\n',b' '*512+b'0 0 0 0\n',b'7f800000 0 0 0\n',b'7f7fffff 0 40000000 0\n',b'7f7f8000 0 3f800000 0\n']
for row in malformed:
    p=subprocess.run([str(exe)],input=row,capture_output=True)
    check(p.returncode!=0 and not p.stdout,'C rejection '+repr(row[:50]))
p=subprocess.run([str(exe)],input=b'\n0 0 3f800000 0',capture_output=True)
check(p.returncode==0 and len(p.stdout.split())==72,'C valid EOF row')

# An exact min-normal operation cannot acquire a tininess-underflow exception.
inputs=np.array([[0x00800000,0,0x3f800000,0]],dtype=np.uint32)
traces=m.calculate(inputs);traces[0,0,4]^=2
reject(lambda:m.independent_check(exe,inputs,traces,OUT,'exact_min_normal_bad_UF',allow_tininess_difference=True),'exact min-normal UF waiver')

result={'status':'PASS','checks':checks,'optimized_python':bool(sys.flags.optimize),'method':'explicit checks, no Python assert statements'}
(OUT/('checks_O.json' if sys.flags.optimize else 'checks.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
