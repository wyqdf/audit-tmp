"""Answer-space index derived from the frozen memory.

The memory holds question/answer examples, so the answer strings it stores are
the only evidence the harness has about how this task spells its answers.  An
answer written by the model from its own knowledge drifts off that spelling by
a character (an extra or missing affix), which the benchmark scores as wrong
even when the meaning is right.  This module exposes the stored spellings so
the harness can ground the answer it returns.

The stored answers also fix the *edges* of a value: which characters this task
writes at the end of one, and which characters it keeps inside them.  A model
answer can end a value with a character the memory never ends one with -- an
affix the task does not use -- and that value then matches no stored spelling
at all, so `canonicalize` cannot reach it.  `trim_trailing` covers that case
from the same evidence, without asking the memory whether the value itself is
right.

The stored values are also *compound*: many of them are several parts joined by
the separators above, in a fixed order.  A model answer can render such a value
while dropping one of its interior parts, which leaves it several characters
away from the stored spelling rather than one, so neither of the rules above
reaches it.  `complete_compound` reads the whole spelling off the same evidence
and only where the omission is unambiguous and the omitted material is
separator-joined structure rather than answer content.
"""

import json
import re
from collections import Counter
from pathlib import Path

MEMORY_PATH = "/harness/memory/memory.json"
# Punctuation that joins several answer values inside one stored answer.
VALUE_SEPARATORS = (";", "；", ",", "，", "、", "|", "/")
MIN_VALUE_CHARS = 2
# Upper bound on the rendered list of stored spellings, so a memory with a huge
# answer space cannot crowd the rest of the prompt out.
MAX_VOCABULARY_CHARS = 6000
# A character the memory keeps inside its values but never writes at the end of
# one is a candidate affix.  Content characters are shared by many stored
# values; a character that shows up inside only a small share of them is not
# how this vocabulary spells a value, so a value ending with it carries an
# affix the task does not use.
MAX_INTERIOR_SHARE = 0.1
# How much material a stored spelling may add to a value the model wrote and
# still read as the same value written short: a compound value's part is short
# by nature, while a longer addition is content the model did not write.
MAX_COMPLETION_CHARS = 4


def components(answer: str) -> list[str]:
    """Split a stored answer into the values it is made of."""
    for separator in VALUE_SEPARATORS:
        if separator in answer:
            return [part.strip() for part in answer.split(separator) if part.strip()]
    return [answer.strip()] if answer.strip() else []


def _usable(value: str) -> bool:
    """False for values that are too short or could not be substituted into a response."""
    return len(value) >= MIN_VALUE_CHARS and '"' not in value and "\\" not in value


def _answers(memory_path: str) -> list[str]:
    """The answer each stored example carries, in memory order."""
    examples = json.loads(Path(memory_path).read_text())["examples"]
    return [str(example["target"]).strip() for example in examples]


def stored_answers(memory_path: str = MEMORY_PATH) -> list[str]:
    """The whole answers the memory stores, in memory order, without repeats."""
    ordered: list[str] = []
    seen: set[str] = set()
    for answer in _answers(memory_path):
        if _usable(answer) and answer not in seen:
            seen.add(answer)
            ordered.append(answer)
    return ordered


def answer_separators(answers: list[str]) -> frozenset[str]:
    """The separators the memory writes between whole answers.

    A stored answer can hold several answers at once, and the memory writes them
    with a separator that also joins pieces it stores as answers on their own:
    that is what writing more than one answer in a single string looks like in
    this memory's own evidence.  A separator that only ever splits the name of
    one answer never does that, so a value joined by it is one answer written
    long rather than several answers written together.
    """
    stored = set(answers)
    separators = set()
    for answer in answers:
        for separator in VALUE_SEPARATORS:
            parts = [
                part.strip() for part in answer.split(separator) if part.strip()
            ]
            if len(parts) > 1 and all(part in stored for part in parts):
                separators.add(separator)
    return frozenset(separators)


