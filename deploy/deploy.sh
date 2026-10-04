#!/bin/bash
# 只能由已持有NB_ROOT/build.lock的调用者运行;手动重跑也要flock
set -euo pipefail
umask 022
if [ -f "$HOME/.nvm/nvm.sh" ]; then . "$HOME/.nvm/nvm.sh"; fi
REPO="${NB_REPO:-/opt/git/nanmu-blog.git}"
ROOT="${NB_ROOT:-/var/www/nanmu-blog}"
RELEASES="$ROOT/releases"
unset GIT_WORK_TREE GIT_INDEX_FILE
export GIT_DIR="$REPO"
SHA=$(git rev-parse refs/heads/main)
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || exit 1
DEST="$RELEASES/$SHA"
WORK=$(mktemp -d)
STAGE=""
cleanup() {
  rm -rf -- "$WORK"
  if [ -n "$STAGE" ]; then rm -rf -- "$STAGE"; fi
}
trap cleanup EXIT
if [ -f "$DEST/.complete" ] && [ "$(cat "$DEST/.complete")" = "$SHA" ]; then
  [ "$(cat "$DEST/dist/release.txt")" = "$SHA" ] || exit 1
else
  if [ -e "$DEST" ]; then
    printf 'incomplete release requires inspection: %s\n' "$DEST" >&2
    exit 1
  fi
  git archive "$SHA" | tar -x -C "$WORK"
  cd "$WORK/site"
  npm ci --prefer-offline --cache /opt/git/nanmu-blog-npm-cache
  npm run verify
  printf '%s\n' "$SHA" > dist/release.txt
  STAGE=$(mktemp -d "$RELEASES/.build.XXXXXX")
  cp -a dist "$STAGE/dist"
  chmod 755 "$STAGE"
  chmod -R a+rX "$STAGE/dist"
  printf '%s\n' "$SHA" > "$STAGE/.complete"
  mv -T "$STAGE" "$DEST"
  STAGE=""
fi
ln -sfn "$DEST" "$ROOT/current.tmp"
mv -T "$ROOT/current.tmp" "$ROOT/current"
printf '%s deployed %s\n' "$(date -Is)" "$SHA"

# 只清理该根下的完整SHA版本,当前版永不删除;共保留当前+最近4个旧版
kept=1
mapfile -t candidates < <(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
for candidate in "${candidates[@]}"; do
  name="${candidate##*/}"
  [[ "$name" =~ ^[0-9a-f]{40}$ ]] || continue
  [ "$candidate" != "$DEST" ] || continue
  [ -f "$candidate/.complete" ] || continue
  if [ "$kept" -lt 5 ]; then kept=$((kept + 1)); continue; fi
  rm -rf -- "$candidate" || printf 'warning: old release cleanup failed: %s\n' "$candidate" >&2
done
