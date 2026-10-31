"""Production baseline gate; accepts only exact reviewed observation evidence; never numeric qualification."""
import hashlib,json,pathlib
ACCEPTED_PROOF_SHA256='f88769ed00ab2dd052752e6ade9cf67f37f7c6f9d4ede64723e5441ca609835c'
ACCEPTED_REVIEW_SHA256='598ff33f10f55ffbf78c589cf9d8ad37e3862bdd52aec9206477c4b04c7b1b7a'
BASELINE_SHA256='222e9985fe5a2c58c56d09cf670b5d667dfe8515fcfc9523f6fd2e24f5c48166'
ACCEPTED_SUMMARY_SHA256='dfacbbe2c6bfdccefca47cf53a61eb3a1b2eac11fb8947850b2d5eee5ed5a677'
def require_accepted_baseline(materialization):
 p=pathlib.Path(materialization)/'OBSERVER_BASELINE_ACCEPTANCE.json'
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=BASELINE_SHA256:raise ValueError('observer baseline source pin')
 d=json.loads(p.read_text())
 if ACCEPTED_PROOF_SHA256 is None or ACCEPTED_REVIEW_SHA256 is None or d['ready'] is not True:raise ValueError('OBSERVER_BASELINE_NOT_READY_ACTUAL_PROOF_AND_REVIEW_REQUIRED')
 if d['actual_sv_only_proof_sha256']!=ACCEPTED_PROOF_SHA256 or d['independent_sv_only_review_sha256']!=ACCEPTED_REVIEW_SHA256:raise ValueError('observer proof review pin')
 for name,expected in (('sv-only-proof.json',ACCEPTED_PROOF_SHA256),('INDEPENDENT_AUDIT.json',ACCEPTED_REVIEW_SHA256),('sv-only-summary.json',ACCEPTED_SUMMARY_SHA256)):
  evidence=pathlib.Path(materialization).parent/'observer_sv_only_20261030/evidence/run41159843264'/name
  if any(x.is_symlink()for x in (evidence,*evidence.parents))or not evidence.is_file()or hashlib.sha256(evidence.read_bytes()).hexdigest()!=expected:raise ValueError('observer actual evidence source pin')
 if d['actual_sv_only_summary_sha256']!=ACCEPTED_SUMMARY_SHA256 or d['numerical_pass']is not False or d['final_rtl_pass']is not False:raise ValueError('observer evidence scope')
 return d
