"""Exact proposed single-process pair envelope; still requires independent GO."""
ARMS = ('postterminal_reference_only',)
PROFILE = 'production_attention_m16_postterminal_reference_r1'
ACTION = 'single_m16_postterminal_reference_revalidation_r1'
LIMITS = dict(cpu_seconds=180, wall_seconds=240, cpus=1,
    address_space_bytes=2 << 30, tree_rss_bytes=1 << 30,
    child_cpu_seconds=160, child_wall_seconds=200,
    cleanup_cpu_reserve=10, cleanup_wall_reserve=30, fresh_processes=1,
    parent_cpu_work=15, parent_cpu_abort_hard=20,
    file_bytes=48 << 20, output_bytes=128 << 20,
    trace_pair_bytes=96 << 20, artifact_bytes=8 << 20, audit_bytes=16 << 20,
    log_bytes=4 << 20, worker_metadata_bytes=2 << 20, parent_metadata_bytes=2 << 20)
EXECUTABLES = ('admission.py','artifacts.py','reference_capture.py','primitives.py',
    'module_inventory.py','runtime_closure.py','launch.py','policy.py','durable.py','boundary.py','worker.py')
