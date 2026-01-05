"""Simple Gemini (GenAI) client wrapper for local usage and tests.

This wrapper tries to use the Google GenAI (`google.genai`) client if available and
exposes two convenience methods:
- generate_text(prompt): returns raw text result from the model
- generate_json(prompt): attempts to parse JSON from the model's output

The wrapper is intentionally small and resilient so tests can mock the methods easily.
"""
from __future__ import annotations

import os
import json
import re
from typing import Any, Optional


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client: Optional[Any] = None

    def _get_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        try:
            from google import genai  # type: ignore

            if not self.api_key:
                # Client library might work without explicit key if running in GCP
                self._client = genai.Client()
            else:
                self._client = genai.Client(api_key=self.api_key)
        except Exception:
            self._client = None
        return self._client

    def _extract_text_from_response(self, resp: Any) -> str:
        # The google-genai SDK uses .text for the result
        if hasattr(resp, "text"):
            return resp.text
        # Fallback for complex response objects
        try:
            return resp.candidates[0].content.parts[0].text
        except:
            return str(resp)

    def generate_text(self, prompt: str, **kwargs) -> str:
        """Return model text for the prompt.

        Raises: RuntimeError if no client is available.
        """
        client = self._get_client()
        if client is None:
            raise RuntimeError("No Gemini client available (missing dependency or API key)")

        try:
            # model name should not have 'models/' prefix for the SDK call
            m = self.model
            if m.startswith("models/"):
                m = m[7:]
            
            resp = client.models.generate_content(model=m, contents=prompt, **kwargs)
            return self._extract_text_from_response(resp).strip()
        except Exception as e:
            raise RuntimeError(f"Gemini generation failed: {e}")

    def generate_json(self, prompt: str, **kwargs) -> dict:
        """Request a JSON object response and return parsed JSON.

        If raw response is not valid JSON, attempt to extract a JSON object from the text.
        Raises ValueError if JSON cannot be recovered.
        """
        text = self.generate_text(prompt, **kwargs)
        try:
            return json.loads(text)
        except Exception:
            # Try to extract the first {...} block
            m = re.search(r"(\{.*\})", text, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        raise ValueError("Could not parse JSON from model response")
