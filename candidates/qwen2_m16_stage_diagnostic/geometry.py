"""Fixed M16 logical work, unchanged 128-row physical Matrix geometry."""
ROWS=16
H=1536
F=8960
HEADS=12
KVHEADS=2
HD=128
CAUSAL=HEADS*ROWS*(ROWS+1)//2
ROPE_BYTES=2*1024*64*4
WORKSPACE_BYTES=48*16384
EXACT=dict(fmas=ROWS*(H+256)*H,adds=ROWS*(H+256)*64,tiles=ROWS*(H+256)//64,
           write_bytes=ROWS*(H+256)*4,read_requests=ROWS*(96+24*3072)+ROWS*(96+4*3072))
V=dict(partials=4,drains=2,wide_matrix_steps=12288,useful_macs=ROWS*256*H,
       executed_macs=50331648,actual_c_fma_calls=50331648,vector_add_requests=ROWS//16*256,
       raw_qkv_ack_bytes=ROWS*256*4)
ATTENTION=dict(causal_pairs=CAUSAL,qk_steps=8*CAUSAL,pv_steps=4*CAUSAL,normal_steps=12*CAUSAL,
               normal_fma=12*CAUSAL*512,useful_macs=CAUSAL*256,write_bytes=ROWS*H*4,kv_bytes=ROWS*2048)
TAIL=dict(dense_steps=1363968,dense_fma=5586812928,useful_macs=ROWS*43646976,
          groups=162,results=800,leases=114,seed_acks=144,silu_calls=ROWS*F//16)
WHOLE=dict(dense_steps=TAIL['dense_steps']+V['wide_matrix_steps'],normal_steps=ATTENTION['normal_steps'],
           dense_fma=TAIL['dense_fma']+V['actual_c_fma_calls'],normal_fma=ATTENTION['normal_fma'],
           useful_macs=TAIL['useful_macs']+V['useful_macs']+EXACT['fmas']+ATTENTION['useful_macs'],
           executed_macs=TAIL['dense_fma']+V['actual_c_fma_calls']+EXACT['fmas']+ATTENTION['normal_fma'])
WHOLE['matrix_opportunities']=4096*(WHOLE['dense_steps']+WHOLE['normal_steps'])
PRODUCERS=('n0','qraw','qr','q','kraw','kr','k','vraw','v')
STAGES=('PC0_NORM','PC1_Q','PC2_Q_BIAS','PC3_Q_ROPE','PC4_K','PC5_K_BIAS','PC6_K_ROPE','PC7_V','PC8_V_BIAS')
TAIL_STAGES={'pc12_release':'PC12_RELEASE','pc13_Dense':'PC13_O','pc14_Add':'PC14_RESIDUAL','pc15_Norm':'PC15_NORM',
 'pc16_18_resident_ffn':'PC16_18_FFN','pc19_down':'PC19_DOWN','pc20_residual':'PC20_RESIDUAL','launch_result_hold_retire':'LAUNCH_RESULT'}
LIMITS_MODEL=dict(cpu_seconds=1200,wall_seconds=1260,address_space_bytes=4<<30,output_bytes=96<<20)
LIMITS_REFERENCE=dict(cpu_seconds=60,wall_seconds=90,address_space_bytes=4<<30,output_bytes=96<<20)

def need(ok,message):
    if not ok:raise ValueError(message)

def exact_totals(records):
    need(len(records)==2,'two full actual Q/K terminals')
    totals=dict(fmas=0,adds=0,tiles=0,write_bytes=0,read_requests=0)
    for pc,n,r in zip((1,4),(1536,256),records):
        j=r['job'];k=r['kernel_delta'];m=r['memory'];t=r['terminal']
        need(j['tag']&65535==pc and (j['m'],j['n'],j['k'])==(ROWS,n,H) and t['status'] is None,'actual M16 Q/K job/terminal')
        need(k['fmas']==ROWS*n*H and k['adds']==ROWS*n*64 and k['tiles_started']==r['tiles_output_acked']==ROWS*n//64,'actual exact64 arithmetic coverage')
        reads=ROWS*(96+n//64*3072);writes=ROWS*n//16
        need(m==dict(read_bytes=reads*64,write_bytes=writes*64,read_requests=reads,write_requests=writes,acks=writes),'actual exact64 Memory/ACK coverage')
        need(t['write_bytes']==ROWS*n*4 and t['useful_macs']==t['executed_macs']==k['fmas'] and r['partial_bytes']==16384,'actual terminal/payload contract')
        need(r['actual_dense_fma_calls_delta']==r['actual_normal_fma_calls_delta']==0 and
             r['matrix_counter_delta'].get('dense_steps',0)==r['matrix_counter_delta'].get('normal_steps',0)==0,'no fake Matrix issue')
        need(r['final_ack_fence']['terminal_strictly_after_final_ack'] is True and r['final_ack_fence']['held_ticks']==5,'actual final ACK fence')
        for key,value in (('fmas',k['fmas']),('adds',k['adds']),('tiles',k['tiles_started']),('write_bytes',t['write_bytes']),('read_requests',reads)):totals[key]+=value
    need(totals==EXACT,'M16 exact totals');return totals

def v_totals(records):
    need(len(records)==1 and records[0]['original_public_job']['tag']&65535==7,'original V only')
    r=records[0];t=r['terminal']
    value=dict(partials=len(r['partials']),drains=len(r['drains']),wide_matrix_steps=r['accepted']['backend_step_fire'],
      useful_macs=t['useful_macs'],executed_macs=t['executed_macs'],actual_c_fma_calls=r['actual_dense_fma_calls_delta'],
      vector_add_requests=r['shared_vector']['add_requests'],raw_qkv_ack_bytes=t['write_bytes'])
    need(value==V,'M16 V actual schedule');return value

def whole(matrix,launch,silu,statistics):
    c=matrix['counters']
    observed=dict(dense_steps=c['dense_steps'],normal_steps=c['normal_steps'],dense_fma=matrix['dense_fma_calls'],
      normal_fma=matrix['normal_fma_calls'],useful_macs=launch['useful_macs'],executed_macs=launch['executed_macs'],
      matrix_opportunities=statistics['full_fixed_array_issued_cell_opportunities'])
    need(observed==WHOLE and silu.calls==int(silu.sf_calls())==TAIL['silu_calls'] and int(silu.sf_failures())==0,'actual M16 whole accounting')
    need(observed['dense_fma']+observed['normal_fma']+EXACT['fmas']==observed['executed_macs'],'separate software and Matrix arithmetic')
    from collections import Counter
    tail=Counter()
    for interval in statistics['intervals']:
        if interval['name'] in ('pc13_Dense','pc16_18_resident_ffn','pc19_down'):
            tail.update(interval['accepted_counter_delta']['matrix'])
    need(tuple(tail[n] for n in ('dense_steps','dense_groups','dense_results','owner_acquires','owner_releases','dense_seed_acks'))==
      (TAIL['dense_steps'],TAIL['groups'],TAIL['results'],TAIL['leases'],TAIL['leases'],TAIL['seed_acks']),'actual original tail physical event schedule')
    return dict(predicted=WHOLE,observed=observed,observed_tail=dict(tail),physical_rows=128,logical_rows=16,hardware_cycles=None,performance='NO_GO')
