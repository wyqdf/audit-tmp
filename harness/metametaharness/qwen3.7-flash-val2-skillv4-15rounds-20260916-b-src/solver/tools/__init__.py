"""Register the lookups the frozen memory can still answer."""

from .memory import AnswerSpace, load_examples
from .retrieval import MAX_CHARS, make_tool
from .verify import make_verify_tool


def build_tools(input_text: str, budget: int = MAX_CHARS):
    """Build the memory's tools and report what they leave for the prompt to say.

    A lookup is only registered where the memory can answer through it, and the
    prompt is written from the same facts: `check_answer` exists only when the
    memory repeats an answer, and the memory file is only worth searching when the
    listing left examples out. The answer space is handed back with them, since a
    memory that repeats an answer holds a spelling the harness can write itself.
    The budget is the listing's, which a second attempt may have to shrink.
    """
    examples = load_examples()
    space = AnswerSpace(examples)
    retrieve_examples, delivered = make_tool(input_text, examples, budget)
    check_answer = make_verify_tool(space)
    tools = [retrieve_examples] + ([] if check_answer is None else [check_answer])
    return tools, {
        "check_answer": check_answer is not None,
        "complete_listing": delivered == len(examples),
        "spelling": space if space.repeats else None,
    }
