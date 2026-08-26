# L5 unified prefill RTL identity lock

Status: PASS. Different sequence lengths must not use separately maintained RTL.

QKV payload uses one compiled binary (`363082ed...`) for q128 and q384. The
same binary was run with runtime workload128 and384; q128 batch0 reproduced its
historical Q/K/V hashes exactly.

The former separate q128/q384 count-controller evidence is superseded by one
runtime-configured controller binary (`5972ba4d...`). In a single simulation it
accepts sequence_length128 and384 and produces the exact respective counts;
unsupported256 is rejected. No datapath/controller source is selected or
recompiled by workload length.
