#!/usr/bin/env python3
"""Publish exact completed regression bytes on main without altering the DUT.

Run in the CI checkout that executed the fixed gate. The temporary Git index is
separate from the worktree index. No checkout/reset/clean or force push is used.
The original tested sources must still match the current main branch exactly.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,uuid
from pathlib import Path


def require(ok,message):
    if not ok:raise ValueError(message)


def git(repo,*args,env=None):
    return subprocess.check_output(['git','-C',str(repo),*args],env=env)


def digest(b):return hashlib.sha256(b).hexdigest()


def selected_files(root):
    skip={'obj','classes','testclasses','test_run_dir','verilator-runtime','offline-tools-runtime','__pycache__','negative_artifacts'}
    suffix={'.json','.log','.gz','.f32le','.bin','.h','.sv','.txt','.exit','.sha256','.xml'}
    selected={}
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if any(part in skip for part in rel.parts) or p.is_symlink() or not p.is_file():continue
        if p.suffix not in suffix:continue
        require(p.resolve().is_relative_to(root.resolve()),'artifact escapes root')
        selected[str(rel)]=p.read_bytes()
    require('REGRESSION_RESULT.json' in selected and 'gate.exit' in selected,'missing complete gate')
    return selected


def publish(repo,root,source):
    require(re.fullmatch('[0-9a-f]{40}',source) is not None,'invalid source commit')
    require(git(repo,'rev-parse','HEAD').decode().strip()==source,'not the executed checkout')
    r=json.loads((root/'REGRESSION_RESULT.json').read_text())
    require(r['status']=='PASS_FIXED_HOST_OWNER_REGRESSION' and r['source_commit']==source,'unsealed run')
    profile=r['profile'];require(profile in ('tiny','real-cross'),'profile')
    require((root/'gate.exit').read_text().strip()=='0','failed suite')
    base=root/('base17' if profile=='tiny' else 'real17')
    identities=json.loads((base/'sources.sha256.json').read_text())
    selected=selected_files(root)
    selected['PUBLICATION_SCOPE.json']=(json.dumps({'schema':1,'source_commit':source,'profile':profile,
        'original_bytes_preserved':True,'excluded':'compiled objects, runtime symlinks, unit build products and deliberately mutated negative-test copies; retained in original run/artifact',
        'official_weights':False,'q1024_full_network':False,'dc':False},indent=2)+'\n').encode()
    manifest={p:digest(b) for p,b in selected.items()}
    selected['PUBLISHED_SHA256.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    prefix=f'reports/execution/OWNER_REGRESSION_{source[:12]}_{profile}'
    blobs={p:subprocess.check_output(['git','-C',str(repo),'hash-object','-w','--stdin'],input=b).decode().strip() for p,b in selected.items()}
    for attempt in range(3):
        subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin','main'],check=True)
        parent=git(repo,'rev-parse','origin/main').decode().strip()
        for path,expected in identities.items():
            rel=Path(path);require(not rel.is_absolute() and '..' not in rel.parts,'unsafe source identity')
            require(digest(git(repo,'show',f'{parent}:{path}'))==expected,'main changed a tested source: '+path)
        index=root/f'publication_index_{uuid.uuid4().hex}'
        env=dict(os.environ,GIT_INDEX_FILE=str(index),GIT_AUTHOR_NAME='heteronpu-verified-regression',
                 GIT_AUTHOR_EMAIL='heteronpu-verified-regression@users.noreply.github.com',
                 GIT_COMMITTER_NAME='heteronpu-verified-regression',GIT_COMMITTER_EMAIL='heteronpu-verified-regression@users.noreply.github.com')
        git(repo,'read-tree',parent,env=env)
        for rel,blob in blobs.items():
            path=f'{prefix}/{rel}'
            old=subprocess.run(['git','-C',str(repo),'show',f'{parent}:{path}'],capture_output=True)
            require(old.returncode!=0 or old.stdout==selected[rel],'refuse to overwrite different evidence')
            git(repo,'update-index','--add','--cacheinfo','100644',blob,path,env=env)
            require(git(repo,'show',':'+path,env=env)==selected[rel],'index byte mismatch')
        tree=git(repo,'write-tree',env=env).decode().strip()
        if tree==git(repo,'rev-parse',parent+'^{tree}').decode().strip():return {'commit':parent,'already_present':True,'files':len(blobs),'path':prefix}
        commit=git(repo,'commit-tree',tree,'-p',parent,'-m',f'test: preserve verified {profile} Host owner regression and numerical outputs [skip ci]',env=env).decode().strip()
        pushed=subprocess.run(['git','-C',str(repo),'push','origin',commit+':main'],capture_output=True,text=True)
        print(pushed.stdout,pushed.stderr)
        if pushed.returncode==0:
            subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin','main'],check=True)
            subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',commit,'origin/main'],check=True)
            return {'commit':commit,'files':len(blobs),'path':prefix,'force_push':False,'tested_sources_changed':False}
    raise ValueError('main kept advancing; verified blobs remain preserved, no force push attempted')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--source',required=True);a=p.parse_args()
    try:print(json.dumps(publish(a.repo.resolve(),a.root.resolve(),a.source),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as e:raise SystemExit('REGRESSION_PUBLICATION_REJECTED: '+str(e))
