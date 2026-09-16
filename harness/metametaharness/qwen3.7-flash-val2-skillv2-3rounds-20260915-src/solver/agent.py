"""Deep Agents candidate, loaded only inside the solver sandbox."""

import os
import time
from pathlib import Path

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import LocalShellBackend
from langchain_core.messages import AIMessage

from answer_space import (
    answers_agree,
    answer_text,
    extends_answer,
    ground_reply,
    load_answer_space,
    panel_winner,
)
from tools import render_demonstrations

SYSTEM_PROMPT = "You are an agent that answers a question by retrieving examples."
SKILL_PATH = "/harness/skills/answer-with-examples/SKILL.md"
PROMPT_PATH = "/harness/solver.md"

# The channel's room is one ceiling and the provider's willingness to read the request is
# another: a question carrying a whole demonstration set can be rejected outright by the
# input filter, before any model has read a word of it.  The refusal arrives as an
# exception on the draw's first call, so the sample would otherwise score zero with no
# reply at all.  The set is therefore delivered along a ladder — the complete set first,
# then the closest part of it, then the closest examples alone — and a refused request
# steps down a rung and asks again: less evidence is a worse answer, no answer is none.
DEMO_LADDER = (1.0, 0.25, 0.01)
# A refusal is a property of the request, not a verdict on the question: the same prompt,
# byte for byte, has been refused for one sample and answered for its sibling in the same
# run.  The first refusal at a rung is therefore answered by asking the same question at
# the same size again, and only a size the provider has refused this many times without
# ever reading it is given up — one rung at a time, and the rung that answers is kept.
REFUSALS_PER_RUNG = 2

# One reply is one draw from the model's own answer distribution, and on the questions where
# that distribution is wide a single draw is close to a coin flip.  The harness therefore asks
# the same question several times and answers with the reply the panel agrees on.
#
# What ends the panel is the sample's own resources, not a count of draws: the wall it owns
# and the failures it can absorb.  A count is not a resource — the ceiling is only what keeps
# the panel inside the sample's model-call limit — so it sits at the depth the vote was
# measured to be worth, and past that depth the record says draws cost without paying: the run
# that ended here drew deeper than eight on 32 samples and not one of them changed its answer,
# at a certain 123 model calls and 6.7M input tokens.  The unanimity stop below ends a panel
# that has settled, and the wall ends one that has not.
PANEL_CEILING = 8
# A unanimous panel of three has already settled on an answer, so later attempts are skipped.
PANEL_MINIMUM = 3
# The wall the sample owns is what a panel spends, and a draw is paid for before it is
# started: what is held back for it is what that draw can cost at worst — the client's own
# timeout, past which no draw survives — plus the room the sample needs outside the panel,
# since the sandbox, the client and the memory are up before the panel's clock starts and the
# answer is written after the panel stops.  The slowest draw so far is not that bound, only a
# lower bound on it: the run that ended here reserved 23s for a draw that cost 350s and left
# its slowest sample 33s inside the wall that kills the process, and a panel killed at the
# wall returns no answer at all, whatever it had collected.
PANEL_SETTLE = 60
# A draw that dies wakes nobody: the panel keeps drawing on the wall it still has, and only
# a run of these consecutive failures — the sample's own model-call or time limit, which no
# later draw survives — ends it.  The tolerance is the panel's, not the later draws': a draw
# that dies before anything has been collected is charged the same way as one that dies after,
# so a single dead draw no longer costs the sample its whole panel.
PANEL_FAILURES = 2

