import os
from datetime import datetime

import altair as alt
from dataclasses import asdict
import pandas as pd
import streamlit as st

from components.config import load_settings
from components.utils.logging import setup_logging
from components.db.bq_client import BigQueryClient
from components.data_sources.ads import meta as meta_ads
from components.data_sources.ads import tiktok as tiktok_ads
from components.data_sources.ads import google_ads as gads
from components.optimizer.fatigue_detector import detect_fatigue
from components.models import Creative
from components.llm.openai_client import score_creative
from components.optimizer.next_best_concepts import propose_next_best_concepts
from components.guardrails.safety import approve_variant
from components.agent.actions import ApprovalQueue, actions_from_fatigue, persist_actions_bq
from components.vision.features import compute_visual_features, novelty_score


st.set_page_config(page_title="Ad Creative Auto-Optimizer", layout="wide")
setup_logging()
settings = load_settings()


@st.cache_data(show_spinner=False)
def load_mock_data(sample_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    creatives = pd.read_csv(os.path.join(sample_dir, "creatives.csv"))
    perf = pd.read_csv(os.path.join(sample_dir, "performance.csv"), parse_dates=["dt"])  # yyyy-mm-dd
    return creatives, perf


def load_data(use_mock: bool):
    if use_mock:
        st.info("Using mock data from data/sample/.")
        return load_mock_data(str(settings.sample_data_dir))
    # Cloud mode: rely on BQ
    bq = BigQueryClient(settings)
    bq.ensure_dataset_and_tables()
    # In a full implementation you'd ingest from APIs into BQ
    return pd.DataFrame(), bq.read_performance()


def sidebar_controls():
    with st.sidebar:
        st.header("Settings")
        use_mock = st.toggle("Use mock data", value=settings.use_mock_data)
        dry_run = st.toggle("Dry-run mode", value=settings.dry_run)
        require_approval = st.toggle("Require approval", value=settings.require_approval)
        st.caption("Provide secrets in .streamlit/secrets.toml or env vars.")
        return use_mock, dry_run, require_approval


def dashboard_tab(creatives: pd.DataFrame, perf: pd.DataFrame):
    st.subheader("Fatigue Detection")
    flags = detect_fatigue(perf)
    st.dataframe(flags, use_container_width=True)

    if not perf.empty:
        agg = perf.groupby("dt", as_index=False).agg({"impressions": "sum", "clicks": "sum", "spend": "sum", "conversions": "sum"})
        agg["ctr"] = agg.eval("clicks / impressions")
        chart = (
            alt.Chart(agg).mark_line().encode(
                x="dt:T",
                y=alt.Y("ctr:Q", title="CTR"),
                tooltip=["dt", alt.Tooltip("ctr", format=".2%")],
            ).properties(height=250)
        )
        st.altair_chart(chart, use_container_width=True)

    return flags


def creatives_tab(creatives: pd.DataFrame):
    st.subheader("Creatives")
    st.dataframe(creatives, use_container_width=True)


def scoring_tab(creatives: pd.DataFrame, perf: pd.DataFrame):
    st.subheader("LLM + Vision Scoring & Variants")
    if creatives.empty:
        st.info("No creatives loaded.")
        return
    ids = creatives["creative_id"].astype(str).tolist()
    selected_id = st.selectbox("Select Creative", ids)
    row = creatives[creatives["creative_id"].astype(str) == selected_id].iloc[0]
    creative = Creative(
        creative_id=str(row.get("creative_id")),
        platform=str(row.get("platform", "meta")),
        title=row.get("title"),
        text=row.get("text"),
        hook=row.get("hook"),
        overlay_text=row.get("overlay_text"),
        frame_desc=row.get("frame_desc"),
        asset_uri=row.get("asset_uri"),
        status=row.get("status"),
    )

    cols = st.columns(2)
    with cols[0]:
        st.write("Scores")
        scores = score_creative(settings, creative)
        st.json(scores)
    with cols[1]:
        st.write("Generate Variants")
        n = st.slider("How many?", 1, 5, 3)
        brand_guidelines = st.text_area("Brand Guidelines (optional)")
        if st.button("Propose Variants"):
            props = propose_next_best_concepts(settings, creative, creatives, perf, brand_guidelines, n)
            for p in props:
                approved = approve_variant(settings, p, creative.platform, brand_guidelines)
                st.json(asdict(approved) if 'asdict' in globals() else approved.__dict__)


def actions_tab(flags: pd.DataFrame):
    st.subheader("Agent Actions (Approval Queue)")
    queue = ApprovalQueue(settings)

    # Propose actions based on fatigue
    if not flags.empty and st.button("Generate Actions from Fatigue"):
        acts = actions_from_fatigue(flags, platform="meta")
        for a in acts:
            queue.add(a)
        st.success(f"Queued {len(acts)} action(s)")

    # List and manage queue
    items = queue.list()
    if not items:
        st.info("No pending actions.")
        return
    for i, a in enumerate(items):
        cols = st.columns([2, 2, 4, 2, 2, 3])
        cols[0].write(a.action_type)
        cols[1].write(f"{a.target_platform}:{a.target_id}")
        cols[2].write(str(a.params))
        approve_col = cols[3]
        exec_col = cols[4]
        res_col = cols[5]
        if approve_col.button("Approve" if not a.approved else "Unapprove", key=f"appr-{i}"):
            queue.approve(i, approved=not a.approved)
            st.experimental_rerun()
        if exec_col.button("Execute", key=f"exec-{i}"):
            queue.execute(i)
            st.experimental_rerun()
        res_col.write(a.result_message or "")

    # Persist executed actions to BQ (optional)
    if st.button("Persist actions to BigQuery"):
        bq = BigQueryClient(settings)
        persist_actions_bq(bq, queue.list())
        st.success("Attempted to persist actions to BigQuery")


def visual_tab(creatives: pd.DataFrame):
    st.subheader("Visual Features & Novelty")
    if creatives.empty:
        st.info("No creatives loaded.")
        return

    # Session cache for computed visual features
    if "visual_features" not in st.session_state:
        st.session_state["visual_features"] = {}

    ids = creatives["creative_id"].astype(str).tolist()
    selected_id = st.selectbox("Select Creative", ids, key="visual-select")
    row = creatives[creatives["creative_id"].astype(str) == selected_id].iloc[0]
    creative = Creative(
        creative_id=str(row.get("creative_id")),
        platform=str(row.get("platform", "meta")),
        title=row.get("title"),
        text=row.get("text"),
        hook=row.get("hook"),
        overlay_text=row.get("overlay_text"),
        frame_desc=row.get("frame_desc"),
        asset_uri=row.get("asset_uri"),
        status=row.get("status"),
    )

    # Display image by URL if possible
    if creative.asset_uri and (creative.asset_uri.startswith("http://") or creative.asset_uri.startswith("https://")):
        st.image(creative.asset_uri, caption=f"Creative {creative.creative_id}", use_column_width=True)

    cols = st.columns(2)
    with cols[0]:
        if st.button("Compute Features", key="compute-one"):
            vf = compute_visual_features(settings, creative)
            if vf:
                st.session_state["visual_features"][creative.creative_id] = vf
            else:
                st.warning("Could not compute features (image not accessible or dependency missing).")
        # Show last computed features
        vf = st.session_state["visual_features"].get(creative.creative_id)
        if vf:
            st.json(vf.__dict__)

    with cols[1]:
        if st.button("Compute All Features", key="compute-all"):
            for _, r in creatives.iterrows():
                cid = str(r.get("creative_id"))
                cr = Creative(
                    creative_id=cid,
                    platform=str(r.get("platform", "meta")),
                    title=r.get("title"),
                    text=r.get("text"),
                    hook=r.get("hook"),
                    overlay_text=r.get("overlay_text"),
                    frame_desc=r.get("frame_desc"),
                    asset_uri=r.get("asset_uri"),
                    status=r.get("status"),
                )
                if cid not in st.session_state["visual_features"]:
                    v = compute_visual_features(settings, cr)
                    if v:
                        st.session_state["visual_features"][cid] = v
        # Novelty score of selected vs others
        vf_map = st.session_state["visual_features"]
        cur = vf_map.get(creative.creative_id)
        if cur:
            others = [v.ahash for k, v in vf_map.items() if k != creative.creative_id]
            nov = novelty_score(cur.ahash, others)
            st.metric("Novelty (0-1)", f"{nov:.2f}")

    # Table of computed features (summary)
    if st.session_state["visual_features"]:
        df = pd.DataFrame([
            {
                "creative_id": v.creative_id,
                "size": f"{v.width}x{v.height}",
                "ahash": v.ahash[:16] + ("…" if len(v.ahash) > 16 else ""),
                "dhash": v.dhash[:16] + ("…" if len(v.dhash) > 16 else ""),
                "avg_brightness": round(v.avg_brightness, 3),
                "entropy": round(v.entropy, 3),
                "overlay_density": round(v.overlay_density, 3),
            }
            for v in st.session_state["visual_features"].values()
        ])
        st.dataframe(df, use_container_width=True)

    # Persist to BigQuery
    if st.button("Persist Visual Features to BigQuery"):
        from datetime import datetime as _dt
        bq = BigQueryClient(settings)
        if not st.session_state["visual_features"]:
            st.info("No features to persist.")
        else:
            import json as _json
            rows = []
            for v in st.session_state["visual_features"].values():
                rows.append({
                    "creative_id": v.creative_id,
                    "width": v.width,
                    "height": v.height,
                    "ahash": v.ahash,
                    "dhash": v.dhash,
                    "dominant_colors": _json.dumps(list(v.dominant_colors)),
                    "avg_brightness": v.avg_brightness,
                    "entropy": v.entropy,
                    "overlay_text": v.overlay_text,
                    "overlay_density": v.overlay_density,
                    "ts": _dt.utcnow().isoformat(),
                })
            bq.upsert_visual_features(pd.DataFrame(rows))
            st.success("Attempted to persist visual features to BigQuery")

def main():
    use_mock, dry_run, require_approval = sidebar_controls()
    # Update in-memory flags (runtime only)
    settings.use_mock_data = use_mock
    settings.dry_run = dry_run
    settings.require_approval = require_approval

    st.title("Ad Creative Auto-Optimizer")
    creatives, perf = load_data(use_mock)
    tabs = st.tabs(["Dashboard", "Creatives", "Scoring & Variants", "Actions", "Visual"])

    with tabs[0]:
        flags = dashboard_tab(creatives, perf)
    with tabs[1]:
        creatives_tab(creatives)
    with tabs[2]:
        scoring_tab(creatives, perf)
    with tabs[3]:
        actions_tab(flags)
    with tabs[4]:
        visual_tab(creatives)


if __name__ == "__main__":
    main()
