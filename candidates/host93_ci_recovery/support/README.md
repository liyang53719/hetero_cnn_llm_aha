# Temporary CI supervision SOURCE component

This component has no executable native CLI and is not a complete CI job. It is
new source for the 2026-10-19 CI recovery, not a restoration of a lost local audit.

It reuses the published fixed_core_build support and its exact five WNOWAIT
supervisor functions and four leader observers. Source buffers and function
fragments are fixed by size/SHA before compile; only the existing phase resource,
environment, affinity, cleanup and sampling projections are used. The small new
adapter invokes that original projected bounded function, saves child usage on
both outcomes, preserves the original error, and rejects postflight expiry.

The complete caller must supply its separately reviewed finite phase table,
fixed argument construction, private environment, complete input/output checks
and safe summary schema. No local audit package or old actual identity is read.
A 6600-second shared stop truncates stage windows, retaining cleanup/postflight
reserves. The outer CI job must also enforce its own wall. This source alone is
not permission or a claim that the full job can execute.

Blocked SIGALRM and an occupied real timer are rejected without modifying them.
The leader remains the original owned unreaped-child anchor. CPU usage is the
RUSAGE_CHILDREN difference; ru_maxrss is explicitly the coordinator's cumulative
child high-water observation, not a phase-specific maximum or a whole-tree
sample. Raw native logs and detailed usage belong only to the private work tree.

Cold commands (data/projections/mocks only):

    python3 -I -S -B test_support_cold.py --repo /path/to/checkout
    python3 -I -S -B -O test_support_cold.py --repo /path/to/checkout

Both modes passed 17 tests. They include corrupt raw source before compile,
symlink/hash rejection, shared/phase exhaustion, blocked mask and occupied timer,
original function projection, mocked child success, original exception retention,
and postflight expiry after child zero. No native child or network was used.
