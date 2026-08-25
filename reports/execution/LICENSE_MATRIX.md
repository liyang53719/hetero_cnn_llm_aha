# L1 license matrix

Third-party source remains external to this delivery.

| Repo | Commit | License evidence | Use boundary |
|---|---|---|---|
| chipyard_gemmini | `e602d917dcc495c58cabe906535e411707096c9c` | BSD-3-Clause (work/upstream/chipyard_gemmini/LICENSE) | official baseline and generated-artifact audit |
| aha | `3b171e813bc5e399b22921c8df20fd4e889f1569` | NO_TOP_LEVEL_LICENSE_FILE (top-level license absent; component review required) | official baseline only; preserve each submodule license |
| idma | `2e0b0fe53b6f8823319e2428e2e9abc2db149b7d` | Solderpad-0.51 / Apache-2.0 option (work/upstream/idma/LICENSE) | external transport baseline and wrapper integration |
| pulp_axi | `4da15979747f326bde2f9869c64e587ce599772c` | Solderpad-0.51 / Apache-2.0 option (work/upstream/pulp_axi/LICENSE) | external AXI primitive baseline and wrapper integration |
| common_cells | `db42769334b4589b4b3fc671b34513bdb98be565` | Solderpad-0.51 / Apache-2.0 option (work/upstream/common_cells/LICENSE) | external primitive baseline and wrapper integration |
| imax3_llm | `ecf4b7590734b123d4004d16251979c66f6adcdf` | MIT (work/upstream/imax3_llm/LICENSE) | software kernel/offload audit only; not RTL source |

AHA has no top-level LICENSE file in this pinned umbrella checkout; its individual submodule licenses must be retained before any source redistribution.
