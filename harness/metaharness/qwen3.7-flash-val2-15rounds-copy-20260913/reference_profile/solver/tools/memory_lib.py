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


def split_parts(text: str, separators: list[str]) -> list[str]:
    """Split an answer into its parts using the separators the references use."""
    parts = [text or ""]
    for separator in separators:
        expanded = []
        for part in parts:
            expanded.extend(part.split(separator))
        parts = expanded
    return [part.strip() for part in parts if part and part.strip()]


def derive_separators(targets: list[str]) -> list[str]:
    """Separators that the reference answers themselves use to join parts."""
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
    return [separator for _, separator in scored[:MAX_SEPARATORS]]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[len(ordered) // 2])


def build_profile(targets: list[str], separators: list[str]) -> dict:
    """Summarise the shape and vocabulary of the reference answers."""
    parts = [part for target in targets for part in split_parts(target, separators)]
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
    separators = derive_separators(answers)
    profile = build_profile(answers, separators)
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
        groups.append(
            {
                "key": key,
                "size": len(members),
                "parts": [[text, count] for text, count in recurring[:MAX_GROUP_PARTS]],
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
        self.labels = [text for text, _ in self.profile.get("labels") or []]
        self.label_set = set(self.labels)
        self._gram_sets: list[set[str]] = []
        self._weights: list[dict[str, float]] = []
        self._norms: list[float] = []
        self._document_frequency: Counter = Counter()
        self._query_group = -2
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
            if key and head.startswith(key):
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
            lines.append(
                "- Reference labels (copy character for character; never add, remove, reorder or"
                " re-word characters, and never append a generic word the references do not use):"
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
                entry += f"; recurring answer parts there: {_truncate(parts, 500)}"
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

    # ------------------------------------------------------------------ checks

    def check(self, draft: str, question: str = "") -> str:
        text = (draft or "").strip()
        if not text:
            return "The draft answer is empty. Produce the answer in the required format."
        repaired = self._extract(text)
        tags = self._required_markup(question)
        core = repaired
        for tag in tags:
            core = core.replace(tag, " ")
        parts = split_parts(core, self.separators)
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
        if self.label_set:
            unknown = [part for part in parts if part not in self.label_set]
            if not unknown:
                notes.append(f"- Labels: all {len(parts)} part(s) match reference labels verbatim.")
            else:
                notes.append(
                    f"- Labels: {len(parts) - len(unknown)} of {len(parts)} part(s) match reference"
                    " labels verbatim."
                )
                for part in unknown:
                    close = difflib.get_close_matches(part, self.labels, n=3, cutoff=0.6)
                    if close:
                        problems.append(
                            f"- Label: '{part}' is not a verbatim reference label. Closest reference"
                            f" labels: {', '.join(close)}. Use the reference spelling exactly when it"
                            " is the correct answer."
                        )
                    else:
                        problems.append(
                            f"- Label: '{part}' is not in the reference label list. Keep it only if it"
                            " is genuinely the correct answer; otherwise use a verbatim reference"
                            " label."
                        )
        else:
            notes.append(
                "- Labels: no fixed label list; check that each part follows the reference format"
                " exactly (characters, separators, case)."
            )
        unbalanced = self._unbalanced(repaired)
        if unbalanced:
            problems.append(f"- Structure: unbalanced {unbalanced} in the draft.")
        header = "Issues to review before answering:" if problems else "Check passed."
        return "\n".join([header, *(problems or []), *notes])

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
