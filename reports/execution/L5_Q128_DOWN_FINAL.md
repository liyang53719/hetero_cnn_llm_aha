# L5 q128 down and final residual batches0-7

Status: PASS; this completes q128 numerical payload.

Eight restartable16-token batches use8-thread k-ordered fmaf goldens and one
unchanged four-thread RTL binary. Every8960x1536 down phase measures430,080
steps and every final residual executes1,536 chunks.

Aggregated down steps are3,440,640 and cycles13,774,848:13,762,560 Matrix plus
12,288 residual. Concatenated down/final SHA256 values are `8efd5406...` and
`39bb6930...`. Build allocation was about1,231 MB; each simulation121 MB. No
OOM occurred.
