"""Relevance-ranked few-shot selection and formatting, exposed as a tool."""

import json
from collections import Counter
from functools import lru_cache
from math import log
from pathlib import Path

from langchain_core.tools import tool

MAX_CHARS = 30000
# The block is bounded by the model's context rather than by a fixed count of characters: a
# memory whose answers fit in this share of the context is delivered whole, and a memory that
# does not is delivered up to it. The share is read as characters per token, the conservative
# reading for text that may be written without spaces, and it is small enough that the block
# stays a part of the context rather than most of it.
CONTEXT_SHARE = 0.06
# The cases nearest the question are kept whatever their answers carry: they are what the
# question is read against, and a case that repeats a label another case already carries is
# still the nearest case of its kind.
HEAD = 20
MAX_EXAMPLES = 9999
ANSWER_KEY_CHARS = 4000
NGRAM = 2
# What each reading of a case is worth when the memory is ranked for a question: the words and
# the characters of the case's own statement, and the answer the case was answered with, the
# three summing to one. Each reading's scores are divided by that reading's own best score for
# this question before they are mixed, so the weights are the share of the order each reading
# decides rather than a scale the reading happens to score on.
WORD_WEIGHT = 0.4
CHARACTER_WEIGHT = 0.4
ANSWER_WEIGHT = 0.2
# A joiner separates the answers of one case; a divider sits inside a single answer.
SEPARATORS = (";", "；", ",", "，", "、", "|", ".")
MIN_JOINER_SHARE = 0.10


def _ngrams(text: str) -> Counter:
    """Character n-grams, so the same measure works for spaced and unsegmented text."""
    text = "".join(text.split())
    if len(text) < NGRAM:
        return Counter([text]) if text else Counter()
    return Counter(text[i:i + NGRAM] for i in range(len(text) - NGRAM + 1))


def _word_ngrams(text: str) -> Counter:
    """Word n-grams: what a text written in words is made of.

    A question written with spaces states what it is about in words, and the characters it has
    in common with another such text are mostly fragments of those words -- a reaction type, a
    symptom, a charge written in one question and its like in another come out as pieces of
    words rather than as the words they are. Reading the same text as its words puts the
    comparison back on the unit the text is written in. A text written without spaces is one
    token and a few whole clauses, which no other text carries, so this reading says nearly the
    same thing about every document there and the character reading decides those questions as
    it did before.
    """
    words = text.lower().split()
    counts = Counter(words)
    counts.update(" ".join(pair) for pair in zip(words, words[1:]))
    return counts


def _similarity(left: Counter, right: Counter) -> float:
    """Cosine similarity of two n-gram count vectors."""
    if not left or not right:
        return 0.0
    return sum((left & right).values()) / (sum(left.values()) * sum(right.values())) ** 0.5


@lru_cache(maxsize=8)
def _memory_carries(inputs: tuple, reader) -> Counter:
    """How much of the memory writes each n-gram, counting a string once per example."""
    counts = Counter()
    for text in inputs:
        counts.update(set(reader(text)))
    return counts


@lru_cache(maxsize=8)
def _memory_weights(inputs: tuple, reader) -> tuple[Counter, float]:
    """What each n-gram is worth as evidence, and what an n-gram no example writes is worth.

    A memory writes some of its text in example after example -- the instructions its task wraps
    every input in, the frame every one of its cases is narrated in -- and those n-grams tell two
    examples apart no more than a blank does, while the n-grams one example writes alone are the
    ones that say what that example is about. The weight is how much of the memory leaves the
    n-gram out, so an n-gram every example carries weighs nothing, one that only this question
    carries weighs the most, and an n-gram no example writes at all weighs as much as the latter.
    """
    carried = _memory_carries(inputs, reader)
    documents = len(inputs)
    return (
        Counter({gram: log((documents + 1) / (count + 1)) for gram, count in carried.items()}),
        log(documents + 1),
    )


def _weighed(text: str, inputs: tuple, reader) -> Counter:
    """A text's own n-grams, each weighed by how much of the memory already writes it."""
    weights, unseen = _memory_weights(inputs, reader)
    weighed = Counter()
    for gram, count in reader(text).items():
        weight = weights[gram] if gram in weights else unseen
        if weight > 0:
            weighed[gram] = count * weight
    return weighed


