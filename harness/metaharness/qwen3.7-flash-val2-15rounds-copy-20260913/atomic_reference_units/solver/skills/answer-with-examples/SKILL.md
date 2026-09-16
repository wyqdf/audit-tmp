## How to answer

1. The reference profile and the closest training references are given above. Treat their
   answers as the authority on vocabulary, surface form and answer shape for this task.
2. Answers are made of *units*. Split the references only at the separators the profile
   names as list separators. Punctuation the profile says belongs to the label itself is
   part of one unit: never split a unit at it, never drop the text on either side of it,
   and never answer with a fragment of a longer reference answer when the facts support
   the longer form.
3. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
4. Decide the answer from the question first, then render it the way the references render
   theirs:
   - Enumerate every unit the facts support before choosing, and check the answer length the
     profile reports for the question type you are answering. A missing unit and an extra
     unit are both scored as wrong, so be complete and precise.
   - When a reference label list is given, use its exact spelling: if your answer is the same
     thing as a listed label but differs in characters, output the listed label character for
     character. Never add, drop, reorder or re-word characters, never append a generic word
     the references do not use, and never shorten a listed label to one of its fragments.
     If the correct answer truly is not in the list, still give it, written in the same style
     as the listed labels.
   - Match the usual number of units and the usual separators.
   - Keep any markup the question asks for exactly as the question spells it.
5. Before submitting, call `check_answer` with your draft answer and fix anything it flags,
   then call `check_answer` again on the corrected draft.
6. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
