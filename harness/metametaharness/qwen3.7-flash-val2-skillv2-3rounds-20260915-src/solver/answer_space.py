"""Ground the solver's answer in the answer space the frozen memory demonstrates.

The memory is the only evidence the harness has about what a valid answer looks like:
which strings recur as answers, which character joins several answers into one, which
characters an answer may end on, which characters separate pieces *inside* one answer,
and which annotation tags or lead-ins wrap them.  A reply that is a near-miss variant
of a memorised answer (an affix added or dropped, a one-character slip), that carries a
trailing affix the demonstrated answers never carry, or that leaves out a stretch of a
memorised answer around one of its internal separators, scores zero even when the
reasoning behind it was right, so the reply is restored to the memory's own answer
strings before it leaves the harness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MEMORY_PATH = "/harness/memory/memory.json"

# Annotation wrappers ("[罪名]...<eoa>", "[DIAGNOSIS]...[/DIAGNOSIS]") are tags, while atom
# brackets inside a SMILES ("[C@@H]", "[n+]") are not: a tag body holds word characters
# only, so chemical notation is never mistaken for markup.
TAG_BODY = r"[A-Za-z0-9_/一-鿿]"
LEAD_TAG = re.compile(rf"^\s*\[{TAG_BODY}{{1,32}}\]")
TRAIL_TAG = re.compile(rf"(\[/?{TAG_BODY}{{1,32}}\]|<[^<>]{{1,32}}>)\s*$")
LEAD_IN = re.compile(r"^\s*[^\s:：\[\]<>]{1,12}[:：]")

# A character only separates answers when the pieces it produces are themselves answers
# (a legal charge list is split by ";", while "、" only ever splits inside one charge).
MIN_PIECE_REUSE = 0.2
# Near misses are repair targets; a larger budget starts rewriting answers that differ.
MAX_EDITS = 1
# A character counts as a separator inside an answer once the memory shows it there more
# than once, so a stray punctuation mark in a single answer demonstrates nothing.
MARKER_MIN_ANSWERS = 2


def strip_annotation(text: str) -> str:
    """Drop the tags and lead-ins a task wraps around an answer."""
    text = (text or "").strip()
    changed = True
    while changed and text:
        changed = False
        match = LEAD_TAG.match(text)
        if match:
            text = text[match.end():].strip()
            changed = True
        match = TRAIL_TAG.search(text)
        if match and match.end() == len(text):
            text = text[: match.start()].strip()
            changed = True
    match = LEAD_IN.match(text)
    if match:
        text = text[match.end():].strip()
    return text


def split_wrapper(text: str) -> tuple[str, str, str]:
    """Split a reply into the leading tag, the body and the trailing tag."""
    text = text or ""
    lead = ""
    match = LEAD_TAG.match(text)
    if match:
        lead = match.group(0)
        text = text[match.end():]
    tail = ""
    match = TRAIL_TAG.search(text)
    if match and match.end() == len(text):
        tail = match.group(0)
        text = text[: match.start()]
    return lead, text, tail


def edit_distance(left: str, right: str, cap: int) -> int:
    """Levenshtein distance, abandoned as soon as it exceeds ``cap``."""
    if abs(len(left) - len(right)) > cap:
        return cap + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (left_char != right_char),
            ))
        if min(current) > cap:
            return cap + 1
        previous = current
    return previous[-1]


def derive_answer_space(targets: list[str], min_reuse: float = MIN_PIECE_REUSE) -> dict:
    """Infer the answer strings, their endings, their separators from memory."""
    answers = [strip_annotation(target) for target in targets or []]
    answers = [answer for answer in answers if answer]
    if not answers:
        return {"items": [], "separator": None, "endings": [], "markers": ""}
    whole = set(answers)
    separators = {}
    for answer in answers:
        for char in set(answer):
            if not char.isalnum() and not char.isspace():
                separators[char] = separators.get(char, 0) + 1
    best = None
    for char, seen in separators.items():
        if seen < 2:
            continue
        pieces = {piece.strip() for answer in answers if char in answer
                  for piece in answer.split(char) if piece.strip()}
        if len(pieces) < 2:
            continue
        reuse = sum(1 for piece in pieces if piece in whole) / len(pieces)
        if reuse < min_reuse:
            continue
        if best is None or (reuse, seen) > best[0]:
            best = ((reuse, seen), char, pieces)
    if best is None:
        items = sorted(whole)
        return {"items": items, "separator": None, "endings": answer_endings(whole),
                "markers": answer_markers(items)}
    items = sorted(best[2] | whole)
    return {
        "items": items,
        "separator": best[1],
        "endings": answer_endings(items),
        "markers": answer_markers(items),
    }


def answer_endings(answers) -> list[str]:
    """The characters the memory ever lets an answer end on."""
    return sorted({answer[-1] for answer in answers if answer})


def answer_markers(items) -> str:
    """The characters the memory demonstrates as separators inside an answer.

    A demonstrated answer may carry punctuation that never joins answers into a
    list (";" splits a charge list, while "、" sits inside one charge): the memory
    still shows the character sitting between pieces of its own answers, so a
    stretch of an answer that carries one of those characters can be left out
    without the answer becoming a different one.
    """
    seen: dict[str, int] = {}
    for item in items or []:
        for char in set(item or ""):
            if not char.isalnum() and not char.isspace():
                seen[char] = seen.get(char, 0) + 1
    return "".join(sorted(char for char, count in seen.items() if count >= MARKER_MIN_ANSWERS))


def omitted_span(item: str, candidate: str):
    """The one stretch ``candidate`` would have to lose to become ``item``."""
    length = len(candidate) - len(item)
    if length <= 0:
        return None
    shared = 0
    while shared < len(item) and candidate[shared] == item[shared]:
        shared += 1
    for start in range(shared + 1):
        if candidate[start + length:] == item[start:]:
            return candidate[start:start + length]
    return None


def restore_abbreviation(item: str, items, markers: str) -> str:
    """Restore an answer the reply wrote with one stretch of it left out.

    The memory demonstrates answers that carry internal separators, so a reply
    that reproduces a demonstrated answer with one stretch of it — a stretch that
    contains a demonstrated separator — left out is that answer abbreviated, and
    the demonstrated answer is restored.  Only the shortest demonstrated answer
    the reply can be cut down to is restored, and only when it is the only one at
    that length: a reply the memory already demonstrates stands, and a stretch
    that drops no separator ("过失..." -> "...") has dropped a word, not a
    separator, so it is a different answer and is left to the near-miss rule.
    """
    stripped = item.strip()
    if not stripped or not markers or stripped in items:
        return item
    best = None
    tied = False
    for candidate in items:
        span = omitted_span(stripped, candidate)
        if span is None or not any(char in markers for char in span):
            continue
        if best is None or len(candidate) < len(best):
            best, tied = candidate, False
        elif len(candidate) == len(best) and candidate != best:
            tied = True
    return item if best is None or tied else best


def trim_affix(item: str, endings) -> str:
    """Drop a trailing character the demonstrated answers never carry as an ending.

    The memory shows which characters terminate an answer.  A reply that ends an
    answer with some other character, sitting on top of a character the memory does
    end answers with, is carrying an affix that no demonstrated answer carries, so
    the affix goes.  A character the reply itself uses inside the same answer is
    notation rather than an affix ("[C@@H]1CC1" is not trimmed), and a trailing
    character that leaves the answer ending on an undemonstrated character keeps the
    reply intact: the evidence only covers what an ending may look like, not what
    may precede one.
    """
    if not item or not endings:
        return item
    endings = set(endings)
    stripped = item.strip()
    if not stripped or stripped[-1] in endings:
        return item
    trimmed = stripped[:-1].strip()
    if not trimmed or trimmed[-1] not in endings:
        return item
    if stripped[-1] in trimmed:
        return item
    return trimmed


def snap_item(item: str, items: list[str], max_edits: int = MAX_EDITS) -> str:
    """Return the answer string the item is a near miss of, if exactly one exists."""
    item = item.strip()
    if not item or item in items:
        return item
    core = strip_annotation(item)
    if not core:
        return item
    lowered = core.lower()
    best = None
    tied = 0
    for candidate in items:
        distance = edit_distance(lowered, candidate.lower(), max_edits)
        if distance > max_edits:
            continue
        key = (distance, -len(candidate))
        if best is None or key < best[0]:
            best = (key, candidate)
            tied = 1
        elif key == best[0]:
            tied += 1
    return best[1] if best is not None and tied == 1 else item


def ground_answer(text: str, space: dict, max_edits: int = MAX_EDITS) -> str:
    """Rewrite every answer string in a reply that is a near miss of a memorised one."""
    items = (space or {}).get("items")
    if not items or not text:
        return text
    endings = (space or {}).get("endings") or []
    markers = (space or {}).get("markers") or ""
    lead, body, tail = split_wrapper(text)
    separator = (space or {}).get("separator")

    def ground_item(piece: str) -> str:
        return restore_abbreviation(
            snap_item(trim_affix(piece, endings), items, max_edits), items, markers,
        )

    if separator and separator in body:
        body = separator.join(ground_item(piece) for piece in body.split(separator))
    else:
        body = ground_item(body)
    return f"{lead}{body}{tail}"


def _parse_object(text: str):
    """Find the JSON object a reply carries, the way the evaluator reads it."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = None
    if isinstance(data, dict):
        return data
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth, position, in_string = 1, start + 1, False
        while position < len(text) and depth > 0:
            char = text[position]
            if char == '"' and (position == 0 or text[position - 1] != "\\"):
                in_string = not in_string
            elif not in_string:
                depth += 1 if char == "{" else (-1 if char == "}" else 0)
            position += 1
        if depth:
            continue
        try:
            data = json.loads(text[start:position])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def ground_reply(text: str, space: dict, max_edits: int = MAX_EDITS) -> str:
    """Ground the final answer of a solver reply, JSON object or bare label alike."""
    if not text or not (space or {}).get("items"):
        return text
    payload = _parse_object(text)
    if isinstance(payload, dict):
        answer = payload.get("final_answer")
        if not isinstance(answer, str):
            return text
        grounded = ground_answer(answer, space, max_edits)
        if grounded == answer:
            return text
        payload["final_answer"] = grounded
        return json.dumps(payload, ensure_ascii=False)
    # No JSON: only a reply that is itself essentially a label is safe to repair.
    return ground_answer(text.strip(), space, max_edits)


