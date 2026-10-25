"""One source-reviewed, separately authorized two-process M2 diagnostic only."""
ARMS=('baseline','normalization_helper')
PROFILE='normalization_helper_two_fresh_m2_v1'
ACTION='two_fresh_m2_normalization_helper_diagnostic_v1'
LIMITS=dict(cpu_seconds=45,wall_seconds=60,cpus=1,address_space_bytes=1<<30,tree_rss_bytes=1<<30,
    child_cpu_seconds=18,child_wall_seconds=26,cleanup_cpu_reserve=3,cleanup_wall_reserve=5,
    parent_cpu_work=4,parent_cpu_abort_hard=6,fresh_processes=2,file_bytes=4<<20,output_bytes=32<<20,
    trace_pair_bytes=1<<20,artifact_bytes=8<<20,audit_bytes=16<<20,log_bytes=1<<20,worker_metadata_bytes=2<<20,parent_metadata_bytes=2<<20)
EXECUTABLES=('admission.py','artifacts.py','binding.py','comparison.py','durable.py','harness.py','launch.py',
    'module_inventory.py','policy.py','runtime_closure.py','stage_clock.py','support.py','worker.py')
