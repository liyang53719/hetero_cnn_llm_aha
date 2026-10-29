#!/usr/bin/env python3
"""Source-derived M128 lower/upper bounds, not simulation; standard library only."""
import json,pathlib
M=128
phases=[(5,64,64,128),(6,64,64,128),(7,64,128,64),(8,64,128,64),(9,64,128,128),(10,64,128,0),(11,64,128,128),(12,64,128,64),(13,64,128,0),(14,128,128,64),(15,128,128,0),(16,128,128,0),(17,64,128,0)]
phase_counts=[]
for p,r,c,k in phases:
 dot=p in (5,6,9,11,12,14);solve=p in (7,8);out=p==17;factor=p in (5,6)
 reads=r*(c//16)*(k+k//16+factor) if dot else 17888 if solve else r*8 if out else 1024 if p==15 else r*(c//16)*2
 vectors=r*(c//16)*(2*k+factor) if dot else 32768 if solve else r*8 if out else r*(c//16)
 writes=r*256//64 if out else r*c*4//64
 phase_counts.append(dict(phase=p,read_beats=reads,write_beats=writes,vector_requests=vectors,min_serial_handshake_cycles=2*(reads+writes+vectors)))
occ=json.loads((pathlib.Path(__file__).resolve().parent/'OCCUPANCY_REFERENCE_SUMMARY.json').read_text())
profiles=[]
for p in range(5):
 h=[1536,1024,1024,2048,2048][p]; heads=[12,16,8,32,16][p]; gdn=p in (1,3);moe=p>=3
 if gdn: widths=[4096+heads*128,heads*128,heads*2];outwidth=heads*128
 elif p==0: widths=[1536,256,256];outwidth=1536
 else:widths=[heads*512,512,512];outwidth=heads*256
 projection=M*h*(sum(widths)+outwidth)
 ffn=0 if moe else M*3*h*(8960 if p==0 else 3584)
 expert=1024*3*2048*512 if moe else 0
 shared=M*3*2048*512 if moe else 0
 router=M*2048*256 if moe else 0
 shared_gate=M*2048 if moe else 0
 attention_rect=0 if gdn else 2*M*M*heads*(128 if p==0 else 256)
 attention_causal=0 if gdn else M*(M+1)*heads*(128 if p==0 else 256)
 total=projection+ffn+expert+shared+router+shared_gate+attention_rect
 waste=(128*occ[p-3]['active_experts']-1024)*3*2048*512+M*2048*31 if moe else 0
 # max efficiency even giving every remaining MAC perfect parallel throughput.
 qk_idle_capacity=7*(attention_rect//2) if p in (2,4) else 0
 geom=total/(total+waste+qk_idle_capacity)
 gc={key:sum(q[key] for q in phase_counts)*heads*2 for key in ('read_beats','write_beats','vector_requests','min_serial_handshake_cycles')} if gdn else {}
 if gdn:
  gc['traffic_bytes']=64*(gc['read_beats']+gc['write_beats'])
  gc['seconds_at_100_decimal_GBps']=gc['traffic_bytes']/100e9
  gc['max_clock_hz_for_80pct_at_100GBps_execute_traffic_only']=total*100e9/(4096*.8*gc['traffic_bytes'])
  gc['max_clock_hz_for_90pct_at_100GBps_execute_traffic_only']=total*100e9/(4096*.9*gc['traffic_bytes'])
  gc['exclusive_chunk_only_full_block_util_ceiling']=total/(total+waste+4096*gc['min_serial_handshake_cycles'])
 profiles.append(dict(profile=p,projection_macs=projection,dense_ffn_macs=ffn,routed_expert_macs=expert,shared_ffn_macs=shared,router_macs=router,shared_gate_logical_macs=shared_gate,attention_rectangular_macs=attention_rect,attention_causal_semantic_macs=attention_causal,total_matrix_macs_rectangular=total,padding_wasted_macs=waste,qk_inactive_physical_capacity_macs=qk_idle_capacity,geometry_only_upper_bound=geom,gdn_execute_5_to_17_only=gc))
print(json.dumps(dict(status='SOURCE_BOUND_NOT_DUT_MEASURED',gdn_phase_counts_per_head_chunk=phase_counts,profiles=profiles),indent=2))
