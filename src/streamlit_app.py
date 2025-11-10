"""
Streamlit Frontend for Ad Creative Auto-Optimizer
Connects to FastAPI backend
"""
import streamlit as st
import requests
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import os

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Ad Creative Auto-Optimizer", layout="wide")

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
def fetch_performance(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool = False) -> Dict:
    """Fetch performance data"""
    return api_request("POST", "/data/performance", json={
        "client_id": client_id,
        "platform": platform,
        "start_date": start_date,
        "end_date": end_date,
        "use_mock": use_mock
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
            show_enabled_only
        )


# ========================================
# TAB FUNCTIONS
# ========================================

def dashboard_tab(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool, show_enabled_only: bool = True):
    """Dashboard tab with enhanced fatigue detection and analytics"""
    st.subheader("📊 Fatigue Detection & Analytics")

    # Fetch both creatives and fatigue data to show complete stats
    creatives_data = fetch_creatives(client_id, platform, use_mock)
    total_creatives = len(creatives_data.get("creatives", [])) if creatives_data else 0

    with st.spinner("Analyzing ad fatigue..."):
        fatigue_data = detect_fatigue(client_id, platform, start_date, end_date, use_mock)

    if not fatigue_data:
        st.info("No fatigue data available")
        return

    df = pd.DataFrame(fatigue_data)

    # Show overview stats
    st.markdown("### 📊 Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Creatives", total_creatives, help="All creatives in your account")
    with col2:
        st.metric("Analyzed Ads", len(df), help="Ads with performance data (includes all statuses: enabled, paused, disabled)")
    with col3:
        ads_without_data = total_creatives - len(df)
        st.metric("No Performance Data", ads_without_data, help="Creatives with zero impressions (new or never served)")

    st.caption("ℹ️ **Note:** Performance analysis includes ALL ads with data, regardless of status (enabled, paused, or disabled)")

    st.divider()

    # Fatigue stats
    st.markdown("### 🔥 Fatigue Status")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fresh Ads", len(df[df["status"] == "fresh"]), delta="Healthy")
    col2.metric("At Risk", len(df[df["status"] == "fatigue-risk"]), delta="Monitor")
    col3.metric("Fatigued", len(df[df["status"] == "fatigued"]), delta="Action Needed", delta_color="inverse")
    col4.metric("Total Analyzed", len(df))

    st.divider()

    # Table 1: Performance Metrics
    st.subheader("📈 Performance Metrics")
    perf_cols = ["creative_id", "status", "impressions", "clicks", "ctr", "conversions", "spend", "revenue"]
    perf_cols = [col for col in perf_cols if col in df.columns]
    st.dataframe(df[perf_cols], use_container_width=True, height=400)

    st.divider()

    # Table 2: Fatigue Analysis Details
    st.subheader("🔍 Fatigue Analysis Details")

    # Create a clean dataframe with only analysis columns
    fatigue_df = pd.DataFrame()
    fatigue_df["creative_id"] = df["creative_id"]
    fatigue_df["status"] = df["status"]

    # Add formatted percentage columns
    if "drop_from_peak_ctr" in df.columns:
        fatigue_df["CTR Drop %"] = (df["drop_from_peak_ctr"] * 100).round(1)

    if "drop_from_peak_roas" in df.columns:
        fatigue_df["ROAS Drop %"] = (df["drop_from_peak_roas"] * 100).round(1)

    if "exposure_index" in df.columns:
        fatigue_df["Exposure %"] = (df["exposure_index"] * 100).round(1)

    if "notes" in df.columns:
        fatigue_df["Reasoning"] = df["notes"]

    st.dataframe(fatigue_df, use_container_width=True, height=400)

    # Add explanation
    st.caption("""
    **How to interpret:**
    - **CTR Drop %**: Decline from peak CTR (>40% = fatigued, >20% = at risk)
    - **ROAS Drop %**: Decline from peak ROAS (>30% = fatigued, >15% = at risk)
    - **Exposure %**: Audience saturation level (>60% + significant drops = fatigued)
    - **Reasoning**: Explanation for the assigned status
    """)

    st.divider()

    # Fetch performance data for charts
    perf_data = fetch_performance(client_id, platform, start_date, end_date, use_mock)

    if perf_data and perf_data.get("performance"):
        perf_df = pd.DataFrame(perf_data["performance"])

        if "dt" in perf_df.columns:
            perf_df["dt"] = pd.to_datetime(perf_df["dt"])

            # Calculate CTR if not present
            if "ctr" not in perf_df.columns and "clicks" in perf_df.columns and "impressions" in perf_df.columns:
                perf_df["ctr"] = (perf_df["clicks"] / perf_df["impressions"] * 100).fillna(0)

            # Chart 1: CTR Trend (top 10 ads)
            st.subheader("📈 CTR Trend Over Time")
            top_ads = perf_df.groupby("creative_id")["impressions"].sum().nlargest(10).index.tolist()
            perf_top = perf_df[perf_df["creative_id"].isin(top_ads)].copy()

            if not perf_top.empty and "ctr" in perf_top.columns:
                chart1 = alt.Chart(perf_top).mark_line(point=True).encode(
                    x=alt.X("dt:T", title="Date"),
                    y=alt.Y("ctr:Q", title="CTR (%)", scale=alt.Scale(zero=False)),
                    color=alt.Color("creative_id:N", title="Creative ID"),
                    tooltip=["dt:T", "creative_id:N", "ctr:Q", "impressions:Q", "clicks:Q"]
                ).properties(height=400)
                st.altair_chart(chart1, use_container_width=True)
                st.caption("📊 Showing top 10 ads by impressions")

            st.divider()

            # Chart 2: Spend vs Revenue
            st.subheader("💰 Spend vs Revenue Comparison")
            spend_revenue = df[["creative_id", "spend", "revenue"]].copy()
            top_spenders = spend_revenue.nlargest(10, "spend")["creative_id"].tolist()
            spend_revenue_top = spend_revenue[spend_revenue["creative_id"].isin(top_spenders)]

            if not spend_revenue_top.empty:
                spend_revenue_melted = spend_revenue_top.melt(
                    id_vars=["creative_id"],
                    value_vars=["spend", "revenue"],
                    var_name="metric",
                    value_name="amount"
                )

                chart2 = alt.Chart(spend_revenue_melted).mark_bar().encode(
                    x=alt.X("creative_id:N", title="Creative ID"),
                    y=alt.Y("amount:Q", title="Amount ($)"),
                    color=alt.Color("metric:N", title="Metric"),
                    xOffset="metric:N",
                    tooltip=["creative_id:N", "metric:N", "amount:Q"]
                ).properties(height=400)
                st.altair_chart(chart2, use_container_width=True)
                st.caption("📊 Showing top 10 ads by spend")

            st.divider()

            # Chart 3: Performance by Status
            st.subheader("🎯 Performance Breakdown by Fatigue Status")
            status_agg = df.groupby("status").agg({
                "conversions": "sum",
                "spend": "sum",
                "revenue": "sum",
                "impressions": "sum"
            }).reset_index()

            if not status_agg.empty:
                col1, col2 = st.columns(2)

                with col1:
                    chart3 = alt.Chart(status_agg).mark_bar().encode(
                        x=alt.X("status:N", title="Status", sort=["fresh", "fatigue-risk", "fatigued"]),
                        y=alt.Y("conversions:Q", title="Total Conversions"),
                        color=alt.Color("status:N", scale=alt.Scale(
                            domain=["fresh", "fatigue-risk", "fatigued"],
                            range=["#2ecc71", "#f39c12", "#e74c3c"]
                        ), legend=None),
                        tooltip=["status:N", "conversions:Q", "spend:Q"]
                    ).properties(height=300, title="Conversions")
                    st.altair_chart(chart3, use_container_width=True)

                with col2:
                    chart4 = alt.Chart(status_agg).mark_bar().encode(
                        x=alt.X("status:N", title="Status", sort=["fresh", "fatigue-risk", "fatigued"]),
                        y=alt.Y("spend:Q", title="Total Spend ($)"),
                        color=alt.Color("status:N", scale=alt.Scale(
                            domain=["fresh", "fatigue-risk", "fatigued"],
                            range=["#2ecc71", "#f39c12", "#e74c3c"]
                        ), legend=None),
                        tooltip=["status:N", "spend:Q", "revenue:Q"]
                    ).properties(height=300, title="Spend")
                    st.altair_chart(chart4, use_container_width=True)


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
                emoji = "✅" if status.upper() in ["ENABLED", "ACTIVE", "LIVE"] else "⏸️" if status.upper() == "PAUSED" else "❌"
                st.metric(f"{emoji} {status}", count)

        st.divider()

    # Apply filter
    if show_enabled_only and "status" in df.columns:
        original_count = len(df)
        # Filter for enabled/active ads
        df = df[df["status"].str.upper().isin(["ENABLED", "ACTIVE", "LIVE"])]

        if len(df) < original_count:
            st.info(f"📌 Showing {len(df)} enabled ads (filtered from {original_count} total). Uncheck 'Show enabled ads only' in the sidebar to see all ads.")

    st.write(f"**Displaying:** {len(df)} creative(s) {('(enabled only)' if show_enabled_only else '(all statuses)')}")

    # Display table
    display_cols = ["creative_id", "platform", "title", "text", "status"]
    display_cols = [col for col in display_cols if col in df.columns]

    st.dataframe(df[display_cols], use_container_width=True)


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
        df = df[df.get("status", pd.Series(["ENABLED"] * len(df))).str.upper().isin(["ENABLED", "ACTIVE", "LIVE"])]
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
                            st.dataframe(metrics_df, use_container_width=True)

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

    use_mock, client_id, client_name, platform, start_date, end_date, show_enabled_only = result

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
            dashboard_tab(client_id, platform, start_date, end_date, use_mock, show_enabled_only)
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