def _question_ngrams(question: str, inputs: tuple, reader) -> Counter:
    """The question's own n-grams, each weighed by how much of the memory already writes it.

    A question reaches the harness wrapped in the instructions its task carries, and those
    characters are the task's rather than the question's: the memory's own questions are wrapped
    in the same ones, so they are carried by example after example and say nothing about which
    example this question resembles. Weighing each n-gram of the query by how much of the memory
    carries it takes that text out of the comparison -- an n-gram every example carries weighs
    nothing and one only this question carries weighs most -- so the examples come back ordered
    by the question's own text rather than by the instructions around it.
    """
    return _weighed(question, inputs, reader)


@lru_cache(maxsize=4096)
def _example_ngrams(document: str, inputs: tuple, reader) -> Counter:
    """The example's own n-grams, weighed as the question's are, so the two are compared alike.

    The comparison is a cosine, and half of it is the example: a case of this task is written in
    the frame every case of the task is written in and carries the instructions its task wraps
    every input in, so an unweighed example spends most of its weight on text that is the task's
    rather than its own and lets that text, not what the case is about, decide how much it has in
    common with the question. Weighing both sides by the same table leaves the comparison over
    the n-grams that tell the memory's examples apart, which is the comparison the question is
    meant to make.
    """
    return _weighed(document, inputs, reader)


@lru_cache(maxsize=4096)
def _answer_ngrams(answer: str, inputs: tuple, reader) -> Counter:
    """The answer's own n-grams, weighed as the case's text is, so both are read alike.

    The answer a case was answered with is the text this question is asking for: a charge named
    after the conduct the facts state, a set of reactants written in the same notation as the
    molecule they are made from, a label naming the finding the symptoms describe. It is weighed
    by the same table as everything else, so the writing every answer of the memory carries --
    the punctuation between entries, the notation's own characters -- decides nothing.
    """
    return _weighed(answer, inputs, reader)


def _scaled(readings: dict) -> dict:
    """Each reading's scores divided by its own best, so no reading's scale decides the mix.

    The readings do not score on one scale: a question written without spaces shares almost
    nothing with the memory read as words, so its word cosines come out orders of magnitude
    below its character cosines, while a question written in words has the two within a factor
    of two. A weighted sum of raw scores therefore hands the order to whichever reading happens
    to score higher rather than to the weights the harness sets -- half the weight given to a
    reading that scores a thousandth as much is not half the say. Dividing each reading by its
    own best score for this question turns each reading into its own ordering of the memory,
    from nothing to the best match, and makes the weights the share of the order each reading
    decides. A reading whose best score is nothing has no match here and contributes nothing.
    """
    scaled = {}
    for name, scores in readings.items():
        best = max(scores) if scores else 0.0
        scaled[name] = [score / best for score in scores] if best > 0 else [0.0] * len(scores)
    return scaled


