#!/usr/bin/env python3
"""Bounded stdlib-only summary arithmetic; optional source SHA check. No payload/EDA."""
import argparse,hashlib,json,math,pathlib
HERE=pathlib.Path(__file__).resolve().parent
CAP=1<<20

def need(ok,msg):
    if not ok:raise ValueError(msg)
def read_json(p):
    need(p.stat().st_size<=CAP,'metadata cap exceeded')
    return json.loads(p.read_text())
def native_bytes(r):
    need(r['dtype'] in ('BF16','F32'),'unknown native dtype')
    need(bool(r['shape']) and all(type(x)is int and x>0 for x in r['shape']),'native shape')
    n=math.prod(r['shape'])*({'BF16':2,'F32':4}[r['dtype']])
    need(n==r['bytes'],'native shape/byte mismatch');return n
def bounds(T,W):
    BW=100_000_000_000;f=1_000_000_000;R=4096
    return dict(cold_weight_time_ms_at_100GBps=1000*W/BW,
      cold_U_upper_at_100GBps_1GHz=min(1,T*BW/(R*f*W)),
      raw_weight_roofline_at_100GBps_1GHz=T*BW/(R*f*W),
      required_GBps_at_1GHz={str(q):q*R*W/T for q in (.8,.9)},
      resident_native_bytes_needed_at_100GBps_1GHz={str(q):max(0,math.ceil(W-T*BW/(q*R*f))) for q in (.8,.9)},
      full_block_cycle_budget_at_1GHz={str(q):T/(q*R) for q in (.8,.9)})
def equal(a,b,name):
    if isinstance(a,dict):
        need(set(a)==set(b),'key mismatch '+name)
        for k,v in a.items():equal(v,b[k],name+'.'+k)
    elif isinstance(a,float):need(math.isclose(a,b,rel_tol=1e-14,abs_tol=1e-14),'value mismatch '+name)
    else:need(a==b,'value mismatch '+name)
def check_summary(summary,inventory):
    need(len(inventory)==70 and len(summary['profiles'])==5,'inventory size')
    need(summary['scope']=='SOURCE_ONLY_CONDITIONAL_NECESSARY_BOUNDS_NOT_RTL_MEASUREMENT','scope drift')
    a=summary['assumptions']
    need(a['hypothetical_bandwidth_bytes_per_second']==100_000_000_000 and a['hypothetical_clock_hz']==1_000_000_000,'hypothetical target drift')
    need(a['hardware_frequency_or_bandwidth_measured'] is False and a['original_reference_routes_not_hardware_stimulus'] is True,'evidence level drift')
    need([sum(r['profile']==p for r in inventory) for p in range(5)]==[12,14,11,18,15],'per-profile inventory size')
    need(len({(r['profile'],r['name']) for r in inventory})==70,'duplicate native entry')
    routes=summary['route_evidence'];need([routes[str(p)]['active_experts'] for p in (3,4)]==[226,218],'frozen reference changed')
    need(all(routes[str(p)]['routes']==1024 for p in (3,4)),'reference route count')
    # Independent mathematical model counts; rectangular attention, one MAC per multiply-add.
    specs=[(1536,8960,1536+256+256+1536,12,128),(1024,3584,6144+2048+32+2048,0,0),(1024,3584,4096+512+512+2048,8,256),(2048,0,8192+4096+64+4096,0,0),(2048,0,8192+512+512+4096,16,256)]
    for p,(H,F,P,heads,dim) in enumerate(specs):
        actual=summary['profiles'][p];need(actual['profile']==p,'profile order')
        rows=[r for r in inventory if r['profile']==p];active=routes[str(p)]['active_experts'] if p>=3 else 0
        W=matrix=full=0
        for r in rows:
            n=native_bytes(r);full+=n
            need(len(r['actual_sha256'])==64 and all(c in '0123456789abcdef' for c in r['actual_sha256']),'digest syntax')
            if '.experts.' in r['name']:
                need(r['shape'] in ([256,1024,2048],[256,2048,512]),'expert native shape')
                n=n//256*active
            need(n==r['required_bytes'],'required native bytes')
            W+=n
            if len(r['shape'])==2 or '.experts.' in r['name']:matrix+=n
        T=128*H*P+3*128*H*F+2*128*128*heads*dim
        if p>=3:T+=1024*3*2048*512+128*3*2048*512+128*2048*256+128*2048
        mapped=W+({0:10240,1:0,2:0,3:126976,4:126976}[p]);mapped_matrix=matrix+(126976 if p>=3 else 0)
        need(mapped_matrix%64==0,'weight beat alignment');N=mapped_matrix//64;C=4*N-1
        values=dict(tokens=128,native_tensor_count=len(rows),active_experts=active,matrix_useful_macs=T,
            native_parameter_bytes=W,native_matrix_parameter_bytes=matrix,native_nonmatrix_parameter_bytes=W-matrix,
            all_256_experts_native_parameter_bytes=full,active_expert_native_bytes=active*3*2048*512*2,
            current_mapped_unique_parameter_bytes=mapped,current_mapped_unique_matrix_weight_bytes=mapped_matrix,
            current_weight_only_min_axi_beats=N,current_single_beat_dma_cycle_lower_bound=C,
            current_weight_only_U_upper_from_single_beat_FSM=min(1,T/(4096*C)),
            current_native_weight_U_upper_at_one_64B_beat_per_root_cycle=min(1,T/(4096*math.ceil(W/64))),
            current_mapped_parameter_min_cycles_at_64B_per_root_cycle=math.ceil(mapped/64),
            current_mapped_parameter_U_upper_at_64B_per_root_cycle=min(1,T/(4096*math.ceil(mapped/64))),
            ideal_fully_warm_weight_DDR_bytes=0,**bounds(T,W))
        for k,v in values.items():equal(v,actual[k],f'P{p}.{k}')
    return {'profiles':5,'native_summary_entries':70,'frozen_reference_active_experts':[226,218]}
