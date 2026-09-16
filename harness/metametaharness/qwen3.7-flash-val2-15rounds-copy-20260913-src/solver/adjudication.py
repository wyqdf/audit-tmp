"""Rewrite the answer onto the spellings the frozen memory stores.

The memory's answer strings are the harness's only statement of how this task
writes an answer, and an answer the model produces from its own knowledge can
denote a stored answer while being spelled differently enough that exact-match
scoring counts it wrong.  `answer_space.canonicalize` reaches only the drift
that a single character at the edge of a stored value explains; the rest needs
the meaning of the answer, which the deterministic rule does not have.

So the model is asked once, after it has answered, which of the values it wrote
denote the same answer as a stored spelling, and the harness accepts a rewrite
only where it can check it against the memory: the replacement has to be a
stored spelling verbatim, and it may not be a fragment of the value it
replaces.  A shorter spelling contained in the answer is a different answer
that happens to share its text, not another way to spell it, so that case is
left as the model wrote it.

The other way a rewrite stops being a spelling is by writing several answers
where the agent wrote one: a replacement that carries more of the separators
the memory writes between whole answers than the fragment it replaces has added
an answer rather than re-spelled one, whatever the agent's own answer said.  The
same check is made on that side, because a spelling rule that can add a value
has stopped describing how this task writes an answer and started choosing what
the answer is.
"""

import json
import re
from string import Template

# The field the answer is carried in, as the runner's output contract names it.
ANSWER_FIELD = "final_answer"
ANSWER_PATTERN = re.compile(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % ANSWER_FIELD)

PROMPT = Template("""An agent answered the problem below. The training memory it draws on
stores answers with the spellings listed after it.

## Problem

$problem

## The answer the agent gave

$answer

## How the training memory spells answers

$spellings

Some value in the agent's answer may denote the same answer as one of the spellings above
and be written differently. List the rewrites that replace such a value with the stored
spelling.

Rules:
- only rewrite a value that denotes exactly the same answer as the stored spelling;
- never add, drop or reorder answer values, and never rewrite a value the memory does not
  spell differently;
- "to" must be copied verbatim from the list above.

Reply as JSON: {"rewrites": [{"from": "<fragment of the agent's answer>", "to": "<stored spelling>"}]}
Return an empty list when nothing should be rewritten.""")


def _json_candidates(text: str):
    """The pieces of a response that may hold the rewrite list."""
    yield text
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        yield match.group(1)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        yield match.group(0)


def rewrites(response: str) -> list[tuple[str, str]]:
    """The (from, to) pairs the model listed, in the order it listed them."""
    for candidate in _json_candidates(response):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        items = data.get("rewrites")
        if not isinstance(items, list):
            continue
        pairs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source, target = item.get("from"), item.get("to")
            if isinstance(source, str) and isinstance(target, str):
                pairs.append((source, target))
        return pairs
    return []


def accepted(
    pairs: list[tuple[str, str]],
    values: frozenset[str],
    separators: frozenset[str],
) -> list[tuple[str, str]]:
    """Keep only the rewrites the memory itself vouches for.

    A rewrite stands when its replacement is a stored spelling and is not a
    fragment of the value it replaces: an answer value that contains a stored
    spelling as a substring is a different, longer answer, and swapping in the
    shorter one would drop the content that distinguishes them.  A rewrite that
    carries more of the separators this memory writes between answers than the
    fragment it replaces is refused on the same ground: it writes another
    answer, so the model is choosing the answer rather than spelling it.
    """
    kept = []
    for source, target in pairs:
        if not source or source == target:
            continue
        if target not in values or target in source:
            continue
        if any(
            target.count(separator) > source.count(separator)
            for separator in separators
        ):
            continue
        kept.append((source, target))
    return kept


def rewrite(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    """Replace the first occurrence of each source, in the order given."""
    applied = 0
    for source, target in pairs:
        if source in text:
            text = text.replace(source, target, 1)
            applied += 1
    return text, applied


def answer_span(text: str) -> tuple[int, int]:
    """Where the answer starts and ends inside the agent's final message.

    The answer is the only part of the message the memory can speak about, so
    the rewrites are confined to it; a message that does not carry the field is
    treated as being all answer.
    """
    match = ANSWER_PATTERN.search(text)
    return (match.start(1), match.end(1)) if match else (0, len(text))


def adjudicate(
    text: str,
    model,
    problem: str,
    values: frozenset[str],
    spellings: str,
    separators: frozenset[str],
) -> tuple[str, int]:
    """Spell the answer's values the way the memory spells them.

    Returns the message with the accepted rewrites applied and how many were
    applied.  Any failure along the way leaves the message as the agent wrote
    it: the correction is an improvement to the answer, never a condition for
    producing one.
    """
    if not text or not spellings:
        return text, 0
    start, end = answer_span(text)
    answer = text[start:end]
    if not answer:
        return text, 0
    try:
        response = model.invoke(PROMPT.substitute(problem=problem, answer=answer, spellings=spellings))
    except Exception:
        return text, 0
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
        )
    kept = accepted(rewrites(str(content)), values, separators)
    corrected, applied = rewrite(answer, kept)
    if not applied:
        return text, 0
    return text[:start] + corrected + text[end:], applied
