# Iteration 11 — cardinality_branch (post-eval)

**Result.** average 0.581 (iteration 10: 0.573, iteration 3 best: 0.584). USPTO 0.283 (0.250),
Symptom2Disease 0.900 (0.890), LawBench 0.560 (0.580). 260 of 260 samples completed.

**The mechanism was inert, and it is measurable.** The design note's falsifier "the new defect
fires often on the single-unit task without a score move" did not fire either way: replaying the
171 `check_answer` calls recorded on that task, the one-unit defect appears **0 times**. The
solver never drafted an answer carrying two units there, so the branch had nothing to act on and
the 0.890 -> 0.900 move is one sample of noise.

**What the run measured.**
- Paired per sample against iteration 10: USPTO +3/-1, Symptom2Disease +2/-1, LawBench 0/-2.
  Every task is inside its own run-to-run spread (USPTO 0.20-0.28, Symptom2Disease 0.85-0.92,
  LawBench 0.54-0.59 over the last five candidates).
- On the two corpora the branch was derived *off* for, the system prompt, profile paragraph,
  rendered skill and check output are byte-identical to iteration 3's (verified by replaying 169
  recorded check calls; 0 differ). Their movement is the noise floor by construction.
- The hypothesis "the single-unit task returns to its iteration-1/2 level of 0.91-0.92" is
  falsified; the task's own errors are substitutions *between* listed units (gastroesophageal
  reflux/drug reaction, common cold/chicken pox, malaria/dengue, asthma/allergy,
  pneumonia/diabetes), all of which the branch was designed to prevent and none of which it
  touched.

**Takeaway.** The answer-count axis is exhausted: the solver already respects the count the
profile gives it, so stating the count again in three more places cannot pay. The loss that is
left is on the multi-unit corpus and it is one-sided — all 23 wrong questions there are
*missing-unit* errors; in 16 of them the missing unit is never named anywhere in the solver's own
text, and in the 7 where the check re-opens it the solver keeps its draft for a reason about the
corpus ("reference cases usually find only the main charge") rather than a fact of the question.
Iteration 12 works that channel: it renders the answer the draft would have if it carried the
candidate, and stops reporting the corpus's marginal answer width as advice.
