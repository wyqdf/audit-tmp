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
4. Decide through a *ledger of acts*, not a choice between units. Write down every separate
   act or component the question's facts establish - one entry each - with the fact that
   establishes it and the unit that fact calls for. An entry may only be marked ruled out
   for a factual reason; "the references never use it", "it is not in the reference unit
   list" and "the references use a commoner unit" are not factual reasons. Then:
   - Two entries that name the *same* act at different levels of generality are one entry,
     decided by the facts (see *Specificity* below). Filling one entry never settles
     another.
   - Two entries that name *different* acts are two entries, and the answer carries a unit
     for each of them. A unit that names a different act is an addition to the answer, not
     a rival spelling of the unit already in the draft, and the number of units the
     references usually use is no reason to leave it out.
   A missing unit and an extra unit both count as wrong, so be complete and precise.
   Two rules settle the hard cases:
   - *Specificity.* When two units differ only by an element one of them adds, they are
     different answers, not two spellings of one. Ask whether the facts establish that
     element. If they do, the unit that contains it is the answer and the broader one is
     wrong here - it is not the safe choice, and being commoner in the references does not
     make it likelier for this question.
   - *Precedent.* The reference case closest to this question, and the unit its answer
     uses, is the evidence for how this task names the situation the question describes.
     Where your own reading of the facts conflicts with a case that matches them closely,
     the case is the better guide to what this task's answers look like.
5. Render the answer the way the references render theirs: use the exact spelling of a
   reference unit when your answer is that unit, match the separators the references use,
   and keep any markup the question asks for exactly as the question spells it. The number
   of units follows from the ledger, not from the usual count: never drop an entry to match
   a commoner answer length, and never add a unit no entry asks for.
6. If the question looks like it comes from a family of questions that recur, use
   `retrieve_examples` with a query built from the decisive details of the question to pull
   more references of that family, and `search_examples` to grep the reference set for a
   term that must appear in the answer.
7. Before submitting, call `check_answer` once with your draft answer and with `ledger` set
   to the ledger from step 4, one entry per line as `act -> unit` (`act -> -` for an act the
   facts rule out). It audits the draft against the ledger: every entry with no unit in the
   draft comes back, with the reference case that answers it, and when the closest
   reference case to this question answers with more parts than your draft, that case is
   quoted. Nothing it reports may be left unaddressed: fill every entry the facts establish,
   replace a fragment with the whole unit, and for an entry you keep out of the answer state
   the fact that rules it out. Do not call it a second time to settle which of two related
   units applies - it reports the same surface facts whichever of them the draft submits,
   so it cannot decide that; settle it once from the facts and submit.
8. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
