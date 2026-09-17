"""Answer conventions read off the frozen training memory.

The memory holds the training question/answer pairs. These helpers turn its answers into
a profile — which literal items the answers are made of and how they are composed — and
compare a candidate answer against that wording. Everything is derived from the answer
strings themselves, so the same code applies to any memory in the same format.

An item read on its own is not the whole convention: the memory may only ever write it
inside a longer answer, in which case that complete answer is what has to be copied, and
it may end its items in a way an item of the answer does not, which the memory's own
items are the only evidence for. Which memory item is the same charge as an item of the
answer is read off the two strings as well — by how far they can be read together from
the front, not by how much of one contains the other.
"""

import json
import re
from collections import Counter
from pathlib import Path

MEMORY_PATH = Path("/harness/memory/memory.json")

# Separators that answers use to list several items; also the punctuation a grader-like
# comparison would split on, so the profile's items are the units an answer is judged by.
ITEM_SEPARATORS = (";", "；", ",", "，", "、")

# Wrappers an answer may carry around its content (a bracketed label, an XML-like tag).
MARKUP = re.compile(r"\[[^\[\]]*\]|<[^<>]*>")

MAX_ITEM_DRIFT = 3  # characters two spellings of one charge may differ by at either end
MAX_SUGGESTIONS = 3
MAX_ITEMS = 2000
MAX_ANSWERS = 2000
MAX_TEMPLATES = 2  # compositions of one item that may be quoted as its complete answer

# A vocabulary-like memory repeats a bounded set of short items; a memory of free-form
# answers (structures, sentences, code) has almost no repetition and much longer items.
REPEAT_RATIO = 0.9
MAX_VOCABULARY_ITEM_CHARS = 40

NOTICE_HEADER = (
    "The answer you are about to finish with was checked against the training memory.\n"
)
NOTICE_FOOTER = (
    "\nRewrite final_answer using the memory's wording above: copy a complete answer as it"
    " is when it fits this case, and otherwise keep every item you identified and fix only"
    " its wording, including the way the memory ends an item. Then reply with the same JSON"
    " object."
)


def split_items(answer: str) -> list[str]:
    """The items of one answer, split on the separators the answers themselves use."""
    text = (answer or "").strip()
    for separator in ITEM_SEPARATORS:
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [text] if text else []


def build_profile(targets: list[str]) -> dict:
    """The answer items of a training set and how the answers are composed."""
    items = Counter()
    separators = Counter()
    answers = Counter()
    multi_item = 0
    for target in targets:
        text = (target or "").strip()
        pieces = split_items(text)
        if len(pieces) > 1:
            multi_item += 1
        for separator in ITEM_SEPARATORS:
            if separator in text:
                separators[separator] += 1
        items.update(pieces)
        if text:
            answers[text] += 1
    total = sum(items.values())
    mean_chars = sum(len(item) * count for item, count in items.items()) / total if total else 0.0
    return {
        "items": dict(items.most_common(MAX_ITEMS)),
        "answers": dict(answers.most_common(MAX_ANSWERS)),
        "separators": dict(separators),
        "multi_item_fraction": round(multi_item / len(targets), 4) if targets else 0.0,
        "mean_item_chars": round(mean_chars, 2),
        "vocabulary_like": bool(total)
        and len(items) / total <= REPEAT_RATIO
        and mean_chars <= MAX_VOCABULARY_ITEM_CHARS,
    }


def profile_from_memory(path: Path = MEMORY_PATH) -> dict:
    """The answer profile stored with the frozen memory, or an empty one."""
    try:
        memory = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    profile = memory.get("answer_profile")
    return profile if isinstance(profile, dict) else {}


