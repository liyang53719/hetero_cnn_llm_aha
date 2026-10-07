"""Independent fail-closed checks for actual RTL result/debug trace ingestion."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from heteronpu.rope_bf16_candidate import add_rne,mul_rne
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('qk_runner',ROOT/'scripts/run_qk_norm256_candidate.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def one():
    x=np.full(256,0x3f800000,dtype=np.uint32);w=np.zeros(256,dtype=np.uint32)
    t=runner.oracle.head_trace(x,w)
    return {'input':x,'weight':w,'norm':np.asarray(t['output_bf16'],dtype=np.uint32),
        'gate':np.arange(256,dtype=np.uint32)<<16,'role':0,'flags':t['aggregate_flags'],
        'mean_eps':t['mean_eps'],'inverse':t['inverse']},t


def result_line(r):
    return f"R 0 00000000 0 0 {r['flags']:02x} {r['mean_eps']:08x} {r['inverse']:08x} {runner.packed(r['norm']>>16):01024x} {runner.packed(r['gate']>>16):01024x}\n"


def debug_lines(t):
    lines=[]
    for c in range(16):
        sl=slice(c*16,c*16+16);m,mf=mul_rne(t['running'][c],0x3b800000);e,ef=add_rne(m,0x358637bd)
        red=0
        for flag in t['tree_flags'][c*15:c*15+15]:red|=flag
        values=[t['partials'][c],0 if c==0 else t['running'][c-1],t['running'][c],m,e,
                runner.packed(t['square_flags'][sl],5),red,t['running_flags'][c],mf,ef,runner.wide(t['squares'][sl])]
        widths=[8,8,8,8,8,20,2,2,2,2,128]
        lines.append(f'C R 0 00000000 {c} '+' '.join(f'{v:0{w}x}' for v,w in zip(values,widths)))
    coeff=runner.oracle.RSQRT_COEFFICIENTS[t['rsqrt_index']]
    vals=[t['mean_eps'],t['rsqrt_norm'],t['rsqrt_scale'],t['rsqrt_index'],coeff>>32,coeff&0xffffffff,*t['rsqrt_values'],runner.packed(t['rsqrt_flags'],5)]
    lines.append('S R 0 00000000 '+' '.join(f'{v:0{w}x}' for v,w in zip(vals,[8,8,8,2]+[8]*10+[10])))
    for c in range(16):
        sl=slice(c*16,c*16+16);f=[v for p in zip(t['scaled_flags'][sl],t['output_fp32_flags'][sl]) for v in p]
        vals=[runner.wide(t['gamma'][sl]),runner.packed(t['gamma_flags'][sl],5),runner.wide(t['scaled'][sl]),runner.wide(t['output_fp32'][sl]),runner.packed(f,5)]
        lines.append(f'O R 0 00000000 {c} '+' '.join(f'{v:0{w}x}' for v,w in zip(vals,[128,20,128,128,40])))
    lines.append(f"Y R 0 00000000 {t['mean_eps']:08x} {t['inverse']:08x} {t['arithmetic_flags']:02x} {runner.wide(t['output_fp32']):02048x}")
    return lines


def test_exact_result_and_debug(tmp_path):
    r,t=one();p=tmp_path/'result';p.write_text(result_line(r))
    actual=runner.verify_results(p,[r]);assert np.array_equal(actual[0],r['norm']>>16)
    p.write_text('\n'.join(debug_lines(t))+'\n')
    assert runner.verify_debug(p,[r])['nodes']=={'C':16,'S':1,'O':16,'Y':1}


@pytest.mark.parametrize('field',list(range(1,10)))
def test_result_field_tamper_rejected(tmp_path,field):
    r,_=one();fields=result_line(r).split();fields[field]=('1' if field==1 else f'{int(fields[field],16)^1:0{len(fields[field])}x}')
    p=tmp_path/'result';p.write_text(' '.join(fields)+'\n')
    with pytest.raises(ValueError):runner.verify_results(p,[r])


@pytest.mark.parametrize('mutation',['missing','duplicate','extra','short','garbage','nonhex','uppercase'])
def test_result_stream_tamper_rejected(tmp_path,mutation):
    r,_=one();s=result_line(r)
    if mutation=='missing':s=''
    elif mutation in ('duplicate','extra'):s+=s
    elif mutation=='short':s=s.replace('00000000','0000000',1)
    elif mutation=='garbage':s+='PASS\n'
    elif mutation=='nonhex':s=s.replace('R 0','R z',1)
    elif mutation=='uppercase':s=s.upper()
    p=tmp_path/'result';p.write_text(s)
    with pytest.raises(ValueError):runner.verify_results(p,[r])


@pytest.mark.parametrize('kind',['C','S','O','Y'])
@pytest.mark.parametrize('mutation',['value','flag','missing','duplicate','reorder','tag','width'])
def test_debug_tamper_rejected(tmp_path,kind,mutation):
    r,t=one();lines=debug_lines(t);idx=next(i for i,s in enumerate(lines) if s.startswith(kind+' '));fields=lines[idx].split()
    if mutation=='missing':lines.pop(idx)
    elif mutation=='duplicate':lines.insert(idx,lines[idx])
    elif mutation=='reorder':lines[idx],lines[(idx+1)%len(lines)]=lines[(idx+1)%len(lines)],lines[idx]
    else:
        field=3 if mutation=='tag' else -1 if mutation=='value' else -2
        if mutation=='width':fields[field]='0'+fields[field]
        else:fields[field]=f'{int(fields[field],16)^1:0{len(fields[field])}x}'
        lines[idx]=' '.join(fields)
    p=tmp_path/'debug';p.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):runner.verify_debug(p,[r])


def test_memh_layout(tmp_path):
    r,_=one();p=tmp_path/'vectors';runner.write_vectors(p,[r]);lines=p.read_text().splitlines()
    assert len(lines)==5 and all(len(x)==2048 for x in lines)
    assert int(lines[0],16)&65535==0x3f80
    assert (int(lines[0],16)>>4096)&65535==0
    assert (int(lines[0],16)>>(4096+16))&65535==1
    assert (int(lines[4],16)>>34)&65535==256
    assert (int(lines[4],16)>>50)&255==0xc1
    assert (int(lines[4],16)>>58)&0xffffffff==0x358637bd


def test_old_default_source_is_frozen():
    assert runner.record(ROOT/runner.LEGACY)['sha256']==runner.LEGACY_HASH


def test_native_threshold_includes_exact_boundary_and_rejects_more():
    records=[]
    for source in ('local','remote'):
        for phase in (0,1):
            for role in (0,1):
                records.append({'source':source,'phase':phase,'role':role,'token':0,'head':0,
                                'native':np.zeros(256,dtype=np.uint32)})
    actual=np.zeros((8,256),dtype=np.uint16);actual[0,0]=0x3d00 # .03125
    report=runner.compare_native(records,actual);assert report['different_values']==1
    actual[0,0]=0x3d01
    with pytest.raises(ValueError):runner.compare_native(records,actual)


def valid_metrics():
    return dict(replay=5152,directed=60,rejected=48,accepted=5208,completed=5208,
        reset_reduction=1,reset_rsqrt=1,reset_output=1,reset_blocked=1,
        stalls=10304,mutations=5152,busy_valid=1,cycles=1)


@pytest.mark.parametrize('key',list(valid_metrics()))
def test_protocol_coverage_cannot_disappear(key):
    m=valid_metrics();runner.verify_protocol_metrics(m,5152);del m[key]
    with pytest.raises(ValueError):runner.verify_protocol_metrics(m,5152)


@pytest.mark.parametrize('change',['vectors=63','random=53','stalls=0','default_equals_explicit_zero=0','original_rtl_bitexact=0'])
def test_legacy_coverage_cannot_disappear(change):
    text='QK_NORM256_LEGACY_DEFAULT_PASS vectors=64 random=54 cycles=20668 stalls=317 default_equals_explicit_zero=1 original_rtl_bitexact=1'
    runner.verify_legacy_log(text)
    key=change.split('=')[0]
    import re
    text=re.sub(key+r'=\d+',change,text)
    with pytest.raises(ValueError):runner.verify_legacy_log(text)


def test_supplemental_cannot_be_omitted(tmp_path):
    p=tmp_path/'results';p.write_text('')
    with pytest.raises(ValueError):runner.verify_supplemental(p)


def test_historical_mode_flag_cannot_be_overwritten_by_legacy_source():
    import ast
    tree = ast.parse((ROOT / 'scripts/run_qk_norm256_candidate.py').read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    assignments = [n for n in ast.walk(run) if isinstance(n, ast.Name)
                   and n.id == 'historical' and isinstance(n.ctx, ast.Store)]
    assert len(assignments) == 1
    assert 'legacy_text' in {n.id for n in ast.walk(run) if isinstance(n, ast.Name)}
