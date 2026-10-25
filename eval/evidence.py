"""Content fingerprints for evidence. Never read credentials or include them in reports."""
import hashlib
import os
import subprocess
import threading
from pathlib import Path

from floorwise.paths import ROOT, KIT, DATA

_lock = threading.Lock()
_cache = {}


def digest(paths, root):
    paths = sorted(p for p in paths if p.is_file())
    signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    with _lock:
        if signature in _cache:
            return _cache[signature]
    h = hashlib.sha256()
    for p in paths:
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b'\0')
        h.update(p.read_bytes())
    value = h.hexdigest()[:20]
    with _lock:
        if len(_cache) > 32:
            _cache.clear()
        _cache[signature] = value
    return value


def revision(root):
    try:
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                       stderr=subprocess.DEVNULL, timeout=3).decode().strip()
    except (OSError, subprocess.SubprocessError):
        return 'unavailable'


def fingerprint():
    source = []
    for folder in ('floorwise', 'server', 'eval', 'tests', 'web/src', 'web/tests'):
        source.extend(p for p in (ROOT / folder).rglob('*') if p.suffix in ('.py', '.ts', '.tsx', '.js', '.cjs', '.css', '.json')
                      and '__pycache__' not in p.parts)
    source.extend(ROOT / p for p in ('pyproject.toml', 'uv.lock', 'web/package.json', 'web/package-lock.json'))
    data = [DATA / 'manifest.csv', KIT / 'CHANGELOG.md']
    for split in ('train', 'dev', 'test'):
        for name in ('building.json', 'questions.jsonl', 'questions_basic.jsonl'):
            data.extend((DATA / split).glob('*/' + name))
    build = [ROOT / 'web/dist/index.html', *(ROOT / 'web/dist/assets').glob('*')]
    from floorwise import llm
    models = {role: llm.model_for(role) for role in ('chat', 'parser', 'judge')}
    return {'version': 1, 'git': revision(ROOT), 'source': digest(source, ROOT),
            'kit_git': revision(KIT), 'dataset': digest(data, KIT),
            'frontend': digest(build, ROOT), 'provider': llm.provider_name(), 'models': models,
            'effort': os.environ.get('FLOORWISE_CHAT_EFFORT', 'low')}


def compatible(recorded, current):
    return bool(recorded and all(recorded.get(k) == current.get(k)
                                for k in ('version', 'source', 'dataset', 'frontend', 'provider', 'models', 'effort')))
