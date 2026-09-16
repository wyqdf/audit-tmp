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
%%DECISION%%
5. Render the answer the way the references render theirs: use the exact spelling of a
   reference unit when your answer is that unit, join units with the separator the profile
   names rather than one of your own, and keep any markup the question asks for exactly as
   the question spells it. How many units the answer carries is what the facts establish:
   the profile reports the widths the references use, which is a fact about the corpus and
   not a count this question has to match.%%MATERIAL%%
6. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
7. Before submitting, call `check_answer` with your draft answer and with `considered` set
   to the candidate units from step 4, comma separated (just the units, not the
   surrounding reasoning). Every candidate your draft does not carry comes back as a defect
   of the draft, with the reference cases that answer it and with the answer written out as
   it would read if it carried it; reference units that share an edge with a unit of your
   draft are reported too. %%REOPEN%%
8. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
