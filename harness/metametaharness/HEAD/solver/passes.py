"""The harness's own reading of the answer, run after the agent has answered.

The conversation answers once: it retrieves the examples, reasons, and writes an answer. Its
residual errors are largely not errors of judgment but errors of writing -- in the frozen Val
runs the answer names the entry the case calls for and writes it in characters the memory never
uses, with a title it does not carry, with a piece of a joined name dropped, or with a piece of
an entry standing in for the whole entry -- so the harness re-reads the answer against the
memory's own list of answer strings and writes each entry the way the memory writes it. The pass
does not derive the answer again and does not decide anything: it never adds an entry the answer
did not choose, never drops one it has, and never writes a different entry in place of one it
chose. A name it writes out in full is the same entry the answer named, and the harness checks
that correspondence itself, so a pass that rewrites the answer into other entries is discarded.

The part of that reading the list itself settles is made here rather than asked for, because the
frozen runs measure the model leaving it unmade: of the parent's 99 readable LawBench answers,
16 carry an entry the list does not carry and the list's own endings settle 10 of them, every
one of which the parent's check left exactly as the answer wrote it.
"""

import re

from langchain_core.messages import HumanMessage

from tools.retrieval import SEPARATORS

# The markup the problem asks for wraps the answer, not an entry of it.
MARKUP = re.compile(r"\[[^\]]*\]|<[^>]*>")

# The list writes each entry as one complete name. When the memory's own answers are several
# entries joined by a separator, an entry the list does not carry still has to be written the
# way the list writes its entries, so the check is licensed to write such a name out in full.
COMPLETION_RULE = (
    "- The list writes an entry's complete name and nothing else: no listed string is a\n"
    "  shortened form of a name, and none carries a title or category word the list never uses.\n"
    "  An entry the list does not write is written the way the list writes its own entries --\n"
    "  the complete name of that entry, in the same style -- so a name the answer wrote short is\n"
    "  written out in full and a title it does not carry is left off. It is the same entry: the\n"
    "  name is written out, not exchanged for a different entry.\n"
)
CONSERVATIVE_RULE = (
    "- An entry the list does not write is left as the answer wrote it, apart from the shape\n"
    "  of the string itself: the listed strings are all answer strings of one kind, and an\n"
    "  entry the list does not have is written that way too.\n"
)


def conform_prompt(case: str, key: str, draft: str, complete: bool) -> str:
    """The writing check: the answer's own entries, written the way the memory writes them."""
    return (
        f"{case}\n\n"
        "You have already answered this problem, and that answer is written below. Nothing here\n"
        "decides the answer again: which entries the answer is made of is settled, and this\n"
        "check only writes those entries the way the memory writes its own answers.\n"
        "- Take the answer's entries one at a time, in the order the answer gives them, and look\n"
        "  for the listed string that is the same entry. The list is the authority on how that\n"
        "  entry is written: copy the listed string exactly, so that a name, title or category\n"
        "  word the answer added and the list never uses, a piece of the entry the answer\n"
        "  dropped, or punctuation the list does not write, is corrected.\n"
        f"{COMPLETION_RULE if complete else CONSERVATIVE_RULE}"
        "- Keep every entry the answer has, in the order it has them. Do not add an entry it did\n"
        "  not choose and do not write a different entry in place of one it chose: an entry the\n"
        "  case does not establish is not this check's business, and neither is a missing one.\n\n"
        f"{key}\n\n"
        "The answer to check is:\n\n"
        f"{draft}\n\n"
        "Write the answer out again with only those spellings corrected, keeping the format the\n"
        'problem asks for and its markup unchanged: {"reasoning": "...", "final_answer": "..."}'
    )


def message_text(message) -> str:
    """One message's content as plain text, whatever shape the provider returned it in."""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        content = "".join(
            block if isinstance(block, str) else block.get("text", "") for block in content
        )
    return content if isinstance(content, str) else ""


# The answer the reply carries, with the text on either side of it, so the field can be
# written again without touching anything else the reply says.
ANSWER_FIELD = re.compile(r'("final_answer"\s*:\s*")(.*?)("\s*(?:,|\}|$))', re.S)


def answer_field(text: str) -> str:
    """The answer field of the JSON the reply is written in, or nothing if it carries none."""
    match = ANSWER_FIELD.search(text)
    return match.group(2) if match else ""


def bare(text: str) -> str:
    """A string's letters and digits, so one entry written two ways can be told from another."""
    return "".join(character for character in text if character.isalnum())


def subsequence(shorter: str, longer: str) -> bool:
    """True when every character of the first string appears in the second in that order."""
    characters = iter(longer)
    return all(character in characters for character in shorter)


def entries(answer: str, joiner: str) -> list[str]:
    """The answer's entries: what the memory's own joiner separates.

    The markup around an answer is the problem's, not the entry's, so it is taken off before
    the entries are read; when the memory joins no entries, the whole answer is the entry.
    """
    if not joiner:
        return [answer.strip()] if answer.strip() else []
    return [part.strip() for part in MARKUP.sub("", answer).split(joiner) if part.strip()]


