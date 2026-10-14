"""Actual O and original hidden -> BF16 residual -> reused H2048 RMS resources."""
from pathlib import Path
from ..qwen35_gdn_prefill.elementwise import model as e
from ..qwen35_35b_output.driver import TypedStreamingProjectionDriver
from ..qwen35_35b_rms import owner as rms
from .strict_rms import StrictPostNormDriver

def require(ok,why):
 if not ok:raise ValueError('35B residual/postnorm stage: '+why)

def prepare_residual(o_driver,initial_rms_driver,memory,scalar,output_base,*,tag=35601):
 require(type(o_driver) is TypedStreamingProjectionDriver and o_driver.memory is memory,
  'same actual O driver/shared memory required')
 j=o_driver.job;extent=j.m*2048*2;r=o_driver.response
 initial=initial_rms_driver
 require(type(initial) is rms.TypedRmsDriver and initial.memory is memory and
  initial.owner.scalar is scalar and initial.response is not None and initial.response.status is None and
  initial.response.tag==initial.job.tag and initial.response.write_bytes==extent and
  initial.owner.job is initial.job, 'original accepted input RMS driver identity required')
 original_input=initial.input
 require(initial.source_hashes==tuple(e.sha(x.raw()) for x in (initial.input,initial.weight)) and
  memory.exact(initial.job.input,extent,readable=True) is original_input,
  'original pre-RMS hidden input and frozen hash required')
 require(o_driver.binding_identity==o_driver._binding_identity() and
  o_driver.bank_identity==o_driver._identity() and o_driver.matrix.epoch==o_driver.epoch and
  o_driver.owner.tiles.banks is o_driver.owner.a_banks and not o_driver.services().error,
  'original O resources/profile/job/epoch changed')
 require(memory.exact(j.a,j.m*j.k*2,readable=True) is o_driver.a and
  memory.exact(j.b,j.k*j.n*2,readable=True) is o_driver.b and
  o_driver.input_hashes==tuple(e.sha(x.raw()) for x in (o_driver.a,o_driver.b)),
  'actual O inputs or physical region bindings changed')
 source=Path(__file__).resolve().parents[1]/'qwen35_35b_output/reference.c'
 require(e.sha(source.read_bytes())==o_driver.profile.source_sha256,
  'calibrated O arithmetic source changed')
 require(j.m in (16,128) and j.k==4096 and j.n==2048 and j.write_bytes==extent,
  'complete original O shape')
 require(type(r) is tuple and r==(j.tag,None,extent) and o_driver._terminal_report is not None and
  o_driver._terminal_report['complete'] is True and tuple(o_driver._terminal_report['response'])==r,
  'accepted complete actual O terminal required')
 require(o_driver.pending_read is None and o_driver.pending_ack is None and o_driver.bridge is None and
  not o_driver.results and not o_driver.sum.busy and o_driver.loan.ports()['drained'] and
  memory.pending is None and o_driver.matrix.owner is None and scalar.client is None and
  o_driver.owner.tiles.idle and not o_driver.owner.tiles.leased and o_driver.owner.lease is None,
  'all O and shared resource obligations drained')
 producer=memory.exact(j.dst,extent,readable=True)
 require(producer is o_driver.output and not producer.readonly and
  producer.written==producer.acknowledged==set(range(0,extent,64)) and
  o_driver.counts['write_data_bytes']==o_driver.counts['ack_bytes']==extent and
  e.sha(producer.raw())==o_driver._terminal_report['output_sha256'], 'actual O data/ACK/bytes required')
 require(memory.exact(original_input.base,extent,readable=True) is original_input and
  original_input.readonly is True, 'authenticated original layer input required')
 owner=e.ElementwiseOwner(scalar,hidden_width=2048,profile=e.RESIDUAL_35B_PROFILE)
 job=e.ElementwiseJob(tag,original_input.base,producer.base,output_base,j.m,
  row_width=2048,profile=e.RESIDUAL_35B_PROFILE)
 d=e.TypedElementwiseDriver(owner,memory,job)
 require(d.a is original_input and d.b is producer,'no copied or normalized residual input')
 return d

def prepare_postnorm(residual_driver,rms_owner,memory,scalar,weight_base,output_base,*,tag=35602):
 d=residual_driver;j=d.job;r=d.response
 require(type(d) is e.TypedElementwiseDriver and d.memory is memory and
  d.owner.profile==j.profile==e.RESIDUAL_35B_PROFILE and j.op==e.ElementwiseOp.Add and
  j.row_width==2048 and d.owner.scalar is scalar, 'actual H2048 residual driver required')
 require(type(r) is e.ElementwiseResult and r.status is None and r.tag==j.tag and
  r.write_bytes==j.write_bytes==d.owner.ack_bytes==d.counts['ack_bytes'] and
  r.staging_complete is True and not any((r.state_committed,r.history_committed,r.generation_advanced)),
  'complete accepted stateless residual terminal')
 require(d.owner.state=='idle' and d.owner.result is None and d.owner.request is None and
  d.owner.program is None and d.owner.counts['owner_results']==1 and d.pending is None and
  d.pending_request is None and d.pending_write is None and memory.pending is None and
  scalar.client is None and d.owner.identity==d.owner.source_identity(),'residual retirement and source identity')
 require(d.sources is d._sources and d.a is d._sources[0] and d.b is d._sources[1] and
  d.source_hashes is d._source_hashes and d.source_hashes==tuple(e.sha(x.raw()) for x in d.sources) and
  all(memory.regions.get(x.base) is x for x in d.sources), 'residual source identities and bytes changed')
 require(type(rms_owner) is rms.RmsOwner and rms_owner.scalar is scalar and
  rms_owner.ports()['job_ready'],'reuse original drained H2048 RMS owner and scalar')
 region=memory.exact(j.output,j.write_bytes,readable=True)
 require(region is d.output and not region.readonly and
  region.written==region.acknowledged==set(range(0,j.write_bytes,64)) and
  e.sha(region.raw())==d._output_hash.hexdigest(),'actual residual bytes/ACK/producer identity')
 result=StrictPostNormDriver(rms_owner,memory,rms.RmsJob(tag,region.base,weight_base,output_base,j.tokens))
 require(result.input is region,'postnorm must consume actual residual region')
 return result
