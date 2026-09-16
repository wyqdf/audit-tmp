# Iteration 8 — family_shape_audit (design note, pre-eval)

**Where iteration 7 left the loss.** Three measured facts set the direction.

1. *The shape evidence the check gives is corpus-wide, and it is a contradiction on almost
   every sample.* It reported a directional discrepancy in 101/101 law and 59/61 chemistry
   checks while 63 (law) and 58 (chemistry) of those reports still ended "the draft checks
   out ... submit this draft unchanged". On the one chemistry draft where the discrepancy was
   right (3 parts against a gold of 2) the model kept its draft. A report that contradicts
   itself is read as the discrepancy not mattering.
2. *The question's own type is far better evidence than the corpus, and it was never used.*
   The references group into question types by their shared opening header, and each type has
   its own answer count: on the 30 chemistry validation questions the type's modal count
   equals the gold count in 26 cases against 22 for the corpus modal count. The type was in
   the prompt as a catalogue line, but never held against the draft.
3. *The type never even matched at solve time.* Types were derived as raw prefixes of the
   question text, so the key ran past the header into the case ("... Oxidations. Input: C"),
   which only the references whose case begins the same way could match; and the text handed
   to the memory while solving is the whole task prompt, which starts with the task's own
   wording, so prefix-anchored matching found no type at all: 0 of 31 validation questions
   matched a type at solve time.
4. *The relation note is a two-way channel.* Iteration 7's "extends a piece" note repaired one
   law draft and destroyed another that was already correct (the model's second draft was the
   gold answer and the note talked it back to a single charge). A note inferred from a shared
   substring cannot tell those two apart, so it has to be narrowed to the reading it can
   support: a term with an ending added, not a term with new content after it.

**Change.** Answer-count evidence becomes the question's own type, and the report becomes
consistent with itself.

1. A question type is derived as a *complete opening sentence* several references share
   (`question_header`), not as a 32-64 character prefix; question types read as full headers
   and a question whose opening is not a complete sentence has no type (the label tasks have
   none, so nothing changes there).
2. Type lookup at solve time looks for the header anywhere in the question text, since the
   text the memory receives is the whole task prompt carrying the question inside it.
3. The check reports the count of the question's own type, and a count that type never uses is
   a **defect**, listed with the markup and structure problems - not a remark beside a verdict
   that affirms the draft. The corpus line remains as the fallback for questions without a
   type and never decides anything: it reported a discrepancy on nearly every draft.
4. The verdict now follows the report: "the draft checks out ... submit this draft unchanged"
   only appears when the report contains nothing, and every other report ends with "fix what
   is listed, then submit; everything not listed stands as it is".
5. The relation note keeps only what it can support: a unit that is exactly a piece of an
   attested unit, a unit that is the beginning of one, and a unit that is an attested term
   with at most a short ending added. The unbounded piece-extension reading is gone.

**Hypothesis.** Reporting the answer count of the question's *own* reference type, and
affirming a draft only when the report has nothing to say about it, raises the mean validation
score above the 0.573 of iteration 7 and the 0.584 of iteration 3 - mainly by turning drafts
whose count their own type never uses into drafts with that type's count (measured on the
replayed run: 2 chemistry drafts, both wrong, whose type answers with 2 parts in 100% while the
draft had 3) and by no longer talking a correct draft out of a unit (1 law draft whose gold
answer was the draft the note rejected) - without regressing the tasks that have no question
type, where the profile, the references and the check are unchanged.

**Falsifiers to look for in the results.**
- The chemistry task does not exceed 0.28: the model reads the count contradiction and keeps
  its count anyway, so count evidence is inert for this solver and iteration 9 must stop
  spending changes on the check.
- The label tasks move at all (Symptom2Disease below 0.90 or LawBench below 0.57 in a way not
  explained by their own flapping): the verdict change ("everything not listed stands") is
  churning drafts that were already settled, and it has to be limited to reports that contain
  a defect.
- LawBench falls while chemistry rises: the cost of dropping the unbounded relation note is
  larger than the 1 draft it is measured to have destroyed, so the note has to come back for
  units whose added text is a generic classifier rather than content.
- `call_budget` losses appear: the "fix what is listed" verdict invites repeated checks.
