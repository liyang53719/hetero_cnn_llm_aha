"""Terminal callback only. Standard-library metrics, never reconstruct DUT tensors.
Caller must bind this source and call exclusively inside ExactOraclePathGate's
live-terminal window. This module is not a security sandbox or execution permit.
"""
import hashlib
import math
from pathlib import Path
import struct
import sys

NODES = ('x','mask','n0','qr','kr','v','cos','sin','q','k','cache_k','cache_v','repeat_k','repeat_v','scores','logits','softmax_fp32','prob','pv','att','o','r','n1','gate','silu','up','act','down','y')
NONMATERIALIZED = ('mask','repeat_k','repeat_v','logits')
CAUSAL = ('scores','prob','softmax_fp32')
WIDTHS = dict(zip(('n0','qr','kr','v','q','k','att','o','r','n1','gate','up','act','down','y'), (1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536)))
THRESHOLDS = {'operator_bf16': {'max_abs_lte':0.03125,'mean_abs_lte':0.005,'combine':'AND'}, 'block_y':{'max_abs_lte':0.05,'mean_abs_lte':0.01,'combine':'AND'},'softmax_fp32':'DIAGNOSTIC_NO_APPROVED_COMPARISON_TOLERANCE','rowsum_abs_error_lte':0.00002}

def need(ok, why):
    if not ok: raise ValueError(why)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def shape(name, rows):
    if name in ('cos','sin'): return [rows,128]
    if name == 'mask': return [1,1,rows,rows]
    if name in CAUSAL or name == 'logits': return [1,12,rows,rows]
    if name in ('q','pv','repeat_k','repeat_v'): return [1,12,rows,128]
    if name in ('k','cache_k','cache_v'): return [1,2,rows,128]
    return [1,rows,8960 if name in ('gate','silu','up','act') else 256 if name in ('kr','v') else 1536]

def words(raw, count, name):
    view = memoryview(raw)
    need(view.contiguous and view.nbytes == count*4, 'actual shape/extent: '+name)
    return view.cast('B').cast('I')

def finite(word, bf):
    need(word & 0x7f800000 != 0x7f800000, 'nonfinite actual/reference value')
    need(not bf or word & 0xffff == 0, 'BF16 container low bits set')
    return struct.unpack('<f', struct.pack('<I',word))[0]

def metric(pairs, *, bf, limits):
    count=0; maximum=0.0; total=0.0
    for a,b in pairs:
        delta=abs(finite(a,bf)-finite(b,bf)); count+=1; maximum=max(maximum,delta); total+=delta
    need(count>0,'empty comparison domain')
    mean=total/count
    return dict(compared_elements=count,max_abs=maximum,mean_abs=mean,
                within_limits=None if limits is None else maximum<=limits['max_abs_lte'] and mean<=limits['mean_abs_lte'])

def source_indices(name, rows):
    """Yield (actual index, official flat index); no tensor expansion."""
    if name in CAUSAL:
        for h in range(12):
            for t in range(rows):
                for k in range(t+1):
                    i=(h*rows+t)*rows+k; yield i,i
    elif name in ('q','k','cache_k','cache_v','pv'):
        heads=2 if name in ('k','cache_k','cache_v') else 12
        for h in range(heads):
            for t in range(rows):
                for c in range(128):
                    j=(h*rows+t)*128+c
                    i=j if name=='pv' else t*heads*128+h*128+c
                    if name=='cache_v': i+=rows*256
                    yield i,j
    elif name in ('cos','sin'):
        for t in range(rows):
            for c in range(128): yield t*64+c%64,t*128+c
    else:
        for i in range(math.prod(shape(name,rows))): yield i,i

def validate_exports(exports, rows):
    need(type(exports) is dict and set(exports)==set(NODES),'exact official29 metadata required')
    result={}
    for name in NODES:
        e=exports[name]; count=math.prod(shape(name,rows))
        need(e['shape']==shape(name,rows),'reference geometry: '+name)
        need(e['native_dtype']==('float32' if name=='softmax_fp32' else 'bfloat16'),'reference dtype: '+name)
        need(e['fp32_file']==name+'.f32.bin' and e['fp32_bytes']==count*4,'reference filename/extent: '+name)
        digest=e['fp32_sha256']; need(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'reference digest')
        result[name]={k:e[k] for k in ('fp32_file','fp32_bytes','fp32_sha256')}
    return result

ATTENTION_FIELDS = ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
BF16_FIELDS = frozenset(('dot_bf16','scores_bf16','prob_bf16','pv_bf16'))

