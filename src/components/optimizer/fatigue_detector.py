from __future__ import annotations

from datetime import timedelta
import pandas as pd
import numpy as np
RECENT_WINDOW_DAYS = 7
BASELINE_WINDOW_DAYS = 30
MIN_RECENT_IMPRESSIONS = 500
FATIGUE_THRESHOLD = 0.5
RISK_THRESHOLD = 0.3


def _relative_drop(recent: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return max((baseline - recent) / baseline, 0.0)


def _relative_increase(recent: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return max((recent - baseline) / baseline, 0.0)


def _aggregate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "impressions", "clicks", "conversions", "spend", "revenue",
            "ctr", "cvr", "roas", "cpa", "cpc"
        ])

    agg = df.groupby("creative_id").agg({
        "impressions": "sum",
        "clicks": "sum",
        "conversions": "sum",
        "spend": "sum",
        "revenue": "sum"
    })

    agg["ctr"] = (agg["clicks"] / agg["impressions"]).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    agg["cvr"] = (agg["conversions"] / agg["clicks"]).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    agg["roas"] = (agg["revenue"] / agg["spend"]).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    agg["cpa"] = (agg["spend"] / agg["conversions"]).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    agg["cpc"] = (agg["spend"] / agg["clicks"]).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return agg


def _compose_notes(metrics: dict) -> str:
    drivers = []
    if metrics["ctr_drop"] >= 0.25:
        drivers.append("CTR down")
    if metrics["cvr_drop"] >= 0.2:
        drivers.append("CVR down")
    if metrics["roas_drop"] >= 0.2:
        drivers.append("ROAS down")
    if metrics["cpa_increase"] >= 0.2:
        drivers.append("CPA up")
    if metrics["cpc_increase"] >= 0.2:
        drivers.append("CPC up")
    if not drivers:
        return "Performance stable"
    return ", ".join(drivers)


def detect_fatigue(
    perf: pd.DataFrame,
) -> pd.DataFrame:
    if perf.empty:
        return pd.DataFrame(columns=[
            "creative_id", "status", "fatigue_score", "ctr_drop", "cvr_drop",
            "roas_drop", "cpa_increase", "cpc_increase", "notes"
        ])

    df = perf.copy()
    df["dt"] = pd.to_datetime(df["dt"]).dt.date
    df = df.sort_values(["creative_id", "dt"])

    max_date = df["dt"].max()
    recent_cutoff = max_date - timedelta(days=RECENT_WINDOW_DAYS - 1)
    baseline_cutoff = max_date - timedelta(days=BASELINE_WINDOW_DAYS - 1)

    recent_df = df[df["dt"] >= recent_cutoff]
    baseline_df = df[df["dt"] >= baseline_cutoff]
    if baseline_df.empty:
        baseline_df = df.copy()

    total_metrics = _aggregate_metrics(df)
    recent_metrics = _aggregate_metrics(recent_df).add_suffix("_7d")
    baseline_metrics = _aggregate_metrics(baseline_df).add_suffix("_30d")

    combined = (
        total_metrics
        .join(recent_metrics, how="left")
        .join(baseline_metrics, how="left")
        .fillna(0.0)
    )

    status = []
    notes = []
    ctr_drop = []
    cvr_drop = []
    roas_drop = []
    cpa_increase = []
    cpc_increase = []
    fatigue_scores = []

    for cid, row in combined.iterrows():
        ctr_d = _relative_drop(row.get("ctr_7d", 0.0), row.get("ctr_30d", 0.0))
        cvr_d = _relative_drop(row.get("cvr_7d", 0.0), row.get("cvr_30d", 0.0))
        roas_d = _relative_drop(row.get("roas_7d", 0.0), row.get("roas_30d", 0.0))
        cpa_inc = _relative_increase(row.get("cpa_7d", 0.0), row.get("cpa_30d", 0.0))
        cpc_inc = _relative_increase(row.get("cpc_7d", 0.0), row.get("cpc_30d", 0.0))

        ctr_drop.append(round(ctr_d, 3))
        cvr_drop.append(round(cvr_d, 3))
        roas_drop.append(round(roas_d, 3))
        cpa_increase.append(round(cpa_inc, 3))
        cpc_increase.append(round(cpc_inc, 3))

        score = (
            0.35 * ctr_d +
            0.25 * cvr_d +
            0.25 * roas_d +
            0.10 * cpa_inc +
            0.05 * cpc_inc
        )
        fatigue_scores.append(round(score, 3))

        recent_impr = row.get("impressions_7d", 0.0)
        if recent_impr < MIN_RECENT_IMPRESSIONS:
            status.append("fresh")
            notes.append(f"Insufficient recent volume (<{MIN_RECENT_IMPRESSIONS} impressions)")
            continue

        if score >= FATIGUE_THRESHOLD:
            status.append("fatigued")
        elif score >= RISK_THRESHOLD:
            status.append("fatigue-risk")
        else:
            status.append("fresh")

        notes.append(_compose_notes({
            "ctr_drop": ctr_d,
            "cvr_drop": cvr_d,
            "roas_drop": roas_d,
            "cpa_increase": cpa_inc,
            "cpc_increase": cpc_inc
        }))

    combined = combined.reset_index()
    combined["status"] = status
    combined["ctr_drop"] = ctr_drop
    combined["cvr_drop"] = cvr_drop
    combined["roas_drop"] = roas_drop
    combined["cpa_increase"] = cpa_increase
    combined["cpc_increase"] = cpc_increase
    combined["fatigue_score"] = fatigue_scores
    combined["notes"] = notes

    combined["ctr"] = (combined["ctr"] * 100).round(2)
    combined["ctr_7d"] = (combined["ctr_7d"] * 100).round(2)
    combined["ctr_30d"] = (combined["ctr_30d"] * 100).round(2)
    combined["cvr"] = (combined["cvr"] * 100).round(2)
    combined["cvr_7d"] = (combined["cvr_7d"] * 100).round(2)
    combined["cvr_30d"] = (combined["cvr_30d"] * 100).round(2)

    if "campaign_name" in df.columns:
        campaign_names = df.groupby("creative_id")["campaign_name"].first().reset_index()
        combined = combined.merge(campaign_names, on="creative_id", how="left")
    else:
        combined["campaign_name"] = None

    numeric_cols = ["impressions", "clicks", "conversions", "spend", "revenue"]
    combined[numeric_cols] = combined[numeric_cols].fillna(0.0)
    combined["impressions"] = combined["impressions"].astype(int)
    combined["clicks"] = combined["clicks"].astype(int)

    return combined[
        [
            "creative_id",
            "status",
            "fatigue_score",
            "impressions",
            "clicks",
            "ctr",
            "conversions",
            "spend",
            "revenue",
            "ctr_drop",
            "cvr_drop",
            "roas_drop",
            "cpa_increase",
            "cpc_increase",
            "notes",
            "impressions_7d",
            "ctr_7d",
            "ctr_30d",
            "roas_7d",
            "roas_30d",
            "cvr_7d",
            "cvr_30d",
            "cpa_7d",
            "cpa_30d",
            "cpc_7d",
            "cpc_30d",
            "campaign_name"
        ]
    ]
