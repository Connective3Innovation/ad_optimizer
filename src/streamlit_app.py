"""
Streamlit Frontend for Ad Creative Auto-Optimizer
Connects to FastAPI backend
"""
import streamlit as st
import requests
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import os

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Ad Creative Auto-Optimizer", layout="wide")

ACTIVE_AD_STATUSES = {"ENABLED", "ACTIVE", "LIVE", "SERVING", "APPROVED", "ELIGIBLE"}

# ========================================
# API CLIENT FUNCTIONS
# ========================================

def api_request(method: str, endpoint: str, **kwargs) -> dict:
    """Make API request with error handling"""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {str(e)}")
        if hasattr(e.response, 'text'):
            st.error(f"Details: {e.response.text}")
        return {}


@st.cache_data(ttl=900)  # Cache for 15 minutes
def get_clients(use_mock: bool = False) -> List[Dict]:
    """Get list of clients"""
    return api_request("GET", f"/clients?use_mock={use_mock}")


@st.cache_data(ttl=900)  # Cache for 15 minutes
def fetch_creatives(client_id: str, platform: str, use_mock: bool = False) -> Dict:
    """Fetch ad creatives"""
    return api_request("POST", "/data/creatives", json={
        "client_id": client_id,
        "platform": platform,
        "use_mock": use_mock
    })


@st.cache_data(ttl=900)  # Cache for 15 minutes
def fetch_performance(
    client_id: str,
    platform: str,
    start_date: str,
    end_date: str,
    use_mock: bool = False,
    view_mode: str = "ad"
) -> Dict:
    """Fetch performance data"""
    return api_request("POST", "/data/performance", json={
        "client_id": client_id,
        "platform": platform,
        "start_date": start_date,
        "end_date": end_date,
        "use_mock": use_mock,
        "view": view_mode
    })


@st.cache_data(ttl=900)  # Cache for 15 minutes
def detect_fatigue(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool = False) -> List[Dict]:
    """Detect ad fatigue"""
    return api_request("POST", "/analysis/fatigue", json={
        "client_id": client_id,
        "platform": platform,
        "start_date": start_date,
        "end_date": end_date,
        "use_mock": use_mock
    })


def generate_variants(creative_id: str, platform: str, client_id: str, n_variants: int = 3, brand_guidelines: Optional[str] = None) -> List[Dict]:
    """Generate creative variants"""
    return api_request("POST", "/variants/generate", json={
        "creative_id": creative_id,
        "platform": platform,
        "client_id": client_id,
        "n_variants": n_variants,
        "brand_guidelines": brand_guidelines
    })


def get_actions_queue() -> List[Dict]:
    """Get actions in queue"""
    return api_request("GET", "/actions/queue")


def generate_actions_from_fatigue(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool = False) -> List[Dict]:
    """Generate actions from fatigue"""
    return api_request("POST", "/actions/generate-from-fatigue", json={
        "client_id": client_id,
        "platform": platform,
        "start_date": start_date,
        "end_date": end_date,
        "use_mock": use_mock
    })


def approve_action(index: int, approved: bool = True) -> Dict:
    """Approve/reject action"""
    return api_request("POST", f"/actions/queue/{index}/approve", json=approved)


def execute_action(index: int) -> Dict:
    """Execute action"""
    return api_request("POST", f"/actions/queue/{index}/execute")


def clear_queue() -> Dict:
    """Clear actions queue"""
    return api_request("DELETE", "/actions/queue/clear")


# ========================================
# SIDEBAR
# ========================================

def sidebar_controls():
    """Render sidebar controls"""
    with st.sidebar:
        st.header("⚙️ Settings")

        # API Connection Status
        try:
            health = api_request("GET", "/health")
            if health.get("status") == "healthy":
                st.success(f"✅ API Connected")
            else:
                st.error("❌ API Unhealthy")
        except:
            st.error(f"❌ API Offline\n\nMake sure API is running at:\n`{API_BASE_URL}`")
            st.info("Run: `python src/api.py`")

        use_mock = st.toggle("Use mock data", value=False)

        st.divider()

        # Client Selection
        st.subheader("🏢 Client & Platform")

        clients = get_clients(use_mock=use_mock)

        if not clients:
            st.warning("No clients found")
            return None, None, None, None, None, None

        client_options = {f"{c['client_name']} ({c['client_id']})": c for c in clients}
        selected_key = st.selectbox("Select Client", options=list(client_options.keys()))
        selected_client = client_options[selected_key]

        # Show available platforms
        available_platforms = [p for p, available in selected_client["platforms"].items() if available]

        if not available_platforms and not use_mock:
            st.warning(f"No platforms configured for {selected_client['client_name']}")
            st.info("Configure credentials in .env file")

        platform_options = ["meta", "google", "tiktok", "pinterest", "linkedin"] if use_mock else available_platforms

        platform = st.selectbox(
            "Platform",
            options=platform_options,
            format_func=lambda x: x.upper()
        )

        st.divider()

        # Date Range
        st.subheader("📅 Date Range")
        default_end = datetime.now()
        default_start = default_end - timedelta(days=90)

        start_date = st.date_input("Start Date", value=default_start)
        end_date = st.date_input("End Date", value=default_end)

        days_span = (end_date - start_date).days
        if days_span > 365:
            st.warning(f"⚠️ {days_span} days - may be slow")

        st.divider()

        # Filter Controls
        st.subheader("🔍 Filters")
        show_enabled_only = st.checkbox("Show enabled ads only", value=True)
        show_with_impressions_only = st.checkbox(
            "Show only ads with impressions in date range",
            value=False,
            help="Filter to ads that actually served (impressions > 0) during the selected date range"
        )

        view_mode = "ad"
        breakdown_level = "ads"
        if platform == "google":
            st.subheader("🧱 View Options")
            view_options = {
                "Ad performance (creative level)": "ad",
                "Asset performance (headlines/descriptions)": "asset"
            }
            selected_view_label = st.selectbox("Data View", options=list(view_options.keys()))
            view_mode = view_options[selected_view_label]

            breakdown_options = {
                "Ads (creatives)": "ads",
                "Ad groups": "ad_group",
                "Campaigns": "campaign"
            }
            breakdown_disabled = view_mode == "asset"
            selected_breakdown_label = st.selectbox(
                "Breakdown Level",
                options=list(breakdown_options.keys()),
                disabled=breakdown_disabled
            )
            breakdown_level = breakdown_options[selected_breakdown_label]
        else:
            st.caption("ℹ️ Advanced breakdown controls are available for Google Ads.")

        st.divider()

        # Cache Control
        st.subheader("⚡ Cache")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.caption("Data cached for 15 minutes")
        with col2:
            if st.button("🔄 Refresh", help="Clear cache and fetch fresh data"):
                st.cache_data.clear()
                st.success("Cache cleared!")
                st.rerun()

        return (
            use_mock,
            selected_client["client_id"],
            selected_client["client_name"],
            platform,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            show_enabled_only,
            show_with_impressions_only,
            view_mode,
            breakdown_level
        )


