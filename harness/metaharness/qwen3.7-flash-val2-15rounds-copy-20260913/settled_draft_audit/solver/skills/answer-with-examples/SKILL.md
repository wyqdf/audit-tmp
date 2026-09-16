## How to answer

1. The reference profile and the closest training references are given above. Treat their
   answers as the authority on vocabulary, surface form and answer shape for this task.
2. Answers are made of *units*. Split the references only at the separators the profile
   names as list separators. Punctuation the profile says belongs to the unit itself is
   part of one unit: never split a unit at it, never drop the text on either side of it,
   and never answer with a fragment of a longer reference answer.
3. Read the question's facts and decide what the answer is. A unit may be set aside only
   for a factual reason: "the references never use it", "it is not in the reference unit
   list" and "the references use a commoner unit" are not factual reasons. The reference
   units are evidence about vocabulary, not a closed list, so when the facts call for a
   unit the references do not list, write that unit yourself, in the same style and at the
   same level of specificity as the listed units, and never put a listed unit in its place
   because the listed one merely looks related (broader, narrower, or similarly spelled).
   A missing unit and an extra unit both count as wrong, so be complete and precise: give
   an answer unit to each thing the facts establish, and to nothing they do not.
4. Decide once. When the facts have settled which units the answer carries, the decision is
   made; do not re-open it while rendering the answer or after the check. The number of
   units follows from the facts, not from how many the references usually use - the profile's
   shape line describes how answers are rendered, and neither trimming to a commoner length
   nor padding to a longer one is safer than answering what the facts establish.
5. Render the answer the way the references render theirs: use the exact spelling of a
   reference unit when your answer is that unit, match the separators the references use,
   and keep any markup the question asks for exactly as the question spells it.
6. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
7. Before submitting, call `check_answer` once with your draft answer. It reports only
   mechanical problems: missing markup, unbalanced structure, the answer count against the
   reference shape, and units that are fragments or near-miss spellings of a reference unit.
   Fix those, then submit. If it reports nothing, the draft is finished and the decision you
   made stands - calling it again over the same draft cannot tell you anything new, and it
   does not re-open the candidates you weighed and set aside.
8. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
