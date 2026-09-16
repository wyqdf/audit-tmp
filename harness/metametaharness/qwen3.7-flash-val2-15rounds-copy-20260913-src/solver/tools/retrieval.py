"""Relevance-ranked few-shot selection, exposed as a tool.

The memory's answers are evidence in their own right, not just the tail of the
examples that carry them: scoring is exact, so an answer counts only when it is
written the way this task writes it, and the answer space can be far larger
than the character budget that whole examples can spend.  The budget therefore
carries two kinds of evidence -- whole examples to reason from and answers to
spell with -- and how much it owes the answers is not a fixed share: it is the
cost of the answers the delivered examples do not already show.  A memory whose
whole examples write its answer space already owes the answers nothing and
spends the budget on cases; a memory whose answer space outruns the cases that
fit pays for the missing answers first and keeps the closest cases whole with
the rest.

The whole memory is larger than that budget, and the questions the agent ends
up asking are not always the question it was handed: a case that resembles the
problem on the aspect the agent is unsure about is worth more to it than the
closest case by the problem's own text.  So the memory is also exposed as a
search the agent writes itself -- the same ranking, the same compact rendering,
a focused budget -- which answers with the cases closest to that query and
says how many of the memory's cases it is showing.  The delivered evidence is
unchanged; what the agent gains is the rest of the memory, asked for in its own
words, instead of a raw file it has to read and parse.

Both tools read a frozen memory and neither changes within a run, so the same
request returns the same answer however often it is made.  Each tool therefore
takes the run's ledger and answers a request it has already answered with a
pointer to what the run holds instead of the payload again: a repeat stops
costing a second copy of content the conversation already carries, and the run
spends its calls on questions it has not asked yet.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool

from .progress import request_key

MAX_CHARS = 30000
# A search answers a question the agent asked itself about one aspect of the
# problem, so it is a slice rather than the whole view: the cases closest to
# that question, inside a budget of its own.
SEARCH_CHARS = 12000
MAX_EXAMPLES = 9999
NGRAM_SIZE = 2
# The split between whole examples and the answers they do not show is a fixed
# point; a handful of passes reaches it, and the bound keeps a memory that
# cannot reach one from spending the question's time on it.
MAX_PASSES = 32


def _ngrams(text: str) -> Counter:
    text = re.sub(r"\s+", " ", text).strip()
    return Counter(
        text[index : index + NGRAM_SIZE]
        for index in range(len(text) - NGRAM_SIZE + 1)
    )


def _idf(documents: list[Counter]) -> dict[str, float]:
    """Weight n-grams by how rare they are across the memory."""
    document_frequency = Counter()
    for document in documents:
        document_frequency.update(document.keys())
    total = max(len(documents), 1)
    return {
        gram: math.log((total + 1) / (count + 1)) + 1.0
        for gram, count in document_frequency.items()
    }


def _weighted_norm(document: Counter, weights: dict[str, float]) -> float:
    return math.sqrt(
        sum((count * weights.get(gram, 1.0)) ** 2 for gram, count in document.items())
    )


def _cosine_similarity(
    query: Counter,
    document: Counter,
    weights: dict[str, float],
    query_norm: float,
    document_norm: float,
) -> float:
    if not query_norm or not document_norm:
        return 0.0
    dot = sum(
        count * document.get(gram, 0) * weights.get(gram, 1.0) ** 2
        for gram, count in query.items()
    )
    return dot / (query_norm * document_norm)


def _rank(input_text: str):
    """The memory examples and the order this question asks for them in."""
    examples = json.loads(Path("/harness/memory/memory.json").read_text())["examples"]
    questions = [example.get("raw_question", example["input"]) for example in examples]
    documents = [_ngrams(question) for question in questions]
    weights = _idf(documents)
    query = _ngrams(input_text)
    query_norm = _weighted_norm(query, weights)
    scores = [
        _cosine_similarity(
            query, document, weights, query_norm, _weighted_norm(document, weights)
        )
        for document in documents
    ]
    # Most similar first; memory order breaks ties so the ranking stays stable.
    ranking = sorted(range(len(examples)), key=lambda index: (-scores[index], index))
    return examples, questions, ranking


def _cost(parts: list[str]) -> int:
    """The characters a list of delivered parts spends, separators included."""
    return sum(len(part) + 2 for part in parts)


def _whole_parts(
    examples: list[dict], questions: list[str], order: list[int], cap: int
) -> list[tuple[str, str]]:
    """The closest examples, whole, for as much of the cap as they fit.

    Each part is paired with the answer it writes, so the caller can ask which
    of the memory's answers the whole examples already show.
    """
    parts: list[tuple[str, str]] = []
    total = 0
    for index in order:
        answer = str(examples[index]["target"])
        part = f"Q: {questions[index]}\nA: {answer}"
        if total + len(part) > cap:
            continue
        parts.append((part, answer))
        total += len(part) + 2
    return parts


def _answer_parts(
    examples: list[dict], order: list[int], whole: list[tuple[str, str]]
) -> list[str]:
    """The answers the whole examples do not already show, once each.

    The answer space is the other kind of evidence, so the ranking continues in
    the same order and each example whose answer the whole tier has not written
    contributes that answer.  An answer written whole, and an answer written by
    an earlier line here, is not paid for again.
    """
    shown = "\n".join(answer for _, answer in whole)
    parts: list[str] = []
    seen: set[str] = set()
    for index in order:
        answer = str(examples[index]["target"])
        if answer in seen or answer in shown:
            continue
        seen.add(answer)
        parts.append(f"A: {answer}")
    return parts


def render(examples: list[dict], questions: list[str], ranking: list[int]) -> str:
    """The evidence this question is given, for the whole budget.

    The answers the whole examples do not show are paid for first and the
    examples spend what is left, so neither kind of evidence is paid for twice
    and a memory whose examples already write its answer space hands the whole
    budget to the examples.  The split is a fixed point -- a smaller whole tier
    leaves out more answers, which cost more -- so both sides are rendered and
    the answers are charged against the examples until the two agree.
    """
    order = ranking[:MAX_EXAMPLES]
    cap = MAX_CHARS
    whole: list[tuple[str, str]] = []
    tail: list[str] = []
    for _ in range(MAX_PASSES):
        whole = _whole_parts(examples, questions, order, cap)
        tail = _answer_parts(examples, order, whole)
        leave = MAX_CHARS - _cost(tail)
        if leave >= cap:
            break
        cap = leave
    # A memory whose answer space alone fills the budget leaves the whole tier
    # nothing, and the passes above may stop short of the fixed point; either
    # way the evidence still fits, so the tail is trimmed to what the whole
    # examples leave.
    parts = [part for part, _ in whole]
    spent = _cost(parts)
    for part in tail:
        if spent + len(part) + 2 > MAX_CHARS:
            continue
        parts.append(part)
        spent += len(part) + 2
    return "\n\n".join(parts)


def select_examples(input_text: str) -> str:
    """The evidence this question is given, in the order the tool delivers it.

    The same rendering the tool returns, derived from the same memory and the
    same question, so a part of the harness that is not the tool can be handed
    exactly the evidence the agent would have retrieved.
    """
    examples, questions, ranking = _rank(input_text)
    return render(examples, questions, ranking)


def search(query: str, budget: int = SEARCH_CHARS) -> str:
    """The memory's cases closest to a question the agent wrote itself.

    The same ranking and the same compact Q/A rendering the tool delivers for
    the problem, with one budget for a slice rather than the whole view, and a
    first line saying how much of the memory the slice shows: the agent is the
    one asking, so it is the one that has to be able to tell when the rest of
    the memory holds something the slice does not.
    """
    examples, questions, ranking = _rank(query)
    order = ranking[:MAX_EXAMPLES]
    whole = _whole_parts(examples, questions, order, budget)
    cases = [part for part, _ in whole]
    if not cases:
        return f"The memory holds {len(examples)} cases and none of them fit a search."
    return "\n\n".join(
        [f"{len(cases)} of the {len(examples)} cases in the memory, closest first:", *cases]
    )


def make_tool(input_text: str, ledger=None):
    examples, questions, ranking = _rank(input_text)

    @tool
    def retrieve_examples() -> str:
        """Get the training Q/A examples to use when answering the current problem."""
        key = request_key("retrieve_examples", {})
        if ledger is not None and ledger.answered(key):
            return ledger.pointer(key)
        text = render(examples, questions, ranking)
        if ledger is not None:
            ledger.record(
                key, f"the evidence for this question, drawn from the {len(examples)} cases in the memory"
            )
        return text

    return retrieve_examples


def make_search_tool(input_text: str, ledger=None):
    @tool
    def search_memory(query: str) -> str:
        """Search the frozen memory for the cases closest to a question you write
        yourself, e.g. one aspect of the problem you are unsure about. Returns the
        closest cases as Q/A pairs and says how many of the memory's cases they are."""
        key = request_key("search_memory", {"query": query})
        if ledger is not None and ledger.answered(key):
            return ledger.pointer(key)
        text = search(query)
        if ledger is not None:
            # The result opens by saying how much of the memory it shows, which is
            # what the agent has to be told when the same question comes back.
            ledger.record(key, text.split("\n", 1)[0].strip().rstrip(":"))
        return text

    return search_memory
