"""Turns a LangGraph run into the event stream vendor-portal-api's `stream_sse` reads.

Each yielded dict becomes one `data: {...}` line (BedrockAgentCoreApp does the SSE framing):

    {"delta": "..."}                        answer text, token by token
    {"thinking": "..."}                     the model's reasoning, shown collapsed in the UI
    {"tool": {"id", "name", "status",       a tool call: "started", then "completed" or
              "input", "output"}}           "failed" with the same id
    {"artifact": {"name", "bucket",         a file a tool stored (its ToolMessage artifact);
                  "key", "size"}}           the portal serves the download
    {"reply": "...", "citations": [...],    once at the end: the whole answer plus
     "model": "...", "usage": {...},        what the API stores for source links
     "toolCalls": 0, "artifacts": [...]}    and cost tracking
"""

import json
import re

# Only these nodes write the answer. Tokens from the grader (a conditional edge that runs
# inside "retrieve_tool") and from "rewrite" are internal and never reach the vendor.
ANSWER_NODES = {"agent", "generate"}

OPEN_TAG, CLOSE_TAG = "<thinking>", "</thinking>"
# A whole block, or a stray tag left on its own.
THINKING_RE = re.compile(r"<thinking>.*?</thinking>|</?thinking>", re.DOTALL)

MAX_CITATIONS = 10
# Tool inputs and outputs are only shown as a summary; the API clips them further.
MAX_TOOL_TEXT = 1000


class ThinkingFilter:
    """Splits Nova's inline `<thinking>...</thinking>` out of streamed text.

    langchain-aws strips these tags from whole responses but not from stream chunks, and a
    tag can be split across chunks, so text that might be the start of a tag is held back
    until the next chunk settles it. `feed` returns (answer text, thinking text).
    """

    def __init__(self):
        self._buf = ""
        self._inside = False

    def feed(self, text: str) -> tuple[str, str]:
        self._buf += text
        out, thought = [], []
        while True:
            if self._inside:
                end = self._buf.find(CLOSE_TAG)
                if end == -1:
                    # Keep only what could be the start of the closing tag.
                    keep = _partial_suffix(self._buf, CLOSE_TAG)
                    thought.append(self._buf[: len(self._buf) - keep])
                    self._buf = self._buf[len(self._buf) - keep :]
                    break
                thought.append(self._buf[:end])
                self._buf = self._buf[end + len(CLOSE_TAG) :]
                self._inside = False
            else:
                start = self._buf.find(OPEN_TAG)
                stray = self._buf.find(CLOSE_TAG)
                # Nova sometimes closes a block it never opened: drop the tag, keep the text.
                if stray != -1 and (start == -1 or stray < start):
                    out.append(self._buf[:stray])
                    self._buf = self._buf[stray + len(CLOSE_TAG) :]
                    continue
                if start != -1:
                    out.append(self._buf[:start])
                    self._buf = self._buf[start + len(OPEN_TAG) :]
                    self._inside = True
                    continue
                keep = max(_partial_suffix(self._buf, OPEN_TAG), _partial_suffix(self._buf, CLOSE_TAG))
                out.append(self._buf[: len(self._buf) - keep])
                self._buf = self._buf[len(self._buf) - keep :]
                break
        return "".join(out), "".join(thought)

    def flush(self) -> tuple[str, str]:
        rest, self._buf = self._buf, ""
        return ("", rest) if self._inside else (rest, "")


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest end of `text` that is a start of `tag`."""
    for k in range(min(len(text), len(tag) - 1), 0, -1):
        if text.endswith(tag[:k]):
            return k
    return 0


def _chunk_text(content) -> str:
    """Text of a chat-model chunk; Bedrock Converse sends a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _chunk_reasoning(content) -> str:
    """Reasoning blocks of a chunk: Claude's extended thinking through Bedrock Converse
    (`reasoning_content`) or the Anthropic-style `thinking` block."""
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "reasoning_content":
            parts.append((block.get("reasoning_content") or {}).get("text", ""))
        elif block.get("type") == "thinking":
            parts.append(block.get("thinking", ""))
    return "".join(p for p in parts if isinstance(p, str))


def _summary(value) -> str | None:
    """A tool's input or output as short display text."""
    content = getattr(value, "content", value)  # a ToolMessage carries its text in content
    if isinstance(content, list):
        content = _chunk_text(content) or json.dumps(content, default=str)
    if content is None or content == "" or content == {}:
        return None
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
    text = text.strip()
    return text if len(text) <= MAX_TOOL_TEXT else text[: MAX_TOOL_TEXT - 1] + "…"


