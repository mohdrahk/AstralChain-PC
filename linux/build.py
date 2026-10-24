"""Build trace.exe on Linux: the same translation and compile as setup_game's build step, with Linux Zig.

  python3 linux/build.py

Needs a Python 3.14 with requirements.txt installed, game/update-exefs from a Windows setup, and game/romfs.bin.
zig.exe under Wine fails ("checking cache failed: manifest_create Unexpected"), so the Linux build of the
same Zig version cross-compiles the Windows executable. Afterwards, run write_fingerprint.py with the Windows
Python (see README.md): setup_game hashes Windows paths, and would otherwise see this build as stale.
"""
import hashlib
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
ZIG_DIR = PROJECT/'tools'/'zig-linux'
ZIG_URL = 'https://ziglang.org/download/0.17.0/zig-x86_64-linux-0.17.0.tar.xz'
ZIG_SHA256 = '1cbe9df9f27e6b78d14ccbca43b6703a404ef79ef1c463de901d7f088d4e2026'


def fetch_zig():
    if (ZIG_DIR/'zig').is_file():
        return
    print('== Downloading Zig 0.17.0 for Linux')
    archive = PROJECT/'tools'/'zig-linux.tar.xz'
    archive.parent.mkdir(exist_ok=True)
    urllib.request.urlretrieve(ZIG_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIG_SHA256:
        archive.unlink()
        raise SystemExit('Zig download: SHA-256 mismatch')
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            member.name = member.name.partition('/')[2]
            if member.name:
                tar.extract(member, ZIG_DIR, filter='data')
    archive.unlink()


def main():
    fetch_zig()
    # native_trace runs in a child Python: hooks/sitecustomize.py gives its NVN build the Windows Vulkan exports.
    os.environ['PYTHONPATH'] = os.pathsep.join([str(PROJECT/'linux'/'hooks'), str(PROJECT)])
    os.environ['AC_LINUX_BUILD'] = str(PROJECT)
    sys.path.insert(0, str(PROJECT))
    from astral_chain import setup_game
    setup_game.ZIG = ZIG_DIR/'zig'
    setup_game.build_game()
    print('Built', setup_game.GAME_BUILD/'round-00'/'trace.exe')


if __name__ == '__main__':
    main()
