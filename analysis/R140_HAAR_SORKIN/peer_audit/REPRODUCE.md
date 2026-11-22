# Повтор проверки R140

В архиве R140_peer_audit.zip находятся только таблица историй R140, проверяющая программа, её результат, разбор и эта инструкция. Имена файлов отсчитываются от корня репозитория. После распаковки проверить контрольные суммы командой ниже.

~~~bash
sha256sum -c R140_PEER_AUDIT.sha256
~~~

**Четыре нулевых исхода, полная вариация, 4186 пар и контраст двух считываний.** В каталоге с распакованным архивом нужны Python и NumPy. Результат содержит раздел endpoints из CHECKS.json. Программа проверяет целые числители амплитуд и точные дроби до вывода результата.

~~~bash
python analysis/R140_HAAR_SORKIN/peer_audit/verify.py --endpoints-only
~~~

**Динамика на нескольких углах и тест уточнения.** Распаковать исходный пакет, затем пакет текущей проверки в один каталог или использовать checkout ветки R140. Исходный пакет содержит оператор R140 и донорские модули, которые он импортирует. Требуются Python, NumPy, SciPy и SymPy. Команда сверяет все поля результата. [Исходный пакет на зафиксированном коммите](https://github.com/IgorSabirov/vm-lab/raw/6ba42e89e603855bfddf42c585a1057945b9d769/analysis/R140_HAAR_SORKIN/R140_reproduction.zip)

~~~bash
set -o pipefail
OPENBLAS_NUM_THREADS=1 python analysis/R140_HAAR_SORKIN/peer_audit/verify.py \
  | diff -u analysis/R140_HAAR_SORKIN/peer_audit/CHECKS.json -
~~~

[Оригинал третьего отзыва](https://github.com/IgorSabirov/vm-lab/blob/research/r140-haar-sorkin/analysis/R140_HAAR_SORKIN/reviews/03_invariants_and_records.txt) · [Карточка исследования](https://github.com/IgorSabirov/vm-lab/pull/205).
