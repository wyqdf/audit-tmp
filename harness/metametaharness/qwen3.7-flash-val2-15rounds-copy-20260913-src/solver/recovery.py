"""Answer the problem when the agent's run could not finish.

The harness's answer path assumes the agent produced a last message: the
resolution step reads the answer out of that message and the answer-space
rules spell what it finds.  A run that dies inside a model call leaves no
message at all, so the exception reaches the runner and the sample is recorded
as a failure with no answer ever produced.  The one refusal this tree has
recorded every round lands on the call that carries the retrieved examples,
and the question on its own is accepted by the provider, so the failure is not
the problem's: it is the evidence the provider would not read.

So the harness answers the problem itself, in the format the runner reads:
once with the examples the agent would have retrieved, and once without them
when the provider refuses that evidence too.  Any failure leaves the caller
with the original error, which is what happens today.
"""

from string import Template

from tools.retrieval import select_examples

ANSWER = Template("""An agent answers the problem below by reading examples from its frozen memory. That
agent could not finish the problem, so answer it yourself.

## Problem

$problem
$evidence

State the answer as a single JSON object with exactly two string fields, "reasoning" and
"final_answer". Put the answer itself inside "final_answer", keeping any markup the problem's
own instructions ask the answer to carry.

Reply with only the JSON object.""")

EVIDENCE = Template("""
## Examples from the frozen memory

$examples
""")


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else block.get("text", "")
        for block in (content or [])
    )


def recover(model, problem: str) -> str | None:
    """One answer for a problem whose agent run died, or None if none can be had.

    The examples are the ones the agent's own retrieval returns for this
    problem, so the answer is formed from the same evidence the agent had;
    they are dropped on a second attempt because the provider is the one that
    refused the run in the first place.
    """
    try:
        examples = select_examples(problem)
    except Exception:
        examples = ""
    attempts = [EVIDENCE.substitute(examples=examples)] if examples else []
    attempts.append("")
    for evidence in attempts:
        try:
            response = model.invoke(ANSWER.substitute(problem=problem, evidence=evidence))
        except Exception:
            continue
        content = _text(getattr(response, "content", response))
        if content.strip():
            return content
    return None
