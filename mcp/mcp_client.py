# my_mcp_client.py
import asyncio
import os
import json

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
HEADERS = {}
if token := os.getenv("BEARER_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {token}"


async def main():
    async with (
        httpx2.AsyncClient(headers=HEADERS, timeout=120) as http_client,
        streamable_http_client(MCP_URL, http_client=http_client, terminate_on_close=False) as (read, write),
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])


            db = await session.call_tool("list_tables")
            tbl = json.loads(db.content[0].text)[0]["table_name"]
            print(json.loads(db.content[0].text)[0]["table_name"])

            describe_tbl = await session.call_tool("describe_table", {"table": tbl}) 

            print(f"DESCRIBING {tbl} table... {describe_tbl}")
            # ok = await session.call_tool("add_numbers", {"a": 25, "b": 434})
            # print("add_numbers:", ok.content[0].text, ok.structured_content)

            # bad = await session.call_tool("cvss_severity", {"score": 9})
            # print("cvss_severity isError:", bad.is_error, "-", bad.content[0].text)

            # res = await session.read_resource("config://runbook")
            # print("runbook:", res.contents[0].text)


asyncio.run(main())