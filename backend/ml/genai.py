"""Simple Gemini (GenAI) client wrapper for local usage and tests."""
from __future__ import annotations

import os
import json
import re
import requests
from typing import Any, Optional

# Try to import Config, handle failure gracefully if run as script
try:
    from app.core.config import Config
except ImportError:
    Config = None

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # Determine API Key with a very strong fallback chain
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key and Config:
             self.api_key = getattr(Config, "GEMINI_API_KEY", "AIzaSyAALpHF3WID0SwotxGpEt0G9PeDBdjc0gY")
        
        # Hard fallback to the key provided by the user if all else fails
        if not self.api_key:
            self.api_key = "AIzaSyAALpHF3WID0SwotxGpEt0G9PeDBdjc0gY"
            
        # Standard model name for current library
        self.model_name = "gemini-1.5-flash"

    def generate_text(self, prompt: str, **kwargs) -> str:
        """Call Gemini API via direct REST request to avoid library versioning conflicts."""
        # We try v1 and v1beta as some keys are restricted to specific versions
        endpoints = [
            f"https://generativelanguage.googleapis.com/v1/models/{self.model_name}:generateContent?key={self.api_key}",
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        ]
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
        }
        
        last_err = None
        for url in endpoints:
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=15)
                if response.status_code == 429:
                    raise RuntimeError("Gemini API Quota Exhausted (429). Please check your billing or usage limits.")
                response.raise_for_status()
                data = response.json()
                
                if 'candidates' in data and data['candidates']:
                    return data['candidates'][0]['content']['parts'][0]['text']
            except Exception as e:
                last_err = e
                continue
        
        raise RuntimeError(f"Gemini generation failed: {last_err}")

    def generate_json(self, prompt: str, **kwargs) -> dict:
        text = self.generate_text(prompt, **kwargs)
        try:
            # Clean markdown code blocks
            clean_text = text.strip()
            if "```" in clean_text:
                clean_text = clean_text.split("```")[-1].split("```")[0]
                if clean_text.startswith("json"): clean_text = clean_text[4:]
                clean_text = clean_text.strip()
            
            return json.loads(clean_text)
        except Exception:
            m = re.search(r"(\{.*\})", text, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        raise ValueError(f"Could not parse JSON from Gemini response.")
