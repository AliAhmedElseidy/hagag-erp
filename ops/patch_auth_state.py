"""Generate atomic writes for the audited Baileys 6.7.24 auth store, retaining its format/locks."""
import argparse
import hashlib
from pathlib import Path

BASE_SHA256 = '39de093873dc675fa453a63636189daa65ec8cf4a5b02eac46001b454f86f8ac'


def patch_auth(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise ValueError('Unreviewed Baileys auth-store version; refusing to patch')
    before = b"                await writeFile(filePath, JSON.stringify(data, BufferJSON.replacer));"
    after = b'''                const temporaryPath = `${filePath}.tmp`;
                const handle = await open(temporaryPath, 'w', 0o600);
                try {
                    await handle.writeFile(JSON.stringify(data, BufferJSON.replacer));
                    await handle.sync();
                } finally {
                    await handle.close();
                }
                await rename(temporaryPath, filePath);'''
    if source.count(before) != 1:
        raise ValueError('Auth-store implementation differs from the reviewed source')
    source = source.replace(b'{ mkdir, readFile, stat, unlink, writeFile }', b'{ mkdir, open, readFile, rename, stat, unlink, writeFile }')
    return source.replace(before, after)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError('Generate a separate candidate, never overwrite a live store module in place')
    args.output.write_bytes(patch_auth(args.source.read_bytes()))
    print('Generated atomic auth writes; existing auth format and per-file locks retained')