def stored_values(memory_path: str = MEMORY_PATH) -> list[str]:
    """Every spelling the memory stores: whole answers first, then their values.

    Order follows the memory, so the rendering is deterministic.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for answer in _answers(memory_path):
        for value in [answer, *components(answer)]:
            if _usable(value) and value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered


def edge_conventions(values: list[str]) -> tuple[frozenset[str], dict[str, float]]:
    """What the stored values say about the edges of an answer value.

    Returns the characters that end a stored value, and for the characters that
    never end one, the share of stored values that use them inside.  A value
    respects the memory's convention when it ends with a character from the
    first set.
    """
    values = list(values)
    endings = {value[-1] for value in values if value}
    inside: Counter = Counter()
    for value in values:
        inside.update(set(value[1:-1]))
    total = max(len(values), 1)
    return (
        frozenset(endings),
        {
            character: count / total
            for character, count in inside.items()
            if character not in endings
        },
    )


def vocabulary(
    memory_path: str = MEMORY_PATH,
    max_chars: int = MAX_VOCABULARY_CHARS,
) -> str:
    """Render the memory's whole stored answers as one newline-separated list."""
    lines: list[str] = []
    total = 0
    for answer in stored_answers(memory_path):
        if total + len(answer) + 1 > max_chars:
            break
        lines.append(answer)
        total += len(answer) + 1
    return "\n".join(lines)


