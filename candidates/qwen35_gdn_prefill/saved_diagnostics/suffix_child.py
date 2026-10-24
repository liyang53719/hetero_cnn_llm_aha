"""Explicit native opt-in child for five fixed suffix cases. TEMP_NOT_EXECUTED.

Shared loading/ticking/receipt control; original model arithmetic is not adapted.
Resident handoffs stay inside each fixed diagnostic. No full-block continuation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from suffix_case import MATRIX_CASES, DENSE_STAGES, plan_case, need
from launch_chunk import save


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_boundary(memory, wire, base, raw):
    """Fresh diagnostic writes/ACKs, never a replay of producer receipts."""
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(wire.WriteCommand(base + offset, 1, 1))
        memory.write_data(struct.unpack_from('<32H', raw, offset), True, mask=(1 << 64) - 1)
        memory.acknowledge(wire.WriteAck(1, False, 64))
    memory.publish(base, (1, None, len(raw)))
    need(region.written == region.acknowledged == set(range(0, len(raw), 64)) and
         region.published and not region.readonly, 'diagnostic loader coverage')
    return region


def construct_driver(factory, memory, scalar):
    # Constructors perform the real owner admission and may acquire Scalar.
    # Test idleness before construction, never undo or reject that acquisition.
    need(memory.pending is None and (scalar is None or scalar.client is None), 'drained stage start')
    return factory()


def dense_bindings(driver):
    owner = driver.owner
    return (owner, driver.matrix, owner.a_banks, owner.b_banks, owner.a_banks.words,
            owner.b_banks.words, owner.workspace, *owner.a_banks.words, *owner.b_banks.words)


def install_audit(plan, run, guard):
    forbidden = ('candidates.qwen35_gdn_prefill.full_driver', 'candidates.qwen35_gdn_prefill.full_compare',
                 'candidates.qwen35_gdn_prefill.native.capture')
    references = {Path(path).resolve() for path in plan['reference_paths']}
    def audit(event, args):
        if event == 'subprocess.Popen' and guard is not None:
            guard.audit(event, args); return
        if event.startswith('subprocess.') or event in ('os.system', 'os.posix_spawn', 'os.posix_spawnp',
                'os.fork', 'os.forkpty', 'os.exec', 'os.spawn', 'pty.spawn') or event.startswith('socket.'):
            raise RuntimeError('subprocess/network outside exact source-identity allowance')
        if event == 'ctypes.dlopen' and args[0] is not None:
            need(plan['case'] in MATRIX_CASES and str(Path(args[0]).resolve()) == plan['matrix_library'], 'native library not admitted')
        if event == 'import':
            need(args[0].split('.')[0] not in ('torch', 'transformers') and args[0] not in forbidden, 'reference/full replay import')
        if event == 'exec':
            need(not any(args[0].co_filename.endswith('/' + name.replace('.', '/') + '.py') for name in forbidden), 'full replay execution')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            need(path not in references and not any(part == 'reference' or part.startswith('native_m') for part in path.parts), 'reference read')
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                need(run == path or run in path.parents, 'write outside fresh run')
    sys.addaudithook(audit)


def setup(plan, selected):
    """Fixed original owner/driver constructors, not arbitrary loadable plugins."""
    addresses = selected['addresses']; name = selected['name']; scalar = binding = matrix = None
    if name in MATRIX_CASES:
        import ctypes
        from candidates.qwen35_gdn_prefill import typed_dense as model
        from candidates.qwen35_gdn_prefill.projection_owner import GdnProjectionOwner
        from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
        library = model.library_from_environment(plan['repository'])
        need(str(library) == plan['matrix_library'], 'exact ordinary Matrix library')
        lib = configure_library(ctypes.CDLL(str(library))); need(lib.td_reset() == 0, 'one initial Matrix reset')
        matrix = model.MatrixService(lib); owner = GdnProjectionOwner(); memory = model.TypedMemory()
        wire = model.dense_wire_authority(owner, model.down.Job())
        base = 0x4000000 if name == 'gate_up' else 0x1000000
        owner.workspace = wire.PrefixWorkspace(base, 524288, 1)
        def dense_driver(stage, input_key, weight_key, k, n, tag, seeded=False):
            job = model.down.Job(m=128, k=k, n=n, tag=tag, a=addresses[input_key], b=addresses[weight_key],
                dst=addresses[stage], activation_bf16=True, weight_bf16=True, output_bf16=True,
                write_bytes=selected['references'][stage]['bytes'])
            if seeded:
                from candidates.qwen35_gdn_prefill.dense_prefix import TypedSeededDenseDriver
                return TypedSeededDenseDriver(owner, matrix, memory, job)
            return model.TypedDenseDriver(owner, matrix, memory, job)
        if name == 'o':
            drivers = [lambda: dense_driver('o', 'gated_norm', 'weight_kn', 2048, 1024, 90)]
        elif name == 'gate_up':
            drivers = [lambda: dense_driver('gate', 'post_norm', 'gate_weight_kn', 1024, 3584, 120),
                       lambda: dense_driver('up', 'post_norm', 'up_weight_kn', 1024, 3584, 130)]
        else:
            from candidates.qwen35_gdn_prefill.elementwise import model as elt
            from candidates.qwen35_35b_exp.scalar import DecayScalar
            from candidates.qwen35_gdn_prefill.scalar_identity import ScalarIdentityGuard
            scalar = DecayScalar(enable_softplus=True, enable_ieee_exp=True); binding = ScalarIdentityGuard(scalar)
            elementwise = elt.ElementwiseOwner(scalar)
            need(owner.workspace.split_k == 2560, 'original seeded Down split')
            silu = elt.ElementwiseJob(140, addresses['gate'], addresses['up'], addresses['silu_mul'],
                                      128, elt.ElementwiseOp.SiluMul, 3584)
            add = elt.ElementwiseJob(160, addresses['attention_residual'], addresses['down'], addresses['output'],
                                     128, elt.ElementwiseOp.Add, 1024)
            drivers = [lambda: elt.TypedElementwiseDriver(elementwise, memory, silu),
                       lambda: dense_driver('down', 'silu_mul', 'weight_kn', 3584, 1024, 150, True),
                       lambda: elt.TypedElementwiseDriver(elementwise, memory, add)]
        wire = model.down
    else:
        from candidates.qwen35_35b_exp.scalar import DecayScalar
        from candidates.qwen35_gdn_prefill.scalar_identity import ScalarIdentityGuard
        scalar = DecayScalar(enable_softplus=True, enable_ieee_exp=True); binding = ScalarIdentityGuard(scalar)
        if name == 'gated_norm':
            from candidates.qwen35_gdn_prefill.gated_norm import model
            memory = model.TypedMemory(); owner = model.GatedNormOwner(scalar)
            job = model.GatedNormJob(80, addresses['core'], addresses['z'], addresses['weight'], addresses['gated_norm'], 128)
            drivers = [lambda: model.TypedGatedNormDriver(owner, memory, job)]
        else:
            from candidates.qwen35_gdn_prefill.elementwise import model
            from candidates.qwen35_gdn_prefill import rms_owner as rms
            memory = model.TypedMemory(); owner = model.ElementwiseOwner(scalar); rms_owner = rms.RmsOwner(scalar)
            add = model.ElementwiseJob(100, addresses['hidden'], addresses['o'], addresses['attention_residual'],
                                      128, model.ElementwiseOp.Add, 1024)
            norm = rms.RmsJob(110, addresses['attention_residual'], addresses['weight'], addresses['post_norm'],
                              128, rms.ReductionPolicy.Torch210CpuDefault1024)
            drivers = [lambda: model.TypedElementwiseDriver(owner, memory, add),
                       lambda: rms.TypedRmsDriver(rms_owner, memory, norm)]
        wire = model
    loaders = []
    boundaries = {'gated_norm': ('core', 'z'), 'o': ('gated_norm',), 'residual_post_norm': ('o',), 'gate_up': ('post_norm',),
                  'final_triplet': ('gate', 'up', 'attention_residual')}[name]
    for key, address in addresses.items():
        if key == 'prefix':
            memory.allocate_output(address, 524288); continue
        if key in selected['stages']:
            memory.allocate_output(address, selected['references'][key]['bytes']); continue
        item = plan['stage_inputs'][key]; raw = Path(item['path']).read_bytes()
        need(len(raw) == item['bytes'] and digest(raw) == item['sha256'], 'saved input identity: ' + key)
        if key in boundaries:
            region = load_boundary(memory, wire, address, raw)
            loaders.append(dict(input=key, bytes=len(raw), sha256=digest(raw), written_beats=len(region.written),
                acknowledged_beats=len(region.acknowledged), published=region.published,
                method='DIAGNOSTIC_BOUNDARY_WRITE_ACK_PUBLICATION_NOT_HISTORICAL_PRODUCER_RECEIPT'))
        else:
            memory.add_readonly(address, raw)
    need(set(memory.regions) == set(addresses.values()), 'only fixed stateless regions')
    return memory, scalar, binding, matrix, drivers, loaders


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('plan', type=Path)
    args = parser.parse_args(); raw = args.plan.read_bytes(); plan_sha = digest(raw)
    need(plan_sha == os.environ['QWEN35_REVIEWED_PLAN_SHA256'], 'reviewed plan changed')
    plan = json.loads(raw); selected = plan_case(plan); run = Path(plan['run_directory'])
    until = time.monotonic() + 3
    while not (run / 'START.json').exists():
        need(time.monotonic() < until, 'durable parent permit absent'); time.sleep(.01)
    identity = json.loads((run / 'START.json').read_text())
    need(identity['pid'] == os.getpid() and identity['ppid'] == os.getppid(), 'exact parent permit')
    guard = None
    if selected['git_calls']:
        from suffix_git_guard import SourceGitGuard
        guard = SourceGitGuard(plan, dict(os.environ), run / 'SOURCE_GIT.jsonl')
    install_audit(plan, run, guard)
    sys.path[:0] = [plan['repository'], str(Path(plan['repository']) / 'src'), plan['numpy_site']]
    started = time.monotonic(); deadline = min(started + selected['driver_seconds'], identity['work_stop_monotonic'] - 1)
    memory, scalar, binding, matrix, factories, loaders = setup(plan, selected)
    physical = {base: (region, region.storage) for base, region in memory.regions.items()}
    actual = run / 'actual'; actual.mkdir(); reports = {}; completed = []; previous = None; handoff = None
    handoffs = []; dense_resource = None; retained_dense_driver = None
    common = dict(case=selected['name'], original_execution_status='UNKNOWN', original_continuation=False,
        full_block_acceptance=False, single_resident_full_block_lifecycle=False, block_generation=0,
        state_committed=False, history_committed=False, generation_advanced=False, output_reference_read=False)
    def check_bindings(driver):
        if scalar is not None:
            binding.check(scalar)
            if hasattr(driver.owner, 'scalar'):
                need(driver.owner.scalar is scalar, 'shared original Scalar')
        if matrix is not None:
            need(matrix.epoch == 0 and not matrix.reset_required, 'no coordinated Matrix reset')
        if retained_dense_driver is not None:
            current = dense_bindings(retained_dense_driver)
            need(len(current) == len(dense_resource) and all(a is b for a, b in zip(current, dense_resource)),
                 'retained Dense owner/Matrix/bank storage')
        if selected['name'] == 'final_triplet':
            need(not memory.regions[selected['addresses']['prefix']].published, 'private prefix never published')
        need(driver.memory is memory and set(memory.regions) == set(physical), 'unchanged TypedMemory')
        for base, (region, storage) in physical.items():
            need(memory.regions[base] is region and region.storage is storage, 'physical region replacement')
    def summary(status):
        return dict(common, status=status, completed_stages=completed, terminal_count=len(completed),
            diagnostic_loaders=loaders, elapsed_seconds=time.monotonic()-started, handoff=handoff, handoffs=handoffs,
            source_git=guard.report() if guard else {'complete': True, 'total_calls': 0}, policy=plan['policy'])
    try:
        for stage, factory in zip(selected['stages'], factories):
            directory = actual / stage; directory.mkdir(); stage_start = time.monotonic()
            need(matrix is None or matrix.owner is None, 'Matrix drained before constructor')
            driver = construct_driver(factory, memory, scalar); check_bindings(driver)
            if stage in DENSE_STAGES:
                resource = dense_bindings(driver)
                if dense_resource is not None:
                    need(all(a is b for a, b in zip(resource, dense_resource)), 'retained Dense owner/Matrix/banks')
                dense_resource = resource; retained_dense_driver = driver
            if previous is not None and selected['name'] == 'residual_post_norm':
                region = previous.output; coverage = set(range(0, 262144, 64))
                need(driver.input is region and driver.input.storage is physical[region.base][1] and region.published and
                     region.written == region.acknowledged == coverage, 'direct genuine residual storage')
                handoff = dict(method='DIRECT_GENUINE_ACCEPTED_TYPED_REGION_NO_COPY_OR_REPLACEMENT',
                    source_sha256=digest(region.raw()), source_bytes=262144, same_scalar=previous.owner.scalar is driver.owner.scalar,
                    same_memory=previous.memory is driver.memory, same_region=driver.input is previous.output,
                    same_storage=driver.input.storage is previous.output.storage, written_beats=4096, acknowledged_beats=4096,
                    producer='attention_residual', consumer='post_norm')
            if previous is not None and selected['name'] == 'final_triplet':
                region = previous.output; consumer = driver.a if stage == 'down' else driver.b
                need(consumer is region and consumer.storage is physical[region.base][1] and region.published and
                     region.written == region.acknowledged == set(range(0, region.extent, 64)), 'direct suffix storage')
                handoffs.append(dict(method='DIRECT_GENUINE_ACCEPTED_TYPED_REGION_NO_COPY_OR_REPLACEMENT',
                    producer=completed[-1], consumer=stage, source_sha256=digest(region.raw()), source_bytes=region.extent,
                    same_memory=previous.memory is driver.memory, same_region=consumer is previous.output,
                    same_storage=consumer.storage is previous.output.storage, written_beats=len(region.written),
                    acknowledged_beats=len(region.acknowledged)))
            save(directory / 'STAGE_START.json', dict(common, stage=stage, plan_sha256=plan_sha, real_owner_terminal=False))
            aborting = False; ticks = 0; next_progress = 0
            while driver.response is None:
                now = time.monotonic(); aborting |= now >= deadline
                need(now < identity['work_stop_monotonic'], 'bounded abort drain')
                check_bindings(driver); driver.tick(abort=aborting); ticks += 1
                if now >= next_progress:
                    save(actual / 'progress.json', dict(common, stage=stage, owner_state=driver.owner.state, ticks=ticks,
                        commands=[{'role': value} for value in completed], roots={'generation': 0},
                        accepted_output_bytes=driver.counts.get('ack_bytes', driver.counts.get('write_bytes', 0))))
                    next_progress = now + 1
            check_bindings(driver); report = driver.report(); expected_bytes = selected['references'][stage]['bytes']
            if stage in DENSE_STAGES:
                need(memory.pending is None and driver.pending_read is None and driver.pending_ack is None and
                     not driver.results and matrix.owner is None and not matrix.reset_required, 'Matrix obligations drained')
                response = list(driver.response); good = response[1] is None and response[2] == expected_bytes
                need(report['executed_fmas'] == (268435456 if stage == 'o' else 469762048) and
                     report['counts']['steps'] == (65536 if stage == 'o' else 114688), 'Dense operation counts')
                if stage == 'down':
                    need(driver.pending_seed_ack is None and driver.active_seed is None and
                         driver.prefix is memory.regions[selected['addresses']['prefix']] and
                         report['prefix_bytes'] == report['prefix_extent'] == 524288 and
                         not report['prefix_published'], 'seeded Down prefix/drain')
            else:
                need(memory.pending is None and driver.pending is None and scalar.client is None, 'Scalar obligations drained')
                response = asdict(driver.response); good = response['status'] is None and response['write_bytes'] == expected_bytes
            need(not aborting and good and driver.output.published, 'genuine successful stage terminal required')
            output = driver.output.raw(); coverage = set(range(0, expected_bytes, 64))
            need(len(output) == expected_bytes and driver.output.written == driver.output.acknowledged == coverage, 'full output coverage')
            with (directory / 'output.bf16le').open('xb') as stream:
                stream.write(output); stream.flush(); os.fsync(stream.fileno())
            report.update(common, stage=stage, status='ISOLATED_STAGE_COMPLETE_UNCOMPARED', terminal_count=1,
                response=response, output_bytes=expected_bytes, output_elements=expected_bytes//2,
                elapsed_seconds=time.monotonic()-stage_start, accepted_write_beats=len(coverage), accepted_ack_beats=len(coverage),
                scalar_arithmetic_binding=binding.report(scalar) if binding else None, aborted_for_deadline=False)
            if stage in DENSE_STAGES:
                report.update(matrix=matrix.report(), workspace_metadata=dict(base=driver.owner.workspace.base,
                    extent=driver.owner.workspace.extent, generation=driver.owner.workspace.generation,
                    prefix_bytes=driver.owner.prefix_bytes, memory_region_allocated=stage == 'down'))
            terminal = dict(common, stage=stage, status='STAGE_COMPLETE_UNCOMPARED', real_owner_terminal=True,
                plan_sha256=plan_sha, terminal_count=1, input_sha256=report['input_sha256'], output_sha256=digest(output),
                output_bytes=expected_bytes, response=response, output_published=True)
            save(directory / 'summary.json', report); save(directory / 'STAGE_TERMINAL.json', terminal)
            reports[stage] = report; completed.append(stage); previous = driver
            save(actual / 'summary.json', summary('RUNNING_SUFFIX_DIAGNOSTIC'))
        need(guard is None or guard.report()['complete'], 'exact successful source-identity call counts')
        save(actual / 'summary.json', summary('ISOLATED_SUFFIX_COMPLETE_UNCOMPARED'))
    except BaseException as error:
        save(actual / 'summary.json', dict(summary('ISOLATED_SUFFIX_FAILED'), failure=type(error).__name__ + ': ' + str(error)))
        raise
    print(json.dumps(dict(status='ISOLATED_SUFFIX_COMPLETE_UNCOMPARED', completed_stages=completed)), flush=True)


if __name__ == '__main__':
    main()
