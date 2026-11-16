"""Build the result report from the complete raw verification, never forecast as fact."""
from pathlib import Path
import json,hashlib
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def main():
    out=HERE/'results/S3_DD_CONVERGENCE_20261116_r1'
    s=read(out/'SUMMARY.json');v=read(HERE/'VERIFICATION.json');forecast=read(out/'LOCAL_FORECAST.json')
    good=sum(r['status']=='STEP_CONVERGED' for r in v['rows']);bad=8-good
    he=s['results']['He3_H_late']['derivatives']['ddtp'];negative=all(x<0 for x in he.values())
    lines=['# D+D: восемь интеграций h=0.25 и 0.125', '',
      f'**Все восемь интеграций завершены. Финальный шаговый критерий 1%: {good}/8 компонент PASS, {bad}/8 FAIL.**', '',
      ('He3/ddtp остаётся отрицательным на всех четырёх шагах: положительная пререгистрированная гипотеза противоречит полученным откликам.' if negative else 'Знак He3/ddtp меняется между шагами; см. таблицу.'),
      'Научная приёмка остаётся `false`. Арифметическая репликация и техническое завершение не удостоверяют ошибку решателя или предел h→0.', '',
      '## Данные и условия', '',
      f'- Исходники до запуска: [{s["source_sha"][:8]}](https://github.com/IgorSabirov/vm-lab/commit/{s["source_sha"]}).',
      '- Родитель: [1ce668ca](https://github.com/IgorSabirov/vm-lab/commit/1ce668ca5bd1d79a128f0c1f761c1ff93ebe3464), девять интеграций h=1 и 0.5.',
      '- Задача: [#79](https://github.com/IgorSabirov/vm-lab/issues/79). Ранее выполненная репликация: [отчёт](../neighbor_review_20261116/REPORT.md).',
      '- Неизменны LINX bfba07c77a5fcba1cc772d42f2d9e9be8a542df8, key_PRIMAT_2023, таблицы, адаптер, общий background.npz, all-other-q=0, Kvaerno3, rtol=1e-6, atol=1e-9, float64.',
      '- Использованы прежние нулевой baseline и фон; девятой дополнительной интеграции не было. Автоматических повторов и изменения допусков не было.',
      '- [UPSTREAM_VERIFICATION.json](UPSTREAM_VERIFICATION.json): 38 используемых файлов сверены по SHA-256 и Git blob SHA; сопоставлены с внешним деревом 197 записей без усечения; прежний патч воспроизведён точно. Неиспользуемые файлы LINX не загружались.',
      '- [WORKER_CHANGES.patch](WORKER_CHANGES.patch): изменения worker ограничены допустимыми q, расположением исходного контракта и экспортом метаданных.',
      '- Физическое rho не измерялось; MC/GP, likelihood, анализ реакционных потоков и оценка пола ошибки не выполнялись.', '',
      '## Фактическая сходимость', '',
      '| Выход | Канал | a(0.25) | a(0.125) | расхождение, % | статус | p |',
      '|---|---|---:|---:|---:|---|---:|']
    for r in v['rows']:
        lines.append(f'| {r["observable"]} | {r["channel"]} | {r["a_h0_25"]:.12g} | {r["a_h0_125"]:.12g} | {r["gap_percent"]:.6f} | {r["status"]} | {r["p"]:.4f} |')
    lines += ['', 'Расхождение = abs(a(h)−a(h/2))/max(abs(a(h)),abs(a(h/2))). Порог <1%; near-zero max|a|<1e-8 выделяется отдельно. Все указанные проценты — измеренные конечные разности, не прогноз.', '',
      'Порядок p=log2(|a(.5)−a(.25)|/|a(.25)−a(.125)|) носит диагностический характер. h=.5 получен в прежней hosted-среде, малые шаги — на локальном CPU, при одинаковом численном dependency lock; дополнительного мостового прогона не было. Поэтому изменение среды входит в интерпретацию p. Финальный критерий .25→.125 сравнивает две реализации в одной локальной среде.', '',
      'Нарушение ожидаемого уменьшения ошибки не устанавливает единственную причину. Оно может отражать ошибку интегратора, особенности адаптивного решения, неасимптотический шаг или отмену членов. Этот пакет различает фактическую сходимость и условный прогноз; диагностика конкретной причины требует отдельного опыта.', '',
      '## κ и условный Ричардсон', '',
      '| Выход | κ(0.25) | κ(0.125) | κ_R по .25/.125 |', '|---|---:|---:|---:|']
    for obs,r in s['results'].items():
        lines.append(f'| {obs} | {r["by_step"]["0.25"]["kappa"]:.10f} | {r["by_step"]["0.125"]["kappa"]:.10f} | {r["richardson"]["0.25_to_0.125"]["kappa"]:.10f} |')
    lines += ['', 'Ричардсон `(4*a(h/2)−a(h))/3` приведён как вычисленная условная комбинация. Если предпосылка ведущего h² не подтверждается, экстраполяцию нельзя выдавать за более точное значение. Все квадратичные формы и rho-сетки сохранены в [SUMMARY.json](results/S3_DD_CONVERGENCE_20261116_r1/SUMMARY.json).', '',
      '## Знак и вклад компонент', '',
      '| h | He3/ddtp |', '|---|---:|']
    for h in ['1.0','0.5','0.25','0.125']:lines.append(f'| {h} | {he[h]:.12g} |')
    lines += ['', 'Точное разложение конечного логарифмического отклика при h=.125 использует логарифмическое среднее суммы и собственный H каждого прогона. Это разложение по видам, не анализ причинных реакционных потоков.', '',
      '| Сумма | Канал | вклад первого вида | вклад второго вида |', '|---|---|---:|---:|']
    for obs,channels in v['finite_window_component_contributions_h0_125'].items():
        for ch,con in channels.items():
            (n1,x),(n2,y)=con.items();lines.append(f'| {obs} | {ch} | {n1}: {x:+.12g} | {n2}: {y:+.12g} |')
    lines += ['', '## Эпоха и исполнение', '',
      f'В новые RESULT экспортированы t_network_start={v["t_network_start_seconds"]:.12g} с и t_network_end={v["t_network_end_seconds"]:.12g} с модельного космического времени. Конец сети T=6×10⁷ K. `post_decay_projection_applied=true`, `observation_epoch=complete_decay_limit`; это не интеграция до конечной эпохи распада Be7 или трития.', '',
      f'Восемь процессов по supervisor: **{s["integration_supervisor_wall_seconds"]:.3f} с**. Вычисление с агрегацией: **{s["wall_seconds_compute_and_analysis"]:.3f} с**. Первый полный член матрицы — {forecast["measured_first_full_integration_seconds"]:.3f} с; записанный до остальных семи прогноз — {forecast["remaining_forecast_seconds"]:.3f} с.', '',
      'Допуск локального исполнения: 60 с на процесс, 480 с на вычислительную секцию, 600 с на пакет с резервами setup/verification/publication. Подготовка исходников и установленной среды выполнена до допуска; вычислительное время не выдаётся за полное время переписки и подготовки. Прежние пределы 600/5400/6600 относятся к родительскому пакету.', '',
      f'[VERIFICATION.json](VERIFICATION.json): проверены {v["verified_artifact_hashes"]} хешей артефактов, восемь сырых векторов, 16 новых производных, четыре κ и восемь финальных расхождений. rel_tol=2e-12, abs_tol=2e-15 — арифметические допуски, не ошибка интегратора.', '',
      '## Открытые вопросы', '',
      '1. Если малые шаги не закрывают критерий, следующий различающий опыт — отдельно спланированное ужесточение rtol/atol с контролем вычислительной среды; уменьшать h автоматически дальше нельзя. Сам пол ошибки здесь не измерен.',
      '2. Причинное объяснение He3/ddtp требует анализа реакционных потоков. Компонентное разложение локализует итог, но не восстанавливает пути сети.',
      '3. Наблюдательная идентифицируемость требует C_obs; rho двух каналов остаётся свободным параметром.',
      '4. Baseline Yp=0.2472485207 отличается от приведённого Aver et al. 2026 BBN+Planck 0.2467 на 0.0005485207, то есть 2.743 их quoted sigma=0.0002. Это не установленное статистическое противоречие: у нашего baseline нет сопоставимой полной ошибки и согласованных параметров. Причину нельзя заранее свести к набору скоростей; сверять следует также baryon density/eta, tau_n, weak/radiative настройки и версию сети. Эта сверка не выполнялась и не входит в восемь интеграций. Источник: https://arxiv.org/abs/2601.22238v1.', '',
      'Научная приёмка принадлежит пользователю. Техническое завершение, публикация и открытость/закрытость #79 не изменяют её автоматически.', '']
    (HERE/'REPORT.md').write_text('\n'.join(lines))
    old=HERE.parent/'ANALYSIS_REPORT.md';text=old.read_text()
    text=text.replace('**Статус:** анализ и проектирование; D+D response расчёт не запускался; научная приёмка `false`.',
      f'**Актуальный статус, 16 ноября 2026:** девять исходных D+D интеграций и восемь меньших шагов завершены. Положительная гипотеза He3/ddtp отклоняется полученными знаками. Финальный шаговый критерий: {good}/8 PASS, {bad}/8 FAIL; научная приёмка `false`.\n\nТекущие числа, сырые выходы и границы: [отчёт восьми интеграций](refinement_20261116/REPORT.md), [встречная проверка](neighbor_review_20261116/REPORT.md). Ниже сохранена исходная постановка; датированные замечания о готовности относятся к прежнему снимку, не к сегодняшнему запуску.')
    text=text.replace('Новый Run 0 остаётся необходимым.','Для исходного пакета требовался новый Run 0; он уже выполнен и опубликован на 1ce668ca. Его фон и baseline переиспользованы для восьми меньших шагов.')
    start=text.index('### 4.3 Никаких');end=text.index('## 5. Генеалогия',start)
    text=text[:start]+'''### 4.3 Полученные отклики и оставшиеся границы

Девять интеграций h=1/0.5 опубликованы на 1ce668ca; восемь интеграций h=.25/.125 — в [текущем отчёте](refinement_20261116/REPORT.md). Получены a_i, κ, шаговые диагностики и условные rho-таблицы. Положительная знаковая гипотеза He3/ddtp противоречит вычисленным откликам. Научная приёмка остаётся false.

Correlated Monte Carlo, GP posterior и физическое rho не получены; observational likelihood, CMB, BH1 и S2 не входят в эти пакеты. Ни арифметическая репликация, ни Ричардсон не заменяют оценки ошибки решателя.

'''+text[end:]
    text=text.replace('## 6. Инженерный статус текущей ветки: до dispatch ещё не готово','## 6. Исторический статус до первого запуска — снимок f7b6060')
    text=text.replace('## 7. Границы следующего результата','## 7. Границы исходного дизайна и полученного результата')
    text=text.replace('Если перечисленные инженерные несоответствия будут закрыты и девять интеграций пройдут, результатом этого пакета станут:','Исходный дизайн предусматривал следующие выходы; они теперь получены в опубликованных raw и SUMMARY, с указанными в текущем отчёте численными ограничениями:')
    text=text.replace('Это будет **локальная двухкоординатная чувствительность стандартной BBN**','Это **локальная двухкоординатная чувствительность стандартной BBN**')
    old.write_text(text)
    gp=HERE.parent/'GENEALOGY.json';g=read(gp)
    g['status_before_refinement_update']=g['scientific_status']
    g['scientific_status']={'original_nine_integrations':'COMPLETE','smaller_step_integrations':8,'numerical_step_gate':s['numerical_step_gate'],'scientific_acceptance':False}
    g['refinement_20261116']={'parent_result_commit':s['parent_result_commit'],'source_commit':s['source_sha'],'plan_commit':'cf5f3df9696cddd7c302ed42d45764c34d97de7b','report':'refinement_20261116/REPORT.md','summary':'refinement_20261116/results/S3_DD_CONVERGENCE_20261116_r1/SUMMARY.json','issue':79,'new_integrations':8,'automatic_retry':False,'scientific_acceptance':False}
    g['genealogy_notes'].append('Earlier no-integration statements describe the historical branch snapshot. The 20261116 refinement field and current report supersede that status, while preserving the old record.')
    gp.write_text(json.dumps(g,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'passed_components':good,'failed_components':bad,'He3_ddtp_negative_all_four_steps':negative}))

if __name__=='__main__':main()
