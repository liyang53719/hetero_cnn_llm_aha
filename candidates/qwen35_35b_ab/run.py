"""Execute one real RMS producer feeding separately calibrated A/B N32 owners."""
import argparse,ctypes,json,os,signal,time
from pathlib import Path
from . import driver,payload,reference
from ..qwen35_35b_payload.packer import load_payload
from ..qwen35_35b_prefill.run_prefix import record,checked_record,source_closure
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
ROOT=Path(__file__).resolve().parents[2]


def checked_calibration(path,digest,tokens):
    raw=Path(path).read_bytes();driver.require(driver.sha(raw)==digest,'independent N32 calibration digest')
    r=json.loads(raw)
    driver.require((r['m'],r['n'],r['k'])==(tokens,32,2048) and
        r['status']=='PASS_NEW_N32_PAIR_ORIGINAL_GATES' and set(r['results'])=={'a','b'},'new fullshape N32 A/B calibration required')
    driver.require(r['no_n8192_profile_inheritance'] and r['sources_unchanged'],'independent frozen N32 profile')
    for p,h in r['source_frozen'].items():driver.require(driver.sha(Path(p).read_bytes())==h,'N32 reference source changed')
    checked_record(r['input']);checked_record(r['producer_report']);checked_record(r['manifest'])
    for item in ('reference_library','compiler','libm','disassembly','ldd'):checked_record(r[item])
    for name in ('a','b'):
        result=r['results'][name];actual=checked_record(result['recipes']['pair_hi_first_two_k1024']['output'])
        expected=checked_record(result['official'])
        driver.require(reference.gate(actual,expected)['passed'],'independent N32 calibration gate recheck')
    return r


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('payload','ab-payload','reference-report','output'):ap.add_argument('--'+name,type=Path,required=True)
    for name in ('manifest-sha256','ab-manifest-sha256','reference-report-sha256'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--tokens',type=int,choices=(16,128),required=True)
    ap.add_argument('--wall-seconds',type=int,default=180);args=ap.parse_args()
    driver.require(30<=args.wall_seconds<=600,'explicit bounded budget')
    driver.require(not args.output.exists() and not args.output.is_symlink() and args.output.resolve().is_relative_to(ROOT/'work'),'fresh ignored output')
    r=checked_calibration(args.reference_report,args.reference_report_sha256,args.tokens)
    _,base=load_payload(ROOT,args.payload,include_qkv=True,manifest_sha256=args.manifest_sha256)
    _,values=payload.load(args.ab_payload,args.ab_manifest_sha256)
    hidden=base['embed_tokens.rows_0_255'][:args.tokens*4096];norm=base['layers.0.input_layernorm.weight']
    weights={n:values['layers.0.linear_attn.in_proj_'+n+'.weight'] for n in ('a','b')}
    driver.require(all(driver.sha(weights[n])==r['results'][n]['weight_sha256'] for n in weights),'same actual N32 original weights')
    c=Path(reference.__file__).with_name('reference.c')
    profiles={n:driver.ReductionProfile('independently_calibrated_35b_'+n+'_n32_m'+str(args.tokens),((0,1024),(1024,2048)),True,driver.sha(c.read_bytes())) for n in weights}
    libpath=driver.dense.library_from_environment(ROOT);lib=configure_library(ctypes.CDLL(str(libpath)))
    driver.require(lib.td_reset()==0,'fresh Matrix')
    matrix=driver.dense.MatrixService(lib);vector=driver.Vector16(Path(os.environ['GDN_VECTOR16_LIBRARY']),exception_policy=driver.IEEE_POLICY)
    compile_path=Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT'])
    native_paths=[libpath,compile_path,vector.library,vector.library.with_suffix('.json'),ROOT/'candidates/qwen35_gdn_prefill/chunk/vector16.cpp',c]
    native_paths += [ROOT/p for p in json.loads(compile_path.read_bytes())['sources_before']]
    args.output.mkdir();started=time.monotonic()
    report=dict(status='RUNNING',tokens=args.tokens,scope='ACTUAL_RMS_TO_TWO_N32_A_B_SOFTWARE_PREFIX',
        reference=record(args.reference_report),source_sha256=source_closure(),native_artifacts=[record(p) for p in native_paths],
        manifest_sha256=args.manifest_sha256,ab_manifest_sha256=args.ab_manifest_sha256,
        full_block=False,rtl_executed=False,conv_or_prep_executed=False,observations=[],comparisons={})
    def save():
        report['host_seconds']=time.monotonic()-started
        (args.output/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    def observe(stage,details,raw):
        path=args.output/(stage+'.actual.bf16le');path.write_bytes(raw)
        report['observations'].append(dict(stage=stage,output=record(path),owner=details));save()
    def timeout(*_):raise TimeoutError('bounded actual A/B prefix')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(args.wall_seconds);save()
    try:
        execution,_=driver.execute_ab(hidden,norm,weights,tokens=args.tokens,profiles=profiles,matrix=matrix,vector=vector,
            deadline=started+args.wall_seconds,observe=observe)
        report['execution']=execution
        driver.require(execution['status']=='PASS_TYPED_AB_EXECUTION_ONLY','actual A/B prefix failed')
        driver.require(execution['actual_rms_output_sha256']==r['input']['sha256'],'same actually computed RMS boundary')
        driver.require([o['stage'] for o in report['observations']]==['input_norm','a','b'] and len(execution['terminals'])==3,'complete real producer inventory')
        for observation in report['observations'][1:]:
            name=observation['stage'];actual=checked_record(observation['output'])
            fixed=checked_record(r['results'][name]['recipes']['pair_hi_first_two_k1024']['output'])
            native=checked_record(r['results'][name]['official'])
            driver.require(actual==fixed,'actual Matrix/Vector differs from independent N32 fixed recipe')
            report['comparisons'][name]=reference.gate(actual,native)
            driver.require(report['comparisons'][name]['passed'],'original per-A/B native gate failed')
        report['source_sha256_after']=source_closure();report['sources_unchanged']=report['source_sha256_after']==report['source_sha256']
        driver.require(report['sources_unchanged'],'actual source drift')
        for item in report['native_artifacts']:checked_record(item)
        report['native_artifacts_unchanged']=True;report['status']='PASS_ACTUAL_RMS_AB_N32_ORIGINAL_GATES'
    except BaseException as error:
        report.update(status='FAILED',error=dict(type=type(error).__name__,message=str(error)))
        if isinstance(error,driver.PrefixExecutionError):
            report['execution']=error.execution_report;report['interrupted_owner']=error.snapshot
            path=args.output/'interrupted.partial.bf16le';path.write_bytes(error.partial_output);report['interrupted_output']=record(path)
        save();raise
    finally:signal.alarm(0)
    save();print(json.dumps(dict(status=report['status'],seconds=report['host_seconds'])),flush=True)

if __name__=='__main__':main()
