# Iteration 3 — considered_unit_audit (design note, pre-eval)

**Change.** The unit vocabulary is no longer presented as the thing to copy from, and the
verification call becomes an audit of the solver's own candidate set.

1. **Vocabulary as evidence.** The profile says the reference units are evidence about
   vocabulary, not a closed list: when the facts call for a unit that is not listed, the
   solver writes it itself, at the same level of specificity, and never substitutes a
   listed unit that merely looks related. The skill names the two reasons that are *not*
   factual reasons to set a unit aside ("the references never use it", "it is not listed").
2. **`check_answer(draft_answer, considered)`.** `considered` is the comma-separated list of
   candidate units the solver named while deciding, including the ones it set aside. Every
   candidate the draft does not contain comes back: one the references use arrives with the
   reference cases that answer it (chosen by similarity to this question, cut down to the
   sentences that line up with it); one the vocabulary does not list arrives explicitly as
   *not a reason to set it aside*. Candidates are ranked by head/tail relation to a unit of
   the draft, then unlisted ones, then the rest, capped at 3.
3. **Unit relationships.** `shared_edge` (longest head/tail two units share, on unit
   boundaries, so `flu` is not a form of `reflux`) and `affix_extension` drive three new
   notes: a submitted unit the references also use in a more specific form (with the
   elements those add), a submitted unit that extends a reference unit with text the
   references never use, and a submitted unit that extends an *element* of a reference unit.
4. **The check no longer argues for the nearest listed unit.** The old wording
   ("'X' is not a verbatim reference label. Closest reference labels: Y. Use the reference
   spelling exactly…") is what flipped iteration 2's one revised answer. Unlisted units are
   now nudged toward a listed spelling only at 0.85 similarity, and a clean check says that
   verbatim spelling is not evidence of completeness.
5. **The check happens.** A middleware hook fires once when the model reaches a final answer
   without ever calling `check_answer`, injects one reminder and jumps back to the model.
   In iteration 2 47 of 100 LawBench samples never called the tool, so without this the
   audit is a no-op for half the samples.

**Hypothesis.** Re-opening the candidates the solver itself named - with the reference cases
that answer each of them - and treating the reference vocabulary as evidence rather than a
closed list raises the mean validation score above the 0.558 of iteration 2, mainly by
converting dropped-but-correct units and near-miss substitutions into submitted ones,
without regressing the tasks that have no unit vocabulary.

**Falsifiers to look for in the results.**
- If the label task does not improve, the dropped candidates were rejected for factual
  reasons after all and the remaining errors are knowledge, not decision hygiene.
- If the score regresses, the audit is destabilising correct answers: the single-unit task
  (ceiling 0.92, 4 hard cases) would show it first, and on the multi-unit task the shape
  note would show it as spurious extra units on samples that were already right.
- If the free-form task loses, sentence-level evidence snippets are hiding the context that
  mattered and the excerpt has to be longer or kept in question order.
- If `check_answer` is still called in only half the samples, the middleware did not fire
  (`jump_to` unsupported on this graph) and the mechanism reduces to a prompt change.
