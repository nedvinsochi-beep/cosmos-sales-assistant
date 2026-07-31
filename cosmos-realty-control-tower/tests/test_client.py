import json

import httpx
import pytest

from cosmos_control_tower.bitrix.client import BitrixClient
from cosmos_control_tower.bitrix.errors import UnsafeMethodError


@pytest.mark.asyncio
async def test_pagination_reads_all_pages() -> None:
    starts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        form = dict(item.split("=") for item in request.content.decode().split("&"))
        starts.append(form["start"])
        if form["start"] == "0":
            return httpx.Response(200, json={"result": [{"ID": "1"}], "next": 50})
        return httpx.Response(200, json={"result": [{"ID": "2"}]})

    client = BitrixClient(
        "https://example.invalid/rest/1/token/",
        rate_limit_per_second=10,
        transport=httpx.MockTransport(handler),
    )
    rows = [row async for row in client.paginate("crm.lead.list")]
    await client.close()
    assert [row["ID"] for row in rows] == ["1", "2"]
    assert starts == ["0", "50"]


@pytest.mark.asyncio
async def test_retry_after_transport_error() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary")
        return httpx.Response(200, json={"result": []})

    client = BitrixClient(
        "https://example.invalid/rest/1/token/",
        rate_limit_per_second=10,
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    assert (await client.call("crm.lead.list"))["result"] == []
    await client.close()
    assert attempts == 2


@pytest.mark.asyncio
async def test_non_transient_http_error_is_not_retried() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(403, json={"error": "forbidden"})

    client = BitrixClient(
        "https://example.invalid/rest/1/token/",
        max_retries=3,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.call("crm.activity.type.list")
    await client.close()
    assert attempts == 1


@pytest.mark.asyncio
async def test_write_method_is_blocked_before_network() -> None:
    requests = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"result": True})

    client = BitrixClient(
        "https://example.invalid/rest/1/token/",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(UnsafeMethodError):
        await client.call("crm.lead.add", {"fields": json.dumps({"TITLE": "unsafe"})})
    await client.close()
    assert requests == 0
