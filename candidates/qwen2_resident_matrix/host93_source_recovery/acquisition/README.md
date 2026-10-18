# Host93 pinned acquisition candidate

Status: SOURCE ONLY. No real dependency/artifact has been downloaded, extracted,
installed, loaded, compiled, or executed by this candidate's development tests.
Successful cold tests establish code behavior on synthetic bytes only. They are
not evidence of artifact reachability, package validity, Host compilation, RTL,
or any full-block pass.

## Five separate plans

- `plans/jar87.json`: exactly the published production 87-JAR profile. No
  profile106/union, Bench/Spec additions, dependency resolution, or version update.
  This is the historical exact conservative sufficient set for the production
  profile, not a per-JAR proven minimal set. Host93 compilation remains unrun.
- `plans/hardfloat20.json`: 20 fixed-revision Scala files, exact sizes and SHA-256
  pins, totaling 149,157 bytes. Acquiring them does not assemble the Host sources.
- `plans/firtool.json`: the opaque official 1.62.1 Linux x64 JAR. The future
  extraction member/hash/cap is retained as review metadata only.
- `plans/verilator.json`: the opaque official Debian 5.032-1+b2 amd64 package.
  Full package identity and required wrapper/backend/runtime components are
  retained. No package installation or runtime-layout symlink creation occurs.
- `plans/idma.json`: existing artifact 12099239717 from run 39030773068, SHA-256
  `a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce`, exact
  archive size 9,926,876 bytes. This is connector-materialized-only. The candidate
  has no credential logic, artifact API fetch, export rerun, or source fallback.
  Historical unexpired metadata is not current availability or byte verification.

All plans relate to the new Host93 closure: production92 plus one new Host-only
common-namespace emitter. This is not historical95. Plan provenance records the
input audit digest and fixed repository revision, not an environment inventory.
`PLAN_LOCK.json` is a readable index; the script independently locks each plan's
SHA-256 and expected count. Changing a plan requires review and explicit lock
updates. No custom manifest or arbitrary URL can be selected from the CLI.

## Resource and transport policy

Unknown JAR, firtool, and Verilator sizes remain `null`. Proposed ceilings are
64 MiB per unknown artifact, 512 MiB total for jar87, and 64 MiB total for each
tool archive. Known-size groups use exact-size checks and one extra transfer
byte per artifact for detecting trailing data. Caps are finite policy proposals,
not measured sizes or authorization. If a cap is reached without EOF, fail closed;
no verified artifact can be as large as its transfer cap. Reads, including bytes
that trigger rejection, never request more than the remaining group/file budget.

Only fixed HTTPS URLs are used. The stdlib default proxy routing and TLS trust
are preserved. Redirects, transformed bodies, unsafe paths, mismatched hashes or
sizes, partial HTTP responses, and duplicate/ambiguous Content-Length headers
are rejected. There are no alternate hosts, direct-network fallback, retries,
credential reads, environment changes, security changes, or tool execution.
Any platform route failure is a blocker, not permission to change transport.
Socket timeouts and between-operation elapsed checks are included; they are not
a hard whole-process wall-clock watchdog.

Archives remain opaque. Safe extraction/member validation, permissions, runtime
layout, and any source assembly are separate future reviews. Downloaded bytes
must not be executed merely because acquisition verification succeeded.

## Offline review now

From this directory, use only these cold commands during source-only review:

```sh
python -I -S -B acquire.py plan
python -I -S -B tests/test_acquire.py -v
python -I -S -B -O tests/test_acquire.py -v
```

The default invocation is the same offline plan summary. Tests mock the transport,
deny sockets, and create only temporary synthetic files inside `tests/`, cleaned
after each test. They never use a real source archive, binary, or downloaded JAR.
Invoke the test file directly: unittest discovery imports test modules and can
read existing bytecode caches. `-B` prevents cache writes, not cache reads. This
test file instead reads `acquire.py` once, verifies its fixed size and
SHA-256 pin, then executes that same raw source using a small `ModuleType` loader.
Source drift fails before compilation or execution; no project `.pyc` is loaded
by this source loader. A synthetic positive control constructs a valid timestamp
cache with a harmless extra attribute, proves that the ordinary import loader
executes it even under `-B`, and proves that the pinned source loader ignores it.
That cache exists only in a cleaned temporary test directory and is never part
of candidate source identity. These controls pass in normal and `-O` modes.

## Future separately authorized acquisition

Do not run `fetch` under the source-only authorization. Its
`--execute-acquisition` switch is only an accident guard and cannot grant approval.
An authorized invocation selects exactly one group, explicitly identifies the
existing checkout with `--repository`, and selects an absolute, nonexistent output
directory whose parent already exists. Output must be outside both that checkout
and the Host93 source candidate. Checkout identity is not guessed from candidate
parent directories, so moving this candidate does not change the exclusion.
Read-only verification also rejects artifact directories within those protected
roots. It cannot merge into existing directories or overwrite existing files.
CLI forms are:

```text
python -I -S -B acquire.py fetch GROUP --repository ABSOLUTE_CHECKOUT_ROOT --output-root ABSOLUTE_NEW_DIRECTORY --execute-acquisition
python -I -S -B acquire.py fetch idma --repository ABSOLUTE_CHECKOUT_ROOT --output-root ABSOLUTE_NEW_DIRECTORY --execute-acquisition --materialized-idma ABSOLUTE_CONNECTOR_FILE
python -I -S -B acquire.py verify GROUP --repository ABSOLUTE_CHECKOUT_ROOT --output-root ABSOLUTE_EXISTING_DIRECTORY
```

For iDMA, first obtain separate permission for the connector's supported archive
materialization step and recheck the fixed artifact's availability. Pass its
verified local file path; do not invent a signed URL, token, credential transfer,
or alternate download mechanism. The script then verifies exact size and hash
without unpacking. Artifact expiry, missing materialization support, or mismatch
must be reported for review; there is no fallback to a new export.

Only a fully successful group atomically publishes `ACQUISITION.json`, next to acquired bytes
outside the repository, with fresh per-file size/hash/origin identity and explicit
no-extraction/no-installation/no-execution flags. On failure, cleanup of the owned current `.part` is attempted independently.
`FAILED.json` records the original error type, any cleanup errors, received bytes,
and partial verified identities; an unlink failure cannot replace the original
exception or suppress the failure-record attempt. No success receipt is issued. Prior verified members may remain as incomplete acquisition evidence.
Read-only `verify` recomputes the pinned byte identities instead of trusting a
receipt; it does not infer or authorize any build stage.

## v3 finite failure corrections

The three independent synthetic counterexamples are retained with corrected expectations. A successful exclusive `ACQUISITION.json` link is the terminal commit: failure to unlink its owned `.part` yields a returned cleanup warning and best-effort nonterminal `CLEANUP_WARNING.json`, never `FAILED.json`. If warning publication itself fails, its error type is returned without changing acquisition state. Before commit, artifact/receipt cleanup errors and failure-receipt publication errors remain secondary notes; the original acquisition exception is re-raised. Verified artifact identities are recorded immediately after exclusive publication so a later cleanup failure cannot erase evidence of a good cached member. Every byte returned by read is counted before the deadline/length rejection; rejected bytes are not written. This is a bounded correction to failure accounting, not new retry or recovery behavior. Five acquisition plans, transport routing, byte ceilings and source-loader rules remain unchanged.
