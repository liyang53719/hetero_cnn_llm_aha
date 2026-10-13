"""Validate and expose only a retired 35B chunk's stateless core intermediate.

This is a software transport boundary, not a block commit or numerical gate.
The caller must supply its actual successful Conv driver's history_out region.
A Region alone cannot attest the Conv receipt that produced it.
"""
from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.chunk.vector import IEEE_POLICY, Vector16
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar
from candidates.qwen35_gdn_prefill.typed_dense import Region, TypedMemory


def _require(condition, detail):
    if not condition:
        raise ValueError('35B core-only publication: ' + detail)


def _private_complete(memory, region, base, extent, name):
    _require(type(region) is Region and region.base == base and
             region.extent == extent and memory.regions.get(base) is region,
             name + ' physical region identity/extent')
    region.check()
    _require(not region.readonly and not region.published and
             region.written == region.acknowledged == set(range(0, extent, 64)),
             name + ' complete private actual data/ACK coverage')


def publish_core_intermediate(driver, history, scalar, vector, *, tokens):
    """Publish the core once, after a complete accepted private chunk receipt.

    The supported route is the current cold M16/M128 35B prefix. Recheck the
    actual typed driver, job, owner, original shared resources, full staging
    spans, accepted terminal and physical drain before the sole mutation.
    State, scratch, Conv history, and all generation fields remain private and
    unchanged. No receipt dictionary or caller-provided bytes can grant access.
    """
    _require(type(driver) is chunk.TypedChunkDriver, 'actual TypedChunkDriver required')
    owner, memory, job, receipt = driver.owner, driver.memory, driver.job, driver.response
    _require(type(owner) is chunk.ChunkOwner and type(memory) is TypedMemory and
             type(job) is chunk.ChunkJob and owner.job is job,
             'original typed owner/memory/job identity')
    _require(type(tokens) is int and tokens in (16, 128) and job.tokens == tokens and
             job.cold is True and job.expected_generation == 0 and
             job.layout == chunk.GROUPED_35B and owner.layout == chunk.GROUPED_35B and
             owner.geometry == (32, 128, 128) and owner.host_batch is True and
             job.cumsum_policy == owner.cumsum_policy == chunk.GUARDED_CUMSUM and
             job.exp_policy == owner.exp_policy == chunk.ep.IEEE_EXP,
             'cold full32 M16/M128 chunk profile')
    job.validate(owner.geometry, owner.layout, owner.cumsum_policy, owner.exp_policy)
    _require(isinstance(scalar, PrepScalar) and type(vector) is Vector16 and
             owner.scalar is scalar and owner.vector is vector and
             vector.exception_policy == IEEE_POLICY,
             'same shared Scalar and finite IEEE Vector16')
    chunk.ep.validate_policy(owner.exp_policy, owner.layout, scalar, vector)
    _require(driver.resource_identity == (
        id(owner), id(memory), id(scalar), id(vector), vector.resource_address,
        owner.host_batch, vector.exception_policy, vector.fatal_mask, owner.layout,
        owner.cumsum_policy, owner.exp_policy, getattr(scalar, 'enable_ieee_exp', False)),
        'original driver resource identity')
    _require(type(receipt) is chunk.ChunkResult and receipt.status is None and
             receipt.staging_complete is True and
             all(type(getattr(receipt, name)) is int for name in (
                 'tag', 'write_bytes', 'output', 'state_out', 'output_bytes',
                 'state_bytes', 'expected_generation', 'model_ticks')) and
             receipt.tag == job.tag and receipt.output == job.output and
             receipt.state_out == job.state_out and
             receipt.output_bytes == job.output_bytes == tokens * 4096 * 2 and
             receipt.state_bytes == job.state_bytes == 32 * 128 * 128 * 4 and
             receipt.write_bytes == job.write_bytes == job.output_bytes + job.state_bytes and
             receipt.expected_generation == job.expected_generation == 0 and
             receipt.model_ticks > 0 and
             receipt.state_committed is False and receipt.history_committed is False and
             receipt.generation_advanced is False,
             'successful complete typed staging receipt identity/extents')
    _require(owner.state == 'idle' and owner.status is None and owner.poison is False and
             driver.aborted is False and owner.counts['owner_results'] == 1 and
             owner.result is None and owner.program is None and owner.request is None and
             owner.ack_bytes == job.write_bytes and
             owner.counts['scratch_ack_bytes'] == job.scratch_bytes,
             'exactly one accepted successful owner terminal')
    _require(memory.pending is None and driver.pending is None and
             driver.pending_request is None and driver.pending_write is None and
             scalar.client is None and vector.client is None,
             'all transport obligations and shared leases drained')
    _require(driver.sources == [driver.input] and
             memory.exact(job.input, job.input_bytes, readable=True) is driver.input and
             not driver.input.readonly and
             driver.input.written == driver.input.acknowledged ==
                 set(range(0, job.input_bytes, 64)) and
             driver.source_hashes == (chunk.sha(driver.input.raw()),),
             'unchanged actual published Prep input')
    _require(owner.identity == chunk.source_identity(
        vector.exception_policy, owner.layout, owner.cumsum_policy, owner.exp_policy),
        'chunk source identity changed after admission')
    for name, extent in (('output', job.output_bytes), ('state_out', job.state_bytes),
                         ('scratch', job.scratch_bytes)):
        _private_complete(memory, getattr(driver, name), getattr(job, name), extent, name)
    _require(type(history) is Region and history.base not in (
        job.input, job.state_in, job.output, job.state_out, job.scratch),
        'separate Conv history staging region')
    _private_complete(memory, history, history.base, 8192 * 8, 'Conv history')
    report = dict(
        core_sha256=chunk.sha(driver.output.raw()),
        state_sha256=chunk.sha(driver.state_out.raw()),
        scratch_sha256=chunk.sha(driver.scratch.raw()),
        history_sha256=chunk.sha(history.raw()),
        core_published=True, state_published=False, scratch_published=False,
        history_published=False, generation_advanced=False,
        expected_generation=receipt.expected_generation,
        accepted_chunk_tag=receipt.tag, output_bytes=receipt.output_bytes,
        state_bytes=receipt.state_bytes,
    )
    # This is deliberately the only externally visible mutation, after every
    # possible validation and digest operation above has succeeded.
    memory.publish(job.output, (receipt.tag, None, receipt.output_bytes))
    return report
