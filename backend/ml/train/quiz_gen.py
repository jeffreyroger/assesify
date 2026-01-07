# quiz_gen.py
import re
import random
from typing import List, Dict, Any

# AI interaction helpers (Gemini client)
from ml.genai import GeminiClient
from ml.schemas import StructuredAnswer, QuizItem

def ai_generate_answer(question: str) -> str:
    """Generate a short textual answer for a question using the configured model."""
    try:
        client = GeminiClient()
        return client.generate_text(question)
    except Exception:
        return "Explanation available upon further review of course materials."

def _try_structured_answer(context: str, difficulty: str = "medium") -> dict:
    """Ask the model to return a structured question based on the context."""
    
    difficulty_guide = {
        "easy": "Focus on fundamental definitions and clear recall.",
        "medium": "Focus on conceptual understanding and cause-and-effect.",
        "hard": "Focus on application of principles and complex synthesis."
    }
    
    guide = difficulty_guide.get(difficulty.lower(), difficulty_guide["medium"])

    prompt = f"""You are an elite educational assessment expert. Generate a professional MCQ based on:
{context}

**Difficulty**: {difficulty.capitalize()}
**Objective**: {guide}

**MCQ STANDARDS**:
1. 100% Standalone (No "the text" references).
2. Concept-focused, professional, and clear.
3. 4 plausible distractors.

Return ONLY JSON:
{{
  "question": "...",
  "options": ["A", "B", "C", "D"],
  "correct_answer": "...",
  "answer": "Explanation...",
  "hint": "Hint..."
}}
"""
    client = GeminiClient()
    return client.generate_json(prompt)


def chunk_text(text: str, max_words: int = 100) -> List[str]:
    """Split text into chunks of at most `max_words` words."""
    words = text.split()
    chunks: List[str] = []
    for i in range(0, len(words), max_words):
        chunks.append(" ".join(words[i:i + max_words]))
    return chunks


def generate_quiz(text: str, difficulty: str = "medium", num_questions: int = 5) -> List[Dict[str, Any]]:
    """Generate a multi-question quiz with robust AI and Smart Fallback."""
    
    quiz_results = []
    
    # --- PHASE 1: AI ATTEMPT ---
    try:
        # We try to get the AI to generate the whole quiz at once for better variety/coherence
        client = GeminiClient()
        prompt = f"""You are an elite educational assessment expert. Create {num_questions} high-fidelity, professional multiple-choice questions for the following material:
        
{text[:2000]}

**UNCOMPROMISING STANDARDS**:
1. Every question must be 100% self-contained (STANDALONE).
2. NEVER refer to "the passage" or "the text".
3. Target {difficulty} difficulty level.
4. Return ONLY valid JSON in this format:
{{
  "quiz": [
    {{
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "...",
      "answer": "...",
      "hint": "..."
    }}
  ]
}}
"""
        resp = client.generate_json(prompt)
        if isinstance(resp, dict) and 'quiz' in resp:
            for item in resp['quiz']:
                # Basic normalization
                if 'choices' in item and 'options' not in item:
                    item['options'] = item.pop('choices')
                if 'question' in item and 'options' in item:
                    quiz_results.append(item)
            
            if len(quiz_results) >= num_questions:
                return quiz_results[:num_questions]
    except Exception as e:
        print(f"AI Quiz Generation failed (Quota/Error): {e}")

    # --- PHASE 2: SMART FALLBACK ENGINE (Varied & Distinct) ---
    # If AI fails or returns partial, fill with dynamic unique questions
    
    # Extract unique keywords (nouns/proper nouns)
    clean_text = re.sub(r'[^\w\s]', '', text)
    candidate_words = [w for w in clean_text.split() if len(w) > 6 and w.lower() not in ['discuss', 'example', 'process', 'result']]
    # Unique and shuffled
    unique_keywords = list(dict.fromkeys(candidate_words))
    random.shuffle(unique_keywords)
    
    templates = [
        {
            "q": "Which of the following best defines the primary role of {topic}?",
            "a": "{topic} represents a foundational concept used to structure understanding in this field.",
            "opt_gen": lambda t: [f"A fundamental defining mechanism of {t}", f"A secondary supportive element for {t}", "A historical framework", "An abstract theoretical model"]
        },
        {
            "q": "How is {topic} typically applied within practical scenarios mentioned in the material?",
            "a": "Practical application of {topic} focuses on operationalizing the core principles discussed.",
            "opt_gen": lambda t: [f"As a core operational component", f"As a metric for measuring {t}", "As a troubleshooting tool", "As a descriptive label"]
        },
        {
            "q": "What is the relationship between {topic} and the broader conceptual framework provided?",
            "a": "{topic} serves as a critical link between theoretical principles and their results.",
            "opt_gen": lambda t: [f"A critical link to results", f"An independent variable of {t}", "A localized exception", "A redundant classification"]
        },
        {
            "q": "Identify the key characteristic that distinguishes {topic} from traditional approaches.",
            "a": "{topic} introduces modern efficiencies or specialized views not found in legacy systems.",
            "opt_gen": lambda t: [f"Specialized modern efficiencies", f"A reliance on manual {t}", "Compatibility with outdated modes", "Universal applicability regardless of context"]
        }
    ]
    
    needed = num_questions - len(quiz_results)
    for i in range(needed):
        if not unique_keywords:
            unique_keywords = ["core principle", "primary function", "standardized model", "strategic approach"]
            
        topic = unique_keywords.pop(0)
        template = random.choice(templates)
        
        q_text = template["q"].format(topic=topic)
        explanation = template["a"].format(topic=topic)
        options = template["opt_gen"](topic)
        correct_answer = options[0]
        
        # Shuffle options so the correct one isn't always at index 0
        random.shuffle(options)
        
        quiz_results.append({
            "question": q_text,
            "answer": explanation,
            "options": options,
            "correct_answer": correct_answer,
            "hint": f"Think about the specific role of {topic} described."
        })
        
    return quiz_results[:num_questions]
