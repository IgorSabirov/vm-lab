"""One arbitrary configuration, e.g. python run_case.py example.json --out trial."""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
from bench import Config,History,solve
from experiment import dump

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    c=Config(**json.loads(args.config.read_text()))
    values=solve(History(),c,args.out/'history.csv')
    dump(args.out/'run.json',dict(config=asdict(c),result=values))
    print(json.dumps(values,indent=2))

if __name__=='__main__': main()
