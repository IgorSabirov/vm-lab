"""List frozen file-and-line leads for one catalog group. No rows are promoted automatically."""
import argparse
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
groups = {r["id"]: r for r in json.loads((HERE/"catalog.json").read_text())}
branches = json.loads((HERE/"snapshot.json").read_text())["branches"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("group", choices=groups)
parser.add_argument("--branch", choices=branches, action="append", help="Search selected frozen tips. Default: all.")
args = parser.parse_args()
pattern = re.compile(groups[args.group]["search"], re.I | re.M)
seen = set()
root = HERE.parents[1]
for name in args.branch or branches:
    commit = branches[name]
    files = subprocess.check_output(["git","ls-tree","-rz",commit],cwd=root)
    with subprocess.Popen(["git","cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,cwd=root) as git:
        for entry in files.split(b"\0")[:-1]:
            header, raw_path = entry.split(b"\t",1)
            mode, kind, oid = header.split()
            path = raw_path.decode()
            if kind != b"blob" or oid in seen or "R142_MAGIC_NUMBERS/" in path:
                continue
            seen.add(oid)
            git.stdin.write(oid+b"\n")
            git.stdin.flush()
            length = int(git.stdout.readline().split()[-1])
            data = git.stdout.read(length)
            git.stdout.read(1)
            if b"\0" in data[:8192]:
                continue
            try:
                content = data.decode()
            except UnicodeDecodeError:
                continue
            match = pattern.search(content)
            if match:
                line = 1+content.count("\n",0,match.start())
                print(f"{commit}\t{path}\t{line}\t{match[0]}")
        git.stdin.close()
