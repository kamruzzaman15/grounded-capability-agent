"""Ollama chat client plus a tolerant JSON extractor.

The generator and the reviewer are separate models, and should be from
different families so the reviewer's entailment judgment is independent of the
writer. Defaults are current small open-weight picks; any Ollama model works,
and the choice is env-driven. See the README "Models" section.

Pick by JSON reliability, not benchmark rank: every step here routes through
extract_json, so a model that emits malformed JSON breaks the loop.
"""

import os
import re
import json
import time

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "qwen3:8b")
REVIEWER_MODEL = os.getenv("REVIEWER_MODEL", "llama3.1:8b")


def chat(messages, model=None, temperature=0.0, retries=2):
    """Call Ollama /api/chat and return the assistant text. Retries on
    transient failure, raises if every attempt fails.
    """
    model = model or GENERATOR_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=240
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries + 1} tries: {last_err}")


def extract_json(text):
    """Best-effort parse of the first JSON object or array in a string. Handles
    code fences and leading prose (including a thinking model's preamble).
    Returns a dict/list or None.
    """
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    for end in range(len(text), start, -1):
        try:
            return json.loads(text[start:end])
        except Exception:
            continue
    return None
