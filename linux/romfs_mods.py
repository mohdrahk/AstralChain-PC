"""Layer loose RomFS mod files onto game/romfs.bin without copying it (like an emulator's mods folder).

  romfs_mods.py apply <romfs.bin> <mod RomFS folder>   add/replace the folder's files
  romfs_mods.py revert <romfs.bin>                     back to the original image
  romfs_mods.py check <romfs.bin> <mod RomFS folder>   look the files up and compare

apply never overwrites existing bytes except the 80-byte header: the files' data and new copies of the four
metadata tables are appended, and the header points at the new tables. The original size and header are kept in
<romfs.bin>.mods.json, so revert truncates and restores the header. A second apply reverts first.
The game build bakes in the image's size and header, so rebuild after apply or revert.
"""
import json
import struct
import sys
from pathlib import Path

ALIGN = 16


def name_hash(parent, name):
    h = parent ^ 123456789
    for c in name:
        h = ((h >> 5) | (h << 27)) & 0xFFFFFFFF
        h ^= c
    return h


class Image:
    def __init__(self, f):
        f.seek(0)
        self.header = f.read(80)
        h = struct.unpack('<10Q', self.header)
        if h[0] != 80:
            raise SystemExit('not a RomFS image')
        self.data_offset = h[9]
        self.tables = []
        for i in (1, 3, 5, 7):
            f.seek(h[i])
            self.tables.append(bytearray(f.read(h[i+1])))
        self.dir_hash, self.dir_meta, self.file_hash, self.file_meta = self.tables

    def bucket(self, table, parent, name):
        return 4 * (name_hash(parent, name) % (len(table) // 4))

    def find_dir(self, parent, name):
        o = struct.unpack_from('<I', self.dir_hash, self.bucket(self.dir_hash, parent, name))[0]
        while o != 0xFFFFFFFF:
            p, _, _, _, nxt, n = struct.unpack_from('<6I', self.dir_meta, o)
            if p == parent and self.dir_meta[o+24:o+24+n] == name:
                return o
            o = nxt
        return None

    def find_file(self, parent, name):
        o = struct.unpack_from('<I', self.file_hash, self.bucket(self.file_hash, parent, name))[0]
        while o != 0xFFFFFFFF:
            p, _, _, _, nxt, n = struct.unpack_from('<IIQQII', self.file_meta, o)
            if p == parent and self.file_meta[o+32:o+32+n] == name:
                return o
            o = nxt
        return None

    def dir_of(self, parts):
        o = 0
        for part in parts:
            o = self.find_dir(o, part.encode())
            if o is None:
                raise SystemExit(f'folder {"/".join(parts)} is not in the image (only new files in existing folders)')
        return o

    def add_file(self, parent, name, offset, size):
        o = len(self.file_meta)
        b = self.bucket(self.file_hash, parent, name)
        first_file = struct.unpack_from('<I', self.dir_meta, parent+12)[0]
        head = struct.unpack_from('<I', self.file_hash, b)[0]
        entry = struct.pack('<IIQQII', parent, first_file, offset, size, head, len(name)) + name
        self.file_meta += entry + b'\0' * (-len(entry) % 4)
        struct.pack_into('<I', self.dir_meta, parent+12, o)
        struct.pack_into('<I', self.file_hash, b, o)


def mod_files(folder):
    folder = Path(folder)
    return sorted((p.relative_to(folder).parts, p) for p in folder.rglob('*') if p.is_file())


def undo_path(image):
    return Path(str(image) + '.mods.json')


def revert(image):
    undo = undo_path(image)
    if not undo.is_file():
        print('no mods applied')
        return
    saved = json.loads(undo.read_text())
    with open(image, 'r+b') as f:
        f.truncate(saved['size'])
        f.seek(0)
        f.write(bytes.fromhex(saved['header']))
    undo.unlink()
    print('reverted to the original image:', saved['size'], 'bytes')


def apply(image, folder):
    revert(image)
    with open(image, 'r+b') as f:
        img = Image(f)
        f.seek(0, 2)
        size = f.tell()
        undo_path(image).write_text(json.dumps({'size': size, 'header': img.header.hex(), 'mod': str(folder)}))
        end = size
        for parts, path in mod_files(folder):
            data = path.read_bytes()
            end += -end % ALIGN
            f.seek(end)
            f.write(data)
            parent = img.dir_of(parts[:-1])
            name = parts[-1].encode()
            o = img.find_file(parent, name)
            if o is None:
                img.add_file(parent, name, end - img.data_offset, len(data))
            else:
                struct.pack_into('<QQ', img.file_meta, o+8, end - img.data_offset, len(data))
            print(('replaced ' if o is not None else 'added ') + '/'.join(parts), len(data))
            end += len(data)
        fields = [80]
        for table in img.tables:
            end += -end % ALIGN
            f.seek(end)
            f.write(table)
            fields += [end, len(table)]
            end += len(table)
        fields.append(img.data_offset)
        f.truncate(end)
        f.seek(0)
        f.write(struct.pack('<10Q', *fields))
    check(image, folder)


def check(image, folder):
    with open(image, 'rb') as f:
        img = Image(f)
        for parts, path in mod_files(folder):
            o = img.find_file(img.dir_of(parts[:-1]), parts[-1].encode())
            if o is None:
                raise SystemExit('missing after apply: ' + '/'.join(parts))
            offset, size = struct.unpack_from('<QQ', img.file_meta, o+8)
            f.seek(img.data_offset + offset)
            if f.read(size) != path.read_bytes():
                raise SystemExit('content differs: ' + '/'.join(parts))
    print('check ok')


if __name__ == '__main__':
    cmd, image = sys.argv[1], Path(sys.argv[2])
    {'apply': lambda: apply(image, Path(sys.argv[3])), 'revert': lambda: revert(image),
     'check': lambda: check(image, Path(sys.argv[3]))}[cmd]()
