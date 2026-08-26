# L5 unified prefill RTL identity lock

Status: PASS. Different sequence lengths must not use separately maintained RTL.

QKV payload uses one compiled binary (`363082ed...`) for q128 and q384. The
same binary was run with runtime workload128 and384; q128 batch0 reproduced its
historical Q/K/V hashes exactly.

The former separate count-controller evidence is superseded by one
runtime-configured controller binary (`ccdeab98...`). In a single simulation it
accepts sequence lengths128,384 and1024 and produces their exact counts;
unsupported256 is rejected. q1024 payload proof remains pending, so only the
controller—not all datapaths—is currently proven for all three lengths.
