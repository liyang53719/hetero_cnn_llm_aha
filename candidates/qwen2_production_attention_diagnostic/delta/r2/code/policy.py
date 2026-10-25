"""Exact proposed single-process pair envelope; still requires independent GO."""
ARMS = ('original', 'selective_identity_r1')
PROFILE = 'production_attention_m16_public3_stream_pair_r2'
ACTION = 'single_m16_public3_production_stream_observer_pair_r2'
LIMITS = dict(cpu_seconds=180, wall_seconds=240, cpus=1,
    address_space_bytes=2 << 30, tree_rss_bytes=1 << 30,
    child_cpu_seconds=160, child_wall_seconds=200,
    cleanup_cpu_reserve=10, cleanup_wall_reserve=30, fresh_processes=1,
    parent_cpu_work=15, parent_cpu_abort_hard=20,
    file_bytes=48 << 20, output_bytes=128 << 20,
    trace_pair_bytes=96 << 20, artifact_bytes=8 << 20, audit_bytes=16 << 20,
    log_bytes=4 << 20, worker_metadata_bytes=2 << 20, parent_metadata_bytes=2 << 20)
EXECUTABLES = ('admission.py', 'artifacts.py', 'binding.py', 'component.py',
    'launch.py', 'module_inventory.py', 'policy.py', 'primitives.py',
    'reference_capture.py', 'runtime_closure.py', 'runtime_observer.py',
    'selective_binding.py', 'stage_clock.py', 'support.py', 'worker.py')
