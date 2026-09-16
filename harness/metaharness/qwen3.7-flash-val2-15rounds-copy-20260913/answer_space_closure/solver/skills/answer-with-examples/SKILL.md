## How to answer

1. The reference profile and the closest training references are given above. Treat their
   answers as the authority on vocabulary, surface form and answer shape for this task.
2. Answers are made of *units*. Split the references only at the separators the profile
   names as list separators. Punctuation the profile says belongs to the unit itself is
   part of one unit: never split a unit at it, never drop the text on either side of it,
   and never answer with a fragment of a longer reference answer.
3. Decide by naming candidates first. Write down every unit the question could support,
   including the ones you are about to set aside, and for each one ask which fact
   establishes it or rules it out. A unit may only be set aside for a factual reason - a
   prior about what the task usually answers, or about what the reference list happens to
   contain, is not one. How much weight the reference units carry is measured and stated in
   the profile above: either they are the set this task's answers are built from - then the
   answer is one of them - or they are evidence about a vocabulary the references only
   sample, and a unit the facts call for is written the same way even when the list does
   not have it. Follow the profile's statement, and never put a listed unit in the place of
   the one the facts establish because the listed one merely looks related (broader,
   narrower, or similarly spelled).
4. A missing unit and an extra unit both count as wrong, so be complete and precise: give
   one answer unit to each thing the facts establish, and to nothing they do not. The number
   of units follows from the facts, so neither trimming to the commoner length nor padding to
   a longer one is safer than answering what the facts establish. When the question states
   the shared header of a question type in the references, that type is the sharpest evidence
   about the count: a count its own cases never use is not a count this question can have, so
   before submitting, hold the draft's count against that type's cases.
5. Render the answer the way the references render theirs: use the exact spelling of a
   reference unit when your answer is that unit, match the usual number of units and the
   usual separators, and keep any markup the question asks for exactly as the question
   spells it.
6. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
7. Before submitting, call `check_answer` once with your draft answer. It reports the answer
   count this question's own type uses - a count the references never use for this question
   is a defect to fix, not a remark - the markup the question states that the draft is
   missing, and the renderings the references prove about its units: the whole unit when a
   unit of the draft is only a piece of one or stops short of one, and the exact spelling
   when a unit is a near miss. Everything the report does not list stands as it is, so fix
   what it lists and submit. It does not re-open the candidates you weighed and set aside,
   and a check that reports nothing is the end of the matter: call it once, and do not call
   it again over the same draft.
8. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