# The vote is the answer, and this lineage has measured the vote to sit on top of what the
# draws it holds contain (a pooled eight-draw replay puts USPTO's mode at 0.30 against an
# oracle of 0.3333 and LawBench's at 0.60 against 0.6667), so an answer can only move if the
# question does.  What the harness knows and the draws do not is the answer space the memory
# demonstrates, and what the samples leave unspent is their calls: the node before the one
# this one derives from used 4.6 calls of the 32 a LawBench sample is allowed and 6.05 on
# USPTO, and the parent's attempt to spend them *after* the answer, beside the panel's own
# reading, was measured dead — 89 reviews at 11.69 calls a sample, 87 of them byte-for-byte
# repeats of the answer they were shown, no addition accepted anywhere — a question that
# carries the answer it is asked to complete gets its own answer back.  The reading is
# therefore asked before anything of the panel is in front of the model: the case, alone,
# and the memory's whole demonstrated answer space
# as the menu the answer has to come from, so the question is one of recognition (which of
# the answers this task counts as answers does the case establish) rather than of recall,
# which is where this lineage's own failures sit — of the wrong LawBench samples that name
# too few charges, every missing charge is a string the memory demonstrates.  It is a panel
# like the first one, bound by the same wall, ceiling, unanimity stop and failure tolerance,
# and its reading replaces the panel's only through `extends_answer`: every answer the panel
# gave survives whole, everything added is a string the memory demonstrates, and the menu
# panel agreed with itself too.  A reading that dies, is refused, runs out of wall, agrees on
# nothing, or answers anything else leaves the panel's answer exactly as the panel left it.
MENU_BLOCK = """
The answers the memory demonstrates for this task are listed below.  Name every answer in
that list the facts of this case establish, and nothing that is not in the list, quoting
the fact that establishes each one.  Separate several answers with "{separator}".

{answers}
"""


