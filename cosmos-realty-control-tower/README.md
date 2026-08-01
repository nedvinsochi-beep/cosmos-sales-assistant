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

Команда создаёт в `output/rop/`:

- `rop-dashboard.html` — локальный экран РОПа;
- `rop-report.md` и `rop-report.json` — итог и ограничения;
- `rop-control.csv` — карточки, требующие внимания;
- `rop-brokers.csv` — нагрузка и дисциплина брокеров;
- `dry-run-actions.csv` — будущие действия роботов без выполнения.

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

## Проверки

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

Подробности: `docs/architecture.md`, `docs/control-rules.md`,
`docs/cosmos-business-data-model.md`, `docs/security.md`.
