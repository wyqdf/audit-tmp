"""Request compatibility for the 9527.codes GLM channel."""

import json


def adapt_request(request):
    def text_content(content):
        if isinstance(content, str):
            return content
        return "\n".join(block["text"] for block in content if block["type"] == "text")

    result = {
        key: request[key]
        for key in ("model", "max_tokens", "stream", "temperature", "top_p")
        if key in request
    }
    messages = []
    if request.get("system"):
        messages.append({"role": "system", "content": text_content(request["system"])})
    for message in request["messages"]:
        content = message["content"]
        if isinstance(content, str):
            messages.append({"role": message["role"], "content": content})
            continue
        text = text_content(content)
        if message["role"] == "assistant":
            row = {"role": "assistant", "content": text or None}
            calls = [
                {"id": block["id"], "type": "function", "function": {
                    "name": block["name"], "arguments": json.dumps(block["input"]),
                }}
                for block in content if block["type"] == "tool_use"
            ]
            if calls:
                row["tool_calls"] = calls
            messages.append(row)
        else:
            for block in content:
                if block["type"] == "tool_result":
                    messages.append({
                        "role": "tool", "tool_call_id": block["tool_use_id"],
                        "content": text_content(block["content"]),
                    })
            if text:
                messages.append({"role": message["role"], "content": text})
    result["messages"] = messages
    if "tools" in request:
        result["tools"] = [
            {"type": "function", "function": {
                "name": tool["name"], "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            }}
            for tool in request["tools"]
        ]
    return result