class GroundedAgent:
    """Ground each reply in the memory's answer space, then answer with the panel's choice."""

    def __init__(
        self,
        agent,
        space: dict,
        prompts: list[str] | None = None,
        refusals: list[str] | None = None,
        panel_ceiling: int = PANEL_CEILING,
        budget: float | None = None,
        reserve: float = 0.0,
        menu: bool = False,
        case: str = "",
    ):
        self._agent = agent
        self._space = space
        self._prompts = list(prompts) if prompts else []
        self._refusals = list(refusals or [])
        self._panel_ceiling = panel_ceiling
        self._budget = budget
        self._reserve = float(reserve)
        self._menu = menu
        self._case = case
        self.settled = False
        self._rung = 0
        self._refused = 0

    def __getattr__(self, name):
        return getattr(self._agent, name)

    def invoke(self, inputs, config=None, **kwargs):
        started = time.monotonic()
        results: list = []
        replies: list[str] = []
        failures = 0
        last_error: Exception | None = None
        separator = (self._space or {}).get("separator")
        while len(results) < self._panel_ceiling:
            if results and self._out_of_budget(started):
                break
            try:
                result = self._agent.invoke(self._restart(inputs), config=config, **kwargs)
            except Exception as error:
                if self._refused_request(error):
                    # The provider would not read this request: the same question goes
                    # back at the same size, and only a size it keeps refusing is
                    # delivered with less of the set.  The panel loses no draw over a
                    # refused request, and a refused request is cheap and short, so it is
                    # not charged to the wall the way a draw that ran is.
                    continue
                if self._is_refusal(error) and not results:
                    # Even the smallest delivery was refused: the provider will not read
                    # this question at any size the harness has, so there is no answer to
                    # give and the sample's own retry is what can still save it.
                    raise
                # A draw that dies is charged to the panel's failure tolerance wherever it
                # falls in the panel, and the panel goes on drawing on the wall it still
                # has: a panel that ran out of time or out of model calls, or that has
                # collected replies while later draws died, still votes with what it has.
                last_error = error
                failures += 1
                if failures >= PANEL_FAILURES:
                    break
                continue
            failures = 0
            grounded = self._grounded(result)
            if grounded is None:
                return results[0] if results else result
            result, reply = grounded
            results.append(result)
            replies.append(reply)
            if len(replies) >= PANEL_MINIMUM and answers_agree(replies, separator):
                break
        if not results:
            # Every draw died and nothing was collected: there is no vote to hold, so the
            # panel's own failure leaves the harness the way a dead sample always has, and
            # the runner's retry is what can still answer the question.
            raise last_error
        self.settled = answers_agree(replies, separator)
        winner = results[panel_winner(replies, separator)]
        selected = self._selected(inputs, config, kwargs, started, winner)
        return winner if selected is None else selected

    def _selected(self, inputs, config, kwargs, started, result):
        """The menu panel's reading, when it is one the panel's answer can grow into.

        The panel answers a question whose answer is often several demonstrated answers at
        once, and a vote among draws that agree with each other cannot add one the draws
        never wrote.  The sample's calls are mostly unspent, so a few of them go on the
        question the draws cannot ask themselves: which of the answers the memory
        demonstrates do the facts of this case establish.  The menu is the memory's own
        answer list, the case is the question the runner sent, and the reading is taken only
        where it keeps the panel's answer whole and adds demonstrated answers to it
        (`extends_answer`).  Nothing else about the sample changes: the menu is a panel like
        the first one, bounded by the same wall and the same ceiling, and any failure of it —
        a dead draw, a refusal, the wall, a reading that agrees on nothing or is not an
        extension — leaves the first panel's answer standing.
        """
        separator = (self._space or {}).get("separator")
        items = (self._space or {}).get("items") or []
        if not self._menu or not self._budget or not separator or not items or not self._case:
            return None
        answer = answer_text(self._text_of(result))
        if not answer.strip():
            return None
        left = self._budget - (time.monotonic() - started)
        if left <= self._reserve:
            return None
        prompt = self._case + MENU_BLOCK.format(
            separator=separator, answers="\n".join(items),
        )
        menu = GroundedAgent(
            self._agent,
            self._space,
            [prompt],
            refusals=self._refusals,
            panel_ceiling=self._panel_ceiling,
            budget=left,
            reserve=self._reserve,
        )
        try:
            selected = menu.invoke(
                self._menu_inputs(inputs, prompt), config=config, **kwargs
            )
        except Exception:
            return None
        if not menu.settled:
            return None
        if not extends_answer(self._space, answer, answer_text(self._text_of(selected))):
            return None
        return selected

    @staticmethod
    def _text_of(result):
        """The text of an attempt's last message, flattened, or the empty string."""
        messages = list((result or {}).get("messages") or [])
        if not messages:
            return ""
        content = messages[-1].content
        if isinstance(content, list):
            content = "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content if isinstance(block, (str, dict))
            )
        return content if isinstance(content, str) else ""

    def _menu_inputs(self, inputs, prompt):
        """The question the runner sent, with the menu block inside the user message."""
        if not isinstance(inputs, dict):
            return inputs
        messages = []
        for message in inputs.get("messages", []):
            message = dict(message)
            if message.get("role") == "user":
                message["content"] = self._with_block(message.get("content"), prompt)
            messages.append(message)
        return {**inputs, "messages": messages}

    def _with_block(self, content, prompt):
        """The menu prompt carrying whatever the runner writes after the harness's own."""
        full = self._prompts[0]
        tail = content[len(full):] if isinstance(content, str) and content.startswith(full) else ""
        if isinstance(content, list):
            return [
                {**block, "text": prompt + tail}
                if isinstance(block, dict) and isinstance(block.get("text"), str) else block
                for block in content
            ]
        return prompt + tail if isinstance(content, str) else content

    def _grounded(self, result):
        """The attempt's result with its reply grounded, and the reply that vote compares."""
        messages = list(result.get("messages") or [])
        if not messages:
            return None
        last = messages[-1]
        content = last.content
        if isinstance(content, list):
            content = "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content if isinstance(block, (str, dict))
            )
        if not isinstance(content, str):
            return None
        grounded = ground_reply(content, self._space)
        if grounded != content:
            messages[-1] = self._copy(last, grounded)
            result["messages"] = messages
        return result, grounded

    def _is_refusal(self, error) -> bool:
        """Whether the provider would not read this request at all.

        The patterns are the ones the runner itself reads as a refusal to carry the
        request, so no provider string is written here and a run whose requests are all
        read behaves exactly as it did before.
        """
        return bool(self._refusals) and any(
            pattern in str(error).lower() for pattern in self._refusals
        )

    def _refused_request(self, error) -> bool:
        """Charge the error as a refusal and say whether the attempt should be repeated.

        True means the provider would not read the request and another attempt is worth
        making: the same question at the same rung while that size has been refused fewer
        than REFUSALS_PER_RUNG times, then the same question at the next rung down.  False
        leaves the error to the panel's ordinary failure handling — which is what a
        refusal at the smallest size gets, there being no smaller delivery to try.
        """
        if not self._is_refusal(error):
            return False
        self._refused += 1
        if self._refused < REFUSALS_PER_RUNG:
            return True
        self._refused = 0
        if self._rung + 1 >= len(self._prompts):
            return False
        self._rung += 1
        return True

    def _out_of_budget(self, started: float) -> bool:
        """True when the wall could not cover another draw at what a draw can cost at worst.

        A draw is paid for before it is started: its worst case is held back out of the wall,
        so the last draw a panel starts still returns inside the wall that kills the process.
        """
        if self._budget is None:
            return False
        return time.monotonic() - started + self._reserve > self._budget

    def _restart(self, inputs):
        """A fresh copy of the inputs: every attempt is an independent run.

        The question is asked at the rung the panel is currently on, so the attempt
        carries as much of the demonstration set as the provider has agreed to read.
        """
        if not isinstance(inputs, dict):
            return inputs
        prompt = self._prompts[self._rung] if self._prompts else None
        messages = []
        for message in inputs.get("messages", []):
            message = dict(message)
            if prompt and message.get("role") == "user":
                message["content"] = self._at_rung(message.get("content"), prompt)
            messages.append(message)
        return {**inputs, "messages": messages}

    def _at_rung(self, content, prompt: str):
        """The message content with this rung's demonstration set in place of the full one."""
        if prompt == self._prompts[0]:
            return content
        if isinstance(content, str):
            return self._swapped(content, prompt)
        if isinstance(content, list):
            return [
                {**block, "text": self._swapped(block["text"], prompt)}
                if isinstance(block, dict) and isinstance(block.get("text"), str) else block
                for block in content
            ]
        return content

    def _swapped(self, content: str, prompt: str) -> str:
        """The prompt the runner was given is the full set plus whatever it appends."""
        full = self._prompts[0]
        return prompt + content[len(full):] if content.startswith(full) else content

    @staticmethod
    def _copy(message, content: str):
        try:
            return message.model_copy(update={"content": content})
        except AttributeError:
            return AIMessage(content=content)


