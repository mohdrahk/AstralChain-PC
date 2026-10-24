"""Run with the Windows Python under Wine after linux/build.py: rewrites build/game/build-fingerprint.txt with
Windows paths, so setup_game (launcher, shader preparation) sees the Linux build as current."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astral_chain import setup_game

setup_game.FINGERPRINT.write_text(setup_game.fingerprint() + '\n', encoding='ascii')
print('current' if setup_game.build_is_current() else 'STALE')
