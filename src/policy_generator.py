"""
src/policy_generator.py (Gemini-only, final updated version)

Gemini-native policy generator with deterministic fallback.

This version FIXES the '404 model not found' issues by using correct model names:
    - gemini-pro
    - gemini-1.5-flash
    - gemini-1.5-pro
    - gemini-1.5-flash-8b

Usage:
- generate_policy_from_chunks(chunks, source_doc, use_model=False)
- save_policy_json(policy_obj, path)
"""

import os
import json
import uuid
import datetime
import re
import time
from typing import List, Dict, Any, Optional

DEFAULT_CONFIDENCE = 0.8

# -------------------------------------------------------
#  FIX → Use correct model names (NO "models/" prefix)
# -------------------------------------------------------
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

# -------------------------------------------------------
# Utility helpers
# -------------------------------------------------------
def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _safe_float(x, default=1.0):
    try:
        return float(x)
    except Exception:
        return default

# -------------------------------------------------------
# JSON extraction helper
# -------------------------------------------------------
def _extract_json_from_text(text: str) -> Optional[dict]:
    """Extract the first JSON object from text."""
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except:
        pass

    m = re.search(r"(\{[\s\S]*\})", text)
    if not m:
        return None

    candidate = m.group(1)

    for end in range(len(candidate), 0, -1):
        try:
            parsed = json.loads(candidate[:end])
            if isinstance(parsed, dict):
                return parsed
        except:
            continue

    return None

# -------------------------------------------------------
# Deterministic offline fallback (no model)
# -------------------------------------------------------
def _deterministic_policy_from_chunks(chunks: List[Dict[str, Any]], source_doc: str) -> Dict[str, Any]:
    """Heuristic risk-policy generator used when Gemini fails."""
    rules = []

    def add_rule(clause_name, policy_rule, explanation, severity, importance, recommended_fix, citation, confidence=DEFAULT_CONFIDENCE):
        rules.append({
            "rule_id": uuid.uuid4().hex[:8],
            "clause_name": clause_name,
            "policy_rule": policy_rule,
            "explanation": explanation,
            "severity": severity,
            "importance": importance,
            "examples": [],
            "recommended_fix": recommended_fix,
            "citation": citation,
            "confidence": confidence
        })

    full_text = "\n\n".join(c.get("text", "") for c in chunks).lower()

    # --- Confidentiality ---
    m = re.search(r'confidenti.*?(\d+)\s*years?', full_text)
    if m:
        years = int(m.group(1))
        if years < 3:
            add_rule("Confidentiality Term","Confidentiality obligations must last for at least 3 years.",
                      f"Found confidentiality duration {years} years.",
                      "MEDIUM",1.0,"Confidentiality shall last 3 years.","SECTION",0.9)
        else:
            add_rule("Confidentiality Term","Confidentiality obligations must last for at least 3 years.",
                      f"Found confidentiality {years} years (OK).",
                      "LOW",0.8,"Confidentiality shall last 3 years.","SECTION",0.9)
    else:
        add_rule("Confidentiality Term","Confidentiality obligations must last for at least 3 years.",
                 "No confidentiality duration found.","MEDIUM",1.0,
                 "Confidentiality shall last 3 years.","SECTION",0.75)

    # --- Liability Cap ---
    if "liability" in full_text:
        if "1.5" in full_text or "1.5x" in full_text:
            add_rule("Liability Cap","Liability cap must not exceed 1.5x the total fees paid.",
                     "Liability seems compliant.","LOW",1.0,"Liability limited to 1.5x fees.","SECTION",0.85)
        else:
            add_rule("Liability Cap","Liability cap must not exceed 1.5x total fees.",
                     "No explicit numeric cap found.","HIGH",1.5,"Liability limited to 1.5x fees.","SECTION",0.8)
    else:
        add_rule("Liability Cap","Liability cap must not exceed 1.5x total fees.",
                 "No liability clause found.","HIGH",1.5,"Liability limited to 1.5x fees.","SECTION",0.75)

    # --- Data Sale ---
    if "sell" in full_text or "commercial" in full_text:
        add_rule("Data Sale Prohibition","Provider must not sell Client Data.",
                 "Data may be sold.","HIGH",1.5,
                 "Provider shall not sell client data.","SECTION",0.9)
    else:
        add_rule("Data Sale Prohibition","Provider must not sell Client Data.",
                 "No data sale found.","LOW",0.8,
                 "Provider shall not sell client data.","SECTION",0.7)

    # --- Security ---
    if "encrypt" in full_text or "security" in full_text:
        add_rule("Security Responsibility","Provider must protect client data.",
                 "Some security text found.","LOW",1.0,"Provider must secure data.","SECTION",0.8)
    else:
        add_rule("Security Responsibility","Provider must protect client data.",
                 "No security terms found.","HIGH",1.5,"Provider must secure data.","SECTION",0.85)

    # --- Governing Law ---
    if "governed by" in full_text:
        add_rule("Governing Law Validity","Agreement must specify valid jurisdiction.",
                 "Governing law exists.","LOW",1.0,"Use proper jurisdiction.","SECTION",0.8)
    else:
        add_rule("Governing Law Validity","Agreement must specify valid jurisdiction.",
                 "No governing law found.","HIGH",1.5,"Agreement must specify governing law.","SECTION",0.85)

    return {
        "policy_id": f"POLICY-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "source_document": source_doc,
        "generated_at": _now_iso(),
        "rules": rules,
        "summary": "Generated using deterministic fallback (Gemini unavailable).",
        "metadata": {"generator": "fallback"}
    }

