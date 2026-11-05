"""Strict public witness schema; hashes are diagnostics, never acceptance."""
import hashlib,json,re
ROLES={'OTHER','IDMA_READ_REQUEST_PACKED','IDMA_READ_RESPONSE_PACKED','IDMA_SPLIT_R_READY','IDMA_SPLIT_R_LAST'}
REASONS={'NONE','NO_CLOSED_PATH','NODE_CAP','EDGE_CAP','OUTPUT_CAP','TIME_CAP','REVERSE_EDGE_MISSING','NAME_CAP','INVALID_ROLE','INTERNAL_ERROR'}
KEYS={'schema','status','reason','digest','node_hashes','roles','edge_origins','closed','edge_checked','visited','inspected','start_hash','start_role'}
def parse_record(s):
 def need(v):
  if not v:raise ValueError('INVALID_WITNESS_RECORD')
 need(type(s)is str and len(s.encode('ascii'))<=8192)
 def object_pairs(rows):
  need(len(rows)==len(dict(rows)));return dict(rows)
 d=json.loads(s,object_pairs_hook=object_pairs)
 need(type(d)is dict and set(d)==KEYS and d['schema']=='BOUNDED_CYCLE_WITNESS_V2')
 need(d['status']in {'CLOSED_WITNESS','INCOMPLETE_WITNESS'} and d['reason']in REASONS)
 for k,cap in [('visited',4096),('inspected',16384)]:need(type(d[k])is int and 0<=d[k]<=cap)
 for k in ('node_hashes','roles','edge_origins'):need(type(d[k])is list and len(d[k])<=32)
 hs,rs,es=d['node_hashes'],d['roles'],d['edge_origins'];need(len(hs)==len(rs)==len(es))
 need(all(type(x)is str and re.fullmatch('[0-9a-f]{64}',x)for x in hs))
 need(all(type(x)is str and x in ROLES for x in rs) and all(x=='UNKNOWN' for x in es))
 need(type(d['closed'])is bool and type(d['edge_checked'])is bool)
 need(type(d['start_hash'])is str and (d['start_hash']=='UNAVAILABLE' or re.fullmatch('[0-9a-f]{64}',d['start_hash'])))
 need(type(d['start_role'])is str and d['start_role']in ROLES)
 need(d['start_hash']!='UNAVAILABLE' or d['start_role']=='OTHER')
 complete=d['status']=='CLOSED_WITNESS'
 if complete:need(bool(hs) and d['start_hash']==hs[0] and d['start_role']==rs[0])
 elif d['start_hash']=='UNAVAILABLE':need(d['reason']in {'TIME_CAP','NAME_CAP','INVALID_ROLE','INTERNAL_ERROR'})
 need(d['closed']==complete and d['edge_checked']==complete)
 need((d['reason']=='NONE' and 1<=len(hs)<=d['visited'] and len(hs)<=d['inspected'])if complete else(d['reason']!='NONE' and not hs))
 need(type(d['digest'])is str and d['digest']==hashlib.sha256('\n'.join(h+':'+r for h,r in zip(hs,rs)).encode()).hexdigest())
 return d
