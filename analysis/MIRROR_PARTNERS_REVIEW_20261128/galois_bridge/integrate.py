#!/usr/bin/env python3
"""Preserve the completed arithmetic bridge and append its existing-R links."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PARENT = "analysis/MIRROR_PARTNERS_REVIEW_20261128"
PACKAGE = PARENT + "/galois_bridge"
REG = "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
BASE = "7aae9af516972c6e7975095baaaf56e4f70af8c5"
IDENT = "GALOIS_FULL_MIRROR_BRIDGE_20261128"

def dump(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def append(path, marker, text):
    p = ROOT / path
    before = p.read_text()
    if marker not in before:
        p.write_text(before.rstrip() + "\n\n" + text.rstrip() + "\n")

def main():
    run = os.environ["GITHUB_RUN_ID"]
    out = ROOT / PACKAGE / "runs" / run
    receipt = json.loads((out / "run_receipt.json").read_text())
    result = json.loads((out / "RESULTS.json").read_text())
    assert receipt["status"] == result["status"] == "PASS"
    section = ("<!-- galois-execution -->\n**Новые конечные проверки: PASS.** "
        "[GitHub run " + run + "](https://github.com/IgorSabirov/vm-lab/actions/runs/" + run +
        "). Код: " + receipt["source_commit"] + ". Основная проверка " +
        format(receipt["main_seconds"], ".6f") + " с, калибровка " +
        format(receipt["calibration_seconds"], ".6f") + " с. "
        "[Точные результаты](runs/" + run + "/checks.json), [квитанция](runs/" + run +
        "/run_receipt.json). Сопоставлены арифметические действия и архивные матрицы; "
        "92 истории R140 повторно не исполнялись. Доказательства всех n, листов и "
        "геометрии отдельно изложены в трёх proof-документах.\n<!-- /galois-execution -->")
    report = ROOT / PACKAGE / "REPORT.md"
    text = report.read_text()
    assert text.count("<!-- galois-execution -->") == 1
    report.write_text(re.sub(r"<!-- galois-execution -->.*?<!-- /galois-execution -->",
                            lambda _: section, text, flags=re.S))
    dump(PACKAGE + "/LATEST.json", {"run_id": run, "source_commit": receipt["source_commit"],
        "status": "PASS", "results": "runs/" + run + "/checks.json",
        "receipt": "runs/" + run + "/run_receipt.json",
        "old_R140_reexecuted": False})
    old_manifest = ROOT / PARENT / "FILES.sha256"
    snapshot = ROOT / PARENT / "checks" / "FILES_7aae9af5.sha256"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        snapshot.write_bytes(old_manifest.read_bytes())
    append(PARENT + "/REPORT.md", 'id="galois-full-bridge"',
        '<a id="galois-full-bridge"></a>\n\n## Галуа и полный арифметический регистр, 28 ноября 2026\n\n'
        'На 12 единицах O/(4), уже являющемся обычным уровнем n=3 R141/R146, '
        'построены F:x↦φx, C′:x↦−x и T:x↦x⁻¹. Они совпадают со всеми матрицами '
        'полного сокращённого регистра #223, включая d. Галуа действует как G=C′^sT. '
        'Два листа R141 уже включены через одночастичный слой m=3. Установлены ограничения '
        'знаковой башни, поправка G при переходе от коядра к фиксированным точкам тора '
        'и аналитическое многочастичное продолжение W. '
        '[Подробный разбор вложения, доказательства и конечная проверка](galois_bridge/REPORT.md).')
    append(PARENT + "/README.md", "galois_bridge/REPORT.md",
        "## Галуа, R141/R146 и полный регистр\n\n"
        "[Мост на 12 единицах O/(4)](galois_bridge/REPORT.md): полный F,T,C′, "
        "два именных среза, заряд d, конечные факторы и точные границы переноса.")
    append(PARENT + "/r140_bridge/REPORT.md", 'id="galois-arithmetic-extension"',
        '<a id="galois-arithmetic-extension"></a>\n\n## Арифметическое продолжение через R141/R146\n\n'
        'В [новом разборе](../galois_bridge/REPORT.md) все опубликованные F,T,C′,d после W '
        'реализованы на 12 единицах O/(4). Сравнение использует сохранённые здесь матрицы '
        'и не повторяет исторический опыт. Галуа равно T на чётном срезе и C′T на нечётном.')
    notes = {
        "R141": "Обычный фактор O/(φ⁶−1)=O/(4) содержит 12 единиц, реализующих полный "
                "сокращённый регистр #223. Прежний F4×→H6 результат атрибутирован parity/REPORT.md; "
                "Галуа, листы и зеркало получили явные различные действия.",
        "R146": "На 12 единицах обычного уровня n=3 построен полный регистр #223. "
                "Галуа задаёт ориентационно сохраняющую изометрию симметричной Sol-метрики; "
                "время потока Риччи не обращается. Коядро и геометрические периодические точки "
                "переносят Галуа с дополнительным минусом. Естественный mod4-фактор отсутствует "
                "во всей знаковой ветви.",
        "R150": "Конструкция F4×, отражение и чтение110 из parity/REPORT.md сохранены как "
                "предшествующий результат. Новое дополнение определяет происхождение отражения "
                "из Галуа и удерживает полный шаг и зеркальную метку mod4. "
                "Выводов о массах, Коиде или числе физических поколений из этого не добавлено.",
    }
    for ident, note in notes.items():
        append("analysis/NOW_RESULTS_SYNTHESIS_20261106/" + ident + ".md", 'id="galois-223-extension"',
            '<a id="galois-223-extension"></a>\n\n## Мост с #223: Галуа и полный регистр, 28 ноября 2026\n\n' +
            note + " [Доказательства и результаты](../MIRROR_PARTNERS_REVIEW_20261128/galois_bridge/REPORT.md). "
            "Действующий научный статус сохранён.")
    source_map = json.loads((ROOT / PARENT / "SOURCE_MAP.json").read_text())
    source_map["galois_full_bridge_addendum"] = {
        "report": PACKAGE + "/REPORT.md", "source_commit": BASE,
        "linked_results": ["R130", "R132", "R140", "R141", "R146", "R150"],
        "original_records_preserved": True, "scientific_status_promoted": False,
        "scope": "explicit arithmetic representation and audited limitations"}
    dump(PARENT + "/SOURCE_MAP.json", source_map)
    data = json.loads((ROOT / REG).read_text())
    results_before = json.dumps(data["results"], sort_keys=True, ensure_ascii=False)
    reviews_before = json.dumps(data.get("external_reviews", []), sort_keys=True, ensure_ascii=False)
    assert not any(x["id"] == IDENT for x in data.get("external_reviews", []))
    check = {"original_result_records_unchanged": True, "original_reviews_unchanged": True,
             "result_count": len(data["results"]), "new_result_ids": [], "new_question_ids": [],
             "scientific_status_promoted": False, "old_R140_reexecuted": False}
    dump(str((out / "registration_check.json").relative_to(ROOT)), check)
    managed = [str(p.relative_to(ROOT)) for p in sorted((ROOT / PACKAGE).glob("*"))
               if p.is_file() and p.suffix in (".md", ".json", ".py")]
    managed += [PACKAGE + "/sources/ATTACHMENT_20261128.txt"]
    managed += [str(p.relative_to(ROOT)) for p in sorted(out.glob("*.json"))]
    rows = [
        ("result:R130", "scope_boundary", "mod4", "The complete named register has an explicit arithmetic representation.",
         "Все матрицы F,T,C′ и заряд d согласованы с 12 единицами O/(4)."),
        ("result:R132", "scope_boundary", "mod4", "Mirror charge and sheet parity have distinct arithmetic readouts.",
         "d=ε и p=N(x) различены; q не спускается через прежний W."),
        ("result:R140", "operational_requirement", "observer", "Exact representation preserves the specified experiment with lifted states and effects.",
         "Старый опыт используется без повторного исполнения; управление, подготовка и прибор остаются входами."),
        ("result:R141", "scope_boundary", "sheets", "The two-sheet one-particle sector is already contained in the full register.",
         "Уточнены прямое включение, нативное Галуа и фактор O/(4)."),
        ("result:R146", "scope_boundary", "geometry", "Galois acts on the mapping torus and requires an equivariant map for its finite observables.",
         "Доказаны геометрическое действие, поправка знака θ и границы знаковой башни."),
        ("result:R150", "premise_context_not_evidence", "provenance", "The prior F4x and H6 parity construction is a parent, not a new mass prediction.",
         "Прежний результат атрибутирован; массы и поколения не выводятся новым представлением."),
        ("question:U006", "joint_model_requirement", "scope", "An explicit arithmetic representation does not identify a unique physical carrier.",
         "Сложение кольца, локальность, энергетический оператор и физическое время остаются отдельными интерфейсами."),
        ("question:U010", "operational_requirement", "observer", "Coherent preparation and the detector remain specified inputs.",
         "Равенства операторов сохраняют согласованные вероятности, но не выводят закон приготовления.")]
    links = [{"target": target, "relation": relation, "claim": claim, "rationale": rationale,
              "evidence": PACKAGE + "/REPORT.md#" + anchor}
             for target, relation, anchor, claim, rationale in rows]
    data.setdefault("external_reviews", []).append({
        "id": IDENT, "title": "Галуа, модуль4 и полный арифметический мост #223–R140–R141–R146",
        "status": "REPRODUCED_ARITHMETIC_REGISTER_WITH_ANALYTIC_SCOPE_PROOFS", "date": "2026-11-28",
        "base_commit": BASE, "report": PACKAGE + "/REPORT.md", "managed_sources": managed,
        "scientific_status_promoted": False, "links": links, "excluded_links": []})
    data.setdefault("revision_history", []).append({
        "id": IDENT, "date": "2026-11-28", "base_commit": BASE, "report": PACKAGE + "/REPORT.md",
        "new_records": [], "linked_results": ["R130", "R132", "R140", "R141", "R146", "R150"],
        "linked_questions": ["U006", "U010"], "scientific_status_promoted": False,
        "note": "Явное представление полного регистра и разбор вложения; старые данные и статусы сохранены."})
    assert results_before == json.dumps(data["results"], sort_keys=True, ensure_ascii=False)
    assert reviews_before == json.dumps(data["external_reviews"][:-1], sort_keys=True, ensure_ascii=False)
    dump(REG, data)
    hashes = {}
    prefix = ROOT / PARENT
    for line in old_manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*").strip()
        p = prefix / name
        if not p.is_file():
            p = ROOT / name
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else digest
    for p in sorted((ROOT / PACKAGE).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            hashes[str(p.relative_to(prefix))] = hashlib.sha256(p.read_bytes()).hexdigest()
    hashes[str(snapshot.relative_to(prefix))] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    old_manifest.write_text("".join(digest + "  " + name + "\n" for name, digest in sorted(hashes.items())))
    subprocess.run(["python", "tools/registry_links.py", "--write"], cwd=ROOT, check=True)
    subprocess.run(["python", "tools/registry_links.py"], cwd=ROOT, check=True)
    print(json.dumps(check))

if __name__ == "__main__":
    main()