def _tool_input(data: dict):
    args = data.get("input")
    if isinstance(args, dict):
        # Injected values (the run config, graph state) aren't the model's arguments.
        args = {k: v for k, v in args.items() if k not in ("config", "state", "runtime") and not k.startswith("_")}
    return args


def _artifact(output) -> dict | None:
    """The file pointer a `content_and_artifact` tool returned, if it is one."""
    artifact = getattr(output, "artifact", None)
    if isinstance(artifact, dict) and all(isinstance(artifact.get(k), str) for k in ("name", "bucket", "key")):
        return {k: artifact[k] for k in ("name", "bucket", "key", "size") if k in artifact}
    return None


def _citation(doc) -> dict | None:
    """A knowledge-base document as a `document` citation."""
    meta = getattr(doc, "metadata", None) or {}
    source = meta.get("source_metadata") or {}
    uri = (
        (meta.get("location") or {}).get("s3Location", {}).get("uri")
        or source.get("x-amz-bedrock-kb-source-uri")
        or meta.get("source")
    )
    if not uri:
        return None
    return {"type": "document", "id": uri, "label": uri.rstrip("/").rsplit("/", 1)[-1]}


async def stream_answer(graph, inputs: dict, config: dict, model: str):
    """Yield the events above while the graph runs, then the final object."""
    filters: dict[str, ThinkingFilter] = {}
    citations: dict[str, dict] = {}
    artifacts: list[dict] = []
    input_tokens = output_tokens = tool_calls = 0
    started = False  # leading whitespace (e.g. left after a thinking block) is dropped

    def emit(text: str):
        nonlocal started
        if not started:
            text = text.lstrip()
            started = bool(text)
        return text

    def split(answer: str, thought: str):
        events = []
        if thought:
            events.append({"thinking": thought})
        piece = emit(answer) if answer else ""
        if piece:
            events.append({"delta": piece})
        return events

    async for event in graph.astream_events(inputs, config=config, version="v2"):
        kind = event["event"]
        node = event.get("metadata", {}).get("langgraph_node")

        if kind == "on_chat_model_stream" and node in ANSWER_NODES:
            content = event["data"]["chunk"].content
            reasoning = _chunk_reasoning(content)
            if reasoning:
                yield {"thinking": reasoning}
            text = _chunk_text(content)
            if text:
                for item in split(*filters.setdefault(event["run_id"], ThinkingFilter()).feed(text)):
                    yield item

        elif kind == "on_chat_model_end":
            if node in ANSWER_NODES and event["run_id"] in filters:
                for item in split(*filters.pop(event["run_id"]).flush()):
                    yield item
            usage = getattr(event["data"].get("output"), "usage_metadata", None) or {}
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)

        elif kind == "on_tool_start":
            tool_calls += 1
            yield {"tool": {
                "id": event["run_id"],
                "name": event["name"],
                "status": "started",
                "input": _summary(_tool_input(event["data"])),
            }}

        elif kind == "on_tool_end":
            output = event["data"].get("output")
            failed = getattr(output, "status", None) == "error"
            yield {"tool": {
                "id": event["run_id"],
                "name": event["name"],
                "status": "failed" if failed else "completed",
                "output": _summary(output),
            }}
            artifact = None if failed else _artifact(output)
            if artifact:
                artifacts.append(artifact)
                yield {"artifact": artifact}

        elif kind == "on_tool_error":
            yield {"tool": {
                "id": event["run_id"],
                "name": event["name"],
                "status": "failed",
                "output": _summary(str(event["data"].get("error") or "The tool failed.")),
            }}

        elif kind == "on_retriever_end":
            for doc in event["data"].get("output") or []:
                citation = _citation(doc)
                if citation:
                    citations.setdefault(citation["id"], citation)

    state = await graph.aget_state(config)
    messages = state.values.get("messages") or []
    last = messages[-1] if messages else None
    reply = getattr(last, "content", last) if last is not None else ""
    reply = THINKING_RE.sub("", _chunk_text(reply)).strip()

    yield {
        "reply": reply,
        "citations": list(citations.values())[:MAX_CITATIONS],
        "model": model,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
        "toolCalls": tool_calls,
        "artifacts": artifacts,
    }