def answer_text(reply: str) -> str:
    """The answer a reply carries: its JSON field when it has one, else the reply itself."""
    payload = _parse_object(reply)
    if isinstance(payload, dict) and isinstance(payload.get("final_answer"), str):
        return payload["final_answer"]
    return (reply or "").strip()


def answer_key(reply: str, separator: str | None = None):
    """What a reply counts as when the panel compares answers.

    An answer is compared the way the memory's wrappers are stripped, so two replies that
    carry the same answer under different markup are one answer.  Where the memory
    demonstrates that an answer is several answers joined into one, the order they are
    joined in is not part of the answer: a reply that re-lists the same answers in another
    order is the answer written again, not a disagreement, so the pieces are compared as
    the set they are.  A space whose answers are never joined (no separator) compares the
    whole rendered answer, exactly as before.
    """
    text = strip_annotation(answer_text(reply))
    if not separator or separator not in text:
        return text
    return tuple(sorted(piece.strip() for piece in text.split(separator) if piece.strip()))


def panel_winner(replies: list[str], separator: str | None = None) -> int:
    """The index of the reply the panel agrees on.

    The most common answer wins and the earliest reply carrying it breaks a tie; the
    answer itself is compared the way ``answer_key`` reads it, so a set written in one
    order and the same set written in another are one vote rather than two.
    """
    keys = [answer_key(reply, separator) for reply in replies]
    counts: dict = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    leader = max(counts, key=lambda key: counts[key])
    return keys.index(leader)


