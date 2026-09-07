#!/usr/bin/env python3
"""Recheck every eight-slice probe output against an independent exact recipe.

Not a model/Host/iDMA performance result. These bounded power-of-two vectors
have exactly representable products/sums, so the closed-form reference does
not depend on the C++ oracle or an alternative FMA implementation.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,re,struct
from pathlib import Path
from audit_matrix_topology import counts

MASKS=(255,1,128,85,170,15)

def require(ok,message):
    if not ok:raise ValueError(message)

def verify(root:Path)->dict:
    require((root/'simulation.exit').read_text().strip()=='0','failed simulator')
    log=(root/'run.log').read_text()
    require(not re.search(r'MATRIX4096_ARITHMETIC_FAIL|%Error|Fatal',log),'failed log')
    expected='MATRIX4096_ARITHMETIC_PASS checked_fp32=102400 bit_differences=0 physical_slices=8 all_columns=256 noncontiguous_masks=1 actual_slice_steps=96 same_dut_reset_recovery=1 cycles='
    finals=[x for x in log.splitlines() if x.startswith('MATRIX4096_ARITHMETIC_PASS ')]
    require(len(finals)==1 and finals[0].startswith(expected) and re.fullmatch('[0-9]+',finals[0][len(expected):]),'wrong completion')
    raw=(root/'generated/Matrix4096ArithmeticProbe.sv').read_bytes()
    hierarchy=counts(raw.decode(),'Matrix4096ArithmeticProbe')
    require(hierarchy['qwen2_matrix_command_endpoint']==8 and hierarchy['ScalableMatrixTileAdapter']==1,'wrong actual arithmetic topology')
    require(not hierarchy['idma_backend_rw_axi_flat_wrap'],'probe scope must not claim Host/iDMA')
    actual=(root/'outputs/actual.f32le').read_bytes();reference=(root/'outputs/reference.f32le').read_bytes()
    require(len(actual)==len(reference)==409600 and actual==reference,'incomplete or mismatched binary output')
    checked=0
    with (root/'outputs/all_elements.csv').open(newline='') as stream:
        rows=csv.reader(stream)
        require(next(rows,None)==['request','mask','row','column','actual_hex','reference_hex'],'CSV header')
        for request in list(range(24))+[25]:
            mask=MASKS[request//4] if request<24 else 255
            k=request%4 if request<24 else 0
            for r in range(16):
                for c in range(256):
                    numerator=(c-128)*((k+1)*(r+1)+k*(k+1)//2)
                    wanted=struct.unpack('<I',struct.pack('<f',numerator/4096 if mask&(1<<(c//32)) else 0.0))[0]
                    got=struct.unpack_from('<I',actual,checked*4)[0]
                    require(got==wanted,'independent eight-slice arithmetic mismatch')
                    row=[str(request),str(mask),str(r),str(c),f'{got:08x}',f'{wanted:08x}']
                    require(next(rows,None)==row,'CSV missing, reordered, or inconsistent')
                    checked+=1
        require(next(rows,None) is None,'extra output rows')
    require(checked==102400,'incomplete grid')
    return {'status':'PASS_MATRIX4096_REAL_ARITHMETIC_PROBE','checked_fp32':checked,'bit_differences':0,
            'columns':256,'rows':16,'physical_512mac_slices':8,'logical_matrix_engines':1,
            'selected_slice_steps':96,'including_masked_zero_output_words':True,
            'same_dut_reset_recovery':True,'independent_exact_recipe':True,
            'source_scope':'test-only Chisel port adapter around unchanged ScalableMatrixTileAdapter and retained arithmetic',
            'model_inference':False,'host_idma_test':False,'timing_signoff':False,
            'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (root/'run.log',root/'generated/Matrix4096ArithmeticProbe.sv',root/'outputs/actual.f32le',root/'outputs/reference.f32le',root/'outputs/all_elements.csv')}}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'preserve old evidence')
        report=verify(a.root.resolve());text=json.dumps(report,indent=2)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError) as e:raise SystemExit('ARITHMETIC_PROBE_REJECTED: '+str(e))
