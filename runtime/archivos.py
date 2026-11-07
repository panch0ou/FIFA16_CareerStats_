"""Instalación acotada a un plan de hashes, con diario previo a la primera escritura."""
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

import hashlib


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def target(root, relative):
    path = root / relative
    if not path.is_relative_to(root) or '..' in Path(relative).parts or path.resolve() != path:
        raise ValueError(f'Unexpected path: {path}')
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Redirected path: {item}')
        if item == root:
            break
    return path


def fingerprint(path):
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f'Expected a regular file: {path}')
    return digest(path)


def copy_atomic(source, destination, expected, *, create=False):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copy2(source, temporary)
        if digest(temporary) != expected:
            raise ValueError(f'Copied file has an unexpected hash: {destination}')
        with temporary.open('rb+') as stream:
            os.fsync(stream.fileno())
        if create:
            temporary.rename(destination)  # Windows refuses an existing destination.
        else:
            temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def apply(root, entries, journal):
    if journal.exists():
        raise RuntimeError(f'A recovery journal already exists: {journal}')
    operations = []
    for relative, source, before, after in entries:
        path = target(root, relative)
        if fingerprint(path) != before or fingerprint(source) != after:
            raise RuntimeError(f'The destination or local resource changed: {relative}')
        backup = journal.parent / ('original_' + before) if before else None
        if backup and fingerprint(backup) != before:
            if backup.exists():
                raise RuntimeError(f'Unexpected backup: {backup}')
            copy_atomic(path, backup, before)
        operations.append(dict(relative=relative, before=before, after=after,
                               backup=backup.name if backup else None))
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=journal.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({'root': str(root), 'files': operations}, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(journal)
    finally:
        temporary.unlink(missing_ok=True)
    try:
        for (relative, source, before, after) in entries:
            path = target(root, relative)
            if fingerprint(path) != before:
                raise RuntimeError(f'The destination changed: {relative}')
            copy_atomic(source, path, after, create=before is None)
    except BaseException:
        restore(root, journal, {entry[0] for entry in entries})
        raise


def restore(root, journal, allowed):
    saved = json.loads(journal.read_text(encoding='utf-8'))
    if (saved['root'] != str(root) or len(saved['files']) != len(allowed)
            or {item['relative'] for item in saved['files']} != allowed):
        raise RuntimeError('The recovery journal belongs to another installation')
    pending = []
    for item in saved['files']:
        path = target(root, item['relative'])
        before, after = item['before'], item['after']
        current = fingerprint(path)
        if current == before:
            continue
        if current != after:
            raise RuntimeError(f'Unrecognized or modified file: {path}')
        backup = None
        if before:
            backup = target(journal.parent, 'original_' + before)
            if backup.name != item['backup'] or fingerprint(backup) != before:
                raise RuntimeError(f'Unexpected backup hash: {path}')
        pending.append((path, backup, before, after))
    for path, backup, before, after in reversed(pending):
        if fingerprint(path) != after:
            raise RuntimeError(f'The file changed before recovery: {path}')
        if backup:
            copy_atomic(backup, path, before)
        else:
            path.unlink()
    journal.unlink()
