# Sandbox continuation v7.5

Completed without local commercial tools:

- Reproduced the measured 4x4 Attention SFU projection exactly.
- Swept 4/8/16 tile lanes and 4/8/16 merge rows with conservative fanout costs.
- Selected balanced 8x8 as the minimum candidate that clears the preferred 320-t/s stress floor.
- Generated adversarial tile/merge numerical vectors and a source-ready eight-row merge wrapper.
- Derived distinct Qwen3.5 and Flash-Next state/KV/index/activation/MoE resource envelopes from frozen profiles.
- Added explicit guards against using dense-attention service curves for QSA or adding QSA/PLE/four-branch residual to Qwen3.5.

Evidence remains E0/source-ready. Verilator/VCS, CLN22UL, integrated E3, official weights and post-route signoff remain local gates.
