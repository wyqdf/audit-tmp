# Iteration 15 — formula_coverage (design note, pre-eval)

**Where iteration 14 left the loss.** Fourteen iterations have spent the check channel on
advice, and the recorded runs say advice is inert: candidates the solver named come back as
defects and change 1-2 answers per 100; shape, spelling and edge-sharing notes are argued
away in the solver's own reasoning ("工具提示仅为关于边缘共享单位和复合词的标准提醒"). Every
note so far is a *reading* of the question, and a reading can be disputed. Meanwhile the
free-form corpus sits at 0.30-0.33 for the sixth iteration running, and its wrong answers
have a structure nobody has used: the answer is a set of formulas, so part of its
correctness is arithmetic, not judgement.

**Measured over the recorded runs (iteration 14, 260 samples).** Of that corpus's 40 wrong
samples, 12 are wrong in a way that is *provable from the question alone*: the answer's
molecules do not contain every element of the material the question states, and a reaction's
atoms all come from its reactants. The same accounting holds for 20 of 20 correct samples.
The class is not noise: of the 61 units the set-answering corpus misses, 33 are not in the
vocabulary at all (iteration 13), but here the missing thing is named by the question itself.
Examples from the recorded drafts: the answer `NS(=O)(=O)c1ccccc1SCc1ccccc1` against a
material of `C13NO3S2` (one O and one S short); an amide answered as a nitrile
(`O` short); a bromide answered as an amine (`O3Br` short).

**Change.** The references measure whether the rule applies, and the harness verifies the
submitted answer against it.

1. **A derivation, not an assumption.** `derive_formula_rule` reads the training references
   with a standard-library formula reader (`parse_formula`: element symbols, brackets,
   aromatic atoms, ring closures and bonds; a letter that is not part of an element symbol
   means the token is prose, not a formula). It measures two shares: how many reference
   answers are written as formulas, and - among those whose question states a material - how
   many account for every heavy atom of it. The rule is enabled only when both are high
   (>= 0.6 answers written as formulas, >= 0.9 coverage, >= 5 measured references). Measured
   on the three training splits this experiment runs: 1.00/0.96 (50 references) for one
   corpus and 0.00/0.00 for the other two, so two of the three never see any of this.
2. **The rule is stated where a draft is made.** The profile gains one line (the measured
   shares), the system prompt one sentence and the skill one paragraph, on the enabled
   corpus only.
3. **The check accounts for the material.** `check_answer` reports the material's heavy
   atoms, the draft's, and the difference, as a defect: "the question's material has the
   heavy atoms C13NO3S2; the draft's molecules account for C13NO2S2, so O is missing ... find
   the disconnection that carries them". When the accounting holds it says so as a remark,
   with the caveat that holding is necessary and not sufficient. A draft that does not read
   as formulas at all is reported too, since on such a corpus that is a defect.
4. **The harness verifies it itself.** The pre-submit middleware already forces one check
   call and repairs an unreadable final turn; it now also recomputes the accounting on the
   submitted answer and, when an element of the material is missing, sends the answer back
   once with the missing elements named. This is the first channel in this experiment that
   does not depend on the model agreeing with a tool: the deficit is arithmetic.

**Measured separation (training and recorded traces only).** Memory profiles are identical
to iteration 14's apart from the new measured field, and so are the stored examples. Over
the recorded conversations, every `check_answer` call was replayed through both libraries:
106/106 outputs byte-identical on the legal corpus, 100/100 on the single-unit corpus, and
on the free-form corpus 58/58 change - 38 by gaining the accounting remark, 20 by gaining
the missing-elements defect. The rendered guide is byte-identical on 10/10 questions of both
untouched corpora and gains exactly one line on the free-form one; the system prompt and the
skill are byte-identical on the former and gain one sentence/paragraph on the latter. A
390-draft fuzz over the free-form questions (empty, prose, bare fragments, gold answers and
gold answers with a fragment added or truncated) raises no exception. On iteration 14's
recorded final answers the accounting flags 12 of 40 wrong and 0 of 20 correct samples; on
the baseline run 20 of 49 wrong and 0 of 11 correct; on all 30 val golds 0.

**Hypothesis.** Stating that the answer has to account for the material's elements, and
sending back the answers that do not, converts part of the 12 flagged wrong free-form
samples - the class is the largest provable one in the experiment - so the free-form corpus
rises above its 0.30-0.33 band, while the other two corpora, whose prompts, memory and check
outputs are byte-identical, stay in their 0.85-0.92 and 0.54-0.59 bands, and the average
rises above 0.594.

**Falsifiers to look for in the results.**
- The free-form corpus stays at or below 0.33: a deficit the solver cannot act on is not
  worth stating, and the missing fragment has to be proposed, not merely named.
- It falls below 0.28: the repair turn pushes answers off drafts that were right - visible
  as correct samples whose answer satisfies the accounting and still changed.
- The other two corpora move by more than their own flapping (1-3 samples): the gating is
  wrong, since their memory, prompts and check output are byte-identical to iteration 14's.
- `call_budget` errors appear or the free-form corpus's model calls rise above ~4 per sample:
  the repair fires too often and needs the two-sided test (the draft must also be formula-like)
  tightened.
