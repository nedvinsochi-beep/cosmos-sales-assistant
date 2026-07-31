import asyncio
import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from cosmos_control_tower.bitrix.errors import BitrixResponseError, UnsafeMethodError

LOGGER = logging.getLogger(__name__)


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False

READ_ONLY_METHODS = frozenset(
    {
        "app.info",
        "profile",
        "scope",
        "methods",
        "server.time",
        "user.current",
        "user.get",
        "department.get",
        "crm.lead.list",
        "crm.lead.fields",
        "crm.deal.list",
        "crm.deal.fields",
        "crm.dealcategory.list",
        "crm.dealcategory.default.get",
        "crm.dealcategory.stage.list",
        "crm.status.list",
        "crm.status.entity.types",
        "crm.activity.list",
        "crm.activity.fields",
        "crm.activity.type.list",
        "tasks.task.list",
        "task.item.list",
    }
)


class BitrixClient:
    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 30,
        rate_limit_per_second: float = 2,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = webhook_url.rstrip("/") + "/"
        self._interval = 1 / rate_limit_per_second
        self._last_request = 0.0
        self._lock = asyncio.Lock()
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def __aenter__(self) -> "BitrixClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    def _assert_read_only(self, method: str) -> None:
        if method not in READ_ONLY_METHODS:
            raise UnsafeMethodError(f"Bitrix method is not approved for read-only use: {method}")

    async def _throttle(self) -> None:
        async with self._lock:
            delay = self._interval - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()

    async def call(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._assert_read_only(method)

        @retry(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.25, min=0.25, max=4),
            retry=retry_if_exception(_is_transient_error),
            reraise=True,
        )
        async def perform() -> dict[str, Any]:
            await self._throttle()
            LOGGER.info("bitrix_request", extra={"method": method})
            response = await self._http.post(f"{self._base_url}{method}.json", data=params or {})
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            if payload.get("error"):
                raise BitrixResponseError(
                    f"{method}: {payload.get('error')} — {payload.get('error_description', '')}"
                )
            return payload

        return await perform()

    async def paginate(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        start = 0
        while True:
            page_params = dict(params or {})
            page_params["start"] = start
            payload = await self.call(method, page_params)
            result = payload.get("result", [])
            rows = result.get("items", []) if isinstance(result, dict) else result
            if not isinstance(rows, list):
                raise BitrixResponseError(f"{method}: unexpected result shape")
            for row in rows:
                if isinstance(row, dict):
                    yield row
            next_start = payload.get("next")
            if next_start is None:
                break
            start = int(next_start)
