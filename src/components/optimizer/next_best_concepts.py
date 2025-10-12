from __future__ import annotations

from typing import List, Optional
import pandas as pd

from ..config import Settings
from ..models import Creative, VariantProposal
from ..llm.openai_client import generate_variants, embed_text


def _top_performers(perf: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    if perf.empty:
        return perf
    df = perf.copy()
    # Simple scoring: conversions prioritized then ROAS
    df["roas"] = df.apply(lambda r: (r.get("revenue", 0.0) / r.get("spend", 0.0)) if r.get("spend", 0.0) else 0.0, axis=1)
    agg = df.groupby("creative_id").agg({"conversions": "sum", "revenue": "sum", "spend": "sum"}).reset_index()
    agg["roas"] = agg.apply(lambda r: (r.revenue / r.spend) if r.spend else 0.0, axis=1)
    agg = agg.sort_values(["conversions", "roas"], ascending=[False, False]).head(top_k)
    return agg


def propose_next_best_concepts(
    settings: Settings,
    creative: Creative,
    all_creatives: pd.DataFrame,
    perf: pd.DataFrame,
    brand_guidelines: Optional[str] = None,
    n: int = 3,
) -> List[VariantProposal]:
    # Optionally use embeddings to bias toward winning angles
    winners = _top_performers(perf, top_k=5)
    _ = [embed_text(settings, (creative.text or "") + " " + (creative.hook or "")) for _ in range(min(3, len(winners)))]
    # For MVP: call LLM to generate structured variants
    proposals = generate_variants(settings, creative, brand_guidelines, n)
    return proposals

