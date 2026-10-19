"""Fetch one fixed project Actions artifact; never extract or execute it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com/repos/liyang53719/hetero_cnn_llm_aha/actions/artifacts/12099239717/zip'
SIZE = 9926876
SHA = 'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def signed_target(value):
    p = urllib.parse.urlsplit(value)
    host = p.hostname or ''
    if (p.scheme != 'https' or p.username is not None or p.password is not None
            or p.fragment or p.port not in (None, 443)
            or not any(host.endswith(s) for s in
                       ('.blob.core.windows.net', '.actions.githubusercontent.com', '.githubusercontent.com'))):
        raise ValueError('artifact redirect destination rejected')
    return value


def copy_archive(response, sink, stop):
    if response.status != 200:
        raise ValueError('artifact body status rejected')
    length = response.headers.get('Content-Length')
    if length is not None and length != str(SIZE):
        raise ValueError('artifact advertised length rejected')
    count = 0
    digest = hashlib.sha256()
    while True:
        raw = response.read(min(65536, SIZE + 1 - count))
        count += len(raw)
        if count > SIZE or time.monotonic() >= stop:
            raise ValueError('artifact byte or time bound')
        if not raw:
            break
        digest.update(raw)
        sink.write(raw)
    if count != SIZE or digest.hexdigest() != SHA:
        raise ValueError('artifact fixed identity rejected')
    return count


def expired(signum, frame):
    raise TimeoutError('fixed artifact 180 second deadline')


def fetch(out):
    if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set()):
        raise ValueError('blocked SIGALRM rejected')
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError('occupied timer rejected')
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('only the approved GitHub job may fetch')
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('job scoped Actions token unavailable')
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise ValueError('fresh archive required')
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + '.part')
    start = time.monotonic()
    stop = start + 180
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        opener = urllib.request.build_opener(NoRedirect())
        request = urllib.request.Request(API, headers={
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'hetero-fixed-idma-recovery'})
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as response:
            if response.code != 302:
                response.close()
                raise ValueError('artifact API rejected') from None
            try:
                location = signed_target(response.headers.get('Location', ''))
            finally:
                response.close()
        else:
            response.close()
            raise ValueError('artifact API did not give expected redirect')
        # The ephemeral token is sent only to the exact GitHub API request above.
        # A fresh unauthenticated request consumes its signed, allowlisted URL.
        body_request = urllib.request.Request(location, headers={'User-Agent': 'hetero-fixed-idma-recovery'})
        with opener.open(body_request, timeout=30) as body:
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as sink:
                count = copy_archive(body, sink, stop)
                sink.flush()
                os.fsync(sink.fileno())
        if time.monotonic() >= stop:
            raise TimeoutError('artifact prepublication deadline')
        os.link(partial, out, follow_symlinks=False)
        partial.unlink()
        if time.monotonic() >= stop:
            raise TimeoutError('artifact final deadline')
        return {'artifact_id': 12099239717, 'bytes': count, 'sha256': SHA,
                'elapsed_seconds': time.monotonic() - start, 'extracted': False}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        result = fetch(args.out)
    except BaseException as error:
        # Do not print request URLs, headers, proxy settings, tokens or traceback.
        print(json.dumps({'stage': 'fixed_idma_download', 'status': 'FAILED',
                          'error_type': type(error).__name__}), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
