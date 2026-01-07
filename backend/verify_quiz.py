import sys
import os

# Ensure backend modules are found
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ml.train.quiz_gen import generate_quiz

text = "Software engineering is the systematic application of engineering approaches to the development of software."

print("Testing Quiz Gen:")
try:
    quiz = generate_quiz(text, difficulty="medium")
    print(quiz)
except Exception as e:
    print(f"Failed: {e}")
