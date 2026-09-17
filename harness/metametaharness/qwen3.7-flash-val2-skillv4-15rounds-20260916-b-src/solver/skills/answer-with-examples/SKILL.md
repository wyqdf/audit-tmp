1. Call `retrieve_examples` before answering. It returns training examples ordered by closeness to the current problem, the closest one first.
2. Follow the closest examples first: when they disagree with the later ones about the answer or its format, trust the earlier ones.
3. An example's answer is an exact string, not a description: when an example answers the question you are solving, use that answer's spelling character for character — the same characters, punctuation and parts — rather than writing the same answer your own way.
[[memory_step]]
[[check_step]]
6. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
