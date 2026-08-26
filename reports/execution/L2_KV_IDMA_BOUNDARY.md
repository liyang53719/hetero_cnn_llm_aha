# L2 KV/iDMA production boundary

The pinned transport boundary is `idma_backend_rw_axi` at iDMA commit
`2e0b0fe53b6f8823319e2428e2e9abc2db149b7d`. Production parameters are 512-bit
data, 64-bit address, 32-bit length, four AXI IDs/in-flight slots, buffer depth
three, hardware legalizer enabled and zero transfers rejected.

The project KV frontend exposes only a flat request carrying source, destination
and byte length with ready/valid, plus response valid/ready/error. A binding
wrapper maps it to the upstream typed request with AXI/INCR, last=1 and compute
disabled. AXI channels remain the upstream PULP types; the project will not
hand-write AXI behavior.

The existing VCS upstream-equivalent backend test remains PASS. Module and
typedef hashes are frozen in `idma_backend_contract_lock.json`.
