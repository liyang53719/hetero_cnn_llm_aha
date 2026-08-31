#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1;then echo MAIN_ONLY_WORKFLOW_SKIP_NOT_GIT;exit 0;fi
branch=$(git symbolic-ref --quiet --short HEAD||true)
if [[ -z "$branch" ]];then
 if [[ "${ALLOW_DETACHED_HEAD:-0}" != 1 && "${CI:-}" != 1 && "${CI:-}" != true ]];then echo 'MAIN_ONLY_WORKFLOW_FAIL detached HEAD outside CI' >&2;exit 2;fi
elif [[ "$branch" != main ]];then echo "MAIN_ONLY_WORKFLOW_FAIL current branch=$branch expected=main" >&2;exit 2;fi
mapfile -t local_extra < <(git for-each-ref --format='%(refname:short)' refs/heads|grep -v '^main$'||true)
if ((${#local_extra[@]}));then printf 'MAIN_ONLY_WORKFLOW_FAIL extra local branch: %s\n' "${local_extra[@]}" >&2;exit 3;fi
mapfile -t remote_extra < <(git for-each-ref --format='%(refname:short)' refs/remotes/origin|grep -Ev '^origin/(HEAD|main)$'||true)
if ((${#remote_extra[@]}));then printf 'MAIN_ONLY_WORKFLOW_FAIL extra origin branch: %s\n' "${remote_extra[@]}" >&2;exit 4;fi
if git remote get-url origin >/dev/null 2>&1;then
 upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null||true)
 if [[ -n "$branch" && "$upstream" != origin/main ]];then echo "MAIN_ONLY_WORKFLOW_FAIL upstream=${upstream:-none}" >&2;exit 5;fi
fi
echo MAIN_ONLY_WORKFLOW_PASS branch=${branch:-detached_ci} local_extra=0 origin_extra=0
