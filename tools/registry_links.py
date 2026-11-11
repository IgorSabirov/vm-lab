#!/usr/bin/env python3
"""Build/check navigation between existing registries; never infer scientific status.

Sources: RESULTS_REGISTER.json, OPEN_QUESTIONS.json, PREMISES_CURRENT.md.
Historical literature IDs L01..L71 in premise prose are NOT open-link IDs.
No network, external dependencies, science calculations or automatic commits.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

MAIN = "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
MAIN_MD = MAIN.replace(".json", ".md")
QUESTIONS = "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.json"
PREMISES = "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md"
OUT = "analysis/REGISTRY_LINKS"


def unique(items, label):
    ids = [x["id"] for x in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate ID in {label}")
    return {x["id"]: x for x in items}


def parse_premises(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\| ([A-G]\d{2}) \| (.*?) \| (.*?) \|\s*$", line)
        if m:
            rows.append({"id": m[1], "current_statement": m[2], "sources_and_routes": m[3]})
    unique(rows, "premises")
    if len(rows) != 66:
        raise ValueError(f"Expected preserved 66 premise IDs, got {len(rows)}")
    return rows


def render_card(r):
    return (f"<a id=\"{r['id'].lower()}\"></a>\n\n### {r['id']}. {r['title']}\n\n"
            f"**Статус:** {r['status']}\n\n**Результат.** {r['result']}\n\n"
            f"**Условия.** {r['inputs']}\n\n**Граница.** {r['limit']}\n\n"
            f"**Место в рамке.** {r['framework_role']}\n\n"
            f"**Родители:** {', '.join(r.get('parent_result_ids', []))}. "
            f"**Конструкции:** {', '.join(r.get('construct_ids', []))}. "
            f"**Вопросы:** {', '.join(r.get('open_question_ids', []))}.\n\n"
            "**Источники:** " + "; ".join(f"[{Path(p).name}](../../{p})" for p in r['sources']) + ".\n\n"
            "**Предпосылки:** " + ", ".join(r.get('premise_ids', [])) +
            "; [реестр 66 условий](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md).\n")


def replace_block(text, key, body):
    begin, end = f"<!-- generated:{key} -->", f"<!-- /generated:{key} -->"
    pattern = re.escape(begin) + r".*?" + re.escape(end)
    replacement = begin + "\n" + body.rstrip() + "\n" + end
    matches = re.findall(pattern, text, re.S)
    if len(matches) > 1:
        raise ValueError(f"Duplicate generated block {key}")
    return re.sub(pattern, lambda _: replacement, text, flags=re.S) if matches else text.rstrip()+"\n\n"+replacement+"\n"


def build(root):
    raw = {p: (root / p).read_text() for p in (MAIN, QUESTIONS, PREMISES)}
    main, questions = json.loads(raw[MAIN]), json.loads(raw[QUESTIONS])
    groups = {"result": unique(main['results'], MAIN), "construct": unique(main['constructs'], MAIN),
              "link": unique(main['open_links'], MAIN), "question": unique(questions['questions'], QUESTIONS)}
    premise_rows = parse_premises(raw[PREMISES])
    groups['premise'] = unique(premise_rows, PREMISES)
    nodes = []
    for kind, group in groups.items():
        for ident, item in group.items():
            path = PREMISES if kind == 'premise' else QUESTIONS.replace('.json','.md') if kind == 'question' else MAIN_MD
            nodes.append({"key": f"{kind}:{ident}", "id": ident, "kind": kind, "title": item.get('title',item.get('current_statement','')),
                          "status": item.get('status'), "path": path})
    edges = set()
    def add(ka, a, kb, b, relation):
        if a not in groups[ka] or b not in groups[kb]:
            raise ValueError(f"Dangling typed reference: {ka}:{a} -> {kb}:{b}")
        edges.add((f"{ka}:{a}",f"{kb}:{b}",relation))
    for ident, r in groups['result'].items():
        for p in r.get('parent_result_ids',[]): add('result',p,'result',ident,'parent')
        for c in r.get('construct_ids',[]): add('result',ident,'construct',c,'addresses')
        for p in r.get('premise_ids',[]): add('result',ident,'premise',p,'direct_conditional_evidence')
        for l in r.get('open_link_ids',[]): add('result',ident,'link',l,'boundary_open')
        for q in r.get('open_question_ids',[]): add('result',ident,'question',q,'informs_not_closes')
    for r, cs in main.get('result_to_constructs',{}).items():
        for c in cs: add('result',r,'construct',c,'addresses')
    for c, item in groups['construct'].items():
        for r in item.get('results',[]): add('result',r,'construct',c,'addresses')
    for e in main.get('lineage_edges',[]):
        add('result',e['parent'],'result',e['child'],'parent')
    for q, item in groups['question'].items():
        for r in item.get('records',[]): add('result',r,'question',q,'informs_not_closes')
        for l in item.get('open_links',[]): add('question',q,'link',l,'related_open_link')
    legacy = [x for x in main.get('legacy_crosswalk',[]) if x.get('source') == PREMISES]
    if {x['id'] for x in legacy} != set(groups['premise']):
        raise ValueError('Legacy crosswalk must cover exactly all 66 premise IDs')
    for x in legacy:
        for c in x.get('constructs',[]): add('premise',x['id'],'construct',c,'historical_navigation_not_proof')
    for r in groups['result'].values():
        for source in r.get('managed_sources',[]):
            if not (root/source).is_file(): raise ValueError(f"Missing managed source {source}")
    graph = {"schema":"vm-lab-registry-links-v1", "sources": {p: hashlib.sha256(s.encode()).hexdigest() for p,s in raw.items()},
             "counts": {k:len(v) for k,v in groups.items()},
             "semantics":"Typed navigation; a link never proves a claim or closes a question. Literature Lxx and research link Lxxx namespaces are not inferred from prose.",
             "nodes": sorted(nodes,key=lambda x:x['key']),
             "edges": [{"source":a,"target":b,"relation":r} for a,b,r in sorted(edges)]}
    bykey = {x['key']: x for x in nodes}
    def mdlink(key):
        n=bykey[key];return f"[{n['id']}](../../{n['path']})"
    lines = ["# Связи реестров", "", "Сгенерировано `python tools/registry_links.py --write`. Научные статусы берутся из исходных карточек; связи их не повышают.", "",
             "[Результаты](../NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md) · [66 предпосылок](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md) · [Вопросы](../NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md)", "",
             "Число записей: " + ", ".join(f"{k}={v}" for k,v in graph['counts'].items()) + ".", "",
             "## Предпосылка → результаты", "", "| ID | Прямое адресное свидетельство | Историческая навигация через конструкции |", "|---|---|---|"]
    for p in premise_rows:
        pk='premise:'+p['id']; direct=sorted(a for a,b,r in edges if b==pk and r=='direct_conditional_evidence')
        cs=sorted(b for a,b,r in edges if a==pk and r=='historical_navigation_not_proof')
        nav=sorted({a for a,b,r in edges if b in cs and r=='addresses'})
        p['direct_result_ids']=[bykey[x]['id'] for x in direct]
        p['navigation_construct_ids']=[bykey[x]['id'] for x in cs]
        p['navigation_result_ids']=[bykey[x]['id'] for x in nav]
        lines.append(f"| {p['id']} | {', '.join(mdlink(x) for x in direct) or 'Нет новой прямой аттестации'} | {', '.join(mdlink(x) for x in cs)}; {', '.join(mdlink(x) for x in nav)} |")
    lines += ["", "## Результат → предпосылки", "", "| Результат | Прямые связи |", "|---|---|"]
    for rid in groups['result']:
        ps=sorted(b for a,b,r in edges if a=='result:'+rid and r=='direct_conditional_evidence')
        if ps: lines.append(f"| {mdlink('result:'+rid)} | {', '.join(mdlink(x) for x in ps)} |")
    lines += ["", "Полный граф с родителями, конструкциями и открытыми вопросами: [INDEX.json](INDEX.json).", "",
              "`premise:C01` не равно `construct:C001`; литературные L01–L71 внутри текста не являются открытыми L-связями проекта."]
    premise_json={"schema":"premises-current-mirror-v1","source":PREMISES,"main_registry":MAIN,
                  "note":"Generated exact-text mirror; preserves 66 historical IDs. The nine N-debts remain in source Markdown. Navigation is not new proof.","entries":premise_rows}
    outputs={OUT+'/INDEX.json':json.dumps(graph,ensure_ascii=False,indent=2)+'\n',
             OUT+'/INDEX.md':'\n'.join(lines)+'\n',
             PREMISES.replace('.md','.json'):json.dumps(premise_json,ensure_ascii=False,indent=2)+'\n'}
    md=(root/MAIN_MD).read_text()
    for r in groups['result'].values():
        if r.get('managed_card'):
            md=replace_block(md,r['id'],render_card(r))
    for kind in ('result','construct'):
        for ident in groups[kind]:
            if not re.search(r'^#{2,4}\s+'+re.escape(ident)+r'(?:[. —:]|$)',md,re.M):
                raise ValueError(f'Missing Markdown entry {ident}')
    # Prevent the specific previously misleading R122 boundary from returning.
    r122=groups['result']['R122']
    if r122.get('managed_boundary') and r122['limit'] not in md:
        raise ValueError('R122 Markdown boundary diverges from JSON')
    outputs[MAIN_MD]=md
    return outputs,graph


def run(root, write=False):
    outputs,graph=build(root)
    stale=[]
    for p,s in outputs.items():
        path=root/p
        if not path.exists() or path.read_text()!=s:
            stale.append(p)
            if write:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(s)
    return stale,graph


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--write',action='store_true')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--summary',type=Path)
    a=p.parse_args()
    stale,graph=run(a.root,a.write)
    summary=json.dumps({'status':'UPDATED' if a.write and stale else 'FAIL' if stale else 'PASS',
                        'counts':graph['counts'],'edges':len(graph['edges']),'stale':stale},ensure_ascii=False)
    print(summary)
    if a.summary:
        with a.summary.open('a') as f:f.write('### Registry consistency\n\n```json\n'+summary+'\n```\n')
    if stale and not a.write:raise SystemExit(1)


if __name__=='__main__':main()