def rank_examples(examples: list[dict], question: str) -> list[dict]:
    """Order the memory by relevance to the question; ties keep memory order.

    A case is read three times -- as the words its statement is written in, as the characters
    those words are made of, and as the answer it was answered with -- and each reading is
    weighed by what the memory already writes, so the instructions a task wraps every input in
    and the frame every case is narrated in decide neither what the question asks for nor what a
    case has to offer. The readings are then brought to one scale (each divided by its own best
    match for this question) and mixed by their weights, so a question asked in words is matched
    by the words it states, a question written without them is left to the characters, and a
    case whose own answer is written from the question's own text is ranked by that too.
    """
    inputs = tuple(example.get("input", "") for example in examples)
    word_query = _question_ngrams(question, inputs, _word_ngrams)
    char_query = _question_ngrams(question, inputs, _ngrams)
    readings = {"word": [], "character": [], "answer": []}
    for example in examples:
        document = example.get("raw_question", example["input"])
        readings["word"].append(
            _similarity(word_query, _example_ngrams(document, inputs, _word_ngrams))
        )
        readings["character"].append(
            _similarity(char_query, _example_ngrams(document, inputs, _ngrams))
        )
        readings["answer"].append(
            _similarity(char_query, _answer_ngrams(example.get("target", ""), inputs, _ngrams))
        )
    scaled = _scaled(readings)
    weights = {"word": WORD_WEIGHT, "character": CHARACTER_WEIGHT, "answer": ANSWER_WEIGHT}
    scored = [
        (sum(weight * scaled[name][index] for name, weight in weights.items()), index)
        for index in range(len(examples))
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [examples[index] for _, index in scored]


def block_budget(context_window) -> int:
    """How much of the memory the block may carry, read from the context the model is given.

    A block is evidence, and evidence the model's own context can hold is worth delivering:
    the frozen memories of the tasks are a few tens of thousands of characters, which is a
    fraction of the context the solver is run with, and cutting them at a fixed count of
    characters withholds cases the model has room to read. A memory larger than the share is
    still cut, so the block stays a part of the context rather than all of it.
    """
    try:
        window = int(context_window)
    except (TypeError, ValueError):
        return MAX_CHARS
    if window <= 0:
        return MAX_CHARS
    return max(MAX_CHARS, int(window * CONTEXT_SHARE))


def select_examples(examples: list[dict], question: str, max_chars: int = MAX_CHARS) -> list[str]:
    """The examples the block carries: the nearest ones, then a case for each answer string.

    A memory writes some of its strings into case after case -- a charge half of its cases are
    answered with, a label a whole family shares -- and those repeats spend the block on
    evidence the solver already has, while the strings only one or two cases write are the ones
    that show what this memory does with a case like this one. So the cases nearest the
    question are kept whatever they carry, and past them a case is kept only when it carries an
    answer string -- one of the memory's answers, or one of the strings those answers are built
    from, which is the list the answer key itself writes -- that no kept case carries yet.
    Everything else follows in relevance order while the budget lasts, so a memory small enough
    to fit the budget is still delivered whole.
    """
    whole, parts = listed_strings(examples)
    listed = [answer for answer in [*whole, *parts] if answer.strip()]
    nearest, covering, rest = [], [], []
    covered = set()
    for index, example in enumerate(rank_examples(examples, question)[:MAX_EXAMPLES]):
        item = f"Q: {example.get('raw_question', example['input'])}\nA: {example['target']}"
        carries = {answer for answer in listed if answer in example.get("target", "")}
        if index < HEAD:
            covered |= carries
            nearest.append(item)
        elif carries - covered:
            covered |= carries
            covering.append(item)
        else:
            rest.append(item)
    chosen, total_chars = [], 0
    for item in [*nearest, *covering, *rest]:
        if total_chars + len(item) > max_chars:
            continue
        chosen.append(item)
        total_chars += len(item) + 2
    return chosen


def format_examples(examples: list[dict], question: str, max_chars: int = MAX_CHARS) -> str:
    """The example block, most relevant first, filled up to the character budget."""
    return "\n\n".join(select_examples(examples, question, max_chars))


def joiner_separator(examples: list[dict]) -> str:
    """The character the memory puts between the several answers of one case.

    A joiner splits an answer into pieces that are themselves answers of the memory,
    while a divider inside one answer leaves fragments that never appear as an answer
    on their own, so the two are told apart without knowing the answer language.
    """
    answers = {example["target"] for example in examples if example.get("target")}
    best, best_share = "", 0.0
    for separator in SEPARATORS:
        joined = [answer for answer in answers if separator in answer]
        if not joined:
            continue
        pieces = {
            piece.strip() for answer in joined for piece in answer.split(separator) if piece.strip()
        }
        share = len(pieces & answers) / len(pieces)
        if share > best_share:
            best, best_share = separator, share
    return best if best_share >= MIN_JOINER_SHARE else ""


def answer_parts(examples: list[dict], separator: str) -> list[str]:
    """The strings the answers are built from that the memory never writes as an answer itself.

    A case carries one or several entries, so what the memory writes are combinations; a new
    case can need a combination no example wrote while every string in it is one the memory
    did write, so those strings are answers the solver may be asked for.
    """
    counts = Counter(example["target"] for example in examples if example.get("target"))
    parts = Counter()
    for answer, count in counts.items():
        for part in answer.split(separator):
            part = part.strip()
            if part:
                parts[part] += count
    return [part for part, _ in parts.most_common() if part not in counts]


def answer_key_rules(examples: list[dict], parts_listed: bool) -> str:
    """The contract the key states, so the solver assembles whole entries instead of inventing."""
    separator = joiner_separator(examples)
    several = (
        f'Several listed strings are joined with "{separator}"; keep every one of them joined\n'
        "that way."
        if separator
        else "The examples show how several entries are written; write them the same way."
    )
    built = (
        "\nThe second list holds the strings the answers above are built from. Each of them is\n"
        "an answer on its own when it is all that applies, and is never a fragment of the\n"
        "answer it was taken from."
        if parts_listed
        else ""
    )
    return (
        "Answer key: the complete answer strings of the examples, most frequent first.\n"
        "An answer is one of these strings, or several of them when the case carries several:\n"
        "the examples show how many a case carries and how several are written. Copy every\n"
        "string you use character for character, never shorten, reword or reorder one. A string\n"
        "from these lists is never a fragment, written alone or joined; a fragment is a piece of\n"
        "one that is not listed. Include every listed string that applies, not only the most\n"
        "obvious one, and add none that does not apply.\n"
        f"{several}{built}\n"
        "If none of the listed strings applies, write the answer in the same style."
    )


def listed_strings(examples: list[dict]) -> tuple[list[str], list[str]]:
    """The strings the answer key writes: the memory's whole answers, then the parts it builds them from.

    The list is capped at the answer key's budget, so a caller outside the key sees the same
    listed strings the solver is shown rather than a longer list of its own.
    """
    separator = joiner_separator(examples)
    counts = Counter(example["target"] for example in examples if example.get("target"))
    parts = answer_parts(examples, separator) if separator else []
    whole, used = [], 0
    for answer, _ in counts.most_common():
        line = f"- {answer}"
        if whole and used + len(line) + 1 > ANSWER_KEY_CHARS:
            break
        whole.append(answer)
        used += len(line) + 1
    built, built_chars = [], 0
    header = "Built from, each being an answer on its own when it is all that applies:"
    for part in parts:
        line = f"- {part}"
        if used + len(header) + 2 + built_chars + len(line) > ANSWER_KEY_CHARS:
            break
        built.append(part)
        built_chars += len(line) + 1
    return whole, built


def format_answer_key(examples: list[dict]) -> str:
    """The complete answer strings of the memory, so the solver can copy instead of invent."""
    whole, parts = listed_strings(examples)
    if not whole:
        return ""
    lines = [f"- {answer}" for answer in whole]
    if parts:
        lines.append("Built from, each being an answer on its own when it is all that applies:")
        lines.extend(f"- {part}" for part in parts)
    return f"{answer_key_rules(examples, bool(parts))}\n" + "\n".join(lines)


def load_examples() -> list[dict]:
    """The frozen memory, read once for both the tool and the harness's own passes."""
    return json.loads(Path("/harness/memory/memory.json").read_text())["examples"]


def memory_answer_key() -> str:
    """The answer key of the frozen memory, so a pass outside the tool sees the same key."""
    return format_answer_key(load_examples())


def memory_joiner() -> str:
    """The memory's answer joiner, empty when its answers are single strings.

    A pass that rewrites an answer's entries one by one needs to know the memory writes
    several entries per answer at all; when it does not, an entry is the whole answer.
    """
    return joiner_separator(load_examples())


def memory_listed_strings() -> tuple[list[str], list[str]]:
    """The answer key's own list, so a pass outside the tool reads the same authority."""
    return listed_strings(load_examples())


def reduced_context(question: str, chars: int = 0) -> str:
    """The examples and the answer key, cut to a smaller share of the block.

    The call a provider refuses is the one carrying the whole block, so an answer derived
    outside the conversation is offered the same evidence in less text: the top of the same
    relevance ranking -- the closest precedents, which is the part of the block that decides
    a charge -- and the answer key, which is what the memory settles on its own. A budget of
    zero leaves the key alone, which is all that is left when no example can be delivered.
    """
    examples = load_examples()
    block = format_examples(examples, question, chars) if chars > 0 else ""
    key = format_answer_key(examples)
    return f"{block}\n\n{key}" if block and key else (block or key)


def make_tool(input_text: str, max_chars: int = MAX_CHARS):
    examples = load_examples()

    @tool
    def retrieve_examples() -> str:
        """Get the training Q/A examples to use when answering the current problem,
        ordered so that the examples most similar to this problem come first."""
        block = format_examples(examples, input_text, max_chars)
        answer_key = format_answer_key(examples)
        return f"{block}\n\n{answer_key}" if answer_key else block

    return retrieve_examples
