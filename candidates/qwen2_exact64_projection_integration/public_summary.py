"""Post-execution strict aggregate-only projection; no paths, hashes or shapes."""
import math

def need(ok,message):
    if not ok:raise ValueError(message)
def integer(v,expected):need(type(v) is int and v==expected,'exact native integer counter');return v
def flag(v,expected):need(type(v) is bool and v is expected,'exact boolean gate');return v
def enum(v,expected):need(type(v) is str and v==expected,'fixed enum');return v
PLAN=(('Q1',2359296,98304,6144,True,False,False),
 ('K2',786432,32768,2048,True,False,False),('K1_STALLED',393216,16384,1024,True,False,False),
 ('ABORT_READ',0,0,0,False,True,False),('FOREIGN_READ',0,0,0,False,True,False),
 ('ABORT_WRITE',98304,4096,64,False,True,False),('FOREIGN_WRITE',98304,4096,64,False,True,False),
 ('SHORT_FINAL_ACK',393216,16384,960,False,False,True))

def project(r):
    need(type(r) is dict,'private result mapping')
    for k,v in dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
      public21='NOT_EXECUTED',profiled_dense_binding='NOT_EXECUTED',reservation_service='ORIGINAL_BASE_MATRIX_SERVICE').items():enum(r[k],v)
    need(type(r['cases']) is list and len(r['cases'])==8,'all fixed cases')
    result=[]
    for c,(name,fmas,adds,acked,success,drain,quarantine) in zip(r['cases'],PLAN):
        enum(c['name'],name);t=c['terminal'];k=c['owner']['kernel_delta']
        if success:need(t['status'] is None,'successful terminal');integer(c['bit_diff_count'],0)
        else:enum(t['status'],'Protocol');need(c['bit_diff_count'] is None,'failed case not numerically compared')
        integer(k['fmas'],fmas);integer(k['adds'],adds)
        integer(t['useful_macs'],fmas);integer(t['executed_macs'],fmas);integer(t['write_bytes'],acked)
        integer(c['owner']['write_bytes'],acked)
        integer(c['matrix']['dense_fma_calls'],0);integer(c['matrix']['normal_fma_calls'],0)
        flag(c['fault_injected'],not success);flag(c['drain_observed'],drain)
        for field in ('physical_pending_retained','matrix_lease_retained','a_lease_retained'):flag(c[field],quarantine)
        integer(c['final_ack_hold_ticks'],5 if success else 0)
        if success:
            a,b=c['last_successful_ack_tick'],c['terminal_tick']
            need(type(a) is int and type(b) is int and 0<=a<b<500000,'actual final ACK ordering')
        result.append(dict(case=name,terminal='SUCCESS' if success else 'EXPECTED_PROTOCOL_FAILURE',
          comparison='BITWISE_EQUAL' if success else 'NOT_COMPARED',actual_fma_count=fmas,actual_add_count=adds,
          acknowledged_output_byte_count=acked,accepted_debt='QUARANTINED' if quarantine else 'DRAINED'))
    return dict(schema=1,scope='DIAGNOSTIC_SOFTWARE_OWNER',hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
      public21='NOT_EXECUTED',profiled_dense_binding='NOT_EXECUTED',reservation_service='ORIGINAL_BASE_MATRIX_SERVICE',
      case_count=8,completed_case_count=8,successful_numerical_case_count=3,expected_protocol_failure_case_count=5,
      compared_output_word_count=2304,bit_diff_count=0,max_abs=0.0,mean_abs=0.0,
      actual_fma_count=4128768,actual_add_count=172032,original_matrix_fma_count=0,cases=result)
