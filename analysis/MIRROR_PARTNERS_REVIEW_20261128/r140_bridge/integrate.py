#!/usr/bin/env python3
"""Append the completed bridge; preserve all original scientific records."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[3]
PARENT="analysis/MIRROR_PARTNERS_REVIEW_20261128"
PACKAGE=PARENT+"/r140_bridge"
REG="analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
BASE="fcc006b30e120fb536eba09288deeaf2dc42f167"
IDENT="MIRROR_R140_BRIDGE_20261128"

def dump(path,data):
    (ROOT/path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
def append(path,marker,text):
    p=ROOT/path;s=p.read_text()
    if marker not in s:p.write_text(s.rstrip()+"\n\n"+text.rstrip()+"\n")

def main():
    run=os.environ["GITHUB_RUN_ID"]; out=ROOT/PACKAGE/"runs"/run
    receipt=json.loads((out/"run_receipt.json").read_text())
    result=json.loads((out/"RESULTS.json").read_text())
    assert receipt["status"]==result["status"]=="PASS"
    p=ROOT/PACKAGE/"REPORT.md"
    section=("<!-- bridge-execution -->\n**Исполнение: PASS.** GitHub Actions [run "+run+
             "](https://github.com/IgorSabirov/vm-lab/actions/runs/"+run+"). Исходный commit: "+
             receipt["source_commit"]+". Основной код: "+format(receipt["main_seconds"],".6f")+
             " с; отдельная калибровка: "+format(receipt["calibration_seconds"],".6f")+
             " с. [Результаты](runs/"+run+"/RESULTS.json), [регистры](runs/"+run+
             "/register_bridge.json), [истории и прибор](runs/"+run+
             "/history_bridge.json), [квитанция](runs/"+run+
             "/run_receipt.json). Научная приёмка владельцем отдельно.\n<!-- /bridge-execution -->")
    p.write_text(re.sub(r"<!-- bridge-execution -->.*?<!-- /bridge-execution -->",
                       lambda _:section,p.read_text(),flags=re.S))
    for name in ("REGISTER_PROOF.md","HISTORY_PROOF.md"):
        append(PACKAGE+"/"+name,"<!-- executed-bridge -->",
               "<!-- executed-bridge -->\n\n**Исполнение протокола:** [LATEST.json](LATEST.json), "
               "[квитанция](runs/"+run+"/run_receipt.json). Доказательство и фактическая проверка имеют отдельные свидетельства.")
    dump(PACKAGE+"/LATEST.json",{"run_id":run,"source_commit":receipt["source_commit"],"status":"PASS",
         "results":"runs/"+run+"/RESULTS.json","receipt":"runs/"+run+"/run_receipt.json",
         "register":"runs/"+run+"/register_bridge.json","histories":"runs/"+run+"/history_bridge.json"})
    old_manifest=ROOT/PARENT/"FILES.sha256"
    snapshot=ROOT/PARENT/"checks"/"FILES_fcc006b3.sha256"
    snapshot.parent.mkdir(parents=True,exist_ok=True)
    if not snapshot.exists():snapshot.write_bytes(old_manifest.read_bytes())
    append(PARENT+"/REPORT.md",'id="r140-bridge"',
           '<a id="r140-bridge"></a>\n\n## Дополнение: мост к R140/H6, 28 ноября 2026\n\n'
           'Построены две зеркальные реализации битового регистра H6 и полный именованный шаг на24 состояниях. '
           'Заряд d=q₁−q₂ различает партнёров и проходит через W; q на трёхмерный фактор не спускается. '
           'Когерентные истории переносятся с именами; индуцированная идентификация поля отделена от обращения голономии M↔M⁻¹. '
           'Запись d сохраняет внутрисекторную интерференцию, запись A/B её уничтожает. '
           '[Доказательства, код и результаты](r140_bridge/REPORT.md). Научные статусы сохранены.')
    append(PARENT+"/README.md","r140_bridge/REPORT.md",
           "## Дополнение к R140/H6\n\n[Мост #223 ↔ R140](r140_bridge/REPORT.md): зеркальные регистры, полный шаг, "
           "заряд d, два полевых подъёма и различие записи сектора/пути. Новый запуск имеет отдельную квитанцию.")
    source_map=json.loads((ROOT/PARENT/"SOURCE_MAP.json").read_text())
    if not any(x.get("id")=="R140" for x in source_map["records"]):
        source_map["records"].append({"id":"R140",
          "title":"Мера Хаара и квантовые истории Соркина на именованных кольцах ADD",
          "source_commit_for_this_addendum":BASE,
          "review_role":"Прямой мост C′ к двум реализациям H6, наблюдаемая d и когерентная запись.",
          "selected_sources":[{"path":q,"url":"https://github.com/IgorSabirov/vm-lab/blob/"+BASE+"/"+q}
            for q in ("analysis/R140_HAAR_SORKIN/REPORT.md",
                      "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/bit_rule/review/AUDIT.md",
                      "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/bit_rule/review/REVISION.md")],
          "addendum":PACKAGE+"/REPORT.md","scientific_status_promoted":False})
    source_map["r140_bridge_addendum"]={"report":PACKAGE+"/REPORT.md","source_commit":BASE,"original_records_preserved":True}
    dump(PARENT+"/SOURCE_MAP.json",source_map)
    backlink=('<a id="mirror-223-bridge"></a>\n\n## Зеркальные регистры #223 и измерение R140, 28 ноября 2026\n\n'
       'В [мосте #223 ↔ R140](../MIRROR_PARTNERS_REVIEW_20261128/r140_bridge/REPORT.md) '
       'C′ переводит {a₁,b₂} в отражённый {b₁,a₂}; полный F включает два именных среза. '
       'Заряд d=q₁−q₂ даёт знак зеркального сектора, q не спускается через W. '
       'Сопоставлены все92 истории и40 именованных выходов, два подъёма поля и приборы записи сектора/пути. '
       'Инверсия голономии сопрягает M с M⁻¹. Статус R140 сохранён.')
    for q in ("analysis/R140_HAAR_SORKIN/REPORT.md","analysis/NOW_RESULTS_SYNTHESIS_20261106/R140.md"):
        append(q,'id="mirror-223-bridge"',backlink)
    data=json.loads((ROOT/REG).read_text())
    old_results=json.dumps(data["results"],sort_keys=True,ensure_ascii=False)
    old_reviews=json.dumps(data.get("external_reviews",[]),sort_keys=True,ensure_ascii=False)
    assert not any(x["id"]==IDENT for x in data.get("external_reviews",[]))
    managed=[PACKAGE+"/"+n for n in ("REPORT.md","REGISTER_PROOF.md","HISTORY_PROOF.md","REVIEW.md",
             "register_bridge.py","history_bridge.py","run.py","RUN_PLAN.json","SOURCE_MANIFEST.json","LINEAGE.json","LATEST.json")]
    managed += [str(x.relative_to(ROOT)) for x in sorted(out.glob("*.json"))]
    rows=[
      ("result:R130","scope_boundary","register","C′ acts on the full named carrier.",
       "Проверены24 именованных состояния и оба среза F, без переименования атомов."),
      ("result:R132","scope_boundary","observable","d descends through W; q does not.",
       "Заряд d различает реализации; явный вектор ядра запрещает спуск q."),
      ("result:R140","operational_requirement","field","Mirror covariance includes geometry, field and instrument.",
       "Два подъёма поля различены; все выходы и инструменты записи проверены."),
      ("result:R141","scope_boundary","register","The full F retains both named slices.",
       "Именные срезы представлены явно и отделены от зеркальных секторов."),
      ("question:U006","joint_model_requirement","scope","Paired representations require a physical map.",
       "Пространственное3+1+3, центральные часы и общая физическая стрела не выведены."),
      ("question:U010","operational_requirement","observer","Sector recording differs from path recording.",
       "Изометрия записи d сохраняет I₂; запись A/B его обнуляет. Самопроизводство аппарата не выведено.")]
    links=[{"target":a,"relation":b,"claim":d,"rationale":e,"evidence":PACKAGE+"/REPORT.md#"+c}
           for a,b,c,d,e in rows]
    data.setdefault("external_reviews",[]).append({"id":IDENT,
       "title":"Мост #223 ↔ R140/H6: зеркальные регистры, заряд d и когерентные истории",
       "status":"REPRODUCED_FINITE_BRIDGE_WITH_SCOPE_LIMITS","date":"2026-11-28","base_commit":BASE,
       "report":PACKAGE+"/REPORT.md","managed_sources":managed,"scientific_status_promoted":False,
       "links":links,"excluded_links":[]})
    data.setdefault("revision_history",[]).append({"id":IDENT,"date":"2026-11-28","base_commit":BASE,
       "report":PACKAGE+"/REPORT.md","new_records":[],"linked_results":["R130","R132","R140","R141"],
       "linked_questions":["U006","U010"],"scientific_status_promoted":False,
       "note":"Построен и проверен конечный мост; прежние R/U и review-записи сохранены."})
    assert old_results==json.dumps(data["results"],sort_keys=True,ensure_ascii=False)
    assert old_reviews==json.dumps(data["external_reviews"][:-1],sort_keys=True,ensure_ascii=False)
    dump(REG,data)
    check={"original_result_records_unchanged":True,"original_reviews_unchanged":True,
           "result_count":len(data["results"]),"new_result_ids":[],"new_question_ids":[],
           "scientific_status_promoted":False}
    (out/"registration_check.json").write_text(json.dumps(check,ensure_ascii=False,indent=2)+"\n")
    # Retain every historical checksum row, including files outside sparse checkout.
    rows={}
    prefix=ROOT/PARENT
    for line in old_manifest.read_text().splitlines():
        if not line.strip():continue
        digest,name=line.split(maxsplit=1);name=name.lstrip("*").strip()
        q=prefix/name
        if not q.is_file():q=ROOT/name
        rows[name]=hashlib.sha256(q.read_bytes()).hexdigest() if q.is_file() else digest
    for q in sorted((ROOT/PACKAGE).rglob("*")):
        if q.is_file() and "__pycache__" not in q.parts and q.suffix!=".pyc":
            rows[str(q.relative_to(prefix))]=hashlib.sha256(q.read_bytes()).hexdigest()
    rows[str(snapshot.relative_to(prefix))]=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    old_manifest.write_text("".join(d+"  "+n+"\n" for n,d in sorted(rows.items())))
    subprocess.run(["python","tools/registry_links.py","--write"],cwd=ROOT,check=True)
    subprocess.run(["python","tools/registry_links.py"],cwd=ROOT,check=True)
    print(json.dumps(check))
if __name__=="__main__":main()
