# Небольшой движок правил Cosmos Control Tower

Движок один раз реализует режим безопасности, расписание, исключения, preview,
эскалацию, KPI, ссылки, идемпотентность и журнал. Бизнес-правила хранятся в
`config/rules.example.json`. Это не браузерный конструктор и не отдельная CRM.

Обязательные поля проверяются Pydantic-моделью и `schemas/rule.schema.json`.
Режимы: `OFF`, `DRY_RUN`, `APPROVAL_REQUIRED`, `ACTIVE`. Последний технически
описан, но сейчас заблокирован движком, как и `--apply`.

```bash
uv run cosmos-control rules list
uv run cosmos-control rules preview MISSED_LEAD_ACCEPTANCE
uv run cosmos-control rules preview NO_NEXT_STEP
uv run cosmos-control rules run-all --dry-run
uv run cosmos-control rules apply NO_NEXT_STEP  # заблокировано
```

Результаты находятся в игнорируемом `output/rules/`: единые HTML, JSON и CSV.
Dry-run читает локальный ledger, но никогда его не изменяет. Запись журнала после
успешного apply будет отдельной задачей после разрешения write-операций.

## Добавление третьего правила

Простое правило добавляется записью JSON по схеме, тестовым примером и запуском
preview. Если нужен сложный расчёт, добавляется небольшой `evaluator` в реестр
`RulesEngine`; CLI, отчёты, безопасность, режимы и журнал не копируются.
