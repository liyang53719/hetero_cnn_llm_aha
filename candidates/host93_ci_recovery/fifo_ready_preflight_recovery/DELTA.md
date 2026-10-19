# Exact bounded delta

- FIFO source: original 4411 / 68de… remains immutable; validated intermediate 4536 / d548…; new derived 4662 / cf5607bf61d0e1ca95d523689ba5170fe937dcfb2f94c001661b4a897bf9e5f6. The new change moves only ready_o's original flush-dependent assignments. Selected319 sum changes from 3072325 to 3072451. Original-base increase is 251 bytes.
- Miter: only derived combinational region changes; new miter 5992 / f243a444637c373cacac66a78cffafaf882b2526ae0108bd396b6e9e4be1ee54. The existing 11336-byte cases file and original reference remain identical.
- Configuration: same cluster selector and warning policy. Exact existing WIDTHEXPAND locations 81→98 and 100→114; no additional waiver.
- Coordinator: generation-diagnostic gets three FIFO phases before the existing32, plus a strictly bound FIFO observation and finite adapter parent labels. Summary schema advances to v6; historical evidence is not reinterpreted. All other mode sequences and shared deadline are unchanged.
- Root-header reads: fixed code/observed-size, unique 4→16 MiB retry condition, correlated schema. No change to root-header or make-graph parser function bodies, log cap, report cap or generation resources.
- Workflow: publisher-provided comment-only successor on the existing Host workflow. Original micro and build-only workflows are untouched.

Actual failure 39220292509 was independently accepted only as failure evidence (review manifest eb09e9bd53bba6456b898b693d6f753b23fd2a1599d6668e13c6335a252457b2). The complete finite source cone review manifest is c7cdea753e07567524061fea5cea866ffb939b6634820a1d6e8d0338fcc66580. Neither grants new native success or whole-design equivalence.

Whole-source review: GO (review_fifo_ready_whole_source_20261019T0847; manifest b8980bdc7114e4848d11092757aac00d04b5d57641cc55b8832e3578e3a42e69; summary b6a1b784b5301dc410478ecc07077e2c3432452047f0b4f451873d096571d61e). New actual: NOT_EXECUTED.