def build_prompts(input_text: str, config: dict) -> list[str]:
    """The question at every rung of delivery: the complete set first, then less of it.

    Every rendering is a prefix of the one before it — same examples, same order by
    closeness — so stepping down a rung takes demonstrations away from the end of the
    list rather than handing the model a different set.
    """
    template = Path(PROMPT_PATH).read_text()
    skill = Path(SKILL_PATH).read_text().strip()
    return [
        template.format(
            examples=render_demonstrations(input_text, config, share=share),
            input=input_text, skill=skill,
        )
        for share in DEMO_LADDER
    ]


def panel_wall(config: dict) -> tuple[float, float]:
    """The wall the panel spends and what a draw started out of it must be reserved.

    The sample owns one wall — the same timeout the runner kills the solver process on — and
    the panel is the only thing that spends it, so the panel is bounded by that wall rather
    than by a share of it.  A draw cannot outlive the client's own timeout, so that timeout,
    plus the room the sample needs outside the panel, is what the next draw is paid with.
    """
    wall = float(config.get("timeout_seconds") or 900)
    reserve = float(config.get("client_timeout_seconds") or wall) + PANEL_SETTLE
    return wall, min(reserve, wall)


def refusal_patterns(config: dict) -> list[str]:
    """The patterns the runner reads as the provider refusing to carry the input."""
    patterns = config.get("error_patterns")
    if not isinstance(patterns, dict):
        return []
    return [str(pattern).lower() for pattern in (patterns.get("content_filter") or [])]


def build_agent(model, input_text: str, config: dict):
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile("openai", profile)
    register_harness_profile(f"openai:{config['model']}", profile)
    backend = LocalShellBackend(
        root_dir="/",
        virtual_mode=True,
        timeout=config["tool_timeout_seconds"],
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    agent = create_deep_agent(
        model=model,
        tools=[],
        system_prompt=SYSTEM_PROMPT,
        middleware=[],
        subagents=[],
        backend=backend,
    )
    # The demonstration set rides with the question: it is the task's whole evidence, and a
    # tool result that size is taken off the conversation before the model ever reads it.
    prompts = build_prompts(input_text, config)
    wall, reserve = panel_wall(config)
    return GroundedAgent(
        agent,
        load_answer_space(),
        prompts,
        refusals=refusal_patterns(config),
        budget=wall,
        reserve=reserve,
        menu=True,
        case=input_text,
    ), prompts[0]
