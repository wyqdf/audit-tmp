1. Call `retrieve_examples` before answering.
2. If the examples do not cover the question, ask the memory with `search_memory` for the cases closest to what you are unsure about.
3. Match the wording, format and level of detail of the examples' answers.
4. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