def repo_relative(value):
    p=pathlib.PurePosixPath(value)
    need(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts,'non-relative repo source path')
    return p
def check_sources(pins,repo,fixed_commands=None):
    out=[]
    rows=list(pins['runtime_sources'].items())+[('constructor_helper',pins['constructor_helper'])]
    for name,r in rows:
        rel=repo_relative(r['repo_path']);p=repo/pathlib.Path(rel)
        override=name=='HostBlockCommandsV4.scala' and fixed_commands is not None
        if override:p=fixed_commands
        need(p.is_file(),'missing pinned source: '+str(rel));need(p.stat().st_size<=CAP,'source cap exceeded: '+name)
        need(hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],'source SHA mismatch: '+name)
        out.append({'name':name,'repo_path':str(rel),'sha256':r['sha256'],'explicit_local_override':override})
    return out

def run(folder=HERE,repo=None,fixed_commands=None):
    need(fixed_commands is None or repo is not None,'--fixed-commands requires --repo')
    summary=read_json(folder/'BOUNDS.json');inventory=read_json(folder/'NATIVE_TENSOR_INVENTORY.json')
    result=check_summary(summary,inventory)
    result.update(status='PASS_SUMMARY_ARITHMETIC_ONLY_NOT_FRESH_SOURCE_OR_HEADER_VALIDATION_NOT_DUT',fresh_header_validation=False,weight_payload_read=False,reference_ids_read=False,hardware_executed=False)
    if repo is not None:
        result['checked_sources']=check_sources(read_json(folder/'SOURCE_PINS.json'),repo,fixed_commands)
        result['status']='PASS_SUMMARY_ARITHMETIC_AND_LOCAL_SOURCE_SHA_ONLY_NOT_HEADER_OR_DUT_VALIDATION'
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=pathlib.Path);p.add_argument('--fixed-commands',type=pathlib.Path);a=p.parse_args()
    print(json.dumps(run(repo=a.repo,fixed_commands=a.fixed_commands),indent=2))
