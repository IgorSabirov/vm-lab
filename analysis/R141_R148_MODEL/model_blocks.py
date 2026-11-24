"""Extract editable offline HTML blocks and merge them into the canonical model."""
import argparse
import contextlib
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

MODEL = Path(__file__).with_name("R141-R148.html")
KEYS = ["overview", *(f"R{i}" for i in range(141,149)), "pairs", "proofs", "time",
        "review", "limits", "sources", "passports", "materials"]
MARK = re.compile(rb"<!--(/?)MODEL-BLOCK ([\w-]+)-->")
META = re.compile(rb'<script type="application/json" id="block-base">(.*?)</script>', re.S)


def regions(data):
    blocks = {}
    active = None
    for m in MARK.finditer(data):
        closing, key = m[1], m[2].decode()
        if closing:
            if key != active:
                raise ValueError(f"Unmatched closing marker {key}")
            blocks[key] = (start, m.start())
            active = None
        else:
            if active or key in blocks or key not in KEYS:
                raise ValueError(f"Invalid or nested block {key}")
            active, start = key, m.end()
    if active:
        raise ValueError(f"Unclosed block {active}")
    return blocks


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = Counter()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids[v] += 1
            if k == "href" and v and v.startswith("#") and len(v)>1:
                self.refs.append(unquote(v[1:]))


def validate(data):
    blocks = regions(data)
    if list(blocks) != KEYS:
        raise ValueError("Model block set/order changed")
    parsed = Anchors()
    parsed.feed(data.decode("utf-8"))
    parsed.close()
    duplicated = [k for k,n in parsed.ids.items() if n>1]
    missing = set(parsed.refs)-set(parsed.ids)
    if duplicated or missing:
        raise ValueError(f"Duplicate IDs {duplicated}, missing anchors {sorted(missing)}")
    for n in range(141,149):
        l,r = blocks[f"R{n}"]
        if f'<h3 id="node{n}">'.encode() not in data[l:r]:
            raise ValueError(f"Invalid card identity R{n}")
    return blocks


def digest(data):
    return hashlib.sha256(data).hexdigest()


def extract(model, keys, output):
    data = model.read_bytes()
    blocks = validate(data)
    if len(keys)!=len(set(keys)):
        raise ValueError("Duplicate selection")
    chosen = {k:data[l:r] for k,(l,r) in blocks.items() if k in keys}
    meta = json.dumps({k:digest(v) for k,v in chosen.items()}).encode()
    head = data[:data.index(b'</head>')]
    title = escape(" · ".join(chosen)).encode()
    head = re.sub(b'<title>.*?</title>',b'<title>'+title+b'</title>',head,count=1)
    link = escape(model.name, quote=True).encode()
    parts = [head, b'</head><body><main><p><a id="whole-model" href="'+link+b'">'+
             'Полная модель'.encode()+b'</a></p><article>']
    for k,v in chosen.items():
        name = k.encode()
        parts.extend([b'<!--MODEL-BLOCK '+name+b'-->',v,b'<!--/MODEL-BLOCK '+name+b'-->'])
    parts.extend([b'</article></main><script type="application/json" id="block-base">',
                  meta,b'</script>',b"""<script>
for (const a of document.querySelectorAll('a[href^="#"]')) {
  const id = decodeURIComponent(a.hash.slice(1));
  if (id && !document.getElementById(id)) a.href = document.querySelector('#whole-model').href+a.hash;
}
</script>""",data[data.rindex(b'</footer>')+len(b'</footer>'):]])
    with output.open('xb') as f:
        f.write(b''.join(parts))


@contextlib.contextmanager
def lock_directory(path):
    # No persistent lockfile in the checkout. All model_blocks writers share this lock.
    import fcntl
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def apply(model, packet):
    edits = packet.read_bytes()
    matches = META.findall(edits)
    if len(matches)!=1:
        raise ValueError("Missing or duplicate export manifest")
    base = json.loads(matches[0])
    incoming = regions(edits)
    if not incoming or set(incoming)!=set(base):
        raise ValueError("Selected blocks or manifest were lost")
    with lock_directory(model.parent):
        data = model.read_bytes()
        slots = validate(data)
        updates = []
        for k,(a,b) in incoming.items():
            l,r = slots[k]
            replacement = edits[a:b]
            if digest(replacement)==base[k] or data[l:r]==replacement:
                continue
            if digest(data[l:r])!=base[k]:
                raise ValueError(f"{k} changed in both copies; extract again and reconcile")
            updates.append((l,r,replacement))
        if not updates:
            return
        for l,r,v in sorted(updates,reverse=True):
            data = data[:l]+v+data[r:]
        validate(data)
        with tempfile.NamedTemporaryFile(dir=model.parent,delete=False) as f:
            tmp = Path(f.name)
        try:
            tmp.write_bytes(data)
            tmp.chmod(model.stat().st_mode & 0o777)
            os.replace(tmp,model)
        finally:
            tmp.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,default=MODEL)
    sub = p.add_subparsers(dest='action',required=True)
    sub.add_parser('list')
    sub.add_parser('check')
    ext = sub.add_parser('extract')
    ext.add_argument('blocks',choices=KEYS,nargs='+')
    ext.add_argument('-o','--output',type=Path,required=True)
    sub.add_parser('apply').add_argument('packet',type=Path)
    a = p.parse_args()
    if a.action == 'extract':
        extract(a.model,a.blocks,a.output)
    elif a.action == 'apply':
        apply(a.model,a.packet)
    else:
        blocks = validate(a.model.read_bytes())
        print(' '.join(blocks) if a.action=='list' else f'OK: {len(blocks)} blocks; anchors resolved')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