# ========================================
# TAB FUNCTIONS
# ========================================

def dashboard_tab(
    client_id: str,
    platform: str,
    start_date: str,
    end_date: str,
    use_mock: bool,
    show_enabled_only: bool = True,
    show_with_impressions_only: bool = False,
    view_mode: str = "ad",
    breakdown_level: str = "ads",
):
    """Dashboard tab with enhanced fatigue detection and analytics"""
    st.subheader("📊 Fatigue Detection & Analytics")

    if platform != "google":
        view_mode = "ad"
        breakdown_level = "ads"

    creatives_data = fetch_creatives(client_id, platform, use_mock)
    creatives_records = creatives_data.get("creatives", []) if creatives_data else []
    creatives_df = pd.DataFrame(creatives_records) if creatives_records else pd.DataFrame()
    total_creatives = len(creatives_df)

    def _render_asset_view():
        st.markdown("### 🧱 Asset Performance (Headlines & Descriptions)")
        with st.spinner("Fetching asset-level insights..."):
            perf_payload = fetch_performance(
                client_id, platform, start_date, end_date, use_mock, view_mode="asset"
            )

        if not perf_payload or not perf_payload.get("performance"):
            st.info("No asset-level performance data for the selected range.")
            return

        asset_df = pd.DataFrame(perf_payload["performance"])
        if asset_df.empty:
            st.info("No asset-level performance data for the selected range.")
            return

        if "dt" in asset_df.columns:
            asset_df["dt"] = pd.to_datetime(asset_df["dt"])

        grouping_fields = [
            "asset_resource_name",
            "field_type",
            "asset_performance_label",
            "asset_text",
            "asset_url",
            "asset_name",
            "asset_type",
        ]
        asset_summary = (
            asset_df.groupby(grouping_fields, dropna=False)
            .agg(
                {
                    "creative_id": pd.Series.nunique,
                    "impressions": "sum",
                    "clicks": "sum",
                    "conversions": "sum",
                    "spend": "sum",
                    "revenue": "sum",
                }
            )
            .reset_index()
            .rename(columns={"creative_id": "ads_served"})
        )
        asset_summary["ctr"] = (
            asset_summary["clicks"] / asset_summary["impressions"] * 100
        ).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        asset_summary["roas"] = (
            asset_summary["revenue"] / asset_summary["spend"]
        ).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        asset_summary["asset_preview"] = (
            asset_summary["asset_text"]
            .fillna(asset_summary["asset_url"])
            .fillna("N/A")
            .astype(str)
            .str.slice(0, 120)
        )

        field_types = sorted([ft for ft in asset_summary["field_type"].dropna().unique()])
        if field_types:
            selected_field = st.selectbox("Field Type", options=["All"] + field_types, index=0)
            if selected_field != "All":
                asset_summary = asset_summary[asset_summary["field_type"] == selected_field]

        asset_types = sorted([ft for ft in asset_summary["asset_type"].dropna().unique()])
        if asset_types:
            selected_asset_type = st.selectbox("Asset Type", options=["All"] + asset_types, index=0)
            if selected_asset_type != "All":
                asset_summary = asset_summary[asset_summary["asset_type"] == selected_asset_type]

        if asset_summary.empty:
            st.info("No assets match the current filters.")
            return

        col1, col2, col3 = st.columns(3)
        col1.metric("Unique assets", asset_summary["asset_resource_name"].nunique())
        total_impr = asset_summary["impressions"].sum()
        avg_ctr = (asset_summary["clicks"].sum() / total_impr * 100) if total_impr else 0
        col2.metric("Avg CTR", f"{avg_ctr:.2f}%")
        total_spend = asset_summary["spend"].sum()
        avg_roas = (asset_summary["revenue"].sum() / total_spend) if total_spend else 0
        col3.metric("Avg ROAS", f"{avg_roas:.2f}x")

        display_cols = [
            "asset_type",
            "field_type",
            "asset_preview",
            "asset_performance_label",
            "ads_served",
            "impressions",
            "ctr",
            "conversions",
            "spend",
            "revenue",
            "roas",
            "asset_url",
        ]
        display_cols = [c for c in display_cols if c in asset_summary.columns]
        st.dataframe(
            asset_summary.sort_values("impressions", ascending=False)[display_cols],
            width="stretch",
            height=500,
        )
        st.caption("Asset view aggregates responsive search ad components so you can compare each headline/description across all ads.")

    if platform == "google" and view_mode == "asset":
        _render_asset_view()
        return

    with st.spinner("Analyzing ad fatigue..."):
        fatigue_data = detect_fatigue(client_id, platform, start_date, end_date, use_mock)

    # Start with all creatives, merge fatigue data if available
    if creatives_df.empty:
        st.info("No creatives data available")
        return

    # Prepare creatives base
    dims_cols = ["creative_id"]
    optional_cols = ["status", "campaign_id", "campaign_name", "adset_id", "adset_name", "title", "text"]
    dims_cols += [col for col in optional_cols if col in creatives_df.columns]
    df = creatives_df[dims_cols].drop_duplicates("creative_id").copy()
    rename_map = {"status": "ad_status", "adset_id": "ad_group_id", "adset_name": "ad_group_name"}
    df = df.rename(columns=rename_map)

    # Merge fatigue data if available (RIGHT JOIN - keep all creatives)
    if fatigue_data:
        fatigue_df = pd.DataFrame(fatigue_data)
        df = df.merge(fatigue_df, on="creative_id", how="left", suffixes=("", "_fatigue"))

        # Fill missing fatigue data with defaults
        if "status" not in df.columns:
            df["status"] = "no-data"
        else:
            df["status"] = df["status"].fillna("no-data")

        if "impressions" not in df.columns:
            df["impressions"] = 0
        else:
            df["impressions"] = df["impressions"].fillna(0)

        # Fill other metrics with 0
        for col in ["clicks", "spend", "conversions", "revenue", "ctr"]:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        if "notes" not in df.columns:
            df["notes"] = "No performance data in date range"
        else:
            df["notes"] = df["notes"].fillna("No performance data in date range")

        # Handle duplicate campaign_name columns
        if "campaign_name_fatigue" in df.columns:
            df["campaign_name"] = df["campaign_name"].fillna(df["campaign_name_fatigue"])
            df = df.drop(columns=["campaign_name_fatigue"])
    else:
        # No fatigue data at all - add default columns
        df["status"] = "no-data"
        df["impressions"] = 0
        df["clicks"] = 0
        df["spend"] = 0.0
        df["conversions"] = 0.0
        df["revenue"] = 0.0
        df["notes"] = "No performance data in date range"

    if show_enabled_only:
        if "ad_status" in df.columns:
            original_count = len(df)
            mask = df["ad_status"].fillna("UNKNOWN").str.upper().isin(ACTIVE_AD_STATUSES)
            df = df[mask].copy()
            if len(df) < original_count:
                st.info(f"📌 Showing {len(df)} enabled ads (filtered from {original_count} analyzed ads)")
        else:
            st.info("ℹ️ No ad status metadata available; showing all ads.")

    # Filter by impressions if requested
    if show_with_impressions_only and "impressions" in df.columns:
        original_count = len(df)
        df = df[df["impressions"] > 0].copy()
        if len(df) < original_count:
            st.info(f"📌 Showing {len(df)} ads with impressions (filtered from {original_count} ads)")

    if "spend" in df.columns and "revenue" in df.columns:
        df["roas"] = (df["revenue"] / df["spend"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)

    total_analyzed = len(df)

    st.markdown("### 📊 Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Creatives", total_creatives, help="All creatives in your account")
    with col2:
        st.metric(
            "Analyzed Ads",
            total_analyzed,
            help=f"Ads with performance data {'(enabled only)' if show_enabled_only else '(all statuses)'}",
        )
    with col3:
        ads_without_data = max(total_creatives - total_analyzed, 0)
        st.metric("No Performance Data", ads_without_data, help="Creatives with zero impressions (new or never served)")

    if df.empty:
        st.warning("No creatives match the current filters. Adjust the filters or expand the date range.")
        return

    if show_enabled_only:
        st.caption("ℹ️ Showing enabled ads only. Uncheck 'Show enabled ads only' in the sidebar to see all ads.")
    else:
        st.caption("ℹ️ Performance analysis includes ALL ads with data, regardless of platform status.")

    st.divider()

    st.markdown("### 🔥 Fatigue Status")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fresh Ads", len(df[df["status"] == "fresh"]), delta="Healthy")
    col2.metric("At Risk", len(df[df["status"] == "fatigue-risk"]), delta="Monitor")
    col3.metric("Fatigued", len(df[df["status"] == "fatigued"]), delta="Action Needed", delta_color="inverse")
    col4.metric("Total Analyzed", total_analyzed)

    st.divider()

    def _prepare_ads_df(base_df: pd.DataFrame) -> pd.DataFrame:
        ads_df = base_df.copy()
        ads_df["creative_count"] = 1
        ads_df["entity_id"] = ads_df["creative_id"]
        ads_df["entity_name"] = ads_df.get("campaign_name", ads_df["creative_id"])
        return ads_df

    def _aggregate_entities(base_df: pd.DataFrame, id_col: str, name_col: str) -> pd.DataFrame:
        group_cols = [id_col]
        if name_col != id_col:
            group_cols.append(name_col)

        agg_df = (
            base_df.groupby(group_cols, dropna=False)
            .agg(
                creative_count=("creative_id", "nunique"),
                impressions=("impressions", "sum"),
                clicks=("clicks", "sum"),
                conversions=("conversions", "sum"),
                spend=("spend", "sum"),
                revenue=("revenue", "sum"),
            )
            .reset_index()
        )

        status_group_cols = group_cols + ["status"]
        status_counts = (
            base_df.groupby(status_group_cols, dropna=False).size().unstack(fill_value=0).reset_index()
        )
        rename_status = {
            "fresh": "fresh_creatives",
            "fatigue-risk": "fatigue_risk_creatives",
            "fatigued": "fatigued_creatives",
        }
        status_counts = status_counts.rename(columns={k: v for k, v in rename_status.items() if k in status_counts.columns})
        merge_keys = group_cols
        agg_df = agg_df.merge(status_counts, on=merge_keys, how="left")

        rename_map = {id_col: "entity_id"}
        if name_col != id_col:
            rename_map[name_col] = "entity_name"
        agg_df = agg_df.rename(columns=rename_map)
        if name_col == id_col:
            agg_df["entity_name"] = agg_df["entity_id"]

        for col in ["fresh_creatives", "fatigue_risk_creatives", "fatigued_creatives"]:
            if col in agg_df.columns:
                agg_df[col] = agg_df[col].fillna(0).astype(int)
        agg_df["ctr"] = (agg_df["clicks"] / agg_df["impressions"] * 100).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        agg_df["roas"] = (agg_df["revenue"] / agg_df["spend"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        return agg_df

    def _resolve_breakdown(base_df: pd.DataFrame, level: str) -> Tuple[str, pd.DataFrame]:
        if level == "ad_group":
            if {"ad_group_id", "ad_group_name"}.issubset(base_df.columns):
                return "ad_group", _aggregate_entities(base_df, "ad_group_id", "ad_group_name")
            st.info("ℹ️ Ad group metadata unavailable; showing ad-level view.")
            return "ads", _prepare_ads_df(base_df)
        if level == "campaign":
            if {"campaign_id", "campaign_name"}.issubset(base_df.columns):
                return "campaign", _aggregate_entities(base_df, "campaign_id", "campaign_name")
            st.info("ℹ️ Campaign metadata unavailable; showing ad-level view.")
            return "ads", _prepare_ads_df(base_df)
        return "ads", _prepare_ads_df(base_df)

    resolved_breakdown, performance_view_df = _resolve_breakdown(df, breakdown_level)
    breakdown_titles = {
        "ads": "Ad level",
        "ad_group": "Ad group level",
        "campaign": "Campaign level",
    }

    st.subheader(f"📈 Performance Metrics — {breakdown_titles[resolved_breakdown]}")
    if resolved_breakdown == "ads":
        status_col = "ad_status" if "ad_status" in df.columns else "status"
        perf_cols = [
            "creative_id",
            "campaign_name",
            "ad_group_name",
            status_col,
            "impressions",
            "clicks",
            "ctr",
            "conversions",
            "spend",
            "revenue",
            "roas",
        ]
        perf_cols = [col for col in perf_cols if col in df.columns]
        display_df = df[perf_cols].copy()
        if "ad_status" in display_df.columns:
            display_df = display_df.rename(columns={"ad_status": "status"})
    else:
        perf_cols = [
            "entity_name",
            "creative_count",
            "fresh_creatives",
            "fatigue_risk_creatives",
            "fatigued_creatives",
            "impressions",
            "clicks",
            "ctr",
            "conversions",
            "spend",
            "revenue",
            "roas",
        ]
        perf_cols = [col for col in perf_cols if col in performance_view_df.columns]
        display_df = performance_view_df[perf_cols].copy().rename(columns={"entity_name": "Entity"})

    st.dataframe(display_df, width="stretch", height=400)

    st.divider()

    st.subheader("🔍 Fatigue Analysis Details")
    fatigue_df = pd.DataFrame()
    fatigue_df["creative_id"] = df["creative_id"]
    if "campaign_name" in df.columns:
        fatigue_df["campaign_name"] = df["campaign_name"]
    fatigue_df["status"] = df["status"]

    if "fatigue_score" in df.columns:
        fatigue_df["Fatigue Score"] = (df["fatigue_score"] * 100).round(1)
    if "ctr_drop" in df.columns:
        fatigue_df["CTR Drop %"] = (df["ctr_drop"] * 100).round(1)
    if "cvr_drop" in df.columns:
        fatigue_df["CVR Drop %"] = (df["cvr_drop"] * 100).round(1)
    if "roas_drop" in df.columns:
        fatigue_df["ROAS Drop %"] = (df["roas_drop"] * 100).round(1)
    if "cpa_increase" in df.columns:
        fatigue_df["CPA Increase %"] = (df["cpa_increase"] * 100).round(1)
    if "cpc_increase" in df.columns:
        fatigue_df["CPC Increase %"] = (df["cpc_increase"] * 100).round(1)
    if "notes" in df.columns:
        fatigue_df["Reasoning"] = df["notes"]

    st.dataframe(fatigue_df, width="stretch", height=400)

    st.caption(
        """
    **How to interpret:**
    - **Fatigue Score**: Weighted blend of CTR/CVR/ROAS drops and CPA/CPC increases
    - **CTR/CVR/ROAS Drop %**: Relative decline (7d vs 30d)
    - **CPA/CPC Increase %**: Rise in acquisition/click costs vs 30d baseline
    - **Reasoning**: Explanation for the assigned status
    """
    )

    st.divider()

    perf_data = fetch_performance(client_id, platform, start_date, end_date, use_mock, view_mode="ad")

    if perf_data and perf_data.get("performance"):
        perf_df = pd.DataFrame(perf_data["performance"])

        if show_enabled_only and not df.empty:
            enabled_creative_ids = df["creative_id"].unique()
            perf_df = perf_df[perf_df["creative_id"].isin(enabled_creative_ids)].copy()

        if "dt" in perf_df.columns:
            perf_df["dt"] = pd.to_datetime(perf_df["dt"])

            if "ctr" not in perf_df.columns and {"clicks", "impressions"}.issubset(perf_df.columns):
                perf_df["ctr"] = (perf_df["clicks"] / perf_df["impressions"] * 100).fillna(0)

            entity_maps = {
                "ads": ("creative_id", "creative_id"),
                "ad_group": ("ad_group_id", "ad_group_name"),
                "campaign": ("campaign_id", "campaign_name"),
            }
            entity_id_col, entity_name_col = entity_maps.get(resolved_breakdown, ("creative_id", "creative_id"))
            if entity_id_col not in perf_df.columns:
                entity_id_col, entity_name_col = ("creative_id", "creative_id")

            st.subheader("📈 CTR Trend Over Time")
            top_entities = (
                perf_df.groupby(entity_id_col)["impressions"].sum().nlargest(10).index.tolist()
            )
            perf_top = perf_df[perf_df[entity_id_col].isin(top_entities)].copy()
            if not perf_top.empty:
                group_cols = ["dt", entity_id_col]
                if entity_name_col != entity_id_col:
                    group_cols.append(entity_name_col)
                perf_top = (
                    perf_top.groupby(group_cols, dropna=False)
                    .agg({"impressions": "sum", "clicks": "sum"})
                    .reset_index()
                )
                if entity_name_col == entity_id_col and entity_name_col not in perf_top.columns:
                    perf_top[entity_name_col] = perf_top[entity_id_col]
                perf_top["ctr"] = (
                    perf_top["clicks"] / perf_top["impressions"] * 100
                ).replace([float("inf"), float("-inf")], 0).fillna(0)
                perf_top["entity_label"] = perf_top[entity_name_col].fillna(perf_top[entity_id_col])

                chart1 = (
                    alt.Chart(perf_top)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("dt:T", title="Date"),
                        y=alt.Y("ctr:Q", title="CTR (%)", scale=alt.Scale(zero=False)),
                        color=alt.Color("entity_label:N", title=breakdown_titles[resolved_breakdown]),
                        tooltip=["dt:T", "entity_label:N", "ctr:Q", "impressions:Q", "clicks:Q"],
                    )
                    .properties(height=400)
                )
                st.altair_chart(chart1, width="stretch")
                entity_caption = {
                    "ads": "ads",
                    "ad_group": "ad groups",
                    "campaign": "campaigns",
                }
                st.caption(f"📊 Showing top 10 {entity_caption.get(resolved_breakdown, 'ads')} by impressions")

            st.divider()

            st.subheader("💰 Spend vs Revenue Comparison")
            spend_source = performance_view_df.copy()
            spend_source = spend_source.sort_values("spend", ascending=False).head(10)
            if not spend_source.empty:
                label_col = (
                    "creative_id" if resolved_breakdown == "ads" else "entity_name"
                )
                spend_source["entity_label"] = spend_source[label_col].fillna(spend_source.get("entity_id"))
                spend_revenue_melted = spend_source.melt(
                    id_vars=["entity_label"],
                    value_vars=[col for col in ["spend", "revenue"] if col in spend_source.columns],
                    var_name="metric",
                    value_name="amount",
                )

                chart2 = (
                    alt.Chart(spend_revenue_melted)
                    .mark_bar()
                    .encode(
                        x=alt.X("entity_label:N", title=breakdown_titles[resolved_breakdown]),
                        y=alt.Y("amount:Q", title="Amount ($)"),
                        color=alt.Color("metric:N", title="Metric"),
                        xOffset="metric:N",
                        tooltip=["entity_label:N", "metric:N", "amount:Q"],
                    )
                    .properties(height=400)
                )
                st.altair_chart(chart2, width="stretch")
                st.caption("📊 Showing top spenders for the current breakdown.")

            st.divider()

            st.subheader("🎯 Performance Breakdown by Fatigue Status")
            status_agg = (
                df.groupby("status")
                .agg({"conversions": "sum", "spend": "sum", "revenue": "sum", "impressions": "sum"})
                .reset_index()
            )

            if not status_agg.empty:
                col1, col2 = st.columns(2)
                with col1:
                    chart3 = (
                        alt.Chart(status_agg)
                        .mark_bar()
                        .encode(
                            x=alt.X("status:N", title="Status", sort=["fresh", "fatigue-risk", "fatigued"]),
                            y=alt.Y("conversions:Q", title="Total Conversions"),
                            color=alt.Color(
                                "status:N",
                                scale=alt.Scale(
                                    domain=["fresh", "fatigue-risk", "fatigued"],
                                    range=["#2ecc71", "#f39c12", "#e74c3c"],
                                ),
                                legend=None,
                            ),
                            tooltip=["status:N", "conversions:Q", "spend:Q"],
                        )
                        .properties(height=300, title="Conversions")
                    )
                    st.altair_chart(chart3, width="stretch")
                with col2:
                    chart4 = (
                        alt.Chart(status_agg)
                        .mark_bar()
                        .encode(
                            x=alt.X("status:N", title="Status", sort=["fresh", "fatigue-risk", "fatigued"]),
                            y=alt.Y("spend:Q", title="Total Spend ($)"),
                            color=alt.Color(
                                "status:N",
                                scale=alt.Scale(
                                    domain=["fresh", "fatigue-risk", "fatigued"],
                                    range=["#2ecc71", "#f39c12", "#e74c3c"],
                                ),
                                legend=None,
                            ),
                            tooltip=["status:N", "spend:Q", "revenue:Q"],
                        )
                        .properties(height=300, title="Spend")
                    )
                    st.altair_chart(chart4, width="stretch")


def creatives_tab(client_id: str, platform: str, use_mock: bool, show_enabled_only: bool = True):
    """Creatives listing tab"""
    st.subheader("🎨 Ad Creatives")

    # Add refresh button at the top
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Refresh Data", help="Clear cache and fetch fresh data"):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Fetching creatives..."):
        data = fetch_creatives(client_id, platform, use_mock)

    if not data or not data.get("creatives"):
        st.info("No creatives found")
        return

    df = pd.DataFrame(data["creatives"])

    # Show data freshness indicator
    import datetime
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    st.caption(f"📊 Data loaded at {current_time} | Cached for 15 minutes")

    # Show status distribution summary at top
    if "status" in df.columns:
        status_counts = df["status"].value_counts()

        st.markdown("### 📊 Overview")
        cols = st.columns(len(status_counts))
        for idx, (status, count) in enumerate(status_counts.items()):
            with cols[idx]:
                status_upper = str(status).upper()
                if status_upper in ACTIVE_AD_STATUSES:
                    emoji = "✅"
                elif status_upper == "PAUSED":
                    emoji = "⏸️"
                else:
                    emoji = "❌"
                st.metric(f"{emoji} {status}", count)

        st.divider()

    # Apply filter
    if show_enabled_only and "status" in df.columns:
        original_count = len(df)
        status_mask = df["status"].fillna("UNKNOWN").str.upper().isin(ACTIVE_AD_STATUSES)
        df = df[status_mask]

        if len(df) < original_count:
            st.info(f"📌 Showing {len(df)} enabled ads (filtered from {original_count} total). Uncheck 'Show enabled ads only' in the sidebar to see all ads.")

    st.write(f"**Displaying:** {len(df)} creative(s) {('(enabled only)' if show_enabled_only else '(all statuses)')}")

    # Display table
    display_cols = ["creative_id", "campaign_name", "platform", "title", "text", "status"]
    display_cols = [col for col in display_cols if col in df.columns]

    st.dataframe(df[display_cols], width="stretch")


def variants_tab(client_id: str, platform: str, use_mock: bool):
    """Variant generation tab"""
    st.subheader("✨ Generate Creative Variants")

    # Fetch creatives first
    data = fetch_creatives(client_id, platform, use_mock)

    if not data or not data.get("creatives"):
        st.info("No creatives found")
        return

    # Convert to DataFrame for easier filtering
    df = pd.DataFrame(data["creatives"])

    st.write(f"**Total Creatives Available:** {len(df)}")

    # Status filter
    col1, col2 = st.columns([1, 3])
    with col1:
        show_all_status = st.checkbox("Show all statuses", value=False, help="Include paused/disabled ads")

    if not show_all_status:
        original_count = len(df)
        if "status" in df.columns:
            status_mask = df["status"].fillna("UNKNOWN").str.upper().isin(ACTIVE_AD_STATUSES)
        else:
            status_mask = pd.Series([True] * len(df), index=df.index)
        df = df[status_mask]
        st.caption(f"Filtered from {original_count} to {len(df)} creatives (enabled only)")

    # Search/filter section
    st.subheader("🔍 Select Creative")
    search_term = st.text_input("Search by ID, Title, or Text", placeholder="Type to search...")

    # Filter creatives based on search
    if search_term:
        mask = (
            df["creative_id"].astype(str).str.contains(search_term, case=False, na=False) |
            df.get("title", pd.Series([""] * len(df))).astype(str).str.contains(search_term, case=False, na=False) |
            df.get("text", pd.Series([""] * len(df))).astype(str).str.contains(search_term, case=False, na=False)
        )
        filtered_df = df[mask]
    else:
        filtered_df = df

    st.write(f"**Showing:** {len(filtered_df)} creative(s)")

    if filtered_df.empty:
        st.warning("No creatives match your search. Try a different term.")
        return

    # Create readable options for dropdown
    creative_options = {}
    for _, row in filtered_df.iterrows():
        creative_id = str(row["creative_id"])
        title = row.get("title", "")[:50] if row.get("title") else "No title"
        status = row.get("status", "unknown")
        display_text = f"{creative_id} - {title} [{status}]"
        creative_options[display_text] = creative_id

    col1, col2 = st.columns([2, 1])

    with col1:
        selected_display = st.selectbox("Select Creative", options=list(creative_options.keys()))
        selected_creative = creative_options[selected_display]

    with col2:
        n_variants = st.number_input("# Variants", min_value=1, max_value=10, value=3)

    # Show selected creative details
    selected_row = df[df["creative_id"] == selected_creative].iloc[0]
    with st.expander("📋 Selected Creative Preview"):
        st.write(f"**ID:** {selected_creative}")
        st.write(f"**Status:** {selected_row.get('status', 'N/A')}")
        st.write(f"**Title:** {selected_row.get('title', 'N/A')}")
        st.write(f"**Text:** {selected_row.get('text', 'N/A')}")
        if selected_row.get("hook"):
            st.write(f"**Hook:** {selected_row.get('hook')}")

    brand_guidelines = st.text_area("Brand Guidelines (Optional)", placeholder="E.g., friendly tone, focus on value...")

    if st.button("Generate Variants", type="primary"):
        with st.spinner("Generating variants with AI..."):
            variants = generate_variants(selected_creative, platform, client_id, n_variants, brand_guidelines)

        if variants:
            st.success(f"Generated {len(variants)} variants!")

            for i, variant in enumerate(variants, 1):
                with st.expander(f"Variant {i} - Est. Uplift: {variant.get('estimated_uplift', 0)*100:.1f}%"):
                    st.write(f"**Title:** {variant.get('title', 'N/A')}")
                    st.write(f"**Text:** {variant.get('text', 'N/A')}")
                    st.write(f"**Hook:** {variant.get('hook', 'N/A')}")
                    st.write(f"**Reasoning:** {variant.get('reasoning', 'N/A')}")
        else:
            st.error("Failed to generate variants")


def actions_tab(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool):
    """Actions approval queue tab"""
    st.subheader("⚡ Agent Actions (Approval Queue)")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Generate Actions from Fatigue"):
            with st.spinner("Generating actions..."):
                actions = generate_actions_from_fatigue(client_id, platform, start_date, end_date, use_mock)
            st.success(f"Generated {len(actions)} actions!")
            st.rerun()

    with col2:
        if st.button("Clear Queue", type="secondary"):
            clear_queue()
            st.success("Queue cleared!")
            st.rerun()

    # List queue
    queue_items = get_actions_queue()

    if not queue_items:
        st.info("No pending actions")
        return

    st.write(f"**Total Actions:** {len(queue_items)}")

    # Platform breakdown
    platform_counts = {}
    for item in queue_items:
        p = item["target_platform"]
        platform_counts[p] = platform_counts.get(p, 0) + 1

    st.write(f"**By Platform:** {', '.join([f'{p}: {c}' for p, c in platform_counts.items()])}")
    st.write(f"**Current Platform:** **{platform}**")

    st.divider()

    # Display actions
    for i, action in enumerate(queue_items):
        cols = st.columns([2, 2, 3, 1, 1, 2])

        cols[0].write(action["action_type"])
        cols[1].write(f"{action['target_platform']}:{action['target_id']}")
        cols[2].write(str(action["params"]))

        if cols[3].button("✓ Approve" if not action["approved"] else "✗ Unapprove", key=f"appr_{i}"):
            approve_action(i, approved=not action["approved"])
            st.rerun()

        if cols[4].button("▶ Execute", key=f"exec_{i}"):
            result = execute_action(i)
            st.success(f"Executed: {result.get('result', '')}")
            st.rerun()

        cols[5].write(action.get("result_message", ""))


def ab_testing_tab(client_id: str, platform: str, use_mock: bool):
    """A/B Testing tab"""
    st.subheader("🧪 A/B Testing")

    # Create new test
    with st.expander("➕ Create New A/B Test"):
        test_name = st.text_input("Test Name", placeholder="e.g., Headline Test - Value vs Quality")

        col1, col2 = st.columns(2)
        with col1:
            variant_a_id = st.text_input("Variant A ID (Control)", placeholder="Creative ID")
        with col2:
            variant_b_id = st.text_input("Variant B ID (Test)", placeholder="Creative ID")

        if st.button("Create Test"):
            if test_name and variant_a_id and variant_b_id:
                result = api_request("POST", "/ab-test/create", json={
                    "test_name": test_name,
                    "variant_a_id": variant_a_id,
                    "variant_b_id": variant_b_id,
                    "platform": platform,
                    "client_id": client_id
                })
                if result:
                    st.success(f"Test created: {result.get('test_id')}")
            else:
                st.error("Please fill all fields")

    # List tests
    st.subheader("📋 Active Tests")
    tests_data = api_request("GET", "/ab-test/list")

    if tests_data and tests_data.get("tests"):
        for test in tests_data["tests"]:
            status = test.get('status', 'unknown')
            status_emoji = {"draft": "📝", "running": "▶️", "paused": "⏸️", "completed": "✅"}.get(status, "❓")

            with st.expander(f"{status_emoji} {test.get('test_name', 'Unnamed Test')} - {status}"):
                st.write(f"**Test ID:** `{test.get('test_id')}`")
                st.write(f"**Variant A (Control):** `{test.get('variant_a_id')}`")
                st.write(f"**Variant B (Test):** `{test.get('variant_b_id')}`")
                st.write(f"**Platform:** {test.get('platform', 'N/A').upper()}")

                st.divider()

                if st.button("📊 View Detailed Results", key=f"results_{test.get('test_id')}"):
                    with st.spinner("Fetching performance data and analyzing..."):
                        results = api_request("GET", f"/ab-test/{test.get('test_id')}/results")

                    if results:
                        st.subheader("📈 Test Results")

                        # Show metrics if available
                        metrics = results.get('metrics', {})
                        if metrics and any(metrics.values()):
                            st.write("### Performance Metrics")
                            metrics_df = pd.DataFrame(metrics).T
                            st.dataframe(metrics_df, width="stretch")

                            # Show winner and confidence
                            winner = results.get('winner')
                            confidence = results.get('confidence_level')
                            if winner:
                                st.success(f"🏆 **Winner:** Variant {winner.upper()}")
                                if confidence:
                                    st.write(f"**Statistical Confidence:** {confidence*100:.1f}%")
                            else:
                                st.warning("⏳ No statistically significant winner yet.")
                                st.info("💡 Need more data or longer test duration for conclusive results.")
                        else:
                            st.warning("⚠️ **No performance data available yet**")
                            st.info("""
                            **Why is this empty?**

                            This test is in **draft** status and hasn't collected real performance data yet.

                            **To see real results:**
                            1. Make sure both variant ads (A and B) are **ENABLED** in your ad platform
                            2. Let them run for at least **3-7 days** to collect meaningful data
                            3. Come back and click "View Detailed Results" again
                            4. The system will fetch actual performance metrics and run statistical analysis

                            **Current Status:** `{status}`
                            """.format(status=status))

                        # Show raw JSON for debugging
                        with st.expander("🔍 Raw API Response (Debug)"):
                            st.json(results)
                    else:
                        st.error("❌ Failed to fetch results. Make sure the API is running.")
    else:
        st.info("No A/B tests found. Create one above!")


def visual_tab(client_id: str, platform: str, use_mock: bool):
    """Visual analysis tab"""
    st.subheader("👁️ Visual Features & Novelty")

    if platform == "google":
        st.warning("⚠️ Visual analysis not available for Google Ads (text-only platform)")
        st.info("Visual features work with image/video platforms: Meta, TikTok, Pinterest")
        return

    # Fetch creatives first
    data = fetch_creatives(client_id, platform, use_mock)

    if not data or not data.get("creatives"):
        st.info("No creatives found")
        return

    creative_ids = [c["creative_id"] for c in data["creatives"] if c.get("asset_uri")]

    if not creative_ids:
        st.warning("No creatives with visual assets (images/videos) found")
        return

    selected_creative = st.selectbox("Select Creative", creative_ids)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Compute Visual Features"):
            with st.spinner("Analyzing visual features..."):
                result = api_request("POST", "/visual/compute-features", json={
                    "creative_id": selected_creative,
                    "platform": platform,
                    "client_id": client_id,
                    "use_mock": use_mock
                })

                if result:
                    st.success("Features computed!")
                    st.json(result.get("features", {}))
                else:
                    st.error("Failed to compute features")

    with col2:
        if st.button("Compute Novelty Score"):
            with st.spinner("Calculating novelty..."):
                result = api_request("POST", "/visual/novelty-score", json={
                    "creative_id": selected_creative,
                    "platform": platform,
                    "client_id": client_id,
                    "use_mock": use_mock
                })

                if result:
                    score = result.get("novelty_score", 0)
                    st.metric("Novelty Score", f"{score:.1f}/100")
                    st.caption(result.get("interpretation", ""))
                else:
                    st.error("Failed to compute novelty")


def meta_partnership_tab():
    """Meta Partnership Ads tab"""
    st.subheader("🤝 Meta Partnership Ads")

    st.info("**Meta Partnership Ads** allow you to boost Instagram posts as ads")

    instagram_id = st.text_input("Instagram Business Account ID", placeholder="17841400123456789")

    if st.button("Fetch Recommended Posts"):
        if not instagram_id:
            st.error("Please enter Instagram Business Account ID")
            return

        with st.spinner("Fetching recommended Instagram posts..."):
            result = api_request("GET", f"/meta/partnership/recommended-medias?instagram_id={instagram_id}")

            if result and result.get("medias"):
                st.success(f"Found {result.get('count')} recommended posts")

                for media in result["medias"]:
                    with st.expander(f"{media.get('media_type')} - {media.get('id')}"):
                        st.write(f"**Caption:** {media.get('caption', 'N/A')}")
                        st.write(f"**Type:** {media.get('media_type')}")
                        st.write(f"**Timestamp:** {media.get('timestamp')}")

                        if media.get("media_url"):
                            if media.get("media_type") == "IMAGE":
                                st.image(media["media_url"])
                            else:
                                st.video(media["media_url"])

                        if st.button("Boost as Partnership Ad", key=f"boost_{media.get('id')}"):
                            st.info("This would create a partnership ad boost action")
            else:
                st.warning("No recommended posts found or API error")


def client_info_tab():
    """Client management info tab"""
    st.subheader("🏢 Client Management")

    st.markdown("""
    ## How to Add Clients

    Clients are configured via environment variables in your `.env` file.

    ### Format:
    ```
    CLIENT_1_NAME=MyClient
    CLIENT_1_META_ACCESS_TOKEN=...
    CLIENT_1_META_AD_ACCOUNT_ID=...
    CLIENT_1_GOOGLE_ADS_DEVELOPER_TOKEN=...
    CLIENT_1_GOOGLE_ADS_CUSTOMER_ID=...
    # ... etc
    ```

    ### Available Platforms:
    - **Meta (Facebook/Instagram)**: Requires access_token, ad_account_id
    - **Google Ads**: Requires developer_token, client_id, client_secret, refresh_token, customer_id, mcc_id
    - **TikTok**: Requires access_token, advertiser_id, app_id
    - **Pinterest**: Requires access_token, ad_account_id
    - **LinkedIn**: Requires access_token, ad_account_id

    See documentation for full credential setup guides.
    """)

    # Show current clients
    st.subheader("📋 Current Clients")
    clients = get_clients(use_mock=False)

    if clients:
        for client in clients:
            with st.expander(f"{client['client_name']} ({client['client_id']})"):
                st.write(f"**Source:** {client['source']}")
                st.write("**Available Platforms:**")
                for platform, available in client["platforms"].items():
                    st.write(f"  - {platform.upper()}: {'✓' if available else '✗'}")


# ========================================
# MAIN APP
# ========================================

def main():
    st.title("🚀 Ad Creative Auto-Optimizer")

    # Sidebar
    result = sidebar_controls()

    if result[0] is None:
        st.warning("Configure clients to get started")
        return

    use_mock, client_id, client_name, platform, start_date, end_date, show_enabled_only, show_with_impressions_only, view_mode, breakdown_level = result

    st.write(f"**Client:** {client_name} | **Platform:** {platform.upper()}")

    # Tabs
    tabs = st.tabs([
        "📊 Dashboard",
        "🎨 Creatives",
        "✨ Scoring & Variants",
        "⚡ Actions",
        "👁️ Visual",
        "🧪 A/B Testing",
        "🤝 Meta Partnership",
        "🏢 Client Info"
    ])

    with tabs[0]:
        if client_id:
            dashboard_tab(client_id, platform, start_date, end_date, use_mock, show_enabled_only, show_with_impressions_only, view_mode, breakdown_level)
        else:
            st.info("Select a client to view dashboard")

    with tabs[1]:
        if client_id:
            creatives_tab(client_id, platform, use_mock, show_enabled_only)
        else:
            st.info("Select a client to view creatives")

    with tabs[2]:
        if client_id:
            variants_tab(client_id, platform, use_mock)
        else:
            st.info("Select a client to use variant generation")

    with tabs[3]:
        if client_id:
            actions_tab(client_id, platform, start_date, end_date, use_mock)
        else:
            st.info("Select a client to manage actions")

    with tabs[4]:
        if client_id:
            visual_tab(client_id, platform, use_mock)
        else:
            st.info("Select a client to analyze visual features")

    with tabs[5]:
        if client_id:
            ab_testing_tab(client_id, platform, use_mock)
        else:
            st.info("Select a client to manage A/B tests")

    with tabs[6]:
        if platform == "meta":
            meta_partnership_tab()
        else:
            st.info("Meta Partnership Ads are only available for Meta (Facebook/Instagram) platform")

    with tabs[7]:
        client_info_tab()


if __name__ == "__main__":
    main()
