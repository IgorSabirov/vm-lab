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
QUESTIONS_MD = QUESTIONS.replace('.json', '.md')
PREMISES = "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md"
OUT = "analysis/REGISTRY_LINKS"
REVIEW_RELATIONS = {
    'scope_boundary', 'operational_requirement', 'clock_comparison',
    'joint_model_requirement', 'conditional_open_system_constraint',
    'classification_only', 'time_scale_analogy', 'premise_context_not_evidence',
}


def strip_block(text, key):
    return re.sub(r'\n*<!-- generated:'+re.escape(key)+r' -->.*?<!-- /generated:'+re.escape(key)+r' -->\n*', '\n', text, flags=re.S).rstrip()+'\n'


def anchor(key):
    return key.lower().replace(':', '-')


def neighborhood(graph, key):
    node = next((n for n in graph['nodes'] if n['key'] == key), None)
    if node is None:
        raise ValueError(f'Unknown typed node {key}')
    return {'node': node, 'incoming': [e for e in graph['edges'] if e['target'] == key],
            'outgoing': [e for e in graph['edges'] if e['source'] == key]}


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
    # Generated premise navigation is not a fourth semantic source (or a hash cycle).
    raw[PREMISES] = strip_block(raw[PREMISES], 'external-review-links')
    main, questions = json.loads(raw[MAIN]), json.loads(raw[QUESTIONS])
    groups = {"result": unique(main['results'], MAIN), "construct": unique(main['constructs'], MAIN),
              "link": unique(main['open_links'], MAIN), "question": unique(questions['questions'], QUESTIONS)}
    premise_rows = parse_premises(raw[PREMISES])
    groups['premise'] = unique(premise_rows, PREMISES)
    groups['review'] = unique(main.get('external_reviews', []), 'external reviews')
    nodes = []
    for kind, group in groups.items():
        for ident, item in group.items():
            path = PREMISES if kind == 'premise' else QUESTIONS.replace('.json','.md') if kind == 'question' else MAIN_MD
            if kind == 'review': path = item['report']
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
    review_details = {}
    exclusions = []
    evidence_hashes = {}
    def validate_target(target):
        parts = target.split(':')
        if len(parts) != 2 or parts[0] not in groups or parts[1] not in groups[parts[0]]:
            raise ValueError(f'Dangling typed review reference: {target}')
        if parts[0] == 'review': raise ValueError('Review targets must be existing registry entries')
        return parts
    for ident, review in groups['review'].items():
        if review.get('scientific_status_promoted') is not False:
            raise ValueError('External review must not promote scientific status')
        for source in review.get('managed_sources', []):
            if not (root/source).is_file(): raise ValueError(f'Missing managed review source {source}')
            evidence_hashes[source] = hashlib.sha256((root/source).read_bytes()).hexdigest()
        if review['report'] not in evidence_hashes:
            raise ValueError('Review report must be a managed source')
        targets = set()
        for item in review['links']:
            kind, target = validate_target(item['target'])
            if item['target'] in targets: raise ValueError('Duplicate review target')
            targets.add(item['target'])
            if item['relation'] not in REVIEW_RELATIONS:
                raise ValueError(f"Unknown review relation {item['relation']}")
            if not item.get('rationale'): raise ValueError('Review link requires rationale')
            source, sep, fragment = item['evidence'].partition('#')
            if source not in evidence_hashes or not sep or not fragment or f'id="{fragment}"' not in (root/source).read_text():
                raise ValueError(f"Missing review evidence anchor {item['evidence']}")
            add('review',ident,kind,target,item['relation'])
            review_details[('review:'+ident,item['target'],item['relation'])] = {k:item[k] for k in ('rationale','evidence','claim')}
        excluded_targets = set()
        for item in review.get('excluded_links', []):
            validate_target(item['target'])
            if item['target'] in targets or item['target'] in excluded_targets:
                raise ValueError('Contradictory or duplicate excluded review target')
            excluded_targets.add(item['target'])
            if not item.get('rationale'): raise ValueError('Excluded link requires rationale')
            exclusions.append({'source':'review:'+ident, **item})
    for ident, item in groups['question'].items():
        ref = item.get('external_review_reference')
        if ref:
            rev = groups['review'].get(ref['review_id'])
            if not rev or ref['report'] != rev['report'] or not any(x['target']=='question:'+ident for x in rev['links']):
                raise ValueError(f'Dangling question review reference {ident}')
    graph = {"schema":"vm-lab-registry-links-v2", "sources": {p: hashlib.sha256(s.encode()).hexdigest() for p,s in raw.items()},
             "managed_review_sources": evidence_hashes,
             "counts": {k:len(v) for k,v in groups.items()},
             "semantics":"Typed navigation; a link never proves a claim or closes a question. Literature Lxx and research link Lxxx namespaces are not inferred from prose.",
             "nodes": sorted(nodes,key=lambda x:x['key']),
             "edges": [{"source":a,"target":b,"relation":r, **review_details.get((a,b,r),{})} for a,b,r in sorted(edges)],
             "excluded_review_links": exclusions}
    bykey = {x['key']: x for x in nodes}
    def mdlink(key):
        n=bykey[key];return f"[{n['id']}](#{anchor(key)})"
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
        p['context_review_ids']=sorted(bykey[a]['id'] for a,b,r in edges if b==pk and a.startswith('review:'))
        lines.append(f"| {p['id']} | {', '.join(mdlink(x) for x in direct) or 'Нет новой прямой аттестации'} | {', '.join(mdlink(x) for x in cs)}; {', '.join(mdlink(x) for x in nav)} |")
    lines += ["", "## Результат → предпосылки", "", "| Результат | Прямые связи |", "|---|---|"]
    for rid in groups['result']:
        ps=sorted(b for a,b,r in edges if a=='result:'+rid and r=='direct_conditional_evidence')
        if ps: lines.append(f"| {mdlink('result:'+rid)} | {', '.join(mdlink(x) for x in ps)} |")
    lines += ["", "Полный граф с родителями, конструкциями и открытыми вопросами: [INDEX.json](INDEX.json).", "",
              "`premise:C01` не равно `construct:C001`; литературные L01–L71 внутри текста не являются открытыми L-связями проекта."]
    lines += ['', '## Карточки и обратные связи', '', 'Каждая связь хранится один раз. Входящие и исходящие переходы ниже вычислены из того же графа. Обратный переход — навигация, а не обратное доказательство.']
    for n in graph['nodes']:
        key = n['key']; adjacent = neighborhood(graph,key)
        lines += ['', f'<a id="{anchor(key)}"></a>', '', f"### {key}", '',
                  f"{n['title']} — [исходная карточка](../../{n['path']}).", '']
        for label,direction,other in [('Входящие','incoming','source'),('Исходящие','outgoing','target')]:
            entries=adjacent[direction]
            lines.append(f"**{label}:** "+('; '.join(f"{mdlink(e[other])} `{e['relation']}`" for e in entries) or 'нет')+'.')
        if n['kind']=='review':
            lines += ['', '| Связь | Смысл и граница | Основание |', '|---|---|---|']
            for e in adjacent['outgoing']:
                lines.append(f"| {mdlink(e['target'])} `{e['relation']}` | {e['rationale']} | [разбор](../../{e['evidence']}) |")
            lines += ['', '**Не включены в положительные связи:**']
            for e in exclusions:
                if e['source']==key:lines.append(f"- {mdlink(e['target'])}: `{e['decision']}` — {e['rationale']}")
    premise_json={"schema":"premises-current-mirror-v1","source":PREMISES,"main_registry":MAIN,
                  "note":"Generated exact-text mirror; preserves 66 historical IDs. The nine N-debts remain in source Markdown. Navigation is not new proof.","entries":premise_rows}
    outputs={OUT+'/INDEX.json':json.dumps(graph,ensure_ascii=False,indent=2)+'\n',
             OUT+'/INDEX.md':'\n'.join(lines)+'\n',
             PREMISES.replace('.md','.json'):json.dumps(premise_json,ensure_ascii=False,indent=2)+'\n'}
    md=(root/MAIN_MD).read_text()
    for r in groups['result'].values():
        if r.get('managed_card'):
            md=replace_block(md,r['id'],render_card(r))
    # Put review backlinks at the point of entry, including legacy cards.
    def review_table(kinds):
        rows=['## Внешние разборы: контекст и границы', '', 'Ссылки не меняют научный статус карточек. [Полная карта](../REGISTRY_LINKS/INDEX.md).', '',
              '| Карточка | Разбор | Тип связи | Смысл |', '|---|---|---|---|']
        for e in graph['edges']:
            if e['source'].startswith('review:') and e['target'].split(':')[0] in kinds:
                rows.append(f"| [{e['target']}](../REGISTRY_LINKS/INDEX.md#{anchor(e['target'])}) | [{e['source'].split(':')[1]}](../../{bykey[e['source']]['path']}) | `{e['relation']}` | {e['rationale']} |")
        return '\n'.join(rows)
    def card_backlinks(text, kinds):
        text=re.sub(r'\n*<!-- generated:review-card-[^>]+ -->.*?<!-- /generated:review-card-[^>]+ -->\n*','\n\n',text,flags=re.S)
        for n in graph['nodes']:
            if n['kind'] not in kinds: continue
            es=[e for e in graph['edges'] if e['source'].startswith('review:') and e['target']==n['key']]
            if not es: continue
            pattern=r'(^#{2,4}\s+'+re.escape(n['id'])+r'(?:[. —:]|$)[^\n]*\n)'
            body='\n\n'.join(f"**Внешний разбор:** [{e['source'].split(':')[1]}](../../{e['evidence']}); `{e['relation']}`. {e['rationale']} [Все связи карточки](../REGISTRY_LINKS/INDEX.md#{anchor(n['key'])})." for e in es)
            block=replace_block('', 'review-card-'+anchor(n['key']), body)
            text,count=re.subn(pattern,lambda m:m[1]+'\n'+block+'\n',text,count=1,flags=re.M)
            if count!=1:raise ValueError(f"Missing review target Markdown entry {n['id']}")
        return text
    md=card_backlinks(md,{'result','construct'})
    md=replace_block(md,'external-review-links',review_table({'result','construct','link'}))
    qmd=card_backlinks((root/QUESTIONS_MD).read_text(),{'question'})
    qmd=replace_block(qmd,'external-review-links',review_table({'question'}))
    outputs[QUESTIONS_MD]=qmd
    outputs[PREMISES]=replace_block(raw[PREMISES],'external-review-links',review_table({'premise'}))
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
    p.add_argument('--node',help='Show typed incoming/outgoing references, e.g. question:U006')
    a=p.parse_args()
    stale,graph=run(a.root,a.write)
    payload={'status':'UPDATED' if a.write and stale else 'FAIL' if stale else 'PASS',
             'counts':graph['counts'],'edges':len(graph['edges']),'stale':stale}
    if a.node: payload['query']=neighborhood(graph,a.node)
    summary=json.dumps(payload,ensure_ascii=False)
    print(summary)
    if a.summary:
        with a.summary.open('a') as f:f.write('### Registry consistency\n\n```json\n'+summary+'\n```\n')
    if stale and not a.write:raise SystemExit(1)


if __name__=='__main__':main()
