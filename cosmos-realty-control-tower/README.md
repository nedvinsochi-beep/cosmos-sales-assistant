# Cosmos Realty Control Tower — контроль РОПа

Безопасный read-only аудит Bitrix24 и прикладной MVP контроля РОПа для задач
CR-BI-001–010.

## Быстрый старт

```bash
cp .env.example .env
# Впишите локальный входящий webhook только с правами чтения.
uv sync
uv run cosmos-control audit-bitrix
```

Без `.env` можно проверить весь локальный конвейер:

```bash
uv run cosmos-control demo
uv run cosmos-control report --demo --department 2 --period week
```

Рабочий read-only отчёт с локальным webhook:

```bash
uv run cosmos-control report --department 2 --period week
uv run cosmos-control report --broker 123 --period month
uv run cosmos-control report --rop 45 --period week
uv run cosmos-control report --source WEB --period month
uv run cosmos-control report --stage NEW --period today
```

По умолчанию показывается только предлагаемый оперативный периметр. Переключение:

```bash
uv run cosmos-control report --work-scope operational
uv run cosmos-control report --work-scope warm
uv run cosmos-control report --work-scope archive --include-inactive-employees
uv run cosmos-control report --work-scope all
```

Правила калибровки имеют статус `PROPOSED_REQUIRES_APPROVAL`: они уменьшают
ложные тревоги, но не являются утверждённым регламентом.

Команда создаёт в `output/rop/`:

- `rop-dashboard.html` — локальный экран РОПа;
- `rop-report.md` и `rop-report.json` — итог и ограничения;
- `rop-control.csv` — карточки, требующие внимания;
- `rop-brokers.csv` — нагрузка и дисциплина брокеров;
- `dry-run-actions.csv` — будущие действия роботов без выполнения.

Дополнительно создаются `output/calibration-summary.html` и
`output/calibration-summary.csv` с причинами исключений и обезличенными
примерами.

Для короткой live-проверки можно ограничить число прочитанных записей:

```bash
uv run cosmos-control report --department 2 --period week --limit 100
```

Повторная генерация без нового обращения к порталу:

```bash
uv run cosmos-control report --snapshot output/rop/operational-snapshot.json
```

Результаты создаются в `output/`. Они не добавляются в Git. Клиент разрешает
только методы из явного списка чтения и блокирует любые неизвестные или
изменяющие методы до сетевого запроса.

`report` по умолчанию подключается к Bitrix24 только на чтение. Флаг `--demo`
полностью исключает подключение. Реализации write-методов и отправки уведомлений
в проекте нет: роботы формируют только preview с `dry_run=true`.

## Робот «Потеряшка» — только dry-run

Утверждённое правило проверяет в 23:50 по Москве лиды, оставшиеся в стадии
`Новый лид — раздача`. Без подключения к Bitrix24:

```bash
uv run cosmos-control acceptance-control --dry-run --as-of "23:50" --demo
```

Live read-only preview:

```bash
uv run cosmos-control acceptance-control --dry-run --as-of "23:50"
```

Bitrix24 пока не отдаёт точное время назначения ответственного, поэтому команда
не подменяет его временем создания или изменения карточки и блокирует опасные
возвраты. `--apply` существует только как закрытый интерфейс и завершается до
подключения к CRM. Подробности: `docs/acceptance-control-rule.md`.

## Правила контроля

«Потеряшка» и «Без следующего шага» работают через общий небольшой движок:

```bash
uv run cosmos-control rules list
uv run cosmos-control rules preview MISSED_LEAD_ACCEPTANCE --demo
uv run cosmos-control rules preview NO_NEXT_STEP --demo
uv run cosmos-control rules run-all --dry-run --demo
```

Конфигурация: `config/rules.example.json`, контракт:
`schemas/rule.schema.json`, экран: `output/rules/rules-dashboard.html`.
`ACTIVE` и `--apply` заблокированы. Подробности: `docs/rules-engine.md`.

## Проверки

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

Подробности: `docs/architecture.md`, `docs/control-rules.md`,
`docs/rules-calibration.md`, `docs/operational-scope.md`,
`docs/exclusion-rules.md`, `docs/cosmos-business-data-model.md`,
`docs/acceptance-control-rule.md`, `docs/rules-engine.md`, `docs/security.md`.
