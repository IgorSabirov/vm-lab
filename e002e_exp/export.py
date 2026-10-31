"""Lossless machine report, local full arrays and a portable result summary."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from e002_exp.model import save_json
from .numerics import ratio, contrast, FLOOR


def serial(value):
    if isinstance(value, complex):
        if not np.isfinite([value.real, value.imag]).all():
            raise ValueError('Nonfinite complex output')
        return dict(re=float(value.real), im=float(value.imag))
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, np.generic):
        return serial(value.item())
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def real_values(values, tolerance=1e-9):
    out = {}
    for name, v in values.items():
        if name.startswith('C_'):
            out[name] = complex(v)
        elif abs(complex(v).imag) > tolerance:
            raise ArithmeticError('Hermitian observable has imaginary residue: '+name)
        else:
            out[name] = float(complex(v).real)
    return out


def conditional_values(raw, errors=None):
    errors = errors or {}
    def conditional(h, p):
        return ratio(raw[h], raw[p], errors.get(h), errors.get(p))
    out = {}
    for key in raw:
        if key.startswith('p_m') and '_N' in key:
            suffix = key[1:]; out['j'+suffix] = conditional('h'+suffix, key)
        if key.startswith('p_N'):
            out['j'+key[1:]] = conditional('h'+key[1:], key)
    if 'P_m6_N2' in raw:
        out['j6'] = conditional('h6', 'P_m6_N2')
    if 'p_e' in raw:
        out['F_over_p_e'] = conditional('F', 'p_e')
    return out


def validate_conditionals(raw, conditioned, errors=None):
    expected = conditional_values(raw, errors)
    if set(expected) != set(conditioned):
        raise ValueError('Conditional fields mismatch')
    for key, item in expected.items():
        actual = conditioned[key]['value']
        if (item['value'] is None) != (actual is None):
            raise ValueError('Conditional null policy mismatch')
        if actual is not None and (not np.isfinite(actual) or abs(actual-item['value']) > 1e-12*max(1., abs(actual))):
            raise ValueError('Conditional reconstruction mismatch')
        if conditioned[key].get('uncertainty') != item['uncertainty']:
            raise ValueError('Conditional uncertainty mismatch')


def summaries(records):
    groups = {}; results = []
    for rec in records:
        c = rec['case']
        fields = ('model', 'dimension', 'mask', 'phi_over_pi', 'node_noise', 'm6_v_over_J', 'v_over_J', 'source', 'sink', 'jump_convention', 'block')
        # R and F1 are one baseline line; F2 remains separated by physical v.
        key = tuple((k, c.get(k)) for k in fields if k != 'block')
        groups.setdefault(key, {})[float(c['epsilon'])] = rec
    for key, line in groups.items():
        if not all(e in line for e in (-.125, 0., .125)):
            continue
        common = set.intersection(*(set(line[e]['conditional']) for e in (-.125, 0., .125)))
        for name in sorted(common):
            result = contrast(*(line[e]['conditional'][name] for e in (-.125, 0., .125)), .125)
            results.append(dict(physical_group=dict(key), observable=name, delta=.125, **result))
    return results


def save_case(report, full, record, state, space):
    case_id = record['id']; validate_conditionals(record['raw'], record['conditional'], record.get('primitive_uncertainty'))
    np.savez_compressed(full/(case_id+'_state.npz'), reduced_state=state, full_indices=space.indices,
                        charges=space.charges, rho=space.unpack(state))
    save_json(report/(case_id+'.json'), serial(record))


def save_correlations(report, full, case_id, fine, coarse, refinement):
    np.savez_compressed(full/(case_id+'_qrt_final.npz'), fine=fine['final'], coarse=coarse['final'])
    np.savez_compressed(report/(case_id+'_qrt.npz'), time=fine['times'], C=fine['C'], coarse_C=coarse['C'],
                        normalized=fine['normalized'], normalization_valid=fine['normalization_valid'])
    absval = abs(fine['C']); flat = absval.reshape(len(fine['times']), -1)
    extrema = []
    for col in range(flat.shape[1]):
        i = int(np.argmax(flat[:, col])); j = int(np.argmin(flat[:, col]))
        extrema.append(dict(output=col//fine['C'].shape[2], input=col%fine['C'].shape[2],
                            max_abs=float(flat[i, col]), time_max=float(fine['times'][i]),
                            min_abs=float(flat[j, col]), time_min=float(fine['times'][j])))
    result = dict(fine=fine['summary'], coarse=coarse['summary'], refinement=refinement,
                  extrema_all_saved_samples=extrema, time_grid_retained='all common samples; no downsampling')
    save_json(report/(case_id+'_qrt.json'), serial(result))
    return result


def write_manifest(report):
    entries = []
    for p in sorted(Path(report).iterdir()):
        if p.is_file() and p.name != 'manifest.json':
            entries.append(dict(path=p.name, size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    save_json(Path(report)/'manifest.json', dict(files=entries, total_bytes=sum(x['size'] for x in entries)))


def write_full_manifest(report, full):
    entries = []
    for p in sorted(Path(full).iterdir()):
        if p.is_file():
            entries.append(dict(path=p.name, size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    save_json(Path(report)/'full_manifest.json', dict(files=entries, total_bytes=sum(x['size'] for x in entries),
                                                    storage='full/ stays on VM; hashes are published'))
    save_json(Path(report)/'data_manifest.json', dict(full_files=entries,
        full_total_bytes=sum(x['size'] for x in entries),
        selection='All declared case records and response values are published; QRT retains every common sample',
        detail_not_published='Full state matrices, QRT final vectors and checkpoints remain on VM; their hashes are in full_manifest.json',
        full_data_access='Only after a separate explicit instruction from the user'))


def write_result(report, config, records, failure, gate, comparisons, qrt_summaries):
    lines = [f"Время: прогноз {gate['expected_seconds']:.6g} с; факт внутреннего участка {gate['actual_seconds']:.6g} с; "
             f"отклонение {gate['deviation_seconds']:.6g} с; статус {gate['status']}. Полное время процесса проверяется по run.json.",
             '', '# E002e: '+config['stage'], '',
             'Режим: '+config['mode']+'. Источник: '+config.get('source_commit', 'UNKNOWN')+'.',
             'Объём план/факт: '+json.dumps(gate['expected_counts'])+' / '+json.dumps(gate['actual_counts'])+'.',
             'Полная физика: 3 двухуровневых узла и 3 трёхуровневых ребра; 216 состояний, q=0: 14580 координат. '
             'J=1, источник/сток=0,5, шум узлов=0,05; точные параметры каждого случая сохранены.',
             '', '## Состояние проверки', '',
             'Ошибка: '+(failure or 'не зарегистрирована')+'.',
             'Малые невязки не являются гарантией ошибки наблюдаемых. Оценки условных величин без независимого '
             'уточнения помечены ERROR_UNRESOLVED. Автоматического вывода о Фано нет.',
             '', '|Случай|Модель/геометрия|ε|F|j6 или F/p_e|NESS|', '|---|---|---:|---:|---:|---|']
    for r in records:
        c = r['case']; j = r['conditional'].get('j6', r['conditional'].get('F_over_p_e', {})).get('value')
        js = 'null' if j is None else f'{j:.8g}'
        lines.append(f"|{r['id']}|{c.get('model', str(c.get('dimension'))+'/'+str(c.get('mask')))}|{c['epsilon']:g}|{r['raw']['F']:.8g}|{js}|{r['quality']['pass']}|")
    lines += ['', 'Показатели таблицы округлены до 8 значащих цифр; JSON/NPZ сохраняют исходные числа.',
              'Контрасты всех доступных троек: contrasts.json. Корреляции: все временные отсчёты в *_qrt.npz; '
              'экстремумы по ним в *_qrt.json. Неразрешённый хвост помечен TAIL_UNRESOLVED.',
              'Отклики с нулевым следом не проверяются на положительность состояния. '
              'Новые фон/резонансные разложения требуют физического обоснования и отложенных предсказаний.',
              'Паспорта среды до/после, фактические счётчики и фазовые времена: metrics.json; контрольные суммы: manifest.json.',
              'Полные состояния и финальные QRT-векторы остаются в full/. Проверка времени предшествует научной приёмке.']
    text = '\n'.join(lines)+'\n'
    if len(text.encode()) > 24*1024:
        raise ValueError('RESULT exceeds portable report cap; no silent truncation')
    (Path(report)/'RESULT.md').write_text(text)
    # The GitHub bridge's medium-v1 contract requires README.md as well.
    (Path(report)/'README.md').write_text(text)


def verify_report(report, full=None):
    report = Path(report); manifest = json.loads((report/'manifest.json').read_text())
    listed = [entry['path'] for entry in manifest['files']]
    if len(listed) != len(set(listed)) or set(listed) != {p.name for p in report.iterdir() if p.is_file() and p.name != 'manifest.json'}:
        raise ValueError('Report manifest completeness mismatch')
    status_path = report/'status.json'
    if status_path.exists() and json.loads(status_path.read_text()).get('status') == 'FAILED':
        raise ValueError('Failed run cannot be verified as complete')
    for entry in manifest['files']:
        name = Path(entry['path'])
        if name.name != str(name):
            raise ValueError('Unsafe manifest path')
        p = report/name
        if p.stat().st_size != entry['size'] or hashlib.sha256(p.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Report hash mismatch')
        if p.suffix == '.json' and p.name.startswith(('full_', 'small_')) and '_qrt' not in p.name and p.name != 'full_manifest.json' and not p.name.endswith('_failure.json'):
            r = json.loads(p.read_text())
            validate_conditionals(r['raw'], r['conditional'], r.get('primitive_uncertainty'))
    full_status = 'NOT_CHECKED_REQUIRES_EXPLICIT_RAW_ACCESS'
    if full is not None:
        full = Path(full); m = json.loads((report/'full_manifest.json').read_text())
        names = [e['path'] for e in m['files']]
        if len(names) != len(set(names)) or set(names) != {p.name for p in full.iterdir() if p.is_file()}:
            raise ValueError('Full data completeness mismatch')
        for e in m['files']:
            name = Path(e['path'])
            if name.name != str(name):
                raise ValueError('Unsafe full-data path')
            p = full/name
            if p.stat().st_size != e['size'] or hashlib.sha256(p.read_bytes()).hexdigest() != e['sha256']:
                raise ValueError('Full data hash mismatch')
        full_status = 'VERIFIED'
    return dict(status='REPORT_BYTES_AND_CONDITIONALS_VERIFIED', files=len(manifest['files']), full_data=full_status)
