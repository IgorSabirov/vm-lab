"""Apply only the published R140 card and rebuild the registry on its frozen R139 base."""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REG=ROOT/'analysis/NOW_RESULTS_SYNTHESIS_20261106'
REPORT='analysis/R140_HAAR_SORKIN/REPORT.md'
BASE='06c4d305ebb74ef6b79081f0973aaed3c186d8ee'
PARENTS={
    'R007':'Gram-представление конечного функционала историй.',
    'R008':'Отрицательный контроль сильной положительности.',
    'R011':'Декогерентные альтернативы и композиция событий.',
    'R047':'Различение кинематической меры и выбора начального состояния.',
    'R130':'Именованный двигатель полного двухканального F=QI.',
    'R133':'Правила цилиндрического переноса и средней рамки.',
    'R139':'Конечная локальная изометрия, унитарная рекомбинация и контроль декогеренции.'}

def register():
    card=json.loads((REG/'R140.json').read_text())
    assert card['parent_result_ids']==list(PARENTS)
    path=REG/'RESULTS_REGISTER.json'
    markdown=REG/'RESULTS_REGISTER.md'
    data=json.loads(path.read_text())
    existing=[r for r in data['results'] if r['id']=='R140']
    if existing:
        if existing != [card]:
            raise ValueError('Existing R140 differs from the published card')
        subprocess.run([sys.executable,'tools/registry_links.py'], cwd=ROOT, check=True)
        return
    # Never replace unrelated edits to the two canonical registry inputs.
    for target in (path,markdown):
        old=subprocess.check_output(['git','show',BASE+':'+target.relative_to(ROOT).as_posix()],cwd=ROOT)
        if target.read_bytes()!=old:
            raise ValueError('Registry base changed; reconcile the R140 additions on the current branch')
    data['results'].append(card)
    data['result_to_constructs']['R140']=card['construct_ids']
    next(c for c in data['constructs'] if c['id']=='C012')['results'].append('R140')
    for parent,note in PARENTS.items():
        data['lineage_edges'].append(dict(parent=parent,child='R140',relation='direct_mathematical_input',note=note))
        data['result_children'].setdefault(parent,[]).append('R140')
    data['revision']='R140_HAAR_SORKIN_20261122'
    data['revision_history'].append(dict(id=data['revision'],date='2026-11-22',base_commit=BASE,
                                    report=REPORT,new_records=['R140'],updates=[],scientific_status_promoted=False))
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    header='> **22 ноября 2026 · [R140](#r140).** [Мера Хаара и квантовые истории на именованных графах ADD](../R140_HAAR_SORKIN/REPORT.md). Научный статус OPEN.\n\n'
    markdown.write_text(header+markdown.read_text())
    subprocess.run([sys.executable,'tools/registry_links.py','--write'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'tools/registry_links.py'],cwd=ROOT,check=True)


if __name__=='__main__':
    register()
