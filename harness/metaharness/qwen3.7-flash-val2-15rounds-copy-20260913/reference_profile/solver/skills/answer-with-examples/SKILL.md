## How to answer

1. The reference profile and the closest training references are given above. Treat their
   answers as the authority on vocabulary, surface form and answer shape for this task.
2. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
3. Decide the answer from the question first, then render it the way the references render
   theirs:
   - When a reference label list is given, use its exact spelling: if your answer is the same
     thing as a listed label but differs in characters, output the listed label character for
     character. Never add, drop, reorder or re-word characters, and never append a generic
     word the references do not use. If the correct answer truly is not in the list, still
     give it, written in the same style as the listed labels.
   - Match the usual number of parts and the usual separators. Include every part that
     applies: a partial answer is scored as wrong, extra parts are scored as wrong, so be
     complete and precise.
   - Keep any markup the question asks for exactly as the question spells it.
4. Before submitting, call `check_answer` with your draft answer and fix anything it flags,
   then call `check_answer` again on the corrected draft.
5. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