def final_answer_field(text: str) -> str:
    """The final_answer value of a model response, whether or not it is fenced."""
    if not text:
        return ""
    for candidate in (text.strip(), *_fenced_blocks(text)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "final_answer" in data:
            return str(data["final_answer"])
    match = re.findall(r'"final_answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
    if match:
        try:
            return str(json.loads(f'"{match[-1]}"'))
        except json.JSONDecodeError:
            return match[-1]
    return ""


def _fenced_blocks(text: str) -> list[str]:
    return [block.split("\n", 1)[-1].strip() for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)]


def answer_items(answer: str) -> list[str]:
    """The items of a candidate answer, read the way the memory's answers are read.

    Markup a response wraps its answer in is dropped first, so the items compared are the
    units the answer is made of rather than fragments of them.
    """
    return split_items(MARKUP.sub("", answer or "").strip())


def answer_notice(profile: dict, answer: str, seen: str = "") -> str:
    """What in an answer departs from the memory's wording; empty when nothing does.

    `seen` is the text the model has been shown — the retrieved examples. A complete
    answer is only quoted back when it is part of that text: an answer the model never
    read is not evidence that the extra items it lists belong to the case at hand.
    """
    if not isinstance(profile, dict) or not profile.get("vocabulary_like"):
        return ""
    inventory = profile.get("items") or {}
    if not inventory:
        return ""
    known = {}
    for item, count in inventory.items():
        known.setdefault(str(item).lower(), (str(item), count))
    answers = _answer_counts(profile)
    endings, carriers = _ending_statistics(inventory)
    parts = written_parts(answers)
    lines = []
    for item in answer_items(answer):
        if item.lower() in known:
            continue
        variant = _closest_known(item, known)
        if variant is None:
            line = _ending_notice(item, endings, carriers, parts)
            if not line:
                continue
        else:
            known_item, count = variant
            compositions = _compositions(known_item, answers, seen)
            if compositions:
                quoted = ", ".join(_written(text, tally) for text, tally in compositions)
                verb = "answer" if len(compositions) == 1 else "answers"
                line = (
                    f'- Your answer has "{item}"; the memory writes that charge only inside the'
                    f" complete {verb} {quoted}, never on its own."
                )
            else:
                line = f'- Your answer has "{item}"; the memory writes it as {_written(known_item, count)}.'
        lines.append(line)
        if len(lines) >= MAX_SUGGESTIONS:
            break
    if not lines:
        return ""
    return NOTICE_HEADER + "\n".join(lines) + NOTICE_FOOTER


def _written(text: str, count: int) -> str:
    """One memory wording with how often the memory writes it."""
    occurrences = "occurrence" if count == 1 else "occurrences"
    return f'"{text}" ({count} {occurrences})'


def _answer_counts(profile: dict) -> dict:
    """The complete answers of the memory with how often each is written."""
    answers = profile.get("answers")
    if isinstance(answers, dict) and answers:
        return {str(text): int(count) for text, count in answers.items()}
    return {}


def _ending_statistics(inventory: dict) -> tuple[Counter, Counter]:
    """How many of the memory's items end with each character, and how many carry it.

    A memory that writes its answers out of a bounded set of items also has a way of
    ending them, and an item can depart from that way while matching no memory item
    closely enough to be quoted — the memory uses the character, just never at the end
    of an item. Both counts say that without knowing anything about the subject matter.
    """
    endings = Counter()
    carriers = Counter()
    for item in inventory:
        if not item:
            continue
        endings[item[-1]] += 1
        for character in set(item):
            carriers[character] += 1
    return endings, carriers


def _ending_notice(item: str, endings: Counter, carriers: Counter, parts: set) -> str:
    """The notice for an item whose ending departs from the memory's; empty otherwise.

    Only the ending is reported when the rest of the item is one of the parts the
    memory's own answers are made of: then the memory does write this charge, and the
    trailing character is the whole of the departure. An item the memory writes no part
    of is not reported — there is no wording to correct it towards.
    """
    last = item[-1:]
    if not last or not item[:-1] or item[:-1] not in parts or endings[last] or not carriers[last]:
        return ""
    total = sum(endings.values())
    return (
        f'- Your answer has "{item}"; the memory never ends an item with "{last}"'
        f" ({endings[last]} of {total} items end with it, though {carriers[last]} of them"
        f" carry it), so the memory writes that charge without it."
    )


def written_parts(answers: dict) -> set:
    """Every part the memory's answers are written out of, at the finest split."""
    parts = set()
    pending = list(answers)
    while pending:
        for piece in split_items(pending.pop()):
            if piece in parts:
                continue
            parts.add(piece)
            pending.append(piece)
    return parts


def _compositions(item: str, answers: dict, seen: str = "") -> list[tuple[str, int]]:
    """The complete memory answers that write an item as one part of themselves.

    Empty when the memory also writes the item as an answer of its own (then the item is
    already the whole wording), when the memory writes it in more compositions than can be
    quoted (then none of them is the convention and listing some would make an arbitrary
    choice look canonical), and when none of them is in what the model has read (then the
    quote is not a wording but an invitation to take over another case's items).
    """
    if not answers or item in answers:
        return []
    found = [
        (text, count)
        for text, count in answers.items()
        if text != item and item in split_items(text) and (not seen or text in seen)
    ]
    if not found or len(found) > MAX_TEMPLATES:
        return []
    found.sort(key=lambda entry: (-entry[1], len(entry[0])))
    return found


def _shared_ends(item: str, other: str):
    """What is left of two strings once their shared beginning and ending are read off.

    None when they do not begin together, which is the whole of the test: a memory item
    that only carries the same ending as an answer item is a different charge that shares
    this one's tail (「过失以危险方法危害公共安全」 for 「以危险方法危害公共安全」), while two
    spellings of one charge part company after a beginning the memory also writes.
    """
    start = 0
    while start < len(item) and start < len(other) and item[start] == other[start]:
        start += 1
    if not start:
        return None
    left, right = item[start:], other[start:]
    end = 0
    while end < len(left) and end < len(right) and left[-1 - end] == right[-1 - end]:
        end += 1
    return left[: len(left) - end], right[: len(right) - end]


def _dropped(one: str, other: str) -> bool:
    """Whether one leftover is the other with characters dropped, not with a word swapped."""
    if len(one) > len(other):
        one, other = other, one
    rest = iter(other)
    return all(character in rest for character in one)


def _closest_known(item: str, known: dict):
    """The longest memory item that is a near-variant of an answer item, with its count.

    The variant has to agree at one end of the item and differ only by characters the
    other spelling already has, so an item the memory writes with a piece dropped
    (「非法采伐国家重点保护植物」 for 「非法采伐、毁坏国家重点保护植物」) is reached and an item
    that names something else (「买卖国家机关证件罪」 for 「买卖国家机关公文」) is not.
    """
    lowered = item.lower()
    best = None
    for key, entry in known.items():
        middles = _shared_ends(lowered, key)
        if middles is None:
            continue
        here, there = middles
        if len(here) > MAX_ITEM_DRIFT or len(there) > MAX_ITEM_DRIFT:
            continue
        if not _dropped(here, there):
            continue
        score = (len(key), entry[1])
        if best is None or score > best[0]:
            best = (score, entry)
    return best[1] if best else None
