"""The frozen memory: its examples, the answers it holds, and the text they are made of."""

import json
import math
import re
from collections import Counter
from pathlib import Path

MEMORY_PATH = "/harness/memory/memory.json"
NGRAM = 3
# An n-gram carried by at least half of the examples separates nothing, so it is
# dropped from both sides before ranking. Every example shares the task's prompt
# template with every question, so the template is what this removes, leaving
# the text that is specific to one problem.
SHARED_DF = 0.5
# Punctuation an answer could be joined with. Which of them this memory actually
# joins answers with is read from the memory's own answers, since some of them
# write a name with a comma inside it (`X、Y`) and others hold two answers in one
# string (`X;Y`).
SEPARATORS = ";；,，、"
MAX_UNITS = 8
MAX_UNIT_CHARS = 60


def load_examples() -> list[dict]:
    """The training examples the memory was prepared from."""
    return json.loads(Path(MEMORY_PATH).read_text())["examples"]


def example_text(example: dict) -> str:
    """What the example shows the solver: the problem without the prompt template."""
    return str(example.get("raw_question") or example["input"])


def learn_joiner(answers: list[str]) -> str | None:
    """The punctuation this memory joins several answers with, if it joins any.

    A separator joins answers when the memory also holds its parts as answers of
    their own: `X;Y` is two answers only if `X` and `Y` are answers somewhere
    else in the memory. A separator whose parts are never answers by themselves
    is part of the name it sits in (`X、Y` is one answer, not two), and holding
    the memory's own text to that distinction is what keeps a name from being
    read as a list of the fragments its punctuation cuts it into.
    """
    whole = {answer.strip() for answer in answers}
    joiner, best = None, 0.0
    for separator in SEPARATORS:
        parts = total = 0
        for answer in whole:
            pieces = [piece.strip() for piece in answer.split(separator) if piece.strip()]
            if len(pieces) < 2:
                continue
            total += len(pieces)
            parts += sum(1 for piece in pieces if piece in whole)
        if total and parts / total > best:
            joiner, best = separator, parts / total
    return joiner


def split_answer(answer: str, joiner: str | None) -> list[str]:
    """The answers one answer string holds, joined the way the memory joins them."""
    if joiner and joiner in answer:
        return [part.strip() for part in answer.split(joiner) if part.strip()]
    return [answer.strip()] if answer.strip() else []


def runs(text: str, alphabet: set[str]) -> list[str]:
    """The stretches of `text` written in the alphabet the memory's answers use."""
    found, current = [], []
    for character in str(text):
        if character in alphabet:
            current.append(character)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found


def ngrams(text: str) -> list[str]:
    """Character n-grams, which match across word forms, Chinese text and identifiers."""
    text = " ".join(str(text).split()).lower()
    return [text[index:index + NGRAM] for index in range(max(0, len(text) - NGRAM + 1))]


