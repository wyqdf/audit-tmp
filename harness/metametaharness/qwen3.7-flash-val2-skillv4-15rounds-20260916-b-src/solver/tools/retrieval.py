"""Memory retrieval: the training examples closest to the current question."""

from langchain_core.tools import tool

from .memory import Ranker, example_text

# One tool result is offloaded to a file by the agent framework above 80000
# characters, so the delivered memory stays below that ceiling.
MAX_CHARS = 60000
# The listing of an attempt made after the provider refused one. The request the
# provider inspects is the one carrying the listing, so a listing that costs a
# quarter of the characters is a smaller amount of text to inspect and to read.
RETRY_CHARS = MAX_CHARS // 4


def example_part(example: dict) -> str:
    """One example as the listing writes it: the problem, then the answer it is graded on."""
    return f"Q: {example_text(example)}\nA: {example['target']}"


def listing(examples: list[dict], closest: list[int], budget: int = MAX_CHARS) -> tuple[str, int]:
    """The examples closest to the question that fit the budget, and how many that is.

    The count is what tells the prompt whether a search of the memory could still
    turn up an example this listing left out. A memory that fits the budget is
    listed whole. A memory that does not is listed an answer at a time: the closest
    example of each answer is kept and an example whose answer the listing already
    carries is passed over, so the same characters carry more of the answers the
    solver's draft is graded against instead of another case the memory already
    showed. An answer is what the solver has to write, and one example is enough
    to show the case it was given for. The budget is the caller's, since an
    attempt made after the provider refused the request lists less of the memory.
    """
    whole = sum(len(example_part(example)) + 2 for example in examples) <= budget
    parts, total, carried = [], 0, set()
    for index in closest:
        example = examples[index]
        answer = str(example["target"])
        if not whole and answer in carried:
            continue
        part = example_part(example)
        if total + len(part) > budget:
            continue
        parts.append(part)
        total += len(part) + 2
        carried.add(answer)
    return "\n\n".join(parts), len(parts)


def make_tool(input_text: str, examples: list[dict], budget: int = MAX_CHARS):
    """The retrieval tool, and the number of examples its listing carries."""
    text, delivered = listing(examples, Ranker(examples).rank(input_text), budget)

    @tool
    def retrieve_examples() -> str:
        """Get the training Q/A examples for the current problem, closest example first."""
        return text

    return retrieve_examples, delivered
