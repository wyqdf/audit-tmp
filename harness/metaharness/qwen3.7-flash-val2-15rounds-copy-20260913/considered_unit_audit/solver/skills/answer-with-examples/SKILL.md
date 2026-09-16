## How to answer

1. The reference profile and the closest training references are given above. Treat their
   answers as the authority on vocabulary, surface form and answer shape for this task.
2. Answers are made of *units*. Split the references only at the separators the profile
   names as list separators. Punctuation the profile says belongs to the unit itself is
   part of one unit: never split a unit at it, never drop the text on either side of it,
   and never answer with a fragment of a longer reference answer.
3. The reference units are evidence about vocabulary, not a closed list: a correct unit can
   be missing from it. When the facts call for a unit the references do not list, write
   that unit yourself, in the same style and at the same level of specificity as the listed
   units. Never put a listed unit in its place because the listed one merely looks related
   (broader, narrower, or similarly spelled).
4. Decide by naming candidates first. Write down every unit the question could support,
   including the ones you are about to set aside, and for each one ask which fact
   establishes it or rules it out. A unit may only be set aside for a factual reason -
   "the references never use it" and "it is not in the reference unit list" are not
   factual reasons. A missing unit and an extra unit both count as wrong, so be complete
   and precise, and check the answer length the profile reports for the question type you
   are answering.
5. Render the answer the way the references render theirs: use the exact spelling of a
   reference unit when your answer is that unit, match the usual number of units and the
   usual separators, and keep any markup the question asks for exactly as the question
   spells it.
6. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
7. Before submitting, call `check_answer` with your draft answer and with `considered` set
   to the candidate units from step 4, comma separated (just the units, not the
   surrounding reasoning). That call re-opens every candidate you left out with the
   reference cases that answer it, and re-opens reference units that share an edge with a
   unit of your draft. Fix everything it flags, including any candidate you cannot rule out
   with a fact, then call it again on the corrected draft.
8. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
