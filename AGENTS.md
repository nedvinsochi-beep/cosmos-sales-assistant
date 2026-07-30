# AGENTS.md

## Project

Cosmos Realty Sales Assistant / Control Tower.

## Mission

Build a reliable BI- and AI-control system on top of Bitrix24 data for Cosmos Realty.

The system must separate management levels:

- broker: personal work queue and performance;
- head of sales department (РОП): department management and intervention queue;
- owner: control of РОПs, company economics, risks and forecasts;
- AI auditor: CRM discipline and data integrity;
- AI analyst: explanations and recommendations.

## Source of truth

Read these files before any implementation:

1. `README.md`
2. `docs/Cosmos_Realty_Control_Tower_TZ_v0.1.md`
3. `CODEX_START.md`

## Mandatory safety rules

Until explicit approval is recorded in the repository:

- operate in read-only mode against Bitrix24;
- do not create, update or delete CRM entities;
- do not create or close tasks;
- do not move leads or deals between stages;
- do not change Bitrix24 settings;
- do not commit secrets;
- do not commit webhook URLs, tokens, passwords or cookies;
- do not include client phone numbers, emails, names or message texts in sample data;
- redact personal data in logs and fixtures;
- never invent Bitrix24 field names, IDs, stages or scopes.

## Engineering rules

- Use typed Python or TypeScript. Prefer the stack already present; if the repository is empty, use Python 3.12 with `uv`, `pydantic`, `httpx`, `pytest`, `ruff`, and `mypy`.
- Keep Bitrix24 integration behind a client interface.
- Implement pagination, retries, backoff, timeout, rate limiting and structured logging.
- All metric definitions must be documented in `docs/metrics.md`.
- All discovered Bitrix24 fields must be documented in `docs/data-dictionary.md`.
- All unresolved business questions must be documented in `docs/open-questions.md`.
- Every calculated metric must be traceable to source records.
- Add tests for transformations, SLA rules and metric calculations.
- Use UTC internally and retain original Bitrix timezone metadata.
- Do not treat AI output as ground truth. Store evidence and confidence.

## Initial deliverables

- Bitrix24 technical audit;
- repository structure;
- read-only Bitrix24 client;
- anonymized data snapshot;
- CRM violation report;
- broker metrics;
- department metrics;
- ROP control metrics;
- daily HTML/Markdown/JSON report;
- initial BI-ready fact and dimension tables.

## Definition of done for every task

A task is complete only when:

- code runs locally;
- configuration is documented;
- tests pass;
- secrets are absent from git;
- outputs are reproducible;
- assumptions are documented;
- limitations are explicit;
- source-to-metric traceability is preserved.

## Git workflow

- work on a dedicated branch;
- make small, descriptive commits;
- do not push directly to `main` unless the user explicitly requests it;
- open a draft pull request with completed work, risks, open questions and next steps.
