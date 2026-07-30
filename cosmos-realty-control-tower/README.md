# Cosmos Realty Control Tower — Audit MVP

Безопасный read-only аудит Bitrix24 для задач CR-BI-001–005.

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
```

Результаты создаются в `output/`. Они не добавляются в Git. Клиент разрешает
только методы из явного списка чтения и блокирует любые неизвестные или
изменяющие методы до сетевого запроса.

## Проверки

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

Подробности: `docs/architecture.md`, `docs/security.md`, `docs/data-audit.md`.
