# Iteration 16 — attested_delimiters (design note, pre-eval)

**Where fifteen iterations left the loss.** Iteration 14's gain came from deleting a
statement the check made that was not true of the corpus; iteration 15's loss came from
adding prompt text that was true. So this iteration deletes another false statement and adds
nothing. The statement is in the check's markup detection, and it is false for the same
reason in every corpus: *a bracketed token is not an answer delimiter merely by appearing in
the question.*

**Measured over the three training corpora (all 500 questions, train and val).** The check
reads every `[...]` token in the question as markup the answer must carry. A free-form
question states its input as a SMILES string, which is written in bracket atoms, so the check
asks for markup the question never mentions: 9 of 30 val questions and 14 of 50 train ones
carry at least one such token (`[N+]`, `[N-]`, `[nH]`, `[C@H]`, `[Si]`, `[O-]`, `[Na+]`,
`[C@@]`). It is not only that corpus: a set-answering fact pattern that cites a year in
brackets is read the same way - 2 of 200 train questions, whose check output then demands
`[2016]` in the answer. The one-unit corpus is unaffected (its `[DIAGNOSIS]` is real) and the
set-answering val split is unaffected.

**The size of it on the recorded runs.** Replayed over iteration 14's 260 submitted answers,
12 of 60 free-form samples carried a `- Markup:` defect; 0 of the 100 one-unit and 0 of the
100 set-answering samples did. Every one of the 12 is the invention above - the free-form
questions that produce it are exactly the 9 val questions with bracket atoms - and the header
of that output is `Issues to review before answering:`, which the system prompt tells the
solver to fix. Seven of the 12 are samples whose answer was correct.

**Change.** One method, `_required_markup`, and one constant. A bracketed token is required
markup when the question *uses* it as one: either it closes the token (`[X] ... [/X]`, the
wrapping form the one-unit corpus uses) or it stands within 40 characters of an
angle-bracket wrapper (`[X] ... <eoa>`, which is how a format example names them). Tokens
that only occur as notation are not delimiters, and a question that shows neither form asks
for no markup at all. The tag list is used in two places, both served by the same method:
the missing-markup defect and the stripping of the tags out of the draft before it is split
into units (which also stops the free-form drafts being mangled before their shape is read).

**Measured separation.** Over the same 500 questions: 250/250 one-unit questions and 50/50
set-answering val questions return byte-identical tag lists, 198/200 set-answering train
questions ditto and the 2 year-citing ones lose the false tag, and 80/80 free-form questions
that carried invented tags return none (the other 59 are unchanged, both readings empty).
Replayed over the recorded answers: 260/260 set-answering and one-unit check outputs
byte-identical, 48/60 free-form byte-identical, and on the remaining 12 the only line kind
that differs is `- Markup:` - the defect count on that corpus goes 12 -> 0. A 360-call fuzz
(empty, prose, bare fragments, unbalanced brackets, 5 kB of filler, gold answers, drafts
carrying the real markup) raises no exception, and the true positives survive: a one-unit
draft missing only `[/DIAGNOSIS]` is still reported, a set-answering draft missing `<eoa>` is
still reported, and the same drafts carrying their markup are not.

**Hypothesis.** Telling 20% of the free-form samples to add text the question never asked for
costs them, so removing the invention raises that corpus above iteration 14's 0.333 while the
other two corpora, whose memory, prompts, skill and check output are byte-identical, stay in
their 0.85-0.92 and 0.54-0.59 bands, and the average is at least 0.594.

**Falsifiers to look for in the results.**
- The free-form corpus stays at or below 0.333: the check's output is inert even when it is
  false, and the next iteration must spend its budget on what the solver reads before it
  drafts (the guide) rather than on what it reads after.
- The other two corpora move by more than 2 samples: the tag lists are not as isolated as the
  replay shows, and the delimiter rule is reaching questions it should not.
- A one-unit or set-answering run reports a missing delimiter it used to report: the closing
  form or the angle-bracket proximity is being misread.
- Any exception in the check: the new token walk is wrong on some question shape.