class Ranker:
    """Cosine similarity between IDF-weighted character n-gram vectors.

    Both the incoming question and the stored examples are wrapped in the same
    prompt template, so ranking the question's whole text against examples
    rendered from the problem alone scores the template's phrases as if they
    described the example. Indexing the examples by their `input` puts the same
    template on both sides, and dropping the n-grams that most examples carry
    takes it back out again.
    """

    def __init__(self, examples: list[dict]):
        self.vectors = [Counter(ngrams(example["input"])) for example in examples]
        frequency = Counter()
        for vector in self.vectors:
            frequency.update(vector.keys())
        total = len(examples) or 1
        self.shared = {gram for gram, count in frequency.items() if count >= SHARED_DF * total}
        self.idf = {
            gram: math.log((total + 1) / (count + 1)) + 1.0 for gram, count in frequency.items()
        }
        self.norms = [
            math.sqrt(
                sum((self.idf[gram] * count) ** 2 for gram, count in vector.items()
                    if gram not in self.shared)
            ) or 1.0
            for vector in self.vectors
        ]

    def rank(self, query: str) -> list[int]:
        """Example indices, closest to the query first."""
        grams = {
            gram: count for gram, count in Counter(ngrams(query)).items()
            if gram not in self.shared
        }
        norm = math.sqrt(
            sum((self.idf.get(gram, 0.0) * count) ** 2 for gram, count in grams.items())
        ) or 1.0
        scored = [
            (
                sum(
                    self.idf[gram] ** 2 * count * grams[gram]
                    for gram, count in vector.items() if gram in grams
                ) / (norm * self.norms[index]),
                index,
            )
            for index, vector in enumerate(self.vectors)
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [index for _, index in scored]


class AnswerSpace:
    """The exact answer strings the memory holds, and how a draft differs from them.

    Answers are scored as strings, so an answer the memory already holds is only
    worth what its spelling is worth: a solver that paraphrases it, that adds or
    drops a conventional word ending, or that names a piece of a longer answer,
    loses a sample it had the evidence to win. This class holds the answers as
    the units the memory itself joins them into, reports which units of a draft
    appear in the memory, which are one of its answers spelled differently, and
    which the memory has nothing like.
    """

    def __init__(self, examples: list[dict]):
        self.answers = [str(example["target"]) for example in examples]
        self.joiner = learn_joiner(self.answers)
        self.units = Counter()
        for answer in self.answers:
            self.units.update(split_answer(answer, self.joiner))
        self.terminals = {unit[-1] for unit in self.units}
        self.alphabet = set("".join(self.units))
        # The pieces the memory writes one answer in, where it puts punctuation a
        # name may be read at but does not join answers with. A draft that names one
        # piece of an answer (`销售伪劣产品` for `生产、销售伪劣产品`) has named the
        # memory's own text, so the answer it belongs to is a spelling the memory
        # writes and the piece is not one.
        self.piece_owners = {}
        for unit in self.units:
            for piece in self.pieces(unit):
                if piece != unit:
                    self.piece_owners.setdefault(piece, set()).add(unit)
        # Runs that most example problems carry are the prompt template, not an
        # answer, and they show up in a draft that copies the task's markup.
        seen = Counter()
        for example in examples:
            seen.update(set(runs(example["input"], self.alphabet)))
        total = len(examples) or 1
        self.shared = {run for run, count in seen.items() if count >= SHARED_DF * total}

    def pieces(self, unit: str) -> list[str]:
        """One answer cut at the punctuation inside it, which does not join answers."""
        separators = "".join(separator for separator in SEPARATORS if separator != self.joiner)
        return [
            piece for piece in re.split(f"[{re.escape(separators)}]", unit) if piece.strip()
        ]

    def piece_owner(self, unit: str) -> str | None:
        """The one answer the memory writes with `unit` as a piece of it, when there is one."""
        owners = self.piece_owners.get(unit)
        return next(iter(owners)) if owners and len(owners) == 1 else None

    @property
    def repeats(self) -> bool:
        """Whether the memory uses an answer more than once.

        An answer no other example uses is a value, not a spelling the memory
        keeps: nothing in such a memory can say that a draft is written the wrong
        way, so neither the check nor the respelling has anything to apply.
        """
        return max(self.units.values(), default=0) > 1

    def draft_units(self, draft: str) -> list[str]:
        """The answer units of a draft, ignoring the markup the task wraps them in."""
        found = []
        for run in runs(draft, self.alphabet):
            if len(run) > 1 or run in self.units:
                found.extend(split_answer(run, self.joiner))
        # An answer that the template also carries is still an answer; only the
        # template's own words go.
        kept = [unit for unit in found if unit not in self.shared or unit in self.units]
        return kept or found

    def full_answer(self, text: str) -> str | None:
        """The one answer the memory holds that begins with `text`, when there is one."""
        longer = [
            unit for unit in self.units if len(unit) > len(text) and unit.startswith(text)
        ]
        return longer[0] if len(longer) == 1 else None

    def echo(self, unit: str) -> str | None:
        """The answer a part repeats the end of, when that is all the part is.

        A draft that writes an answer and then writes its own tail again
        (`bronchial asthmanchial asthma` for `bronchial asthma`) has written the
        memory's answer twice over: the second copy adds text the memory does not
        write after that answer, so the part is the answer written once.
        """
        matches = [
            answer for answer in self.units
            if len(unit) > len(answer) and unit.startswith(answer)
            and answer.endswith(unit[len(answer):])
        ]
        return matches[0] if len(matches) == 1 else None

    def variant(self, unit: str) -> tuple[str, str] | None:
        """The memory's spelling of `unit`, with why it differs, when it has one.

        Only differences read off the memory's own answers are acted on: a
        trailing character that no answer ends with (the solver's own word
        ending, which the memory never writes), a part the memory holds only as
        the beginning of an answer written in full (an answer cut short by
        naming a piece of it), a part that is one piece of an answer the memory
        writes with punctuation inside it (an answer cut short in the middle of
        its name), and a part that repeats the end of the one answer it begins
        with (an answer the solver wrote twice over). Anything else is left as
        the solver wrote it.
        """
        if unit in self.units:
            return None
        if len(unit) > 2 and unit[-1] not in self.terminals:
            shorter = unit[:-1]
            if shorter in self.units:
                return shorter, f"no answer in the memory ends with '{unit[-1]}'"
            longer = self.full_answer(shorter)
            if longer:
                return longer, "the memory writes that answer in full"
        longer = self.full_answer(unit)
        if longer:
            return longer, "the memory writes that answer in full"
        owner = self.piece_owner(unit)
        if owner:
            return owner, "the memory writes that answer in full"
        echo = self.echo(unit)
        if echo:
            return echo, "that part repeats the end of that answer"
        return None

    def corrections(self, draft: str) -> list[tuple[str, str]]:
        """The parts of a draft the memory writes differently, and its spelling of them."""
        found = []
        for unit in self.draft_units(draft):
            variant = self.variant(unit)
            if variant:
                found.append((unit, variant[0]))
        return found

    def respell(self, draft: str) -> str:
        """A draft answer written the way the memory writes its answers.

        The same rule the check reports, applied to the answer itself: a part of
        the draft that the memory spells differently is replaced by the memory's
        spelling, so an answer is worth the spelling the memory holds whether or
        not the solver asked about it.
        """
        for unit, spelling in self.corrections(draft):
            draft = draft.replace(unit, spelling)
        return draft

    def check(self, draft: str) -> str:
        """A report on how a draft answer's units compare with the memory's answers."""
        units = self.draft_units(draft)
        if not units:
            return "No answer text found in the draft."
        if not any(unit in self.units or self.variant(unit) for unit in units):
            return (
                "No part of this draft is an answer in the memory, so there is no spelling"
                " to copy from it; keep your own wording, in the examples' style."
            )
        lines = [
            f"The memory holds {len(self.units)} answers over {len(self.answers)} examples,"
            " compared character for character. It knows how an answer it holds is written,"
            " not which answer is right."
        ]
        for unit in units[:MAX_UNITS]:
            unit = unit[:MAX_UNIT_CHARS]
            if unit in self.units:
                lines.append(f"- in memory: {unit} ({self.units[unit]} examples)")
                continue
            variant = self.variant(unit)
            if variant:
                spelling, reason = variant
                lines.append(f"- change: {unit} -> {spelling} ({reason})")
            else:
                lines.append(
                    f"- not in memory: {unit} (no answer the memory holds is written like"
                    " it, so there is no spelling to copy; keep your own wording)"
                )
        return "\n".join(lines)
