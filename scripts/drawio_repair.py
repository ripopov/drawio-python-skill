"""Shared no-clobber delivery for independently verified diagram repairs."""
import hashlib
import os
from pathlib import Path
import tempfile


def findings_severity(page):
    rank = {'info': 0, 'advisory': 1, 'warning': 2}
    return {(c['type'], *sorted((c['a'], c['b']))): rank[c['severity']] for c in page['collisions']}


def repair_paths(source, output):
    source = Path(source).resolve()
    destination = Path(output).absolute() if output is not None else None
    if destination is not None and (destination.exists() or destination.is_symlink()):
        raise ValueError('Output must be a new file, distinct from the source')
    return source, destination, source.read_bytes()


def publish_repair(source, original, destination, data):
    if source.read_bytes() != original:
        raise RuntimeError('Source changed during repair; no output published')
    if destination is None:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, prefix='.drawio-repair-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        # Atomic no-clobber publish, including a destination created during checking.
        os.link(name, destination)
    finally:
        os.unlink(name)
    return hashlib.sha256(data).hexdigest()
