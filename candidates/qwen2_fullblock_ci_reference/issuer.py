"""Expand an externally pinned source-policy certificate; never create approval."""
from __future__ import annotations
import argparse
import importlib.util
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
import recipe as R
ISSUER='root-source-policy-issuer'
APPROVAL_BASIS='external_static_source_policy_certificate'
CERTIFICATE_ENV='QWEN2_BOOTSTRAP_CERTIFICATE_SHA256'
CLOSURE_ENV='QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256'
RUN_ID='ci01'


def digest(value):
    R.need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None and value!='0'*64,
           'explicit non-placeholder external SHA256 required')
    return value


def external_pins(certificate_sha256=None,source_closure_sha256=None):
    cert=digest(os.getenv(CERTIFICATE_ENV));closure=digest(os.getenv(CLOSURE_ENV))
    if certificate_sha256 is not None:
        R.need(digest(certificate_sha256)==cert,'certificate argument differs from external launch pin')
    if source_closure_sha256 is not None:
        R.need(digest(source_closure_sha256)==closure,'closure argument differs from external launch pin')
    return cert,closure


def source_closure_digest():
    path=R.safe_path(R.ROOT,'candidates/qwen2_fullblock_ci_execution/closure.py')
    name='_ci_bootstrap_source_closure'
    spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)])
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module.digest(R.ROOT)

def budgets():
    pins=R.O.load_pins(R.ROOT)
    return dict(capture_limits=pins['capture_limits'],disk_budget=pins['budget'],
                outer_watchdog_seconds=122,cleanup_grace_seconds=2)


def validate_certificate(path,certificate_sha256=None,source_closure_sha256=None):
    """Both external launch pins are mandatory; computing a file hash is not approval."""
    cert_sha,closure_sha=external_pins(certificate_sha256,source_closure_sha256)
    R.need(source_closure_digest()==closure_sha,'actual source closure differs from external launch pin')
    target=R.safe_path(R.ROOT,path)
    R.need(target.is_relative_to(R.ROOT/R.WORK) and target.is_file() and target.stat().st_size<=262144,
           'bounded external certificate in CI work namespace required')
    spec=dict(path=str(target.relative_to(R.ROOT)),**R.identity(target))
    R.need(spec['sha256']==cert_sha,'external certificate byte identity mismatch')
    cert=R.parse(R.checked(R.ROOT,spec['path'],spec))
    expected=dict(schema=1,status='APPROVED_SOURCE_POLICY_FOR_SINGLE_BOOTSTRAP',
        source_manifest=R.source_manifest(),source_closure_sha256=closure_sha,
        policy_sha256=R.sha(R.encoded(R.bootstrap_policy())),run_id=RUN_ID,mode='bootstrap',
        output_scope='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',maximum_invocations=1,
        no_retry=True,exclusive_numeric_slot=True,numeric_executed=False,
        observed_bindings_independently_reviewed=False,historical_receipts_revalidated=False,
        frozen_mode_available=False,numerical_acceptance_allowed=False,budgets=budgets())
    R.exact_keys(cert,set(expected)|{'reviewer','tool_identity'},'external static certificate')
    R.fields(cert,expected,'external static source-policy certificate')
    R.need(type(cert['reviewer']) is str and cert['reviewer'].strip() and cert['reviewer']!=ISSUER,
           'actual independent certificate reviewer required')
    R.fields(cert['tool_identity'],dict(implementation='cpython',python_major_minor=[3,12],
        source_manifest=expected['source_manifest']),'actual review tool/source identity')
    return cert,spec


def expand(cert,spec,pins):
    """Generated document discloses its issuer and keeps observations unreviewed."""
    source=R.source_manifest()
    review=dict(status='APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP',source_manifest=source,mode='bootstrap',
        numeric_executed=False,reviewer=cert['reviewer'],tool_identity=cert['tool_identity'],
        generated_by=ISSUER,approval_basis=APPROVAL_BASIS,external_certificate=spec,
        ci_binding_policy=R.bootstrap_policy(),historical_receipts_revalidated=False,
        observed_bindings_independently_reviewed=False,
        observed_binding=dict(path=R.BINDING,**R.identity(R.ROOT/R.BINDING)),
        observed_effective_pins_sha256=R.sha(R.encoded(pins)))
    return review


