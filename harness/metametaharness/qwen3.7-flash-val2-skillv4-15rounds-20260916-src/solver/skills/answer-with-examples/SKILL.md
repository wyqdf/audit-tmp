1. Call `retrieve_examples` before answering.
2. If the examples do not cover the question, search the memory under `/harness/memory` yourself.
3. Match the wording, format and level of detail of the examples' answers, copying every
   item exactly as the examples write it — nothing added, dropped or reworded.
4. Reply as JSON: `{"reasoning": "[your reasoning]", "final_answer": "[your answer]"}`
