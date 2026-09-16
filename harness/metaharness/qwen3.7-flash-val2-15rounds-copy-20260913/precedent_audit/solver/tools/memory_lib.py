"""Reference memory: answer profile, similarity retrieval and pre-submit checks.

Everything here is derived from the training references only, and the module is
standard-library only so the memory preparation step can load it directly.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from collections import Counter

CANDIDATE_SEPARATORS = [";", "；", "、", "，", ",", "|", "/", "."]
MIN_SEPARATOR_SHARE = 0.15
MIN_PARTS_WHEN_SPLIT = 1.2
MAX_SEPARATORS = 3
# A separator only cuts answers into units when the pieces it produces are also
# attested as complete answers somewhere else in the references. Punctuation that
# only ever appears inside an answer (and whose pieces never stand alone) is part
# of the answer itself, so splitting on it manufactures fragments.
MIN_PIECE_ATTESTATION = 0.15
RELATIVE_PIECE_ATTESTATION = 0.4

MAX_QUESTION_CHARS = 4000
MAX_STORED_REFS = 1200

MAX_LABEL_CHARS = 2800
MAX_FULL_ANSWERS = 40
MAX_GROUPS = 10
MAX_GROUP_PARTS = 8

GRAM_SIZE = 4
GROUP_SIMILARITY = 0.08
DIVERSITY_PENALTY = 0.55
MAX_REFERENCES_FULL = 120

MAX_AUDIT_UNITS = 4
MAX_EVIDENCE_CASES = 1
EVIDENCE_CHARS = 260
MAX_RELATED = 4
# Writing systems without spaces let a unit sit directly against its modifier, so an
# edge match alone is evidence there; in spaced scripts the junction has to fall on a
# word boundary, otherwise "flu" would look like a form of "reflux".
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")


def split_parts(text: str, separators: list[str]) -> list[str]:
    """Split an answer into its parts using the separators the references use."""
    parts = [text or ""]
    for separator in separators:
        expanded = []
        for part in parts:
            expanded.extend(part.split(separator))
        parts = expanded
    return [part.strip() for part in parts if part and part.strip()]


def piece_attestation(targets: list[str], separator: str) -> float:
    """Share of a separator's pieces that also occur as complete reference answers.

    High attestation means the separator really joins stand-alone units. Zero means
    every piece only ever exists inside a bigger answer, i.e. the punctuation sits
    *within* the units, so cutting there would invent fragments that the references
    never use as answers.
    """
    whole = set(targets)
    pieces = [
        part.strip()
        for target in targets
        if separator in target
        for part in target.split(separator)
        if part.strip()
    ]
    if not pieces:
        return 0.0
    return sum(1 for piece in pieces if piece in whole) / len(pieces)


def affix_extension(shorter: str, longer: str) -> tuple[str, str] | None:
    """How ``longer`` extends ``shorter`` at one of its edges, if it does.

    Returns ``(side, added)`` where side is ``"head"`` when the added text precedes
    the shorter unit and ``"tail"`` when it follows it. Only edges count, and in
    spaced scripts the junction must fall on a word boundary, so an answer is never
    reported as a form of a longer word that merely contains it.
    """
    if not shorter or len(shorter) >= len(longer):
        return None
    for side in ("tail", "head"):
        if side == "tail" and longer.endswith(shorter):
            cut = len(longer) - len(shorter)
            added, junction = longer[:cut], longer[cut - 1]
        elif side == "head" and longer.startswith(shorter):
            added, junction = longer[len(shorter) :], longer[len(shorter)]
        else:
            continue
        if not added:
            continue
        if CJK.search(shorter) or not (junction.isalnum() or junction == "_"):
            return side, added
    return None


def _junction_ok(*ends: tuple[str, int, bool]) -> bool:
    """Whether a shared run ends where a unit could end, on every side it was cut from.

    ``ends`` are ``(text, size, forward)``; ``forward`` says whether the shared run is
    at the head of ``text``. A run written in a spaced script only counts when the
    character just past it is not part of a word, so sharing the letters of a word is
    not the same as sharing a word.
    """
    for text, size, forward in ends:
        shared = text[:size] if forward else text[-size:]
        if CJK.search(shared):
            continue
        rest = text[size:] if forward else text[:-size]
        if not rest:
            continue
        junction = rest[0] if forward else rest[-1]
        if junction.isalnum() or junction == "_":
            return False
    return True


def shared_edge(first: str, second: str) -> int:
    """Length of the longest head or tail two units share, as whole elements."""
    best = 0
    limit = min(len(first), len(second))
    for size in range(limit, 1, -1):
        if first[:size] == second[:size] and _junction_ok(
            (first, size, True), (second, size, True)
        ):
            best = max(best, size)
        if first[-size:] == second[-size:] and _junction_ok(
            (first, size, False), (second, size, False)
        ):
            best = max(best, size)
    return best


def derive_separators(targets: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split the punctuation the references use into list separators and inner punctuation.

    Returns ``(shape_separators, label_separators, inner_punctuation)``:

    - ``label_separators`` cut answers into stand-alone units and are the only ones
      used to build the label inventory, so the inventory never contains fragments.
    - ``shape_separators`` describe how many units an answer has. When nothing is
      attested they fall back to the most frequent candidate, which still tells the
      solver how answers are structured even when the units are free-form.
    - ``inner_punctuation`` occurs inside answers but never separates stand-alone
      units; it belongs to the surrounding unit.
    """
    total = len(targets) or 1
    scored = []
    for separator in CANDIDATE_SEPARATORS:
        hits = sum(1 for target in targets if separator in target)
        if hits / total < MIN_SEPARATOR_SHARE:
            continue
        widths = [
            len([part for part in target.split(separator) if part.strip()])
            for target in targets
            if separator in target
        ]
        if not widths or sum(widths) / len(widths) < MIN_PARTS_WHEN_SPLIT:
            continue
        scored.append((hits, separator))
    scored.sort(key=lambda item: (-item[0], item[1]))
    candidates = [separator for _, separator in scored[:MAX_SEPARATORS]]
    evidence = {separator: piece_attestation(targets, separator) for separator in candidates}
    best = max(evidence.values()) if evidence else 0.0
    threshold = max(MIN_PIECE_ATTESTATION, RELATIVE_PIECE_ATTESTATION * best)
    label_separators = [separator for separator in candidates if evidence[separator] >= threshold]
    inner = [separator for separator in candidates if separator not in label_separators]
    shape_separators = label_separators or candidates[:1]
    return shape_separators, label_separators, inner


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[len(ordered) // 2])


def build_profile(
    targets: list[str],
    separators: list[str],
    label_separators: list[str],
    inner_punctuation: list[str] | None = None,
) -> dict:
    """Summarise the shape and vocabulary of the reference answers.

    The vocabulary is cut with ``label_separators`` only, so punctuation that sits
    inside a single answer never turns one reference answer into several fragments.
    """
    parts = [part for target in targets for part in split_parts(target, label_separators)]
    part_counts = Counter(parts)
    total_parts = sum(part_counts.values())
    recurring = sum(count for count in part_counts.values() if count >= 2)
    distinct = len(part_counts)
    median_chars = _median([len(target) for target in targets])
    label_like = (
        median_chars <= 40 and distinct <= max(20, int(0.6 * total_parts))
    ) or (total_parts > 0 and recurring / total_parts >= 0.5)

    widths = Counter(len(split_parts(target, separators)) for target in targets)
    profile = {
        "separators": separators,
        "label_separators": label_separators,
        "inner_punctuation": [
            [separator, round(sum(1 for target in targets if separator in target) / (len(targets) or 1), 2)]
            for separator in (inner_punctuation or [])
        ],
        "label_like": bool(label_like),
        "n_references": len(targets),
        "part_widths": {str(width): count for width, count in sorted(widths.items())},
        "median_answer_chars": median_chars,
        "labels": [],
        "answer_patterns": [],
        "groups": [],
    }
    if label_like:
        ordered = sorted(part_counts.items(), key=lambda item: (-item[1], item[0]))
        profile["labels"] = [[text, count] for text, count in ordered]
    repeated = [(text, count) for text, count in Counter(targets).items() if count >= 2]
    repeated.sort(key=lambda item: (-item[1], item[0]))
    profile["answer_patterns"] = [[text, count] for text, count in repeated[:MAX_FULL_ANSWERS]]
    return profile


def derive_group_keys(questions: list[str], min_prefix: int = 32, max_prefix: int = 64) -> list[str]:
    """Question headers that several references share, longest first."""
    total = len(questions)
    if total < 8:
        return []
    min_support = max(3, math.ceil(0.05 * total))
    counts: Counter = Counter()
    for question in questions:
        head = " ".join((question or "").split())
        limit = min(max_prefix, max(min_prefix, len(head) // 2))
        for length in range(limit, min_prefix - 1, -1):
            counts[head[:length]] += 1
    keys = [key for key, count in counts.items() if count >= min_support]
    keys.sort(key=len, reverse=True)
    kept: list[str] = []
    for key in keys:
        if any(existing.startswith(key) for existing in kept):
            continue
        kept.append(key)
        if len(kept) >= MAX_GROUPS:
            break
    return kept


def assign_groups(questions: list[str], keys: list[str]) -> list[int]:
    """Index of the most specific shared header each question belongs to (-1 none)."""
    assignment = []
    for question in questions:
        head = " ".join((question or "").split())
        index = -1
        for position, key in enumerate(keys):
            if head.startswith(key):
                index = position
                break
        assignment.append(index)
    return assignment


def build_memory(train: list[dict], epochs: int = 1) -> dict:
    """Turn the training references into the frozen memory the solver reads."""
    items = list(train)
    if len(items) > MAX_STORED_REFS:
        step = math.ceil(len(items) / MAX_STORED_REFS)
        items = items[::step]
    seen = set()
    examples = []
    for _ in range(max(1, int(epochs))):
        for item in items:
            question = " ".join(str(item.get("raw_question") or item.get("input") or "").split())
            answer = str(item.get("target") or "").strip()
            key = (question, answer)
            if not answer or key in seen:
                continue
            seen.add(key)
            examples.append({"q": question[:MAX_QUESTION_CHARS], "a": answer})
    answers = [example["a"] for example in examples]
    separators, label_separators, inner_punctuation = derive_separators(answers)
    profile = build_profile(answers, separators, label_separators, inner_punctuation)
    keys = derive_group_keys([example["q"] for example in examples])
    assignment = assign_groups([example["q"] for example in examples], keys)
    groups = []
    for position, key in enumerate(keys):
        members = [example for example, group in zip(examples, assignment) if group == position]
        if len(members) < 3:
            continue
        parts = Counter(
            part for member in members for part in split_parts(member["a"], separators)
        )
        recurring = [(text, count) for text, count in parts.items() if count >= 2]
        recurring.sort(key=lambda item: (-item[1], item[0]))
        member_widths = Counter(len(split_parts(member["a"], separators)) for member in members)
        groups.append(
            {
                "key": key,
                "size": len(members),
                "parts": [[text, count] for text, count in recurring[:MAX_GROUP_PARTS]],
                "widths": {str(width): count for width, count in sorted(member_widths.items())},
            }
        )
    profile["groups"] = groups
    for example, group in zip(examples, assignment):
        example["g"] = group
    return {"epochs": int(epochs), "examples": examples, "profile": profile}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def clean_group_key(key: str) -> str:
    """Trim a shared question header back to its last full sentence when possible."""
    cut = key.rfind(". ")
    if cut + 1 >= 24:
        return key[: cut + 1]
    return key


class MemoryView:
    """Read-only view over the frozen memory, used while solving."""

    def __init__(self, memory: dict):
        self.memory = memory or {}
        self.examples = list(self.memory.get("examples") or [])
        self.profile = dict(self.memory.get("profile") or {})
        self.separators = list(self.profile.get("separators") or [])
        self.label_separators = list(self.profile.get("label_separators") or [])
        self.inner_punctuation = [pair[0] for pair in self.profile.get("inner_punctuation") or []]
        self.label_pairs = list(self.profile.get("labels") or [])
        self.labels = [text for text, _ in self.label_pairs]
        self.label_set = set(self.labels)
        self._related: dict[str, tuple[list[tuple[str, int]], list[tuple[str, int]]]] = {}
        self._pieces: dict[str, list[tuple[str, int]]] | None = None
        self._gram_sets: list[set[str]] = []
        self._weights: list[dict[str, float]] = []
        self._norms: list[float] = []
        self._document_frequency: Counter = Counter()
        self._query_group = -2
        self._support_cache: tuple[str, dict[str, float]] | None = None
        self._indexed = False

    # ---------------------------------------------------------------- retrieval

    @staticmethod
    def _grams(text: str) -> set[str]:
        text = " ".join((text or "").lower().split())
        if len(text) <= GRAM_SIZE:
            return {text} if text else set()
        return {text[index : index + GRAM_SIZE] for index in range(len(text) - GRAM_SIZE + 1)}

    def _index(self) -> None:
        if self._indexed:
            return
        self._indexed = True
        self._gram_sets = [self._grams(example.get("q", "")) for example in self.examples]
        document_frequency: Counter = Counter()
        for grams in self._gram_sets:
            document_frequency.update(grams)
        self._document_frequency = document_frequency
        total = len(self._gram_sets) or 1
        self._weights = []
        self._norms = []
        for grams in self._gram_sets:
            vector = {
                gram: math.log((total + 1) / (document_frequency[gram] + 1)) + 1.0
                for gram in grams
            }
            self._weights.append(vector)
            self._norms.append(math.sqrt(sum(value * value for value in vector.values())) or 1.0)

    def _idf(self, gram: str) -> float:
        total = len(self.examples) or 1
        return math.log((total + 1) / (self._document_frequency.get(gram, 0) + 1)) + 1.0

    def _similarity(self, query: str, index: int) -> float:
        self._index()
        query_vector = {gram: self._idf(gram) for gram in self._grams(query)}
        query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
        reference = self._weights[index]
        shared = set(query_vector) & set(reference)
        if not shared:
            return 0.0
        dot = sum(query_vector[gram] * reference[gram] for gram in shared)
        score = dot / (query_norm * self._norms[index])
        if index < len(self.examples) and self.examples[index].get("g", -1) >= 0:
            if self.examples[index].get("g") == self._query_group:
                score += GROUP_SIMILARITY
        return score

    def _set_query_group(self, query: str) -> None:
        keys = [group.get("key", "") for group in self.profile.get("groups") or []]
        head = " ".join((query or "").split())
        self._query_group = -1
        for position, key in enumerate(keys):
            # The question reaches the solver wrapped in the task's own boilerplate, so
            # the shared header counts wherever it occurs in the question, not only at
            # its start; the stored references are bare questions that begin with it.
            if key and key in head:
                self._query_group = position
                break

    def _pair_similarity(self, first: int, second: int) -> float:
        self._index()
        left, right = self._gram_sets[first], self._gram_sets[second]
        if not left or not right:
            return 0.0
        union = len(left | right)
        return len(left & right) / union if union else 0.0

    def _mmr(self, scores: list[float], pool: list[int], limit: int) -> list[int]:
        pool = list(pool)
        chosen: list[int] = []
        while pool and len(chosen) < limit:
            best_index, best_value = pool[0], float("-inf")
            for index in pool:
                penalty = max(self._pair_similarity(index, other) for other in chosen) if chosen else 0.0
                value = scores[index] - DIVERSITY_PENALTY * penalty
                if value > best_value:
                    best_index, best_value = index, value
            chosen.append(best_index)
            pool.remove(best_index)
        return chosen

    def search(self, query: str, limit: int = 10, diverse: bool = True) -> list[int]:
        if not self.examples:
            return []
        self._set_query_group(query)
        scores = [self._similarity(query, index) for index in range(len(self.examples))]
        pool = sorted(range(len(self.examples)), key=lambda index: -scores[index])
        limit = max(1, min(limit, len(pool)))
        if not diverse:
            return pool[:limit]
        return self._mmr(scores, pool, limit)

    def select_for_prompt(self, query: str, reference_chars: int, max_references: int) -> list[int]:
        """References to quote in the prompt: the whole set when it fits, else a ranked subset."""
        if not self.examples:
            return []
        self._set_query_group(query)
        scores = [self._similarity(query, index) for index in range(len(self.examples))]
        order = sorted(range(len(self.examples)), key=lambda index: -scores[index])
        if self._query_group >= 0:
            order = [index for index in order if self.examples[index].get("g") == self._query_group] + [
                index for index in order if self.examples[index].get("g") != self._query_group
            ]
        rendered = sum(
            len(self.render([index], per_reference=1200)) for index in order[: MAX_REFERENCES_FULL]
        )
        if len(order) <= MAX_REFERENCES_FULL and rendered <= reference_chars:
            return order
        chosen: list[int] = []
        if self._query_group >= 0:
            family = [index for index in order if self.examples[index].get("g") == self._query_group]
            chosen = self._mmr(scores, family, max(2, max_references // 2))
        rest = [index for index in range(len(self.examples)) if index not in set(chosen)]
        chosen.extend(self._mmr(scores, rest, max(1, max_references - len(chosen))))
        return chosen

    def keyword_search(self, keyword: str, limit: int = 8) -> list[int]:
        if not keyword:
            return []
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        hits = [
            index
            for index, example in enumerate(self.examples)
            if pattern.search(example.get("q", "")) or pattern.search(example.get("a", ""))
        ]
        return hits[:limit]

    # -------------------------------------------------------------- formatting

    def render(self, indexes: list[int], per_reference: int = 900, start: int = 1) -> str:
        if not indexes:
            return "No reference cases available."
        keys = [group.get("key", "") for group in self.profile.get("groups") or []]
        blocks = []
        for offset, index in enumerate(indexes):
            example = self.examples[index]
            group = example.get("g", -1)
            header = f"[{start + offset}]"
            if isinstance(group, int) and 0 <= group < len(keys):
                header += f" (question type: {_truncate(clean_group_key(keys[group]), 70)})"
            blocks.append(
                f"{header}\nQ: {_truncate(example.get('q', ''), per_reference)}\nA: {example.get('a', '')}"
            )
        return "\n\n".join(blocks)

    def render_references(self, query: str, limit: int = 10, per_reference: int = 900) -> str:
        return self.render(self.search(query, limit=limit, diverse=True), per_reference=per_reference)

    def _shape_text(self) -> str:
        widths = {int(width): count for width, count in (self.profile.get("part_widths") or {}).items()}
        total = sum(widths.values()) or 1
        detail = ", ".join(
            f"{width} part{'s' if width != 1 else ''} in {round(100 * count / total)}%"
            for width, count in sorted(widths.items())
        )
        if self.separators:
            shown = " ".join(f"'{separator}'" for separator in self.separators)
            joined = f"parts are normally separated by {shown}"
        else:
            joined = "each reference answer is a single part"
        return f"- Answer shape: {detail}; {joined}."

    def _group_shape_note(self, width: int) -> str:
        """What questions of this type usually answer with, when the draft is shorter.

        The profile states the answer shape for the whole corpus; a question that belongs
        to a recurring type is better compared against that type, whose answers repeat the
        same units, so a unit that applies can be seen to be missing from the draft.
        """
        groups = self.profile.get("groups") or []
        index = self._query_group
        if not groups or not isinstance(index, int) or not 0 <= index < len(groups):
            return ""
        group = groups[index]
        widths = {int(size): count for size, count in (group.get("widths") or {}).items()}
        total = sum(widths.values()) or 1
        more = sum(count for size, count in widths.items() if size > width)
        if not widths or more / total <= 0.2:
            return ""
        note = (
            f"- Question type: this question is of the type"
            f" {_truncate(clean_group_key(group.get('key', '')), 60)!r} ({group.get('size')}"
            f" references), where {round(100 * more / total)}% of the answers have more units than"
            " yours."
        )
        recurring = ", ".join(
            f"{text} ({count})" for text, count in (group.get("parts") or [])[:MAX_GROUP_PARTS]
        )
        if recurring:
            note += f" Units that recur in the answers there: {recurring}."
        note += " Check whether an applicable unit was left out."
        return note

    def _profile_text(self) -> str:
        if not self.examples:
            return ""
        lines = [f"REFERENCE PROFILE (derived from {len(self.examples)} training references)"]
        lines.append(self._shape_text())
        patterns = self.profile.get("answer_patterns") or []
        compound = any(
            any(separator in text for separator in self.separators) for text, _ in patterns
        )
        if patterns and (compound or not (self.profile.get("label_like") and self.labels)):
            shown = ", ".join(f"{text} ({count})" for text, count in patterns[:MAX_FULL_ANSWERS])
            lines.append(
                f"- Reference answers that appear more than once: {_truncate(shown, 1400)}"
            )
        if self.profile.get("label_like") and self.labels:
            for separator, share in self.profile.get("inner_punctuation") or []:
                if not any(separator in label for label in self.labels):
                    continue
                lines.append(
                    f"- '{separator}' appears inside {round(100 * share)}% of the reference answers"
                    " but never separates units that stand alone as answers elsewhere. It belongs to"
                    " the label itself: the labels below already contain it where it applies, so never"
                    " split a label at it, never drop the text on either side of it, and never answer"
                    " with only one side of it."
                )
            lines.append(
                "- Reference units in use, with how many references use each (this is evidence about"
                " vocabulary, not a closed list: a correct unit may be missing from it). When your"
                " answer is one of these units, copy it character for character. When the facts call"
                " for a unit that is not here, write that unit yourself in the same style and at the"
                " same level of specificity, and never put a listed unit in its place just because"
                " the listed one looks related:"
            )
            inventory: list[str] = []
            used = 0
            for text, count in self.profile.get("labels") or []:
                entry = f"{text} ({count})"
                if used + len(entry) + 2 > MAX_LABEL_CHARS:
                    if inventory:
                        lines.append("  " + ", ".join(inventory))
                    lines.append("  ... (further labels omitted; grep the memory for more)")
                    inventory, used = [], 0
                    break
                inventory.append(entry)
                used += len(entry) + 2
            if inventory:
                lines.append("  " + ", ".join(inventory))
        else:
            lines.append(
                "- Reference labels: none; answers are free-form, so match the reference format and"
                " separators instead of choosing from a list."
            )
        for group in self.profile.get("groups") or []:
            parts = ", ".join(f"{text} ({count})" for text, count in group.get("parts") or [])
            entry = (
                f"- Question type {_truncate(clean_group_key(group.get('key', '')), 70)!r}"
                f" ({group.get('size')} references)"
            )
            if parts:
                entry += f"; recurring answer units there: {_truncate(parts, 500)}"
            widths = group.get("widths") or {}
            total = sum(widths.values()) or 1
            if widths and len(widths) > 1:
                spread = ", ".join(
                    f"{width} unit{'s' if int(width) != 1 else ''} in {round(100 * count / total)}%"
                    for width, count in sorted(widths.items(), key=lambda item: int(item[0]))
                )
                entry += f"; answer length there: {spread}"
            lines.append(entry)
        return "\n".join(lines)

    def guide(self, query: str, reference_chars: int = 12000, max_references: int = 16) -> str:
        """Compact briefing injected into the solver prompt before it starts."""
        if not self.examples:
            return ""
        indexes = self.select_for_prompt(query, reference_chars, max_references)
        budget = reference_chars
        shown: list[str] = []
        for index in indexes:
            block = self.render([index], per_reference=1200, start=len(shown) + 1)
            if len(block) > budget:
                if shown:
                    break
                block = self.render([index], per_reference=max(300, budget - 40), start=1)
            shown.append(block)
            budget -= len(block) + 2
            if budget <= 0:
                break
        header = "TRAINING REFERENCES" if len(shown) == len(self.examples) else "MOST SIMILAR TRAINING REFERENCES"
        return "\n".join([self._profile_text(), "", header, "\n\n".join(shown)])

    # ------------------------------------------------------- unit relationships

    def units_of(self, answer: str) -> list[str]:
        return split_parts(answer, self.label_separators)

    def related_units(self, unit: str) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        """Reference units related to ``unit`` by what sits at its edge.

        Returns ``(broader, narrower)``: units that extend ``unit`` (they add an
        element at one edge, so they say the same thing more specifically) and units
        that ``unit`` extends. Edge sharing is how a family of units that differ only
        by a modifier presents itself, so this is the set worth re-reading the facts
        against before choosing between them.
        """
        if unit in self._related:
            return self._related[unit]
        broader: list[tuple[str, int]] = []
        narrower: list[tuple[str, int]] = []
        for label, count in self.label_pairs:
            if label == unit:
                continue
            if affix_extension(unit, label):
                broader.append((label, count))
            elif affix_extension(label, unit):
                narrower.append((label, count))
        broader.sort(key=lambda item: (-item[1], item[0]))
        narrower.sort(key=lambda item: (-item[1], item[0]))
        self._related[unit] = (broader[:MAX_RELATED], narrower[:MAX_RELATED])
        return self._related[unit]

    def mentioned_units(self, text: str, limit: int | None = None) -> list[tuple[str, int]]:
        """Reference units the solver named in its own notes, most used first.

        A longer unit name that contains a shorter one wins, so a note that names a
        full unit is not also read as naming each of its fragments.
        """
        if not text:
            return []
        hits = [(label, count) for label, count in self.label_pairs if label in text]
        hits.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
        kept: list[tuple[str, int]] = []
        for label, count in hits:
            if any(label in other for other, _ in kept):
                continue
            kept.append((label, count))
            if limit is not None and len(kept) >= limit:
                break
        return kept

    def _relation_text(self, unit: str, other: str) -> str:
        """Spell out how one of two edge-related units is built from the other.

        The element they differ by is what the facts have to decide, so the note names
        it instead of leaving the solver to re-derive it: ``'非国家工作人员受贿' =
        '非国家工作人员' + '受贿'``.
        """
        for shorter, longer in ((other, unit), (unit, other)):
            extension = affix_extension(shorter, longer)
            if not extension:
                continue
            side, added = extension
            if side == "tail":
                return f"'{longer}' = '{added}' + '{shorter}'"
            return f"'{longer}' = '{shorter}' + '{added}'"
        return ""

    def support_scores(self, question: str) -> dict[str, float]:
        """How strongly this question's own references support each unit.

        For every unit, the similarity of the closest reference case that answers with
        it. This is the local evidence for a unit - a case with nearly these facts that
        was answered that way - as opposed to how often the unit occurs in the corpus.
        """
        cached = getattr(self, "_support_cache", None)
        if cached is not None and cached[0] == question:
            return cached[1]
        self._set_query_group(question)
        scores: dict[str, float] = {}
        for index, example in enumerate(self.examples):
            similarity = self._similarity(question, index)
            if similarity <= 0:
                continue
            for unit in self.units_of(example.get("a", "")):
                if similarity > scores.get(unit, 0.0):
                    scores[unit] = similarity
        self._support_cache = (question, scores)
        return scores

    def _audit_rank(
        self, entry: tuple[str, int], units: list[str], support: dict[str, float]
    ) -> tuple:
        """Order the reconsidered units: the ones this question's references support first.

        A candidate that competes with a unit already in the draft is the either/or
        decision the facts have to settle, so those come first; the rest follow the
        evidence, i.e. how close the reference cases that answer them are to this
        question. Corpus frequency is deliberately not what decides the order: a unit
        that is common in the references is not more likely to be the answer here.
        """
        label, count = entry
        confusable = any(
            affix_extension(unit, label)
            or affix_extension(label, unit)
            or shared_edge(unit, label) >= 2
            or difflib.SequenceMatcher(None, unit, label).ratio() >= 0.6
            for unit in units
        )
        return (
            0 if confusable else 1,
            -round(support.get(label, 0.0), 6),
            -count,
            -len(label),
            label,
        )

    def _in_draft(self, label: str, units: list[str]) -> bool:
        return any(label == unit or label in unit for unit in units)

    def piece_units(self) -> dict[str, list[tuple[str, int]]]:
        """Elements that only ever occur inside a longer reference unit.

        A reference unit can be several words joined by punctuation the references
        never use to separate answers. Answering with one element of such a unit plus
        a word of one's own is not that unit, and this index is what makes it visible.
        """
        if self._pieces is None:
            index: dict[str, list[tuple[str, int]]] = {}
            for label, count in self.label_pairs:
                for piece in split_parts(label, self.inner_punctuation):
                    if piece and piece != label and len(piece) >= 2:
                        index.setdefault(piece, []).append((label, count))
            self._pieces = index
        return self._pieces

    # ------------------------------------------------------------- evidence

    def _excerpt(self, question: str, query: str, chars: int = EVIDENCE_CHARS) -> str:
        """The part of a reference question that lines up with the current question.

        Reference questions can be long and mostly boilerplate; scoring sentences
        against the query keeps the evidence about the facts that matter here.
        """
        head = " ".join((question or "").split())
        if len(head) <= chars:
            return head
        sentences = [part.strip() for part in re.split(r"(?<=[。！？!?;；])|\n+", head) if part.strip()]
        if len(sentences) < 2:
            return _truncate(head, chars)
        self._index()
        query_vector = {gram: self._idf(gram) for gram in self._grams(query)}
        query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
        scored = []
        for position, sentence in enumerate(sentences):
            grams = self._grams(sentence)
            shared = set(query_vector) & grams
            if not shared:
                continue
            norm = math.sqrt(sum(self._idf(gram) ** 2 for gram in grams)) or 1.0
            dot = sum(query_vector[gram] * self._idf(gram) for gram in shared)
            scored.append((dot / (query_norm * norm), position))
        if not scored:
            return _truncate(head, chars)
        scored.sort(key=lambda item: -item[0])
        chosen = sorted(position for _, position in scored[:3])
        out = ""
        for position in chosen:
            candidate = out + sentences[position]
            if len(candidate) > chars and out:
                break
            out = candidate
        return _truncate(out or sentences[scored[0][1]], chars)

    def evidence(self, label: str, query: str, cases: int = MAX_EVIDENCE_CASES) -> list[str]:
        """Reference cases that answer with ``label``, closest to the current question."""
        self._set_query_group(query)
        matching = [
            index
            for index, example in enumerate(self.examples)
            if label in self.units_of(example.get("a", ""))
        ]
        matching.sort(key=lambda index: -self._similarity(query, index))
        out = []
        for index in matching[:cases]:
            example = self.examples[index]
            out.append(
                f"  Q: {self._excerpt(example.get('q', ''), query)}\n     A: {example.get('a', '')}"
            )
        return out

    # ------------------------------------------------------------------ checks

    def check(self, draft: str, question: str = "", considered: str = "") -> str:
        if not isinstance(considered, str):
            considered = ", ".join(str(unit) for unit in considered or [])
        if not isinstance(draft, str):
            draft = str(draft)
        text = (draft or "").strip()
        if not text:
            return "The draft answer is empty. Produce the answer in the required format."
        repaired = self._extract(text)
        self._set_query_group(question)
        tags = self._required_markup(question)
        core = repaired
        for tag in tags:
            core = core.replace(tag, " ")
        parts = split_parts(core, self.separators)
        units = split_parts(core, self.label_separators)
        problems: list[str] = []
        notes: list[str] = []
        widths = {int(width): count for width, count in (self.profile.get("part_widths") or {}).items()}
        total_widths = sum(widths.values()) or 1
        if widths:
            low, high = min(widths), max(widths)
            more = sum(count for width, count in widths.items() if width > len(parts))
            fewer = sum(count for width, count in widths.items() if width < len(parts))
            if low == high:
                line = (
                    f"- Shape: your answer has {len(parts)} part(s); every reference answer has"
                    f" {low} part(s)."
                )
            else:
                line = (
                    f"- Shape: your answer has {len(parts)} part(s); reference answers run from {low}"
                    f" to {high} parts"
                )
                if high > len(parts) and more / total_widths > 0.2:
                    line += (
                        f", and {round(100 * more / total_widths)}% of references have more parts than"
                        " yours - check whether an applicable part was left out."
                    )
                elif len(parts) > low and fewer / total_widths > 0.2:
                    line += (
                        f", and {round(100 * fewer / total_widths)}% of references have fewer parts"
                        " than yours - check whether every part you listed really applies."
                    )
                else:
                    line += "."
            notes.append(line)
        for tag in tags:
            if tag not in repaired:
                problems.append(
                    f"- Markup: the question asks for {tag}, which is missing from the draft."
                )
        review: list[str] = []
        if self.label_set:
            known = [part for part in units if part in self.label_set]
            unknown = [part for part in units if part not in self.label_set]
            for part in unknown:
                review.append(self._unknown_unit_note(part))
            for part in known:
                broader, narrower = self.related_units(part)
                if broader:
                    shown = ", ".join(f"{label} ({count})" for label, count in broader)
                    spelled = "; ".join(
                        spelled
                        for spelled in (
                            self._relation_text(part, label) for label, _ in broader[:2]
                        )
                        if spelled
                    )
                    review.append(
                        f"- Unit: '{part}' is used by the references, and so are the units that say it"
                        f" more specifically: {shown}. They are different units, not longer spellings of"
                        + (f" yours: {spelled}." if spelled else " yours.")
                        + " Settle it on the facts, not on which unit is commoner: the answer is the"
                        " one whose elements the facts establish - the longer unit if they establish"
                        " the element it adds, and this one if they do not."
                    )
                if narrower:
                    shown = ", ".join(f"{label} ({count})" for label, count in narrower)
                    spelled = "; ".join(
                        spelled
                        for spelled in (
                            self._relation_text(label, part) for label, _ in narrower[:2]
                        )
                        if spelled
                    )
                    review.append(
                        f"- Unit: '{part}' adds an element to the reference unit(s) {shown}"
                        + (f" ({spelled})" if spelled else "")
                        + ". That longer form is never used by the references; use the reference unit"
                        " verbatim unless the added element is genuinely part of the answer."
                    )
            review.extend(self._considered_audit(considered, units, question))
            if not unknown:
                notes.append(
                    f"- Units: all {len(units)} unit(s) are reference units, spelled verbatim."
                    " That only means the spelling is right, not that the set is complete."
                )
        else:
            notes.append(
                "- Units: no reference unit list; check that each part follows the reference format"
                " exactly (characters, separators, case)."
            )
            shape = self._group_shape_note(len(parts))
            if shape:
                notes.append(shape)
        unbalanced = self._unbalanced(repaired)
        if unbalanced:
            problems.append(f"- Structure: unbalanced {unbalanced} in the draft.")
        header = (
            "Issues to review before answering:"
            if problems
            else "No surface problem found. Surface checking cannot show that the answer is complete"
            " or correct - work through the points below before submitting."
        )
        return "\n".join([header, *(problems or []), *(review or []), *notes])

    def _unknown_unit_note(self, part: str) -> str:
        """How to review a draft unit the reference vocabulary does not contain.

        The vocabulary comes from a sample of references, so a correct unit can be
        missing from it. The note therefore never tells the solver to prefer a listed
        unit over this one; it only separates a genuine near miss from a unit that is
        a differently scoped relative of a listed one.
        """
        broader, narrower = self.related_units(part)
        if narrower:
            shown = ", ".join(f"{label} ({count})" for label, count in narrower)
            return (
                f"- Unit: '{part}' extends the reference unit(s) {shown} with extra text the"
                " references never use. If that reference unit is the answer, submit it verbatim on"
                " its own; only keep the longer form if the extra text is genuinely part of it."
            )
        pieces = self.piece_units()
        if part in pieces:
            shown = ", ".join(f"{label} ({count})" for label, count in pieces[part][:MAX_RELATED])
            return (
                f"- Unit: '{part}' is one element of the reference unit(s) {shown}, which the"
                " references never use in pieces. If one of those whole units is the answer, submit"
                " it verbatim and complete - answering with one element of it is not that unit, and"
                " never split a unit at the punctuation inside it. Keep it on its own only if the"
                " facts make it a complete unit by itself."
            )
        owners = [
            (piece, units)
            for piece, units in pieces.items()
            if affix_extension(piece, part)
        ]
        if owners:
            owners.sort(key=lambda item: (-max(count for _, count in item[1]), -len(item[0])))
            piece, units = owners[0]
            shown = ", ".join(f"{label} ({count})" for label, count in units[:MAX_RELATED])
            return (
                f"- Unit: '{part}' extends '{piece}', which the references use only as part of the"
                f" unit(s) {shown}. The whole unit is the answer, not one element of it plus a word of"
                " your own: if that unit is the answer, submit it verbatim and complete."
            )
        if broader:
            shown = ", ".join(f"{label} ({count})" for label, count in broader)
            return (
                f"- Unit: '{part}' is a piece of the reference unit(s) {shown}, which the references"
                " always use whole. If that whole unit is the answer, submit it verbatim and complete;"
                f" keep '{part}' on its own only if the facts make it a complete unit by itself."
            )
        close = difflib.get_close_matches(part, self.labels, n=3, cutoff=0.85)
        if close:
            return (
                f"- Unit: '{part}' is not a reference unit but is spelled almost exactly like"
                f" {', '.join(close)}. If that reference unit is the answer, use its spelling"
                " character for character."
            )
        return (
            f"- Unit: '{part}' is not in the reference vocabulary. That is not a reason to change it:"
            " the vocabulary is only what the training references happen to show. Keep it if the facts"
            " establish it, written in the same style and at the same level of specificity as the"
            " units the references use, and do not swap it for a listed unit that merely looks similar."
        )

    def considered_units(self, text: str) -> list[str]:
        """The candidate units the solver listed, in the order it listed them.

        The list is free text, so tokens are kept only when they look like a unit
        rather than a sentence: short, and not running past a sentence break.
        """
        if not text:
            return []
        units: list[str] = []
        for raw in re.split(r"[,，、;；|\n]+", text):
            token = raw.strip().strip("。.!?！？:：-—*\"'()（）[]【】 ")
            if len(token) < 2 or len(token) > 40 or re.search(r"[。！？!?]", token):
                continue
            if token not in units:
                units.append(token)
        return units

    def _considered_audit(self, considered: str, units: list[str], question: str) -> list[str]:
        """Re-open the units the solver named while deciding but did not submit.

        The candidate set a solver talks itself out of is where wrong answers come
        from. A candidate that the references use comes back with the cases that
        answer it; a candidate they do not use comes back as a unit that may still be
        right, because the vocabulary is only what the sample happens to show. Either
        way it may only be set aside for a factual reason.
        """
        if not self.label_set:
            return []
        if not (considered or "").strip():
            return [
                "- Considered units: none were reported. If you named any candidate unit while"
                " deciding, list them in `considered` on the next call, including the ones you set"
                " aside - a unit may only be set aside because the facts rule it out, never because"
                " the reference vocabulary does not list it."
            ]
        counts = dict(self.label_pairs)
        candidates = self.considered_units(considered) + [
            label for label, _ in self.mentioned_units(considered)
        ]
        candidates.sort(key=len, reverse=True)
        kept: list[str] = []
        for unit in candidates:
            if any(unit in other for other in kept) or self._in_draft(unit, units):
                continue
            kept.append(unit)
        support = self.support_scores(question)
        dropped = sorted(
            kept,
            key=lambda unit: self._audit_rank((unit, counts.get(unit, 0)), units, support),
        )[:MAX_AUDIT_UNITS]
        if not dropped:
            return []
        out = [
            "- Considered units: your notes name "
            + ", ".join(f"'{unit}'" for unit in dropped)
            + ", which the draft does not include."
        ]
        for unit in dropped:
            if unit in self.label_set:
                out.append(
                    f"  Closest reference case(s) that answer '{unit}':"
                )
                out.extend(self.evidence(unit, question) or ["  (no case found)"])
            else:
                out.append(
                    f"  '{unit}' is not in the reference vocabulary, which is only a sample of how"
                    " the references answer: that is not a reason to set it aside."
                )
        out.append(
            "  For each one: if the facts establish it, put it in the answer verbatim (units joined"
            " the way the references join them); if a fact rules it out, say which fact and keep your"
            " draft. The case quoted for a unit is the local evidence about how this task names this"
            " situation, and the answer is compared as an exact set of units - a unit that does not"
            " match the facts is wrong even when it is the more common one in the references, and a"
            " broader unit that covers the same facts is a different answer, not a safer one."
        )
        return out

    @staticmethod
    def _extract(text: str) -> str:
        if '"final_answer"' not in text:
            return text
        match = re.search(r'"final_answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if not match:
            return text
        try:
            return json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            return match.group(1)

    @staticmethod
    def _required_markup(question: str) -> list[str]:
        if not question:
            return []
        tags = re.findall(r"\[[^\[\]\s]{1,24}\]", question)
        tags += [f"<{name}>" for name in re.findall(r"<([A-Za-z_][A-Za-z0-9_]{0,11})>", question)]
        unique: list[str] = []
        for tag in tags:
            if tag not in unique:
                unique.append(tag)
        return unique[:4]

    @staticmethod
    def _unbalanced(text: str) -> str:
        for opener, closer in {"(": ")", "[": "]", "{": "}"}.items():
            if text.count(opener) != text.count(closer):
                return f"{opener}{closer}"
        return ""