def validate_expansion(review,pins):
    R.need(type(review) is dict and 'external_certificate' in review,'external certificate reference required')
    spec=review['external_certificate']
    R.exact_keys(spec,('path','bytes','sha256'),'expanded certificate identity')
    cert,actual=validate_certificate(spec['path'])
    R.need(R.same(spec,actual),'expanded certificate identity drift')
    expected=expand(cert,actual,pins)
    R.need(R.same(review,expected),'expanded source-policy review drift')
    return cert


def issue(path,certificate_sha256,source_closure_sha256,run_id):
    R.need(R.ROOT==R.CI_ROOT,'issuer requires exact CI root')
    R.need(run_id==RUN_ID,'certificate permits only ci01 bootstrap')
    R.source_manifest()
    cert,spec=validate_certificate(path,certificate_sha256,source_closure_sha256)
    pins=R.load_pins()
    R.source_check(R.ROOT,pins)
    directory=R.safe_path(R.ROOT,R.WORK+'/'+run_id)
    review_path=directory/'SOURCE_REVIEW.json';go_path=directory/'GO.json'
    R.need(not directory.exists(),'fresh one-use issuer directory required; no retries')
    review=expand(cert,spec,pins)
    review_raw=R.encoded(review)
    review_spec=dict(path=str(review_path.relative_to(R.ROOT)),bytes=len(review_raw),sha256=R.sha(review_raw))
    go=dict(schema=1,action='single-bootstrap',run_id=run_id,source_manifest=R.source_manifest(),
        source_review=review_spec,issued_by=ISSUER,maximum_invocations=1,no_retry=True,exclusive_numeric_slot=True)
    # Recheck certificate and observed bindings immediately before publishing GO.
    validate_expansion(review,pins)
    R.need(R.same(pins,R.load_pins()),'observed binding drift during issuance')
    directory.mkdir(parents=True,exist_ok=False)
    with review_path.open('xb') as stream:stream.write(review_raw)
    with go_path.open('xb') as stream:stream.write(R.encoded(go))
    return dict(status='EXTERNAL_SOURCE_POLICY_EXPANDED_FOR_SINGLE_BOOTSTRAP',
        generated_by=ISSUER,approval_basis=APPROVAL_BASIS,
        observed_bindings_independently_reviewed=False,numeric_executed=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--execute',action='store_true');modes.add_argument('--validate-only',action='store_true')
    parser.add_argument('--certificate')
    parser.add_argument('--certificate-sha256');parser.add_argument('--source-closure-sha256');parser.add_argument('--run-id')
    x=parser.parse_args(argv)
    if not (x.execute or x.validate_only):
        R.need(not any((x.certificate,x.certificate_sha256,x.source_closure_sha256,x.run_id)),'issuer execution requires explicit flags')
        result=dict(status='NOT_EXECUTED',approval_generated=False,numeric_executed=False)
    else:
        R.need(all((x.certificate,x.certificate_sha256,x.source_closure_sha256,x.run_id)),
               'external certificate and both reviewed launch digests required')
        R.need(R.ROOT==R.CI_ROOT,'certificate admission requires exact CI root')
        R.need(x.run_id==RUN_ID,'certificate permits only ci01 bootstrap')
        if x.validate_only:
            validate_certificate(x.certificate,x.certificate_sha256,x.source_closure_sha256)
            result=dict(status='EXTERNAL_STATIC_SOURCE_POLICY_VALIDATED_ONLY',
                approval_generated=False,numeric_executed=False,observed_bindings_read=False)
        else:
            result=issue(x.certificate,x.certificate_sha256,x.source_closure_sha256,x.run_id)
    print(R.encoded(result).decode(),end='')
    return 0
if __name__=='__main__':raise SystemExit(main())
