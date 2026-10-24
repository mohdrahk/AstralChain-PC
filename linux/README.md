# Linux (Steam / Proton)

Notes and scripts from running Astral Chain PC on Linux (Bazzite, RX 9060 XT, Proton-CachyOS). The game itself
is the normal Windows build, run through Proton. Setup (extracting the dump) was done once on Windows; after
that, `game/` and the rest of the folder were copied over. Everything here is optional and changes nothing in
the Windows path.

## Running through Proton

The launcher's **Play** needs PowerShell, so a Steam shortcut starts `build\game\round-00\trace.exe` directly:

- **Start in** `build/game`, launch options `<env> %command% 'G:\build\game\round-00\relocations.bin'`, where
  `<env>` is the `run-env.txt` lines plus `AC_NVN_HLE_LINKED=vulkan AC_PARALLEL=1
  AC_GLSLANG='G:\tools\glslang\bin\glslang.exe' AC_DATA_DIR='G:\linux-data'` (what `run_guarded.ps1` sets).
- **A drive letter for the game folder.** The save code rejects a path whose folders Wine reports as reparse
  points, which a `Z:\run\media\...` path is (save open fails, win32 error 13). A `G:` link in the prefix's
  `dosdevices` to the game folder avoids it.
- **`AC_DATA_DIR`** points at a folder with symlinks `romfs.bin -> ../game/romfs.bin` and
  `images -> ../build/native-images`; saves go into its `save` folder. The build bakes in the Windows paths
  of these, so a copied folder needs it.
- **Shaders:** `setup_game --rebuild-if-stale` runs under Wine with the Windows `.venv` (from `G:\`, with the
  variables above set) and prepares shaders and the GPU warm-up as on Windows. Its output only shows when
  redirected inside `cmd` (`> G:\setup.log 2>&1`); the same holds for the game's own output.

## Building on Linux

`zig.exe` fails under Wine (`checking cache failed: manifest_create Unexpected`, also with the cache on `C:`),
so the build uses the Linux release of the same Zig version, which cross-compiles the same Windows target:

```
python3 -m venv .venv-linux && .venv-linux/bin/pip install -r requirements.txt
.venv-linux/bin/python linux/build.py
```

`build.py` downloads Zig 0.17.0 for Linux into `tools/zig-linux` (checked by SHA-256) and calls
`setup_game.build_game` with it. It needs `game/update-exefs` and `game/romfs.bin` from a Windows setup; the
dump is not needed again.

- The NVN build makes its `vulkan-1` import library from `C:\Windows\System32\vulkan-1.dll`.
  `hooks/sitecustomize.py` supplies the export names from `vulkan-1.def` instead, taken from a Windows build
  (Wine's `vulkan-1.dll` lacks 5 of the loader's 265 exports, all display-plane and headless-surface calls).
- `build-fingerprint.txt` hashes paths with the host's separator, so a Linux build looks stale to the Windows
  Python, which would then rebuild. Run `linux\write_fingerprint.py` with the Windows Python under Wine once
  after the build.

A full build (122 units) took about 6 minutes here; with only the runtime changed, about 10 seconds. Checked
by playing: the `upscaling` branch at 2560x1440, with `main` merged in for the depth clamp fix.

## RomFS mods

There is no mods folder, and `game/romfs.bin` is 10 GB. `romfs_mods.py` layers files onto it in place:

```
python3 linux/romfs_mods.py apply  game/romfs.bin <folder laid out like the RomFS>
python3 linux/romfs_mods.py revert game/romfs.bin
```

`apply` appends the files and new copies of the four metadata tables, and rewrites only the 80-byte header
(the original size and header go to `romfs.bin.mods.json`; `revert` truncates and restores them). The game
then finds the files through the normal RomFS lookup. The build bakes in the image's size and header, so
rebuild after `apply` or `revert` (delete `build/game/build-fingerprint.txt` first).

**Astral Chain ignores loose files.** With PlayStation button prompts (GameBanana mod 604666, loose
`ui/ui_core*.dat/.dtt` files) added this way, the `ROMFS read` lines showed the game reading the new tables
but none of the files: its UI loads from `ui/ui.pkz` only. `pkz_pack.py` puts files into a `.pkz` (pkzl:
an entry table, a name table and per-file ZStandard data), and the new archive is applied as above:

```
python3 linux/pkz_pack.py game/romfs.bin ui/ui.pkz <folder with ui_core.dat ...> mods/x/RomFS/ui/ui.pkz
python3 linux/romfs_mods.py apply game/romfs.bin mods/x/RomFS
```

With the archive replaced, the prompts showed in game.
