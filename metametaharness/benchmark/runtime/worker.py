"""Fixed solver process entry; receives input and a per-question gateway token."""

import importlib.util
import json
import re
import sys

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from openai import OpenAI

EXPLICIT_CACHE = False


def mark_cache_prefix(messages):
    """Cache the stable prefix and history through the latest message."""
    prefix = [
        index for index, message in enumerate(messages)
        if message.get("role") in {"system", "user"}
    ][:2]
    marked = {*prefix, len(messages) - 1}
    out = []
    for index, message in enumerate(messages):
        if index in marked:
            content = message.get("content")
            if isinstance(content, str):
                message = dict(message, content=[{
                    "type": "text", "text": content,
                    "cache_control": {"type": "ephemeral"},
                }])
            elif isinstance(content, list) and content:
                blocks = [dict(block) if isinstance(block, dict) else block for block in content]
                if isinstance(blocks[-1], dict):
                    blocks[-1]["cache_control"] = {"type": "ephemeral"}
                message = dict(message, content=blocks)
        out.append(message)
    return out


class DeepSeekChatOpenAI(ChatOpenAI):
    """Preserve DeepSeek reasoning across the harness's non-streaming tool turns."""

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        data = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, data["choices"]):
            if "reasoning_content" in choice["message"]:
                generation.message.additional_kwargs["reasoning_content"] = choice["message"]["reasoning_content"]
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        for message, original in zip(payload["messages"], self._convert_input(input_).to_messages()):
            if original.type == "ai" and "reasoning_content" in original.additional_kwargs:
                message["reasoning_content"] = original.additional_kwargs["reasoning_content"]
        if EXPLICIT_CACHE:
            payload["messages"] = mark_cache_prefix(payload["messages"])
        return payload


def has_final_answer_field(text):
    """True if the response is (or contains) JSON carrying a final_answer field."""
    if not text:
        return False
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "final_answer" in data:
            return True
    except (json.JSONDecodeError, TypeError):
        pass
    return bool(re.search(r'"final_answer"\s*:', text))


def reformat_to_schema(client, model, response):
    """One no-think json_object call to wrap a free-form answer into the schema."""
    result = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You convert answers into JSON. Output only JSON."},
            {"role": "user", "content": (
                'Convert the following answer into a JSON object with exactly two string'
                ' fields, "reasoning" and "final_answer". Copy the answer content unchanged,'
                ' preserving any required markup such as [DIAGNOSIS]...[/DIAGNOSIS] inside'
                f' final_answer.\n\nAnswer:\n\n{response}'
            )},
        ],
        response_format={"type": "json_object"},
        extra_body={"enable_thinking": False},
    )
    converted = result.choices[0].message.content or ""
    return converted if has_final_answer_field(converted) else response


class ToolTrace(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self.emit("tool_start", run_id=str(run_id), name=serialized.get("name"), input=input_str)

    def on_tool_end(self, output, *, run_id, **kwargs):
        value = output.model_dump(mode="json") if hasattr(output, "model_dump") else str(output)
        self.emit("tool_end", run_id=str(run_id), output=value)

    def on_tool_error(self, error, *, run_id, **kwargs):
        self.emit("tool_error", run_id=str(run_id), error=str(error))

    @staticmethod
    def emit(event, **values):
        print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def main():
    request = json.load(sys.stdin)
    config = request["solver"]
    global EXPLICIT_CACHE
    EXPLICIT_CACHE = bool(config.get("explicit_cache"))
    # The subclass is provider-agnostic: it preserves reasoning_content across tool
    # turns and keeps the wire field as max_tokens, which DashScope (qwen) requires.
    model_class = DeepSeekChatOpenAI if config.get("provider") in {"deepseek", "qwen"} else ChatOpenAI
    model = model_class(
        model=config["model"],
        base_url=request["gateway_url"],
        api_key=request["gateway_token"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        reasoning_effort=config.get("reasoning_effort"),
        extra_body=config.get("extra_body"),
        timeout=config.get("client_timeout_seconds", config["request_timeout_seconds"]),
        max_retries=0,
        streaming=False,
        use_responses_api=False,
        profile={
            "tool_calling": True,
            "max_input_tokens": config["context_window"],
            "max_output_tokens": config["max_tokens"],
        },
    )
    sys.path.insert(0, "/harness")
    spec = importlib.util.spec_from_file_location("candidate", "/harness/agent.py")
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    agent, prompt = candidate.build_agent(model, request["input"], config)
    if config.get("answer_guard"):
        prompt += (
            "\n\nFINAL OUTPUT REQUIREMENT (mandatory, overrides anything else): Your final"
            ' message MUST be a single JSON object with exactly two string fields,'
            ' "reasoning" and "final_answer". Put the answer itself (keeping any required'
            ' markup such as [DIAGNOSIS]...[/DIAGNOSIS]) inside "final_answer". Output'
            " nothing outside the JSON object."
        )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"callbacks": [ToolTrace()], "recursion_limit": config["max_model_calls"] * 4 + 20},
    )
    response = result["messages"][-1].content
    if isinstance(response, list):
        response = "".join(block if isinstance(block, str) else block.get("text", "") for block in response)
    if config.get("answer_guard") and not has_final_answer_field(response):
        guard_client = OpenAI(
            base_url=request["gateway_url"], api_key=request["gateway_token"],
            timeout=config["client_timeout_seconds"], max_retries=0,
        )
        response = reformat_to_schema(guard_client, config["model"], response)
    ToolTrace.emit("final", response=response)


if __name__ == "__main__":
    main()
