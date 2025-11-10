# Enhanced dashboard tab - to be integrated into streamlit_app.py

def dashboard_tab(client_id: str, platform: str, start_date: str, end_date: str, use_mock: bool, show_enabled_only: bool = True):
    """Dashboard tab with fatigue detection"""
    import streamlit as st
    import pandas as pd
    import altair as alt

    st.subheader("📊 Fatigue Detection")

    with st.spinner("Analyzing ad fatigue..."):
        fatigue_data = detect_fatigue(client_id, platform, start_date, end_date, use_mock)

    if not fatigue_data:
        st.info("No fatigue data available")
        return

    df = pd.DataFrame(fatigue_data)

    # Stats at the top
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fresh Ads", len(df[df["status"] == "fresh"]))
    col2.metric("At Risk", len(df[df["status"] == "fatigue-risk"]))
    col3.metric("Fatigued", len(df[df["status"] == "fatigued"]))
    col4.metric("Total Ads", len(df))

    st.divider()

    # Table 1: Performance Metrics
    st.subheader("📈 Performance Metrics")
    perf_cols = ["creative_id", "status", "impressions", "clicks", "ctr", "conversions", "spend", "revenue"]
    perf_cols = [col for col in perf_cols if col in df.columns]
    st.dataframe(df[perf_cols], use_container_width=True)

    st.divider()

    # Table 2: Fatigue Analysis
    st.subheader("🔍 Fatigue Analysis Details")
    fatigue_cols = ["creative_id", "status", "drop_from_peak_ctr", "drop_from_peak_roas", "exposure_index", "notes"]
    fatigue_cols = [col for col in fatigue_cols if col in df.columns]
    st.dataframe(df[fatigue_cols], use_container_width=True)

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

            # Calculate ROAS if not present
            if "roas" not in perf_df.columns and "revenue" in perf_df.columns and "spend" in perf_df.columns:
                perf_df["roas"] = (perf_df["revenue"] / perf_df["spend"]).replace([float('inf'), float('-inf')], 0).fillna(0)

            # Chart 1: CTR over time (only top 10 ads to avoid clutter)
            st.subheader("📈 CTR Trend Over Time")

            # Get top 10 ads by total impressions
            top_ads = perf_df.groupby("creative_id")["impressions"].sum().nlargest(10).index.tolist()
            perf_top = perf_df[perf_df["creative_id"].isin(top_ads)].copy()

            if not perf_top.empty and "ctr" in perf_top.columns:
                chart1 = alt.Chart(perf_top).mark_line().encode(
                    x=alt.X("dt:T", title="Date"),
                    y=alt.Y("ctr:Q", title="CTR (%)", scale=alt.Scale(zero=False)),
                    color=alt.Color("creative_id:N", title="Creative ID"),
                    tooltip=["dt:T", "creative_id:N", "ctr:Q", "impressions:Q", "clicks:Q"]
                ).properties(height=400)
                st.altair_chart(chart1, use_container_width=True)
                st.caption("📊 Showing top 10 ads by impressions")

            st.divider()

            # Chart 2: Spend vs Revenue
            st.subheader("💰 Spend vs Revenue")

            spend_revenue = df[["creative_id", "spend", "revenue"]].copy()
            spend_revenue_melted = spend_revenue.melt(id_vars=["creative_id"], value_vars=["spend", "revenue"],
                                                       var_name="metric", value_name="amount")

            # Show top 10 by spend
            top_spenders = spend_revenue.nlargest(10, "spend")["creative_id"].tolist()
            spend_revenue_top = spend_revenue_melted[spend_revenue_melted["creative_id"].isin(top_spenders)]

            if not spend_revenue_top.empty:
                chart2 = alt.Chart(spend_revenue_top).mark_bar().encode(
                    x=alt.X("creative_id:N", title="Creative ID", sort="-y"),
                    y=alt.Y("amount:Q", title="Amount ($)"),
                    color=alt.Color("metric:N", title="Metric", scale=alt.Scale(scheme="set2")),
                    tooltip=["creative_id:N", "metric:N", "amount:Q"]
                ).properties(height=400)
                st.altair_chart(chart2, use_container_width=True)
                st.caption("📊 Showing top 10 ads by spend")

            st.divider()

            # Chart 3: Conversions by Status
            st.subheader("🎯 Conversions by Fatigue Status")

            status_conversions = df.groupby("status").agg({
                "conversions": "sum",
                "spend": "sum",
                "revenue": "sum"
            }).reset_index()

            if not status_conversions.empty:
                col1, col2 = st.columns(2)

                with col1:
                    chart3 = alt.Chart(status_conversions).mark_bar().encode(
                        x=alt.X("status:N", title="Status"),
                        y=alt.Y("conversions:Q", title="Total Conversions"),
                        color=alt.Color("status:N", scale=alt.Scale(
                            domain=["fresh", "fatigue-risk", "fatigued"],
                            range=["#2ecc71", "#f39c12", "#e74c3c"]
                        )),
                        tooltip=["status:N", "conversions:Q"]
                    ).properties(height=300)
                    st.altair_chart(chart3, use_container_width=True)

                with col2:
                    chart4 = alt.Chart(status_conversions).mark_bar().encode(
                        x=alt.X("status:N", title="Status"),
                        y=alt.Y("spend:Q", title="Total Spend ($)"),
                        color=alt.Color("status:N", scale=alt.Scale(
                            domain=["fresh", "fatigue-risk", "fatigued"],
                            range=["#2ecc71", "#f39c12", "#e74c3c"]
                        )),
                        tooltip=["status:N", "spend:Q"]
                    ).properties(height=300)
                    st.altair_chart(chart4, use_container_width=True)

            st.divider()

            # Chart 4: Exposure Index Distribution
            st.subheader("📊 Exposure Index Distribution")

            if "exposure_index" in df.columns:
                chart5 = alt.Chart(df).mark_bar().encode(
                    x=alt.X("exposure_index:Q", bin=alt.Bin(maxbins=20), title="Exposure Index"),
                    y=alt.Y("count():Q", title="Number of Ads"),
                    color=alt.Color("status:N", scale=alt.Scale(
                        domain=["fresh", "fatigue-risk", "fatigued"],
                        range=["#2ecc71", "#f39c12", "#e74c3c"]
                    )),
                    tooltip=["count():Q", "status:N"]
                ).properties(height=300)
                st.altair_chart(chart5, use_container_width=True)
                st.caption("📊 Distribution of exposure index across ads by status")
