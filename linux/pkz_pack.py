"""Replace files inside a PlatinumGames .pkz archive (pkzl, per-file ZStandard).

  pkz_pack.py <romfs.bin> <path in romfs, e.g. ui/ui.pkz> <folder of replacement files> <output .pkz>

Reads the original archive out of romfs.bin, swaps every entry whose name matches a file in the folder
(compressed with zstd), copies the other entries' compressed data unchanged and writes a new archive.
Astral Chain reads its UI from ui/ui.pkz only (loose ui/*.dat files in the RomFS are ignored), so mods for
those files have to go into the archive.

Layout: header '<4sIQIII' (magic, version, total size, count, entry table offset, name table size), then
count entries '<4Q' (name offset in the name table, size, data offset, compressed size), the name table
(compression name first), and the data, each entry 16-byte aligned.
"""
import struct
import sys
from compression import zstd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import romfs_mods


def read_from_romfs(image, inner):
    parts = inner.split('/')
    with open(image, 'rb') as f:
        img = romfs_mods.Image(f)
        o = img.find_file(img.dir_of(parts[:-1]), parts[-1].encode())
        if o is None:
            raise SystemExit(inner + ' is not in the image')
        offset, size = struct.unpack_from('<QQ', img.file_meta, o+8)
        f.seek(img.data_offset + offset)
        return f.read(size)


def repack(pkz, replacements):
    magic, version, total, count, entries, names_size = struct.unpack_from('<4sIQIII', pkz, 0)
    if magic != b'pkzl' or total != len(pkz):
        raise SystemExit('not a pkzl archive')
    names = entries + 32*count
    data_start = names + names_size
    out = bytearray(pkz[:data_start])
    done = set()
    for i in range(count):
        name_offset, size, offset, packed = struct.unpack_from('<4Q', pkz, entries + 32*i)
        name = pkz[names+name_offset:pkz.index(b'\0', names+name_offset)].decode()
        if name in replacements:
            raw = replacements[name].read_bytes()
            blob = zstd.compress(raw, level=19)
            size = len(raw)
            done.add(name)
            print(f'replaced {name}: {len(raw)} bytes ({len(blob)} packed)')
        else:
            blob = pkz[offset:offset+packed]
        out += b'\0' * (-len(out) % 16)
        struct.pack_into('<4Q', out, entries + 32*i, name_offset, size, len(out), len(blob))
        out += blob
    missing = set(replacements) - done
    if missing:
        raise SystemExit('not in the archive: ' + ', '.join(sorted(missing)))
    struct.pack_into('<Q', out, 8, len(out))
    return bytes(out)


def verify(pkz, replacements):
    _, _, total, count, entries, _ = struct.unpack_from('<4sIQIII', pkz, 0)
    names = entries + 32*count
    assert total == len(pkz)
    for i in range(count):
        name_offset, size, offset, packed = struct.unpack_from('<4Q', pkz, entries + 32*i)
        name = pkz[names+name_offset:pkz.index(b'\0', names+name_offset)].decode()
        raw = zstd.decompress(pkz[offset:offset+packed])
        assert len(raw) == size, name
        if name in replacements:
            assert raw == replacements[name].read_bytes(), name
    print(f'verified {count} entries')


if __name__ == '__main__':
    image, inner, folder, output = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    replacements = {p.name: p for p in folder.iterdir() if p.is_file()}
    new = repack(read_from_romfs(image, inner), replacements)
    verify(new, replacements)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(new)
    print('wrote', output, len(new))
