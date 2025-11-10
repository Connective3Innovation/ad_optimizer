from __future__ import annotations

import pandas as pd
import numpy as np
from ..models import FatigueReport


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def detect_fatigue(
    perf: pd.DataFrame,
    ctr_drop_threshold: float = 0.4,
    roas_drop_threshold: float = 0.3,
    exposure_threshold: float = 0.6,
) -> pd.DataFrame:
    if perf.empty:
        return pd.DataFrame(columns=[
            "creative_id", "status", "drop_from_peak_ctr", "drop_from_peak_roas", "exposure_index", "notes"
        ])

    df = perf.copy()
    # Ensure dtypes
    df["dt"] = pd.to_datetime(df["dt"]).dt.date
    df = df.sort_values(["creative_id", "dt"])  # ensure order
    df["ctr"] = df.eval("clicks / impressions").replace([np.inf, -np.inf], 0.0).fillna(0.0)
    df["roas"] = df.apply(lambda r: _safe_div(r.get("revenue", 0.0), r.get("spend", 0.0)), axis=1)

    # Rolling peaks per creative
    df["peak_ctr"] = df.groupby("creative_id")["ctr"].cummax()
    df["peak_roas"] = df.groupby("creative_id")["roas"].cummax()
    # Current is the last value per creative
    last = df.groupby("creative_id").tail(1).set_index("creative_id")

    drop_ctr = (last["peak_ctr"] - last["ctr"]).clip(lower=0)
    drop_ctr_ratio = (drop_ctr / last["peak_ctr"]).fillna(0.0)
    drop_roas = (last["peak_roas"] - last["roas"]).clip(lower=0)
    drop_roas_ratio = (drop_roas / last["peak_roas"]).fillna(0.0)

    # Exposure index: normalized cumulative impressions per creative
    exposure = df.groupby("creative_id")["impressions"].sum()
    if exposure.max() > 0:
        exposure_ix = (exposure / exposure.max()).reindex(last.index).fillna(0.0)
    else:
        exposure_ix = pd.Series(0.0, index=last.index)

    status = []
    notes = []
    for cid in last.index:
        dctr = float(drop_ctr_ratio.loc[cid])
        droas = float(drop_roas_ratio.loc[cid])
        expi = float(exposure_ix.loc[cid])
        if (dctr >= ctr_drop_threshold or droas >= roas_drop_threshold) and expi >= exposure_threshold:
            status.append("fatigued")
            notes.append("Significant drop from peak with high exposure")
        elif dctr >= (ctr_drop_threshold * 0.5) or droas >= (roas_drop_threshold * 0.5):
            status.append("fatigue-risk")
            notes.append("Moderate drop from peak; monitor")
        else:
            status.append("fresh")
            notes.append("Within normal variance")

    # Aggregate performance metrics
    agg_metrics = df.groupby("creative_id").agg({
        "impressions": "sum",
        "clicks": "sum",
        "spend": "sum",
        "conversions": "sum",
        "revenue": "sum"
    }).reindex(last.index)

    # Get campaign_name if available (take first value per creative since it should be the same)
    campaign_name_series = None
    if "campaign_name" in df.columns:
        campaign_name_series = df.groupby("creative_id")["campaign_name"].first().reindex(last.index)

    # Calculate CTR and ROAS
    agg_metrics["ctr"] = (agg_metrics["clicks"] / agg_metrics["impressions"] * 100).fillna(0).round(2)
    agg_metrics["roas"] = (agg_metrics["revenue"] / agg_metrics["spend"]).replace([np.inf, -np.inf], 0.0).fillna(0).round(2)

    out = pd.DataFrame({
        "creative_id": last.index,
        "status": status,
        "impressions": agg_metrics["impressions"].values.astype(int),
        "clicks": agg_metrics["clicks"].values.astype(int),
        "ctr": agg_metrics["ctr"].values,
        "conversions": agg_metrics["conversions"].values.round(1),
        "spend": agg_metrics["spend"].values.round(2),
        "revenue": agg_metrics["revenue"].values.round(2),
        "drop_from_peak_ctr": drop_ctr_ratio.values.round(3),
        "drop_from_peak_roas": drop_roas_ratio.values.round(3),
        "exposure_index": exposure_ix.values.round(3),
        "notes": notes,
    })

    # Add campaign_name if available
    if campaign_name_series is not None:
        out["campaign_name"] = campaign_name_series.values

    return out

