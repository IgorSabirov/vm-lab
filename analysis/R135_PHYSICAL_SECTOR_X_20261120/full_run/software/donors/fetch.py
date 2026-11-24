"""Retrieve R135 inputs from pinned donor releases; verify cache bytes on every use."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def sources():
    items = json.loads((HERE / 'sources.json').read_text())
    planck = json.loads((HERE.parent / 'planck_pr3/release.json').read_text())
    for key in ('archive', 'zero_X_theory'):
        items['planck-' + key] = dict(planck[key], group='planck')
    policy = json.loads((HERE.parent / 'planck_pr3/nuisance.json').read_text())
    repo = policy['repository'].removeprefix('https://github.com/')
    for path, info in policy['source_files'].items():
        url = f"https://raw.githubusercontent.com/{repo}/{policy['commit']}/{path}"
        items['cobaya-' + Path(path).stem] = dict(info, url=url, group='planck_priors')
    return items


def verified(path, item):
    if not path.is_file() or path.stat().st_size != item['bytes']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']


def obtain(cache, item, offline=False):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / item['sha256']
    if verified(target, item):
        return target
    if offline:
        raise ValueError(f"Missing or corrupt cache entry for {item['url']}")
    errors = []
    for url in [item['url'], item.get('mirror')]:
        if not url:
            continue
        try:
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as tmp:
                path = Path(tmp.name)
            try:
                request = Request(url, headers={'User-Agent': 'R135-source-replay/1.0'})
                with urlopen(request, timeout=90) as src, path.open('wb') as dest:
                    size = 0
                    while block := src.read(1 << 20):
                        size += len(block)
                        if size > item['bytes']:
                            raise ValueError("Release exceeds pinned size")
                        dest.write(block)
                if not verified(path, item):
                    raise ValueError("Release size or SHA-256 differs")
                os.replace(path, target)
                return target
            finally:
                path.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            errors.append(f'{url}: {exc}')
    raise ValueError('; '.join(errors))


def acquire(cache, groups, offline=False):
    return {key: obtain(cache, row, offline) for key, row in sources().items()
            if row['group'] in groups}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', nargs='+', choices=['all', *sorted({item['group'] for item in sources().values()})])
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    groups = {i['group'] for i in sources().values()} if 'all' in args.group else set(args.group)
    for name, path in acquire(args.cache, groups, args.offline).items():
        print(name, path)


if __name__ == '__main__':
    main()
