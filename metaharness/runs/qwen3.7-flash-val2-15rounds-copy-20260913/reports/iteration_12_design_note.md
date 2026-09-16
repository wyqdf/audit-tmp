# Iteration 12 — carry_offer (design note, pre-eval)

**Where iteration 11 left the loss.** Four measured facts, all from the recorded runs.

1. *The multi-unit corpus fails one-sidedly.* Of its 50 validation questions, 23 are wrong, and
   every one of the 23 is a *missing-unit* error: 0 are answered with an extra unit and no
   golden unit. In 16 of them the missing unit never appears anywhere in the solver's own text;
   in 7 the solver named it and the check re-opened it, and about one of those converted.
2. *The check channel is nearly inert there because it asks a question instead of reporting a
   defect.* The re-opened candidate comes back as "if the facts establish it, put it in the
   answer verbatim ... if a fact rules it out, say which fact and keep your draft", under a
   header that reads "No surface problem found". Replaying the recorded conversations, the final
   answer differs from the first draft in 1-3 samples per 100 on that task, and the solver's own
   reasons for keeping its draft are about the corpus ("reference cases usually find only the
   main charge"), not about the question.
3. *The harness itself supplies a corpus statistic that the solver uses as a case fact.* The
   profile prints "1 part in 68%, 2 parts in 29% ..." and the check prints "32% of references
   have more parts than yours"; recorded reasoning cites the distribution to justify a one-unit
   answer ("shape 1 part, consistent with the reference distribution"), and on the free-form
   corpus a draft was changed to drop a component "following ... the prevalence of 2-part
   answers in the reference set" - that draft was wrong.
4. *The missing unit cannot be proposed from the corpus.* Measured and discarded this iteration:
   answer co-occurrence (recall 2/23, and it would fire on 12/27 correct questions), a cue index
   over question n-grams (3/32 missed units in its top 10, 4-5 spurious suggestions per correct
   question), literal unit mentions in the question (7% of units), the width of the nearest
   reference answer (1 part for 22 of 25 two-unit golds), and retrieval coverage (questions whose
   gold units are already shown score 40%, those whose gold is in no reference at all score 57%).
   The candidate has to come from the solver, which is why the channel is the solver's own list.

**Change.** The candidates the solver names become binding, and the corpus's width frequencies
stop being reported as advice.

1. `_unruled_candidates` reports every named candidate the draft does not carry as a *defect* of
   the draft - it moves under "Issues to review before answering:" - with the reference cases
   that answer it and, new, **the answer written out** the way it would read if it carried it
   (the question's own markup, the separator the references join units with); a candidate whose
   text contains the draft's units is written out as a replacement, not a join.
2. The system prompt, the skill and the check name the reasons that do not rule a candidate out:
   the vocabulary not listing it, the references usually answering with one unit, another unit
   covering the same acts. Only a fact of the question does.
3. The scoping is measured, not stylistic: on a corpus whose answers are a single unit a
   candidate cannot be *missing* from the answer, only competing with it, and 9 correct questions
   there vs 7 wrong ones have a named-but-dropped attested candidate - so a hard rule would break
   more than it fixes. On that corpus the same lines stay remarks and only gain the written-out
   replacement.
4. `_shape_text` and the check report the widths the references use as a range (or as the
   regularity when all references share one width) and no longer print the modal percentage or
   the "N% have more/fewer parts than yours" clause. The one-unit rule is unchanged.

**Measured separation (training only).** The derivation is untouched: rebuilding memory from the
training splits reproduces the recorded profiles exactly (widths 137/58/5 single, 200 single,
18/30/2), so the one-unit branch is on for the same corpus as in iteration 11. The carry render
was replayed over all 289 recorded `check_answer` calls (117 + 102 + 70): 0 exceptions and 0
renders whose parsed unit set differs from draft ∪ candidate (or the replacement). On the
one-unit corpus 100 of 102 calls keep the "No surface problem found" header.

**Hypothesis.** Reporting the candidates a draft does not carry as defects and writing out the
answer that would carry them converts more of the 7 named-and-dropped cases than the question
form did (about 1), and removing the corpus's modal width stops the frequent count from being
used as a reason to drop a unit, so the multi-unit task rises above its 0.56-0.59 band and the
free-form task stays inside 0.20-0.28, while the single-unit task's 0.90 does not move.

**Falsifiers to look for in the results.**
- The multi-unit task stays in or below its band: the solver's judgment, not the channel's
  framing, sets the count, and the next lever is candidate generation on the first call (before a
  draft exists to defend).
- The multi-unit task falls below 0.52: the defect framing carries candidates the facts exclude -
  visible as new predictions with extra units.
- The single-unit task falls below 0.85: the replacement renders pushed swaps; the scoping in
  point 3 is wrong and the channel must revert to remarks everywhere.
- The free-form task falls below 0.20: removing the "more parts than yours" clause cost the only
  component-count advice there.