def answers_agree(replies: list[str], separator: str | None = None) -> bool:
    """True when every reply of the panel carries the same answer."""
    return len({answer_key(reply, separator) for reply in replies}) == 1


def extends_answer(space: dict, before: str, after: str) -> bool:
    """Whether ``after`` keeps every answer ``before`` gave and adds demonstrated ones.

    A question's answer is often several answers the memory demonstrates at once, and the
    memory is the only thing that can vouch for a string being one of them.  A second
    reading of a reply may therefore only *add* to it: every answer the first reading gave
    has to survive whole, and everything that appears besides them has to be a string the
    memory itself demonstrates as an answer.  A space that never joins several answers into
    one (no separator) has nothing to add to, so nothing is accepted there.
    """
    separator = (space or {}).get("separator")
    items = set((space or {}).get("items") or [])
    if not separator or not items:
        return False

    def pieces(text: str) -> set:
        return {
            piece.strip()
            for piece in strip_annotation(answer_text(text)).split(separator)
            if piece.strip()
        }

    given, reviewed = pieces(before), pieces(after)
    added = reviewed - given
    return bool(given) and given <= reviewed and bool(added) and added <= items


def load_answer_space(path: str = MEMORY_PATH) -> dict:
    """Derive the answer space of the memory frozen for this task."""
    try:
        memory = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {"items": [], "separator": None, "endings": [], "markers": ""}
    examples = memory.get("examples") if isinstance(memory, dict) else memory
    if not isinstance(examples, list):
        return {"items": [], "separator": None, "endings": [], "markers": ""}
    targets = [
        example.get("target", example.get("answer", ""))
        for example in examples if isinstance(example, dict)
    ]
    return derive_answer_space(targets)
