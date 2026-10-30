Время: прогноз 1072.671632 с; диапазон 643.602979–1501.740284 с; внутренний факт 1069.3541795859928; статус PASS.
Полный факт проверяется отдельно по run.json: job.finished − job.started; очередь и публикация отдельно.
Запуск E002c_IC_RETRY_v001_r001; код 535dfd231f00a93f74c2c216ff07baeb3ab2aac6; kernel 50b45825b56e5f5b5b7061a999325d4b5b7755de1ff13402b14ac49735e7e3a8.
Объём: 54 траекторий, 580000 шагов, 2320000 RHS, 54054 scalar, 5454 diagnostic, 594 snapshots.
Проверки: volume=True; failures=[].
IC-статусы: {'ic_structural_status': 'structural_PASS', 'ic_transport_status': 'structural_matched_hop_mismatch'}. Шесть целей pL/ell, три alpha, никаких новых каналов; hop не входит в поиск.
Поиск: 53 вызовов, 52 вычислений, 1 попаданий кэша; максимум 141 вызов. Не доказательство глобальной невозможности IC-1.

|Старт|Вызовы|Различных alpha01/12/02|Оптимизатор status/success|
|---|---:|---|---|
|0.25|7|[3, 3, 3]|None/False|
|1.0|19|[8, 8, 8]|1/True|
|4.0|27|[13, 13, 13]|1/True|

Выбрано alpha=[0.06489310345717117, 0.06489313511138023, 0.07065096360073866]; max error=0.0018757323679257113; SHA256=021b2eff5265da81ddbfc018bbbcbad0c924fb3dc1ac9d2e6a9dcc526aeb1908.
Валидация: structural_pass=True; шесть ошибок dt.01/.005=[[0.00017439560735011685, 0.0001742413960705116, 0.001871505385545374, 0.00017558890430866578, 0.00017574572641100821, 0.0018757323679273411], [0.00017439560734917316, 0.00017424139607035433, 0.0018715053855457944, 0.0001755889043093357, 0.00017574572641127617, 0.0018757323679266169]]; dt pass=True.
Held-out transport: {'evaluable': True, 'comparison': {'policy': 'same_horizon_stationary_or_fixed_window_200_v1', 'kind': 'stationary', 'comparable': True, 'reasons': [], 'case_ids': ['QS_P05_dt005', 'RETRY_VALIDATE_0.005'], 'horizons': [200.0, 200.0], 'window': [190.0, 200.0], 'evidence_level': 'REFINEMENT_CHECKED'}, 'QS_case_id': 'QS_P05_dt005', 'IC_case_id': 'RETRY_VALIDATE_0.005', 'baseline_source': {'run_id': 'E002c_REPAIR_v001_r001', 'report_commit': '7fd36d60044b436484e81a5e92a80163c4688b45', 'metrics_sha256': 'b7ca2385a31a7bd9a1e95c47fa61706188ccbcb5578bdf342d9b40837ab12f45'}, 'QS_h': 0.1098400932168605, 'IC_h': 0.09328301404644547, 'relative_error': 0.1507380291249927, 'denominator_QS': 0.1098400932168605}.
Подробности: metrics.json, checks.json, data_manifest.json. Исходные прогоны и их статусы не изменены.
