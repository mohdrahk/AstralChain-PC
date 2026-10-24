#!/bin/bash
# Update on Linux: pull the developer's main and upscaling branches into the local branch, rebuild trace.exe
# with linux/build.py, rewrite the build fingerprint and prepare shaders under Proton, and refresh the
# addresses from run-env.txt in the launch wrapper. RomFS mods in game/romfs.bin stay applied (the build reads
# the image as it is).
#
#   linux/update.sh            update if the developer pushed something
#   linux/update.sh --force    rebuild even if nothing is new
#
# Rolling back: the previous commit is printed at the start; `git reset --hard <it>` and run with --force.
set -euo pipefail

PROJECT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PROTON=${PROTON:-"$HOME/.local/share/Steam/compatibilitytools.d/Proton-CachyOS Latest/proton"}
PREFIX=${PREFIX:-"$HOME/.local/share/Steam/steamapps/compatdata/2693640791"}  # its dosdevices/g: is the game folder
WRAPPER=${WRAPPER:-"$HOME/astral-fx"}  # exports the AC_* variables, used by the Steam shortcut
BRANCHES=(origin/main origin/upscaling)

cd "$PROJECT"
step() { printf '\n== %s\n' "$*"; }
die() { printf 'Stopped: %s\n' "$*" >&2; exit 1; }
wine_run() {  # cmd.exe line, run from G:\ ; output goes to the log file named as the first argument
    local log=$1; shift
    STEAM_COMPAT_DATA_PATH=$PREFIX STEAM_COMPAT_CLIENT_INSTALL_PATH=$HOME/.local/share/Steam \
        "$PROTON" run cmd.exe /c "cd /d G:\\ && $* > G:\\$log 2>&1" >/dev/null 2>&1 || true
    tr '\r' '\n' < "$log" | grep -vE '^\s*$|(Preparing shaders|Compiling for your GPU): [0-9]+/' || true
    rm -f "$log"
}

pgrep -x trace.exe >/dev/null && die 'the game is running; close it first.'
[ -x "$PROTON" ] || die "Proton not found: $PROTON"
[ -d "$PREFIX/pfx/dosdevices/g:" ] || die "the prefix has no G: drive: $PREFIX"
[ -x .venv-linux/bin/python ] || die 'no .venv-linux (see linux/README.md).'
[ -z "$(git status --porcelain --untracked-files=no)" ] || die 'uncommitted changes in tracked files (git status).'

step 'Fetching'
git fetch -q origin
before=$(git rev-parse HEAD)
echo "Current commit: $before ($(git branch --show-current))"
new=0
for b in "${BRANCHES[@]}"; do
    log=$(git log --oneline "HEAD..$b")
    if [ -n "$log" ]; then new=1; printf '%s:\n%s\n' "$b" "$log"; fi
done
if [ $new = 0 ] && [ "${1:-}" != --force ]; then echo 'Already up to date.'; exit 0; fi

if [ $new = 1 ]; then
    step 'Merging'
    for b in "${BRANCHES[@]}"; do
        git merge-base --is-ancestor "$b" HEAD && continue
        if ! git merge -q --no-edit "$b"; then
            conflicts=$(git diff --name-only --diff-filter=U)
            if [ "$conflicts" = README.md ]; then
                git checkout --ours README.md && git add README.md && git commit -q --no-edit
                echo "$b: README.md conflict, kept the local README"
            else
                git merge --abort
                die "merging $b conflicts in: $conflicts"
            fi
        fi
    done
    git log --oneline -1
    if ! git diff --quiet "$before" HEAD -- requirements.txt; then
        step 'requirements.txt changed'
        .venv-linux/bin/pip install -q -r requirements.txt
        echo 'Updated .venv-linux. The Windows .venv may need the same (run setup.cmd on Windows, or pip under Wine).'
    fi
fi

step 'Building (Linux)'
[ "${1:-}" = --force ] && rm -f build/game/build-fingerprint.txt
.venv-linux/bin/python linux/build.py 2>&1 | grep -E 'Build cache|Built|rror|Traceback' || true
[ -f build/game/round-00/trace.exe ] || die 'the build failed (run .venv-linux/bin/python linux/build.py to see why).'

step 'Fingerprint (Windows Python)'
result=$(wine_run fingerprint.log 'G:\.venv\Scripts\python.exe G:\linux\write_fingerprint.py')
echo "$result"
[ "$result" = current ] || die 'the Windows side still sees the build as stale.'

step 'Launch wrapper addresses'
while IFS='=' read -r key value; do
    value=${value%$'\r'}
    [ -n "$key" ] || continue
    current=$(sed -n "s/^export $key='\?\([^']*\)'\?$/\1/p" "$WRAPPER")
    if [ "$current" = "$value" ]; then
        echo "$key unchanged"
    elif [ -n "$current" ]; then
        cp -n "$WRAPPER" "$WRAPPER.bak-$(date +%Y%m%d)" || true
        sed -i "s|^export $key=.*|export $key='$value'|" "$WRAPPER"
        echo "$key updated"
    else
        die "$key is not in $WRAPPER"
    fi
done < build/game/run-env.txt

step 'Shaders and GPU warm-up'
(
    eval "$(grep '^export AC_' "$WRAPPER")"
    wine_run shaders.log 'G:\.venv\Scripts\python.exe -m astral_chain.setup_game --rebuild-if-stale'
)

step 'Done'
echo "Updated from $before to $(git rev-parse HEAD)."
