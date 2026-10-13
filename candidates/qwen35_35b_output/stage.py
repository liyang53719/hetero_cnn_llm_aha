"""Actual norm producer admission into four independent partials/left-fold.

This is real control admission, not numerical acceptance. The caller runs all
Matrix/DMA/Vector handshakes; no saved output is imported as a producer.
"""
from ..qwen35_gdn_prefill import typed_dense as dense
from ..qwen35_gdn_prefill.gated_norm import model as norm
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from ..qwen35_gdn_prefill.conv.scalar import ConvScalar
from ..qwen35_gdn_prefill.prep.layout import GROUPED_35B
from .streaming_owner import StreamingProjectionOwner,NoPrefixWorkspace
from .driver import TypedStreamingProjectionDriver,FourProfile
K,N=4096,2048
WEIGHT_BYTES=K*N*2

def require(condition,detail):
    if not condition:raise ValueError('35B output stage: '+detail)

def _actual_norm(driver, memory, scalar, tokens):
    require(type(driver) is norm.TypedGatedNormDriver,
            'actual TypedGatedNormDriver required, not a Region or receipt')
    owner, job, receipt = driver.owner, driver.job, driver.response
    require(type(owner) is norm.GatedNormOwner and type(job) is norm.GatedNormJob
            and driver.memory is memory and owner.job is job,
            'same actual norm owner/job/shared memory required')
    require(job.tokens == tokens and job.heads == owner.heads == 32
            and job.layout == owner.layout == GROUPED_35B,
            'actual full32 35B norm geometry required')
    job.validate(owner.heads, owner.layout)
    require(isinstance(scalar, ConvScalar) and owner.scalar is scalar
            and driver.scalar_resource is scalar
            and driver.resource_identity == (id(owner), id(memory), id(scalar), GROUPED_35B),
            'same original shared Scalar and norm resources required')
    require(type(receipt) is norm.GatedNormResult
            and all(type(getattr(receipt, field)) is int for field in
                    ('tag', 'write_bytes', 'model_ticks'))
            and receipt.tag == job.tag and receipt.status is None
            and receipt.write_bytes == job.write_bytes == tokens * K * 2
            and receipt.model_ticks > 0 and receipt.staging_complete is True
            and receipt.state_committed is False
            and receipt.history_committed is False
            and receipt.generation_advanced is False,
            'accepted successful complete stateless norm terminal required')
    require(owner.state == 'idle' and owner.status is None and owner.poison is False
            and owner.counts['owner_results'] == 1 and owner.result is None
            and owner.program is None and owner.request is None
            and driver.aborted is False and driver.pending is None
            and driver.pending_request is None and driver.pending_write is None
            and memory.pending is None and scalar.client is None,
            'norm terminal must be accepted with every obligation drained')
    beats = job.write_bytes // 64
    require(owner.ack_bytes == job.write_bytes
            and owner.counts['write_requests'] == owner.counts['write_acks'] == beats
            and driver.counts['write_bytes'] == job.write_bytes,
            'complete actual norm write requests/data/ACK count required')
    output = memory.exact(job.output, job.write_bytes, readable=True)
    require(type(output) is dense.Region and output is driver.output
            and output.readonly is False and output.published is True
            and output.written == output.acknowledged == set(range(0, job.write_bytes, 64)),
            'O A must be exact published writable actual norm producer')
    require(driver.sources == (driver.core, driver.gate, driver.weight)
            and all(memory.regions.get(region.base) is region for region in driver.sources)
            and driver.source_hashes == tuple(norm.sha(region.raw()) for region in driver.sources),
            'actual norm producer sources changed')
    require(owner.identity == norm.source_identity(layout=GROUPED_35B),
            'actual norm source identity changed')
    return output


def prepare_output_projection(norm_driver,projection_owner,matrix,memory,*,weight_base,
                              output_base,tokens,scalar,vector,profile,tag=35501):
    require(type(tokens) is int and tokens in (16,128),'M16/M128')
    require(type(memory) is dense.TypedMemory and type(matrix) is dense.MatrixService and
            type(projection_owner) is StreamingProjectionOwner,'same exact streaming resources')
    require(type(profile) is FourProfile,'explicit independently calibrated four-part profile')
    profile.validate(K)
    require(type(vector) is Vector16 and vector.exception_policy==IEEE_POLICY and
            vector.client is None and matrix.owner is None and not matrix.reset_required and
            memory.pending is None,'shared resources drained')
    owner=projection_owner
    require(owner.state=='idle' and owner.error is None and not owner._ordinary_live and
            owner.window_request is None and owner.drain_request is None and owner.lease is None and
            owner.tiles.idle and not owner.tiles.leased and not owner.tiles.poison,
            'all previous projection obligations retired')
    require(type(owner.workspace) is NoPrefixWorkspace and owner.a_banks is owner.tiles.banks and
            len(owner.a_banks.words)==16 and all(len(x)==1376 for x in owner.a_banks.words) and
            len(owner.b_banks.words)==16 and all(len(x)==160 for x in owner.b_banks.words) and
            matrix.resource_address==matrix.lib.matrix_accumulator_address() and
            matrix.lib.matrix_accumulator_bytes()==5*16*256*4,'fixed physical banks/contexts')
    activation=_actual_norm(norm_driver,memory,scalar,tokens)
    require(type(tag) is int and 0<tag<(1<<32)-8 and tag!=norm_driver.job.tag,'distinct bounded tag/identities')
    weight=memory.exact(weight_base,WEIGHT_BYTES,readable=True)
    require(weight.readonly is True,'complete immutable packed KN O weight')
    output=memory.exact(output_base,tokens*N*2,readable=False)
    job=dense.down.Job(m=tokens,k=K,n=N,tag=tag,a=activation.base,b=weight_base,dst=output_base,
        activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=tokens*N*2)
    resources=(id(owner),id(owner.workspace),id(owner.a_banks),id(owner.b_banks),id(owner.tiles),
               matrix.resource_address,matrix.epoch,id(memory),id(scalar),id(vector))
    driver=TypedStreamingProjectionDriver(owner,matrix,memory,job,vector=vector,profile=profile,role='synthetic')
    require(driver.a is activation and driver.b is weight and driver.output is output and
            driver.owner is owner and resources==(id(owner),id(owner.workspace),id(owner.a_banks),
            id(owner.b_banks),id(owner.tiles),matrix.resource_address,matrix.epoch,id(memory),id(scalar),id(vector)),
            'actual producer and resources retained through admission')
    return driver