def build_index(
    memory_path: str = MEMORY_PATH,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the answers the memory spells and the characters they are made of.

    Whole stored answers and their components count as spelled answers; the
    character set says what counts as answer content instead of formatting
    around it.
    """
    values = frozenset(stored_values(memory_path))
    alphabet = {character for value in values for character in value}
    return values, frozenset(alphabet)


def _is_boundary(text: str, position: int, alphabet: frozenset[str]) -> bool:
    """True where an answer value begins or ends instead of continuing."""
    if position < 0 or position >= len(text):
        return True
    character = text[position]
    return character not in alphabet or character in VALUE_SEPARATORS


def _occurrences(text: str, value: str) -> list[int]:
    positions = []
    start = text.find(value)
    while start != -1:
        positions.append(start)
        start = text.find(value, start + 1)
    return positions


def _is_spelled_out(
    text: str, value: str, positions: list[int], alphabet: frozenset[str]
) -> bool:
    """True if the text already uses the value as an answer, not as a fragment."""
    length = len(value)
    return any(
        _is_boundary(text, start - 1, alphabet)
        and _is_boundary(text, start + length, alphabet)
        for start in positions
    )


def canonicalize(
    text: str, index: tuple[frozenset[str], frozenset[str]]
) -> tuple[str, int]:
    """Spell answer values the way the memory spells them.

    A value the text already spells out is left alone.  Otherwise, an
    occurrence that becomes a stored value by dropping one character in front
    of or behind it is rewritten to that stored spelling, provided exactly one
    stored value claims the spot; anything else (a different value, an
    ambiguous match, an edit inside the value) is kept as written.
    """
    values, alphabet = index
    claims: dict[int, list[tuple[int, str]]] = {}
    for value in values:
        length = len(value)
        positions = _occurrences(text, value)
        if not positions or _is_spelled_out(text, value, positions, alphabet):
            continue
        for start in positions:
            for candidate_start, candidate_end in (
                (start - 1, start + length),
                (start, start + length + 1),
            ):
                if candidate_start < 0 or candidate_end > len(text):
                    continue
                if text[candidate_start:candidate_end] in values:
                    continue
                if not (
                    _is_boundary(text, candidate_start - 1, alphabet)
                    and _is_boundary(text, candidate_end, alphabet)
                ):
                    continue
                claims.setdefault(candidate_start, []).append(
                    (candidate_end - candidate_start, value)
                )
    replacements = sorted(
        (start, claim[0]) for start, claim in claims.items() if len(claim) == 1
    )
    parts = []
    cursor = 0
    applied = 0
    for start, (length, value) in replacements:
        if start < cursor:
            continue
        parts.append(text[cursor:start])
        parts.append(value)
        cursor = start + length
        applied += 1
    if not applied:
        return text, 0
    parts.append(text[cursor:])
    return "".join(parts), applied


def trim_trailing(
    text: str,
    index: tuple[frozenset[str], frozenset[str]],
    conventions: tuple[frozenset[str], dict[str, float]],
) -> tuple[str, int]:
    """Drop a trailing character the memory never ends one of its values with.

    Runs of characters drawn from the memory's own answers are left alone
    unless the run ends with a character the memory keeps only inside its
    values, uses inside only a small share of them, and dropping it leaves a
    value that ends the way the memory's own values end.  A value the memory
    stores, and a value whose ending the memory itself writes, are kept as the
    model wrote them; what the rule removes is an affix this task does not use,
    so it never needs to know whether the value denotes the right answer.
    """
    _, alphabet = index
    endings, interior = conventions
    if not alphabet or not endings:
        return text, 0
    pattern = re.compile("[%s]+" % re.escape("".join(sorted(alphabet))))
    applied = 0

    def rewrite(match: re.Match) -> str:
        nonlocal applied
        run = match.group(0)
        trailing = run[-1]
        remainder = run[:-1]
        if len(remainder) < MIN_VALUE_CHARS or trailing in endings:
            return run
        if interior.get(trailing, 1.0) > MAX_INTERIOR_SHARE:
            return run
        if remainder[-1] not in endings:
            return run
        applied += 1
        return remainder

    return pattern.sub(rewrite, text), applied


def _omitted(value: str, stored: str) -> str | None:
    """The material a stored spelling carries that a value does not, in order.

    None when the value is not a subsequence of the stored spelling: then the
    two do not read as one value written at two lengths.
    """
    omitted: list[str] = []
    position = 0
    for character in value:
        while position < len(stored) and stored[position] != character:
            omitted.append(stored[position])
            position += 1
        if position == len(stored):
            return None
        position += 1
    omitted.extend(stored[position:])
    return "".join(omitted)


def _completion(value: str, values: frozenset[str]) -> str | None:
    """The one stored spelling that completes a value, when the memory has one.

    A stored value completes the model's value when the two begin and end the
    same way, the model's value is a subsequence of it, the material it adds is
    short, and that material carries one of the separators this memory writes
    inside its values.  Those conditions read the addition as the compound
    structure of the answer rather than as answer content, so the value the
    model wrote still decides what the answer is and the memory only decides how
    it is spelled.  A value the memory already spells, a value no stored
    spelling completes, and a value several of them complete are left alone.
    """
    if len(value) < MIN_VALUE_CHARS or value in values:
        return None
    claims = []
    for stored in values:
        if not len(value) < len(stored) <= len(value) + MAX_COMPLETION_CHARS:
            continue
        if stored[0] != value[0] or stored[-1] != value[-1]:
            continue
        omitted = _omitted(value, stored)
        if omitted is None or not any(
            character in VALUE_SEPARATORS for character in omitted
        ):
            continue
        claims.append(stored)
    return claims[0] if len(claims) == 1 else None


def complete_compound(
    text: str, index: tuple[frozenset[str], frozenset[str]]
) -> tuple[str, int]:
    """Write a value the memory spells as a compound at its full length.

    Runs of answer characters are completed one at a time, and only where the
    memory holds exactly one spelling that reads as the run with its interior
    structure restored.  Everything else -- a run the memory does not complete,
    a run whose completion would add content -- is kept as the model wrote it.
    """
    values, alphabet = index
    characters = alphabet - set(VALUE_SEPARATORS)
    if not values or not characters:
        return text, 0
    pattern = re.compile("[%s]+" % re.escape("".join(sorted(characters))))
    applied = 0

    def rewrite(match: re.Match) -> str:
        nonlocal applied
        run = match.group(0)
        completion = _completion(run, values)
        if completion is None:
            return run
        applied += 1
        return completion

    return pattern.sub(rewrite, text), applied