# -------------------------------------------------------
# Gemini call (FINAL FIXED VERSION)
# -------------------------------------------------------
def _call_gemini(prompt: str, max_retries: int = 3) -> str:
    """
    Dynamically select a supported Gemini model and call it.
    Tries, in order:
      - genai.GenerativeModel(...).generate_content (with application/json)
      - genai.generate_content(...)
      - genai.generate(...)
    Falls back to deterministic behavior via exceptions so caller can handle it.
    """
    try:
        import google.generativeai as genai
    except Exception as e:
        raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai") from e

    # ensure key loaded
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in environment.")
    genai.configure(api_key=key)

    # Try to discover usable models
    try:
        available = genai.list_models()
    except Exception as e:
        # If listing fails, fall back to environment model name or default
        available = []
        print("⚠ Warning: list_models() failed:", e)

    # Build a list of candidate model names (from env var + discovered models)
    candidates = []
    env_model = os.getenv("GEMINI_MODEL")
    if env_model:
        candidates.append(env_model)
    # common safe defaults (no 'models/' prefix)
    candidates.extend(["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.5-flash-8b", "gemini-pro", "gemini"])
    # add names discovered from API (prefer explicit .name attributes)
    for m in available:
        try:
            name = getattr(m, "name", None) or getattr(m, "model", None) or str(m)
            if name and name not in candidates:
                candidates.append(name)
        except Exception:
            continue

    # Deduplicate while preserving order
    seen = set()
    candidates = [c for c in candidates if c and not (c in seen or seen.add(c))]

    last_err = None
    for model_name in candidates:
        for attempt in range(max_retries):
            try:
                print(f"➡ Trying model: {model_name} (attempt {attempt+1}/{max_retries})")
                # Preferred path: modern GenerativeModel wrapper
                if hasattr(genai, "GenerativeModel"):
                    try:
                        gm = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})
                        out = gm.generate_content(prompt)
                        if hasattr(out, "candidates") and out.candidates:
                            cand = out.candidates[0]
                            content = getattr(cand, "content", None) or getattr(cand, "text", None)
                            if isinstance(content, (dict, list)):
                                return json.dumps(content)
                            if isinstance(content, str):
                                return content
                        return str(out)
                    except Exception as e_gm:
                        # If the model doesn't support generate_content or model is invalid, try other fallbacks
                        last_err = e_gm
                        errstr = str(e_gm).lower()
                        if "not found" in errstr or "404" in errstr:
                            print(f"   ✖ Model {model_name} not found or unsupported for this key.")
                            break  # try next model_name
                        if "mime" in errstr or "mimetype" in errstr:
                            # try text/plain instead
                            try:
                                gm2 = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "text/plain"})
                                out2 = gm2.generate_content(prompt)
                                if hasattr(out2, "candidates") and out2.candidates:
                                    cand2 = out2.candidates[0]
                                    content2 = getattr(cand2, "content", None) or getattr(cand2, "text", None)
                                    if isinstance(content2, (dict, list)):
                                        return json.dumps(content2)
                                    if isinstance(content2, str):
                                        return content2
                                return str(out2)
                            except Exception as e2:
                                last_err = e2
                                break
                        # otherwise retry with backoff
                        time.sleep(1.0 * (2 ** attempt))
                        continue

                # Secondary: genai.generate_content function (older SDK)
                if hasattr(genai, "generate_content"):
                    try:
                        out = genai.generate_content(model=model_name, prompt=prompt, response_mime_type="application/json")
                        if hasattr(out, "candidates") and out.candidates:
                            cand = out.candidates[0]
                            content = getattr(cand, "content", None) or getattr(cand, "text", None)
                            if isinstance(content, (dict, list)):
                                return json.dumps(content)
                            if isinstance(content, str):
                                return content
                        return str(out)
                    except Exception as e_gc:
                        last_err = e_gc
                        errstr = str(e_gc).lower()
                        if "not found" in errstr or "404" in errstr:
                            print(f"   ✖ Model {model_name} not found for generate_content.")
                            break
                        if "mime" in errstr:
                            # try text/plain
                            try:
                                out2 = genai.generate_content(model=model_name, prompt=prompt, response_mime_type="text/plain")
                                if hasattr(out2, "candidates") and out2.candidates:
                                    cand2 = out2.candidates[0]
                                    content2 = getattr(cand2, "content", None) or getattr(cand2, "text", None)
                                    if isinstance(content2, (dict, list)):
                                        return json.dumps(content2)
                                    if isinstance(content2, str):
                                        return content2
                                return str(out2)
                            except Exception as e2:
                                last_err = e2
                                break
                        time.sleep(1.0 * (2 ** attempt))
                        continue

                # Tertiary: older .generate API
                if hasattr(genai, "generate"):
                    try:
                        out = genai.generate(prompt=prompt, model=model_name)
                        if hasattr(out, "candidates") and out.candidates:
                            cand = out.candidates[0]
                            txt = getattr(cand, "content", None) or getattr(cand, "text", None)
                            if isinstance(txt, str):
                                return txt
                        return str(out)
                    except Exception as e_gen:
                        last_err = e_gen
                        errstr = str(e_gen).lower()
                        if "not found" in errstr or "404" in errstr:
                            print(f"   ✖ Model {model_name} not found for generate.")
                            break
                        time.sleep(1.0 * (2 ** attempt))
                        continue

                # If we reached here, couldn't call any method on genai for this model; continue to next
                break

            except Exception as outer_e:
                last_err = outer_e
                # small backoff then retry
                time.sleep(1.0 * (2 ** attempt))
                continue

    # If nothing returned by now, raise helpful error including last exception and candidate list
    candidate_list = ", ".join(candidates)
    raise RuntimeError(f"No usable Gemini model found among candidates: {candidate_list}. Last error: {last_err}")