def check_words(raw, count, name, *, bf, expected_digest, observed=None):
    view=words(raw,count,name)
    need(sha(view)==expected_digest,'registry inventory digest: '+name)
    need(observed is None or len(observed)==count,'inventory presence extent: '+name)
    for i,value in enumerate(view):
        if observed is None or observed[i]: finite(value,bf)
    return view

def validate_inventory(actual, fields, entries, rows):
    """Scan all actual 32 registry entries; cache entries alias verified KV.
    Only true observed diagnostic words are finite-checked, never sentinels.
    Presence/frequency and source hashes are validated before numerical oracle IO.
    """
    expected=set(WIDTHS)|{'qraw','kraw','vraw','kv'}
    need(set(actual)==expected and set(fields)==set(ATTENTION_FIELDS),'exact raw/ten-field inventory')
    need(set(entries)==expected|set(ATTENTION_FIELDS)|{'silu','cache_k','cache_v'},'exact32 registry inventory')
    views={}
    widths=dict(WIDTHS,qraw=1536,kraw=256,vraw=256,kv=512)
    for name,width in widths.items():
        views[name]=check_words(actual[name],rows*width,name,bf=name not in ('qraw','kraw','vraw'),expected_digest=entries[name]['raw_sha256'])
    kv=views['kv']
    need(all(kv[i]==views['k'][i] for i in range(rows*256)),'exact KV readback differs from k')
    need(all(kv[rows*256+i]==views['v'][i] for i in range(rows*256)),'exact KV readback differs from v')
    for name in ATTENTION_FIELDS:
        f=fields[name]
        causal=name not in ('normalizer','pv_raw','pv_bf16')
        width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
        shape=[12,rows,rows,16] if name=='dot_parts' else [12,rows,width] if not causal else [12,rows,rows]
        count=math.prod(shape)
        need(list(f['shape'])==shape and len(f['observed'])==len(f['frequency'])==count,'diagnostic shape/presence: '+name)
        need(sha(f['observed'])==entries[name]['presence_sha256'] and sha(f['frequency'])==entries[name]['frequency_sha256'],'registry mask/frequency digest: '+name)
        view=words(f['words'],count,name)
        for i in range(count):
            at=i//width
            present=not causal or at%rows<=(at//rows)%rows
            frequency=(8 if name in ('prob_bf16','softmax_fp32') else 1) if present else 0
            need(f['observed'][i]==int(present) and f['frequency'][i]==frequency,'missing/duplicate/foreign capture: '+name)
            need(present or view[i]==0xa5963cc3,'unobserved future filled: '+name)
        check_words(f['words'],count,name,bf=name in BF16_FIELDS,expected_digest=entries[name]['raw_sha256'],observed=f['observed'])
    return views

def make_comparator(reference_root, exports, *, rows=128, terminal_guard):
    """No file opens here. exports must be pinned metadata extracted by admission.
    terminal_guard must assert the actual gate's open callback window. Its code,
    all source/metadata identity and original live-state verification are bound
    by worker admission, not by a user-provided boolean in this comparator.
    """
    need(rows==128,'separately reviewed M128 only')
    need(sys.byteorder=='little','little endian required')
    need(callable(terminal_guard),'live gate guard required')
    pins=validate_exports(exports,rows); root=Path(reference_root); used=False
    def compare(actual, observation, registry_report, *, terminal_values):
        nonlocal used
        terminal_guard()
        need(not used,'single-use comparison'); used=True
        need(registry_report.get('whole_terminal') is True and registry_report.get('resources_clean') is True and registry_report.get('rows')==rows,'sealed whole terminal required')
        need(registry_report.get('status')=='COMPLETE_ACTUAL_INVENTORY_NUMERIC_TEMP','registry status')
        need(terminal_values.get('provenance')=='ORIGINAL_READONLY_ALLOCATION_AND_ORIGINAL_PHASE4_SEAL','actual x/SiLU provenance')
        need(terminal_values.get('x_shape')==[rows,1536] and terminal_values.get('silu_shape')==[rows,8960] and terminal_values.get('rope_physical_shape')==[rows,64],'terminal extra shape')
        need(set(actual)==set(WIDTHS)|{'qraw','kraw','vraw','kv'},'exact actual inventory')
        fields=observation['capture'].data.fields
        validate_inventory(actual,fields,registry_report['entries'],rows)
        def inventory_hashes():
            return {**{n:sha(v) for n,v in actual.items()},**{n+'.'+k:sha(f[k]) for n,f in fields.items() for k in ('words','observed','frequency')}}
        inventory_before=inventory_hashes()
        buffers={name:words(actual[name],rows*width,name) for name,width in WIDTHS.items()}
        kv=words(actual['kv'],rows*512,'kv'); buffers.update(cache_k=kv,cache_v=kv)
        buffers['x']=words(terminal_values['readonly_x'],rows*1536,'x')
        buffers['silu']=words(terminal_values['sealed_silu'],rows*8960,'silu')
        for name in ('cos','sin'): buffers[name]=words(terminal_values['rope_operands'][name],rows*64,name)
        for name,key in (('scores','scores_bf16'),('prob','prob_bf16'),('softmax_fp32','softmax_fp32'),('pv','pv_bf16')):
            f=fields[key]; count=12*rows*(128 if name=='pv' else rows)
            buffers[name]=words(f['words'],count,name)
            need(len(f['observed'])==len(f['frequency'])==count,'presence extent')
            for i in range(count):
                present=True if name=='pv' else i%rows <= (i//rows)%rows
                frequency=(8 if name in ('prob','softmax_fp32') else 1) if present else 0
                need(f['observed'][i]==int(present) and f['frequency'][i]==frequency,'missing/duplicate/foreign capture: '+name)
                need(present or buffers[name][i]==0xa5963cc3,'unobserved future filled')
        before={name:sha(v) for name,v in buffers.items()}
        # Validate every existing registry source digest before any oracle read.
        for name in WIDTHS: need(before[name]==registry_report['entries'][name]['raw_sha256'],'registry actual digest: '+name)
        need(before['cache_k']==registry_report['entries']['kv']['raw_sha256'],'registry KV digest')
        need(before['silu']==registry_report['entries']['silu']['raw_sha256'],'registry SiLU digest')
        for n,key in (('scores','scores_bf16'),('prob','prob_bf16'),('softmax_fp32','softmax_fp32'),('pv','pv_bf16')):
            need(before[n]==registry_report['entries'][key]['raw_sha256'],'registry observation digest')
        results={}; gates=[]
        for name in NODES:
            if name in NONMATERIALIZED:
                results[name]=dict(status='PHYSICALLY_NONMATERIALIZED_NO_NUMERICAL_CLAIM',compared_elements=0,full_elements=math.prod(shape(name,rows))); continue
            terminal_guard()
            p=pins[name]; path=root/p['fp32_file']
            need(path.resolve().parent==root.resolve(),'reference escaped root')
            raw=path.read_bytes()
            need(len(raw)==p['fp32_bytes'] and sha(raw)==p['fp32_sha256'],'reference payload identity: '+name)
            ref=words(raw,len(raw)//4,name)
            limits=None if name=='softmax_fp32' else THRESHOLDS['block_y' if name=='y' else 'operator_bf16']
            result=metric(((buffers[name][i],ref[j]) for i,j in source_indices(name,rows)),bf=name!='softmax_fp32',limits=limits)
            result.update(domain='CAUSAL_ONLY' if name in CAUSAL else 'FULL_LOGICAL_VIEW', full_elements=len(ref),
                          unobserved_elements=len(ref)-result['compared_elements'],
                          status='DIAGNOSTIC_NO_APPROVED_COMPARISON_TOLERANCE' if limits is None else 'WITHIN_LIMITS' if result['within_limits'] else 'FAIL')
            if limits is not None: gates.append(result['within_limits'])
            if name in ('cos','sin'): result.update(actual_physical_elements=rows*64,logical_alias_mapping='column % 64; actual operands only; no expanded tensor')
            results[name]=result
        row_errors=[]; probability=buffers['softmax_fp32']
        for h in range(12):
            for t in range(rows): row_errors.append(abs(math.fsum(finite(probability[(h*rows+t)*rows+k],False) for k in range(t+1))-1.0))
        rowsum=max(row_errors); gates.append(rowsum<=THRESHOLDS['rowsum_abs_error_lte'])
        need(before=={name:sha(v) for name,v in buffers.items()} and inventory_before==inventory_hashes(),'comparison modified actual buffers')
        terminal_guard()
        return dict(status='OBSERVED_DOMAIN_WITHIN_ORIGINAL_LIMITS' if all(gates) else 'OBSERVED_DOMAIN_NUMERICAL_FAIL',
                    observed_domain_passed=all(gates),nodes=results,thresholds=THRESHOLDS,softmax_fp32_rowsum_max_abs_error=rowsum,
                    full29_numeric_pass=False,nonmaterialized_protocol_evidence_required=list(NONMATERIALIZED),
                    oracle_used_as_actual=False,future_values_filled=False,actual_buffers_unchanged=True,
                    configuration_difference=dict(project_rotary_positions=256,official_max_position_embeddings=32768,positions_compared=list(range(rows)),official_config_modified=False,impact='actual cos/sin and q/k metrics above; no claim of isolated configuration causality'),
                    hardware_pass=False,utilization_acceptance=False)
    return compare
