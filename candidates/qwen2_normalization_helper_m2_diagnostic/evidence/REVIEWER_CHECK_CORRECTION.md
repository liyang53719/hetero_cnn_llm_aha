# Retained reviewer-only check correction

Original SHA256: `0a17fa1d356a9b8c25be6441bd42d2170dc045b9a85b4a02b2c9b0b95fcaee91`.

Initial reviewer check compared the registry object directly with capture fields and failed twice. Inspection of both exact registry sources and all 20 actual rows confirms the intended registry adds precisely three metadata fields: storage=observer_only_not_DDR, provenance=ACTUAL_PASSIVE_ATTENTION_OBSERVATION and field-specific causal/complete coverage. Revised independent check requires exact capture fields plus exactly these three values, without removing any numerical/integrity gate. Original v1 script, output and receipt retained. No production source or actual evidence modified; no DUT or recipe rerun.
