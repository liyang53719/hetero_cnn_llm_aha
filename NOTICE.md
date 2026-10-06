# Third-party notice

The accelerator implementation contains original clean-room code and scripts. It does not vendor Gemmini, Chipyard, Stanford AHA/Garnet/Lake/Canal/PEak, PULP iDMA/AXI/common_cells, IMAX3-LLM, vLLM, or their generated artifacts.

The local execution plan clones each upstream repository separately. Preserve each upstream license and commit history. Do not copy an upstream source file into `rtl/` or `src/heteronpu/`; integration must use generated macros, package dependencies, wrappers, or clearly isolated patch files.

Official Transformers Python source snapshots under `config/upstream/` are retained only as isolated provenance data, with their original copyright and Apache-2.0 notices intact. The metadata validators never import or execute them. Pinned Qwen model configs, indexes, safetensors headers and public API responses in the same directory contain provenance/geometry only, not checkpoint tensor payloads. Each manifest records its official source URL and revision; see the repository LICENSE for Apache-2.0 terms.
