"""Common failure categories; provider-specific patterns come from configuration."""

RETRYABLE = {"timeout", "connection_error", "rate_limit", "upstream_error"}


def classify_error(value, status_code=None, patterns=None):
    if isinstance(value, dict):
        message = str(value.get("message", value))
        code = str(value.get("type", "")) + " " + str(value.get("code", ""))
    else:
        message, code = str(value), type(value).__name__
    text = (code + " " + message).lower()
    category = next((
        name for name, terms in (patterns or {}).items()
        if any(term.lower() in text for term in terms)
    ), None)
    if category is None:
        if "model-call limit exceeded" in text:
            category = "call_budget"
        elif "timeout" in text or "timed out" in text or "deadline exceeded" in text or status_code == 408:
            category = "timeout"
        elif status_code == 429:
            category = "rate_limit"
        elif status_code in {401, 403}:
            category = "authentication"
        elif any(name in text for name in ("connecterror", "readerror", "connectionerror")):
            category = "connection_error"
        elif status_code is not None and status_code >= 500:
            category = "upstream_error"
        elif status_code is not None and status_code >= 400:
            category = "invalid_request"
        else:
            category = "execution_error"
    return {"type": category, "message": message, "retryable": category in RETRYABLE}


class EvaluationError(RuntimeError):
    def __init__(self, error):
        self.error = error
        super().__init__(error["message"])