def same_entry(entry: str, written: str) -> bool:
    """True when the rewrite is the answer's own entry, only written differently.

    The rewrite may write the entry's name out with the pieces the answer left out of it
    (`容留卖淫` as the listed `引诱、容留、介绍卖淫`) or leave off a title the answer
    carries (`破坏电力设备罪` as `破坏电力设备`), and nothing else: a shorter name the
    entry is only a piece of is a different entry, not another writing of this one.
    """
    given, said = bare(entry), bare(written)
    return subsequence(given, said) or given.startswith(said) or said.startswith(given)


def kept(answer: str, rewritten: str, joiner: str) -> bool:
    """True when the rewrite holds the answer's own entries, none added, dropped or replaced."""
    given, written = entries(answer, joiner), entries(rewritten, joiner)
    if len(given) != len(written):
        return False
    for entry in given:
        for index, candidate in enumerate(written):
            if same_entry(entry, candidate):
                written.pop(index)
                break
        else:
            return False
    return True


def listed_endings(whole: list[str], parts: list[str]) -> set[str]:
    """The characters a written name of the list ends with.

    A listed answer is read as the names it is divided into -- that is what the memory's own
    separators are for -- so what a name can end with is what any of those names ends with.
    """
    endings = set()
    for listed in [*whole, *parts]:
        for name in re.split("[" + re.escape("".join(SEPARATORS)) + "]", listed):
            characters = bare(name)
            if characters:
                endings.add(characters[-1])
    return endings


def piece_of_a_listed_name(name: str, listed: set[str]) -> bool:
    """True when the list writes this string inside one of its own names.

    The list's answers are written from strings like this one -- the key lists those strings
    too, and the skill tells the solver to write one of them on its own when that is all that
    applies -- so a name the list does not carry as an answer can still be a name the list
    writes, and one of those is left exactly as the answer wrote it.
    """
    return any(name != other and name in other for other in listed)


def written_the_lists_way(name: str, listed: set[str], endings: set[str]) -> str:
    """The name with the characters the list never ends a name with left off.

    The list is the authority on how its entries are written, and each of its names ends with a
    character the list writes at the end of a name. A name the list does not carry that ends
    with a character the list never ends a name with is therefore the entry with something
    appended to it -- a title or category word the list never uses -- so the harness writes it
    the way the list writes its names, and stops as soon as it has one. Nothing else is touched:
    the characters come off the end, and the entry is neither exchanged for another nor dropped,
    so a name the list writes inside a name of its own is left exactly as the answer wrote it.
    """
    if name in listed or len(name) < 3 or piece_of_a_listed_name(name, listed):
        return name
    end = len(name)
    while end - 1 >= 2 and name[end - 1] not in endings:
        end -= 1
        if name[:end] in listed:
            break
    return name[:end]


def name_positions(piece: str) -> list[int]:
    """Where an entry's own characters sit in the text, the problem's markup left out."""
    markup = {index for match in MARKUP.finditer(piece) for index in range(match.start(), match.end())}
    return [
        index for index, character in enumerate(piece)
        if character.isalnum() and index not in markup
    ]


def written_answer(answer: str, whole: list[str], parts: list[str], joiner: str) -> str:
    """The answer's text with every entry written the list's way, its markup and separators kept.

    An entry is what the memory's own joiner separates, as everywhere else in this pass, so a
    name the list writes with a divider inside it stays one entry. A memory whose answers are
    single strings has no names to write out, and an answer of its that the list does not carry
    is another answer rather than a misspelling, so nothing is corrected there.
    """
    if not joiner or not answer:
        return answer
    listed = {bare(name) for name in [*whole, *parts] if name.strip()}
    endings = listed_endings(whole, parts)
    if not listed or not endings:
        return answer

    pieces, position = [], 0
    for match in re.finditer(re.escape(joiner), answer):
        pieces.append(answer[position:match.start()])
        pieces.append(match.group())
        position = match.end()
    pieces.append(answer[position:])

    kept = []
    for piece in pieces:
        positions = name_positions(piece)
        name = "".join(piece[index] for index in positions)
        written = written_the_lists_way(name, listed, endings)
        if written == name:
            kept.append(piece)
            continue
        # Take the characters off where they are written, so the markup around them is kept.
        dropped = set(positions[len(written):])
        kept.append("".join(c for index, c in enumerate(piece) if index not in dropped))
    return "".join(kept)


def written_message(text: str, whole: list[str], parts: list[str], joiner: str) -> str:
    """The reply with its answer written the list's way, everything else left as it was."""
    return ANSWER_FIELD.sub(
        lambda match: (
            match.group(1) + written_answer(match.group(2), whole, parts, joiner) + match.group(3)
        ),
        text,
        count=1,
    )


def conform(model, case: str, key: str, draft: str, joiner: str = "", complete: bool = False) -> str:
    """One model call; an empty result leaves the conversation's own answer in place."""
    answer = answer_field(draft)
    if not answer.strip():
        return ""
    try:
        message = model.invoke(
            [HumanMessage(content=conform_prompt(case, key, draft, complete))]
        )
    except Exception:
        # The pass sharpens an answer that already exists, so its own failure must not
        # cost the sample: a filtered or timed-out call returns nothing and the draft stands.
        return ""
    content = message_text(message)
    # A rewrite that carries no answer, or that answers with entries other than the answer's
    # own -- dropping one, replacing one, or adding one -- is not a correction of how those
    # entries are written, so the conversation's answer stands.
    if not kept(answer, answer_field(content), joiner):
        return ""
    return content