# -------------------------------------------------------
# Entry point for generator
# -------------------------------------------------------
def generate_policy_from_chunks(chunks, source_doc, use_model=False, top_k=5):
    """Generate full policy JSON using Gemini or fallback."""
    context = "\n\n---\n\n".join(c["text"] for c in chunks[:top_k])

    prompt = f"""
You are a legal policy generator. Produce STRICT JSON ONLY.

Schema:
{{
  "policy_id": "...",
  "source_document": "...",
  "generated_at": "...",
  "rules": [
    {{
      "rule_id": "...",
      "clause_name": "...",
      "policy_rule": "...",
      "explanation": "...",
      "severity": "LOW|MEDIUM|HIGH",
      "importance": 1.0,
      "examples": [],
      "recommended_fix": "...",
      "citation": "...",
      "confidence": 0.85
    }}
  ],
  "summary": "...",
  "metadata": {{ "generator": "gemini" }}
}}

Contract excerpts:
{context}

Return ONLY valid JSON.
"""

    if use_model:
        try:
            raw = _call_gemini(prompt)
            parsed = _extract_json_from_text(raw)

            if parsed:
                parsed.setdefault("policy_id", f"POLICY-{uuid.uuid4().hex[:8]}")
                parsed.setdefault("source_document", source_doc)
                parsed.setdefault("generated_at", _now_iso())
                parsed.setdefault("metadata", {"generator": "gemini"})

                return parsed

            print("⚠ Gemini returned non-JSON. Falling back.")
        except Exception as e:
            print("Model failed. Falling back:", e)

    return _deterministic_policy_from_chunks(chunks, source_doc)

# -------------------------------------------------------
# Save output
# -------------------------------------------------------
def save_policy_json(policy_obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(policy_obj, f, indent=2)
