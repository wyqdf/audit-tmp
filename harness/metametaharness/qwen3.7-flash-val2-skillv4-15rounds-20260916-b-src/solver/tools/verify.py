"""Answer verification: the spelling the memory uses for the answer in hand."""

from langchain_core.tools import tool

from .memory import AnswerSpace


def make_verify_tool(space: AnswerSpace):
    """The check, or nothing where the memory holds no spelling for it to check.

    An answer no other example uses is a value, not a spelling the memory repeats,
    so a memory of one-off answers has nothing to hold a draft to. A tool that
    answers every call with the same nothing is worse than no tool: it is called
    again, and it spends the call budget the answer needs.
    """
    if not space.repeats:
        return None

    @tool
    def check_answer(draft: str) -> str:
        """Compare your draft answer with the answers the memory holds.

        Returns the memory's spelling for each unit of the draft: `change` lines
        are answers the memory writes differently and must be used verbatim,
        `not in memory` lines are units the memory has nothing like.
        """
        return space.check(draft)

    return check_answer
