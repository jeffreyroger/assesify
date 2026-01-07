import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.abspath("."))

from ml.train.quiz_gen import generate_quiz

text = """
Photosynthesis is a process used by plants and other organisms to convert light energy into chemical energy that, through cellular respiration, can later be released to fuel the organism's activities. This chemical energy is stored in carbohydrate molecules, such as sugars and starches, which are synthesized from carbon dioxide and water. In most cases, oxygen is also released as a waste product. Most plants, algae, and cyanobacteria perform photosynthesis; such organisms are called photoautotrophs. Photosynthesis is largely responsible for producing and maintaining the oxygen content of the Earth's atmosphere, and supplies most of the energy necessary for life on Earth.
"""

print("--- MULTI-QUESTION GENERATION TEST ---")
quiz = generate_quiz(text, num_questions=5)

print(f"Total Questions Generated: {len(quiz)}\n")

for i, q in enumerate(quiz):
    print(f"--- Question {i+1} ---")
    print(f"Q: {q['question']}")
    print(f"Options: {', '.join(q['options'])}")
    print(f"Correct Answer: {q['correct_answer']}")
    print(f"Explanation: {q['answer']}")
    print("-" * 20)
    print("\n")
