"""Answer parsing copied from the selected baseline."""

import json
import re


def extract_json_field(text: str, field: str, default: str = "") -> str:
    """Helper function to extract a field from JSON in LLM response."""
    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get(field, default))
    except json.JSONDecodeError:
        pass

    # Try code blocks: ```json ... ``` or ``` ... ```
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return str(data.get(field, default))
        except json.JSONDecodeError:
            pass

    # Find balanced braces and try parsing
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth, pos, in_str = 1, start + 1, False
        while pos < len(text) and depth > 0:
            c = text[pos]
            if c == '"' and (pos == 0 or text[pos - 1] != "\\"):
                in_str = not in_str
            elif not in_str:
                depth += 1 if c == "{" else (-1 if c == "}" else 0)
            pos += 1
        if depth == 0:
            candidate = text[start:pos]
            candidate = re.sub(
                r",\s*([\]}])", r"\1", candidate
            )  # Remove trailing commas
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return str(data.get(field, default))
            except json.JSONDecodeError:
                pass

    # Regex fallback
    match = re.findall(rf'"{field}"\s*:\s*"([^"]*)"', text)
    return match[-1] if match else default
