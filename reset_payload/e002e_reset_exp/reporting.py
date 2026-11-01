"""Portable result <=24 KiB; primitive vectors and certificates remain available."""
from .plan import PROTOCOL


def render(config,metrics,records):
    g=metrics['runtime_gate']
    lines=[f"# E002e RESET: {config['mode']}",
        f"Время: прогноз {g['expected_seconds']:.6g} с; факт внутреннего участка {g['actual_seconds']:.6g} с; статус {g['status']}. Полное время — по служебному run.json.",
        f"Source: `{config['source_commit']}`. Протокол: `{metrics['protocol_sha256']}`.",
        'J=1, Φ=π/2, ε=0, v=1, φ_n=0,05. QS и RR_QS; γ=0/0,001/0,002. Полное пространство 216, q=0:14580.',
        f"План/факт объёма: {metrics['counts']}. Внутренние обращения к факторам учтены отдельно в каждом solver record.",
        'Primary — знак производной S_F(QS), LU-ветвь с собственным фиксированным τ_E. GMRES проверяет решение и чувствительность к baseline; ветви не усредняются.']
    for rec in records:
        lines+=['',f"## {rec['model']}"]
        if config['mode']=='calibration':
            lines+=['Только известные baseline и закреплённые случайные бесследовые RHS. Новые S_F/F_ss(γ>0) не вычислены.']
        else:
            r=rec['result'];s=r['sign'];w=r['window'];tail=r['tail']
            lines += [f"S_F={s['value']:.12g} ± {s['uncertainty']:.3g}; H_sign: {s['status']}.",
                f"A₂₀={rec['area_reference']:.12g}; H_window: {w['status']}; Δ_tail={tail['value']:.12g} ± {tail['uncertainty']:.3g}.",
                f"Слабый режим: {r['linearity_status']}.",
                '', '| γ | ΔF | u_ΔF | Qγ | Линейность |','|---|---:|---:|---:|---|']
            for p in r['finite']:lines.append(f"| {p['gamma']} | {p['delta_F']:.12g} | {p['u_delta_F']:.3g} | {p['Q']:.12g} | {p['linearity']['status']} |")
            lines+=['','| γ | F | ΔE/event | P_reset | I(N:E) |','|---|---:|---:|---:|---:|']
            for row in rec['rows']:
                if row['method']=='lu':
                    d=row['diagnostics'];lines.append(f"| {row['gamma']} | {row['raw']['F']:.12g} | {d['energy']['delta_E_event']:.8g} | {d['energy']['P_reset']:.8g} | {d['correlations']['mutual_information']:.8g} |")
        rows=rec['rows']
        lines += [f"Факторизации: {len(rows)}; обращения к факторам: {sum(x['solver']['counts']['factor_calls'] for x in rows)}; обработанные столбцы RHS: {sum(x['solver']['counts']['factor_rhs_columns'] for x in rows)}.",
                  'Экспортированы обе ветви, векторы, хеши targets, невязки, PSD/sector/balance и сертификат единственности.']
    lines+=['','## Ограничения',
        'Интервалы инженерные; согласие решателей и onenormest не являются строгой границей общей ошибки. 20%/10% — научные полосы, численные допуски отдельны.',
        'Каждый reset сохраняет узловое состояние и заменяет рёбра фиксированным τ_E. При конечном γ это одновременно удаление корреляций и закрепление marginal рёбер.',
        'Δ_tail — площадь, не время релаксации или спектральная ширина. P_reset не равен полной цене внешнего устройства.',
        'Фано, квантовая специфичность, объяснение всего преимущества QS и автопоэзис не устанавливаются. Ширина/фон остаются UNRESOLVED.',
        'Все научные точки и диагностические векторы опубликованы; непубликованный архив для этой проверки не нужен. Результат требует приёмки пользователем.']
    result='\n'.join(line if line.startswith('|') or not line else line+'\n' for line in lines)+'\n'
    if len(result.encode())>24576:raise ValueError('Portable report too large')
    return result
