from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from typing import Dict, List, Optional

from ..config import Settings
from ..models import Creative, VariantProposal, EmbeddingVector
from ..utils.logging import get_logger


log = get_logger(__name__)


def _have_openai(settings: Settings) -> bool:
    if not settings.openai_api_key:
        return False
    try:
        import openai  # noqa: F401
        return True
    except Exception:
        return False


def _get_client(settings: Settings):
    from openai import OpenAI
    return OpenAI(api_key=settings.openai_api_key)


def _heuristic_score(creative: Creative) -> Dict[str, float | int | List[str]]:
    text = (creative.text or "") + " " + (creative.hook or "") + " " + (creative.overlay_text or "")
    text = text.lower()
    length = len(text)
    # Simple heuristics: presence of CTA words and length balance
    cta_words = ["buy", "shop", "learn", "save", "free", "now"]
    cta_score = sum(1 for w in cta_words if w in text) / max(1, len(cta_words))
    ideal_len = 160
    len_score = max(0.0, 1.0 - abs(length - ideal_len) / ideal_len)
    hook_score = min(1.0, cta_score * 0.6 + len_score * 0.4)
    overlay_score = min(1.0, (0.3 + cta_score * 0.7)) if creative.overlay_text else 0.4
    framing_score = 0.6 if creative.frame_desc else 0.5
    tags = []
    if "% off" in text or "sale" in text:
        tags.append("promo")
    if any(w in text for w in ["limited", "today", "now", "hurry"]):
        tags.append("urgency")
    return {
        "hook": round(hook_score * 100),
        "overlay": round(overlay_score * 100),
        "framing": round(framing_score * 100),
        "tags": tags,
    }


def score_creative(settings: Settings, creative: Creative) -> Dict[str, object]:
    if not _have_openai(settings):
        return _heuristic_score(creative)
    try:
        client = _get_client(settings)
        system = (
            "You are a performance creative analyst. Score the effectiveness of hooks, framing, and text overlays "
            "for paid social ads on a 0-100 scale. Return JSON with keys: hook, overlay, framing, tags[]"
        )
        user = (
            f"Platform: {creative.platform}\n"
            f"Title: {creative.title}\n"
            f"Text: {creative.text}\n"
            f"Hook: {creative.hook}\n"
            f"Overlay: {creative.overlay_text}\n"
            f"Frame: {creative.frame_desc}\n"
        )
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = completion.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except Exception:
            log.warning("LLM returned non-JSON; falling back to heuristic")
            return _heuristic_score(creative)
    except Exception as e:
        log.warning("OpenAI error; falling back to heuristic: %s", e)
        return _heuristic_score(creative)


def generate_variants(
    settings: Settings,
    creative: Creative,
    brand_guidelines: Optional[str] = None,
    n_variants: int = 3,
) -> List[VariantProposal]:
    if not _have_openai(settings):
        # Simple templated variants
        base = creative.hook or creative.text or "High-quality, affordable."
        seeds = ["value-first", "problem-agitate-solve", "social-proof"]
        out: List[VariantProposal] = []
        for i in range(n_variants):
            style = seeds[i % len(seeds)]
            out.append(
                VariantProposal(
                    creative_id=creative.creative_id,
                    idea_title=f"Variant ({style})",
                    new_hook=f"{base} — {style} angle",
                    new_overlay_text="Limited time — Shop now",
                    new_body_text=(creative.text or "").strip()[:140],
                    rationale=f"Heuristic variant emphasizing {style} angle.",
                    compliance_flags=[],
                    estimated_uplift=0.05,
                )
            )
        return out

    try:
        client = _get_client(settings)
        sys = (
            "You are a compliant creative copy generator for paid social/search. Generate N variant concepts with "
            "hooks and overlays that align with brand guidelines. Return strict JSON list of objects with keys: "
            "idea_title, new_hook, new_overlay_text, new_body_text, rationale."
        )
        user = (
            f"Creative:\n{json.dumps(asdict(creative), ensure_ascii=False)}\n\n"
            f"Brand guidelines (optional):\n{brand_guidelines or 'None'}\n\n"
            f"N variants: {n_variants}"
        )
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.6,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
        )
        content = completion.choices[0].message.content or "[]"
        data = json.loads(content)
        out: List[VariantProposal] = []
        for item in data:
            out.append(
                VariantProposal(
                    creative_id=creative.creative_id,
                    idea_title=item.get("idea_title") or "Variant",
                    new_hook=item.get("new_hook"),
                    new_overlay_text=item.get("new_overlay_text"),
                    new_body_text=item.get("new_body_text"),
                    rationale=item.get("rationale"),
                )
            )
        return out
    except Exception as e:
        log.warning("OpenAI error in generate_variants; using heuristic: %s", e)
        return generate_variants(Settings(openai_api_key=None), creative, brand_guidelines, n_variants)


def embed_text(settings: Settings, text: str, model: str = "text-embedding-3-small") -> EmbeddingVector:
    if not _have_openai(settings):
        # Deterministic pseudo-embedding for offline mode
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Map to 64 floats in [0,1)
        vec = [b / 255.0 for b in h[:64]]
        return EmbeddingVector(creative_id="", vector=vec, model=model)
    try:
        client = _get_client(settings)
        resp = client.embeddings.create(model=model, input=text)
        vec = resp.data[0].embedding
        return EmbeddingVector(creative_id="", vector=vec, model=model)
    except Exception as e:
        log.warning("OpenAI embedding error; using pseudo: %s", e)
        return embed_text(Settings(openai_api_key=None), text, model)

