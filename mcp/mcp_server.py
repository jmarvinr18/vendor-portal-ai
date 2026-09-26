# my_mcp_server.py
from datetime import datetime, timezone
from fastmcp import FastMCP
from fastmcp.utilities.http import find_available_port
port = find_available_port('127.0.0.1')

print(f"PORT: {port}")


mcp = FastMCP("devsecops-tools")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool()
def cvss_severity(score: float) -> str:
    """Map a CVSS v3 base score (0.0-10.0) to its severity label."""
    if not 0.0 <= score <= 10.0:
        raise ValueError("score must be between 0.0 and 10.0")
    if score == 0.0:
        return "None"
    if score < 4.0:
        return "Low"
    if score < 7.0:
        return "Medium"
    if score < 9.0:
        return "High"
    return "Critical"


@mcp.tool()
def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@mcp.resource("config://runbook")
def runbook() -> str:
    """Short incident runbook the agent can read."""
    return "1. Triage severity. 2. Page on-call if High/Critical. 3. Open ticket."


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)