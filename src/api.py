"""
FastAPI Backend for Ad Creative Auto-Optimizer
This API provides endpoints for managing ad campaigns across multiple platforms.
"""
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import asdict
import pandas as pd
import uvicorn

from components.config import load_settings
from components.utils.logging import setup_logging, get_logger
from components.db.bq_client import BigQueryClient
from components.client_manager import ClientManager
from components.data_sources.ads import meta as meta_ads
from components.data_sources.ads import meta_partnership_ads as meta_pa
from components.data_sources.ads import tiktok as tiktok_ads
from components.data_sources.ads import google_ads as gads
from components.data_sources.ads import pinterest as pinterest_ads
from components.data_sources.ads import linkedin as linkedin_ads
from components.optimizer.fatigue_detector import detect_fatigue
from components.models import Creative, AgentAction, Client, VariantProposal, ABTest
from components.llm.openai_client import score_creative
from components.optimizer.next_best_concepts import propose_next_best_concepts
from components.guardrails.safety import approve_variant
from components.agent.actions import ApprovalQueue, actions_from_fatigue, persist_actions_bq
from components.vision.features import compute_visual_features, novelty_score
from components.ab_testing import ABTestManager

# Initialize FastAPI app
app = FastAPI(
    title="Ad Creative Auto-Optimizer API",
    description="""
    ## Ad Creative Auto-Optimizer API

    This API provides comprehensive ad campaign management across multiple platforms:
    - **Meta (Facebook/Instagram)**
    - **Google Ads**
    - **TikTok**
    - **Pinterest**
    - **LinkedIn**

    ### Key Features:
    - Fetch ad creatives and performance data from multiple platforms
    - Detect ad fatigue using AI-powered analysis
    - Generate creative variants using GPT
    - Score and approve creative variants
    - Visual feature analysis for image/video ads
    - A/B testing management
    - Action approval queue for campaign changes

    ### Route Categories:
    1. **Clients** - Manage advertising clients
    2. **Data** - Fetch creatives and performance metrics
    3. **Analysis** - Fatigue detection and scoring
    4. **Variants** - Generate and approve creative variants
    5. **Actions** - Queue and execute campaign actions
    6. **Testing** - A/B test management
    7. **Visual** - Image/video feature analysis
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize
setup_logging()
logger = get_logger(__name__)
settings = load_settings()
bq_client = BigQueryClient(settings)
ab_test_manager = ABTestManager(bq_client)


# ========================================
# REQUEST/RESPONSE MODELS
# ========================================

class ClientResponse(BaseModel):
    """Client information response"""
    client_id: str
    client_name: str
    source: str
    platforms: Dict[str, bool] = Field(description="Available platforms for this client")


class DataRequest(BaseModel):
    """Request for fetching creatives/performance data"""
    client_id: str = Field(description="Client identifier")
    platform: str = Field(description="Platform: meta, google, tiktok, pinterest, linkedin")
    use_mock: bool = Field(default=False, description="Use mock data instead of live API")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    view: str = Field(default="ad", description="Performance view: 'ad' (default) or 'asset'")


class FatigueDetectionResponse(BaseModel):
    """Fatigue detection results"""
    creative_id: str
    campaign_name: Optional[str] = Field(None, description="Campaign name")
    status: str = Field(description="fresh, fatigue-risk, or fatigued")
    fatigue_score: Optional[float] = Field(None, ge=0, le=1, description="Weighted fatigue score (0-1)")
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    ctr: Optional[float] = None
    conversions: Optional[float] = None
    spend: Optional[float] = None
    revenue: Optional[float] = None
    ctr_drop: Optional[float] = Field(None, description="Relative CTR drop (0-1)")
    cvr_drop: Optional[float] = Field(None, description="Relative CVR drop (0-1)")
    roas_drop: Optional[float] = Field(None, description="Relative ROAS drop (0-1)")
    cpa_increase: Optional[float] = Field(None, description="Relative CPA increase (0-1)")
    cpc_increase: Optional[float] = Field(None, description="Relative CPC increase (0-1)")
    impressions_7d: Optional[int] = Field(None, description="Impressions in the past 7 days")
    ctr_7d: Optional[float] = Field(None, description="CTR (percentage) in the past 7 days")
    ctr_30d: Optional[float] = Field(None, description="CTR (percentage) in the past 30 days")
    roas_7d: Optional[float] = Field(None, description="ROAS in the past 7 days")
    roas_30d: Optional[float] = Field(None, description="ROAS in the past 30 days")
    cvr_7d: Optional[float] = Field(None, description="CVR (percentage) in the past 7 days")
    cvr_30d: Optional[float] = Field(None, description="CVR (percentage) in the past 30 days")
    cpa_7d: Optional[float] = Field(None, description="CPA in the past 7 days")
    cpa_30d: Optional[float] = Field(None, description="CPA in the past 30 days")
    cpc_7d: Optional[float] = Field(None, description="CPC in the past 7 days")
    cpc_30d: Optional[float] = Field(None, description="CPC in the past 30 days")
    notes: Optional[str] = Field(None, description="Explanation for the assigned status")


class VariantRequest(BaseModel):
    """Request to generate creative variants"""
    creative_id: str = Field(description="Creative ID to generate variants for")
    platform: str = Field(description="Platform: meta, google, tiktok, etc.")
    client_id: str = Field(description="Client identifier")
    n_variants: int = Field(default=3, ge=1, le=10, description="Number of variants to generate (1-10)")
    brand_guidelines: Optional[str] = Field(None, description="Optional brand guidelines text")


class VariantResponse(BaseModel):
    """Generated variant proposal"""
    title: Optional[str] = None
    text: Optional[str] = None
    hook: Optional[str] = None
    reasoning: Optional[str] = Field(description="Why this variant might perform better")
    estimated_uplift: Optional[float] = Field(description="Estimated performance uplift (0.0-0.2)")


class ActionRequest(BaseModel):
    """Request to create an action"""
    action_type: str = Field(description="pause_ad, update_copy, boost_partnership_ad, etc.")
    target_platform: str = Field(description="Platform: meta, google, tiktok, etc.")
    target_id: str = Field(description="Creative/Campaign/Ad ID")
    params: Dict[str, Any] = Field(default_factory=dict, description="Additional parameters")


class ActionResponse(BaseModel):
    """Action in approval queue"""
    action_type: str
    target_platform: str
    target_id: str
    params: Dict[str, Any]
    approved: bool
    executed: bool
    result_message: Optional[str] = None


class ABTestRequest(BaseModel):
    """Request to create A/B test"""
    test_name: str = Field(description="Name for the A/B test")
    test_type: str = Field(default="creative", description="Test focus: creative, copy, audience, budget")
    variant_a_id: str = Field(description="Creative ID for variant A (control)")
    variant_b_id: str = Field(description="Creative ID for variant B (test)")
    platform: str = Field(description="Platform: meta, google, tiktok, etc.")
    client_id: str = Field(description="Client identifier")


# ========================================
# HELPER FUNCTIONS
# ========================================

def dataframe_to_dict_list(df: pd.DataFrame) -> List[Dict]:
    """Convert pandas DataFrame to list of dicts with NaN handling"""
    if df.empty:
        return []
    # Replace NaN with None for JSON serialization
    return df.where(pd.notna(df), None).to_dict(orient="records")


def fetch_platform_data(
    platform: str,
    client_id: str,
    use_mock: bool,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    view: str = "ad",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch creatives and performance data for a specific platform

    Args:
        platform: Platform name (meta, google, tiktok, pinterest, linkedin)
        client_id: Client identifier
        use_mock: Whether to use mock data
        start_date: Start date for performance data
        end_date: End date for performance data

    Returns:
        Tuple of (creatives_df, performance_df)
    """
    if use_mock:
        import os
        creatives = pd.read_csv(os.path.join(settings.sample_data_dir, "creatives.csv"))
        perf = pd.read_csv(os.path.join(settings.sample_data_dir, "performance.csv"), parse_dates=["dt"])
        if not creatives.empty:
            creatives["client_id"] = client_id
            creatives["platform"] = platform
        if not perf.empty:
            perf["client_id"] = client_id
            perf["platform"] = platform
        return creatives, perf

    # Live mode
    bq = BigQueryClient(settings)
    bq.ensure_dataset_and_tables()
    client_mgr = ClientManager(bq)

    creds = client_mgr.get_client_for_platform(client_id, platform, use_mock=use_mock)

    if not creds or not any(creds.values()):
        logger.warning(f"No {platform} credentials for client {client_id}")
        return pd.DataFrame(), pd.DataFrame()

    # Default date range
    if start_date is None or end_date is None:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

    try:
        # Fetch based on platform
        if platform == "meta":
            creatives_df = meta_ads.fetch_creatives(
                api_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id"),
                api_version=creds.get("api_version", "v19.0")
            )
            perf_df = meta_ads.fetch_performance(
                start=start_date,
                end=end_date,
                api_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id"),
                api_version=creds.get("api_version", "v19.0")
            )

        elif platform == "google":
            creatives_df = gads.fetch_creatives(
                developer_token=creds.get("developer_token"),
                client_id=creds.get("client_id"),
                client_secret=creds.get("client_secret"),
                refresh_token=creds.get("refresh_token"),
                customer_id=creds.get("customer_id"),
                mcc_id=creds.get("mcc_id")
            )
            perf_df = gads.fetch_performance(
                start=start_date,
                end=end_date,
                developer_token=creds.get("developer_token"),
                client_id=creds.get("client_id"),
                client_secret=creds.get("client_secret"),
                refresh_token=creds.get("refresh_token"),
                customer_id=creds.get("customer_id"),
                mcc_id=creds.get("mcc_id"),
                view=view,
            )

        elif platform == "tiktok":
            creatives_df = tiktok_ads.fetch_creatives(
                access_token=creds.get("access_token"),
                advertiser_id=creds.get("advertiser_id"),
                app_id=creds.get("app_id")
            )
            perf_df = tiktok_ads.fetch_performance(
                start=start_date,
                end=end_date,
                access_token=creds.get("access_token"),
                advertiser_id=creds.get("advertiser_id"),
                app_id=creds.get("app_id")
            )

        elif platform == "pinterest":
            creatives_df = pinterest_ads.fetch_creatives(
                access_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id")
            )
            perf_df = pinterest_ads.fetch_performance(
                start=start_date,
                end=end_date,
                access_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id")
            )

        elif platform == "linkedin":
            creatives_df = linkedin_ads.fetch_creatives(
                access_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id")
            )
            perf_df = linkedin_ads.fetch_performance(
                start=start_date,
                end=end_date,
                access_token=creds.get("access_token"),
                ad_account_id=creds.get("ad_account_id")
            )

        else:
            logger.error(f"Unknown platform: {platform}")
            return pd.DataFrame(), pd.DataFrame()

        # Add client_id
        if not creatives_df.empty:
            creatives_df["client_id"] = client_id
        if not perf_df.empty:
            perf_df["client_id"] = client_id

        return creatives_df, perf_df

    except Exception as e:
        logger.error(f"Error fetching {platform} data: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()


# ========================================
# API ROUTES
# ========================================

@app.get("/", tags=["General"])
async def root():
    """
    **API Health Check**

    Returns basic API information and status.
    """
    return {
        "service": "Ad Creative Auto-Optimizer API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs"
    }


@app.get("/health", tags=["General"])
async def health_check():
    """
    **Health Check Endpoint**

    Check if the API is running and all dependencies are accessible.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "settings_loaded": settings is not None
    }


# ========================================
# CLIENT MANAGEMENT ROUTES
# ========================================

@app.get("/clients", response_model=List[ClientResponse], tags=["Clients"])
async def list_clients(use_mock: bool = Query(False, description="Return mock clients for testing")):
    """
    **List All Clients**

    Get a list of all configured clients and their available platforms.

    - **use_mock**: Set to true to get mock/demo clients

    Returns client_id, client_name, source (database or environment),
    and available platforms (meta, google, tiktok, pinterest, linkedin).
    """
    try:
        bq = BigQueryClient(settings)
        client_mgr = ClientManager(bq)
        clients = client_mgr.list_clients(use_mock=use_mock)

        result = []
        for client in clients:
            # Check which platforms are available
            platforms = {
                "meta": bool(client.meta_access_token and client.meta_ad_account_id),
                "google": bool(client.google_ads_developer_token and client.google_ads_customer_id),
                "tiktok": bool(client.tiktok_access_token and client.tiktok_advertiser_id),
                "pinterest": bool(client.pinterest_access_token and client.pinterest_ad_account_id),
                "linkedin": bool(client.linkedin_access_token and client.linkedin_ad_account_id),
            }

            # Determine source based on client_id prefix
            source = "mock" if use_mock else ("environment" if client.client_id.startswith("env_") else "database")

            result.append(ClientResponse(
                client_id=client.client_id,
                client_name=client.client_name,
                source=source,
                platforms=platforms
            ))

        return result

    except Exception as e:
        logger.error(f"Error listing clients: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clients/{client_id}", response_model=ClientResponse, tags=["Clients"])
async def get_client(client_id: str, use_mock: bool = Query(False)):
    """
    **Get Client Details**

    Retrieve detailed information for a specific client.

    - **client_id**: The unique client identifier
    - **use_mock**: Whether to search in mock clients
    """
    try:
        bq = BigQueryClient(settings)
        client_mgr = ClientManager(bq)
        clients = client_mgr.list_clients(use_mock=use_mock)

        client = next((c for c in clients if c.client_id == client_id), None)
        if not client:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

        platforms = {
            "meta": bool(client.meta_access_token and client.meta_ad_account_id),
            "google": bool(client.google_ads_developer_token and client.google_ads_customer_id),
            "tiktok": bool(client.tiktok_access_token and client.tiktok_advertiser_id),
            "pinterest": bool(client.pinterest_access_token and client.pinterest_ad_account_id),
            "linkedin": bool(client.linkedin_access_token and client.linkedin_ad_account_id),
        }

        # Determine source based on client_id prefix
        source = "mock" if use_mock else ("environment" if client.client_id.startswith("env_") else "database")

        return ClientResponse(
            client_id=client.client_id,
            client_name=client.client_name,
            source=source,
            platforms=platforms
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# DATA FETCHING ROUTES
# ========================================

@app.post("/data/creatives", tags=["Data"])
async def fetch_creatives(request: DataRequest):
    """
    **Fetch Ad Creatives**

    Retrieve all ad creatives for a specific client and platform.

    Returns creative details including:
    - creative_id, title, text, hook, overlay_text
    - asset_uri (image/video URL)
    - status, campaign_id, adset_id
    - platform-specific fields

    **Parameters:**
    - **client_id**: Client identifier
    - **platform**: meta, google, tiktok, pinterest, or linkedin
    - **use_mock**: Use sample data (for testing)
    - **start_date/end_date**: Not used for creatives (optional)
    """
    try:
        creatives_df, _ = fetch_platform_data(
            platform=request.platform,
            client_id=request.client_id,
            use_mock=request.use_mock
        )

        if creatives_df.empty:
            return {"creatives": [], "count": 0}

        return {
            "creatives": dataframe_to_dict_list(creatives_df),
            "count": len(creatives_df),
            "platform": request.platform,
            "client_id": request.client_id
        }

    except Exception as e:
        logger.error(f"Error fetching creatives: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/data/performance", tags=["Data"])
async def fetch_performance(request: DataRequest):
    """
    **Fetch Performance Metrics**

    Retrieve performance data for ads over a date range.

    Returns daily metrics including:
    - creative_id, dt (date)
    - impressions, clicks, spend
    - conversions, revenue
    - CTR, ROAS (calculated)

    **Parameters:**
    - **client_id**: Client identifier
    - **platform**: meta, google, tiktok, pinterest, or linkedin
    - **start_date**: Start date in YYYY-MM-DD format (default: 30 days ago)
    - **end_date**: End date in YYYY-MM-DD format (default: today)
    - **use_mock**: Use sample data (for testing)
    - **view**: `ad` (default) for creative-level metrics or `asset` for RSA asset performance

    **Note:** Date range is typically limited to last 37 months by platform APIs.
    """
    try:
        # Parse dates
        start_date = datetime.fromisoformat(request.start_date) if request.start_date else None
        end_date = datetime.fromisoformat(request.end_date) if request.end_date else None

        _, perf_df = fetch_platform_data(
            platform=request.platform,
            client_id=request.client_id,
            use_mock=request.use_mock,
            start_date=start_date,
            end_date=end_date,
            view=request.view
        )

        if perf_df.empty:
            return {"performance": [], "count": 0}

        return {
            "performance": dataframe_to_dict_list(perf_df),
            "count": len(perf_df),
            "platform": request.platform,
            "client_id": request.client_id,
            "date_range": {
                "start": request.start_date or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "end": request.end_date or datetime.now().strftime("%Y-%m-%d")
            }
        }

    except Exception as e:
        logger.error(f"Error fetching performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# ANALYSIS ROUTES
# ========================================

@app.post("/analysis/fatigue", response_model=List[FatigueDetectionResponse], tags=["Analysis"])
async def detect_ad_fatigue(request: DataRequest):
    """
    **Detect Ad Fatigue**

    Analyze performance data to detect ad fatigue using ML algorithms.

    Returns fatigue status for each creative:
    - **fresh**: Performing well, no fatigue
    - **fatigue-risk**: Warning signs, consider refreshing
    - **fatigued**: Performance declining, needs attention

    The algorithm considers:
    - CTR trends over time
    - Performance degradation patterns
    - Statistical significance of changes

    **Parameters:**
    - **client_id**: Client identifier
    - **platform**: meta, google, tiktok, pinterest, or linkedin
    - **start_date/end_date**: Date range for analysis
    - **use_mock**: Use sample data
    """
    try:
        start_date = datetime.fromisoformat(request.start_date) if request.start_date else None
        end_date = datetime.fromisoformat(request.end_date) if request.end_date else None

        creatives_df, perf_df = fetch_platform_data(
            platform=request.platform,
            client_id=request.client_id,
            use_mock=request.use_mock,
            start_date=start_date,
            end_date=end_date
        )

        logger.info(f"Fetched {len(creatives_df)} creatives and {len(perf_df)} performance records")

        if perf_df.empty:
            return []

        # Run fatigue detection - campaign_name comes from performance data now
        flags = detect_fatigue(perf_df)

        # Log campaign name coverage
        if "campaign_name" in flags.columns:
            campaign_names_found = flags['campaign_name'].notna().sum()
            logger.info(f"Campaign names in fatigue results: {campaign_names_found}/{len(flags)} ads")

        result = []
        for _, row in flags.iterrows():
            result.append(FatigueDetectionResponse(
                creative_id=str(row.get("creative_id")),
                campaign_name=str(row.get("campaign_name")) if pd.notna(row.get("campaign_name")) else None,
                status=row.get("status", "fresh"),
                fatigue_score=float(row.get("fatigue_score", 0.0)) if pd.notna(row.get("fatigue_score")) else None,
                impressions=int(row.get("impressions", 0)) if pd.notna(row.get("impressions")) else None,
                clicks=int(row.get("clicks", 0)) if pd.notna(row.get("clicks")) else None,
                ctr=float(row.get("ctr", 0.0)) if pd.notna(row.get("ctr")) else None,
                conversions=float(row.get("conversions", 0.0)) if pd.notna(row.get("conversions")) else None,
                spend=float(row.get("spend", 0.0)) if pd.notna(row.get("spend")) else None,
                revenue=float(row.get("revenue", 0.0)) if pd.notna(row.get("revenue")) else None,
                ctr_drop=float(row.get("ctr_drop", 0.0)) if pd.notna(row.get("ctr_drop")) else None,
                cvr_drop=float(row.get("cvr_drop", 0.0)) if pd.notna(row.get("cvr_drop")) else None,
                roas_drop=float(row.get("roas_drop", 0.0)) if pd.notna(row.get("roas_drop")) else None,
                cpa_increase=float(row.get("cpa_increase", 0.0)) if pd.notna(row.get("cpa_increase")) else None,
                cpc_increase=float(row.get("cpc_increase", 0.0)) if pd.notna(row.get("cpc_increase")) else None,
                impressions_7d=int(row.get("impressions_7d", 0)) if pd.notna(row.get("impressions_7d")) else None,
                ctr_7d=float(row.get("ctr_7d", 0.0)) if pd.notna(row.get("ctr_7d")) else None,
                ctr_30d=float(row.get("ctr_30d", 0.0)) if pd.notna(row.get("ctr_30d")) else None,
                roas_7d=float(row.get("roas_7d", 0.0)) if pd.notna(row.get("roas_7d")) else None,
                roas_30d=float(row.get("roas_30d", 0.0)) if pd.notna(row.get("roas_30d")) else None,
                cvr_7d=float(row.get("cvr_7d", 0.0)) if pd.notna(row.get("cvr_7d")) else None,
                cvr_30d=float(row.get("cvr_30d", 0.0)) if pd.notna(row.get("cvr_30d")) else None,
                cpa_7d=float(row.get("cpa_7d", 0.0)) if pd.notna(row.get("cpa_7d")) else None,
                cpa_30d=float(row.get("cpa_30d", 0.0)) if pd.notna(row.get("cpa_30d")) else None,
                cpc_7d=float(row.get("cpc_7d", 0.0)) if pd.notna(row.get("cpc_7d")) else None,
                cpc_30d=float(row.get("cpc_30d", 0.0)) if pd.notna(row.get("cpc_30d")) else None,
                notes=str(row.get("notes", "")) if pd.notna(row.get("notes")) else None
            ))

        return result

    except Exception as e:
        logger.error(f"Error detecting fatigue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analysis/score-creative", tags=["Analysis"])
async def score_creative_endpoint(
    creative_id: str = Body(...),
    platform: str = Body(...),
    client_id: str = Body(...),
    use_mock: bool = Body(False)
):
    """
    **Score Creative with AI**

    Use GPT to score an ad creative's effectiveness.

    Analyzes:
    - Copy quality and clarity
    - Emotional appeal
    - Call-to-action strength
    - Brand alignment
    - Predicted performance

    Returns a score (0-100) and detailed feedback.

    **Parameters:**
    - **creative_id**: ID of the creative to score
    - **platform**: Platform name
    - **client_id**: Client identifier
    - **use_mock**: Use sample data

    **Note:** Requires OpenAI API key configured in environment.
    """
    try:
        creatives_df, perf_df = fetch_platform_data(
            platform=platform,
            client_id=client_id,
            use_mock=use_mock
        )

        if creatives_df.empty:
            raise HTTPException(status_code=404, detail="No creatives found")

        # Find the creative (convert both to strings for comparison)
        creatives_df["creative_id"] = creatives_df["creative_id"].astype(str)
        creative_id_str = str(creative_id)
        creative_row = creatives_df[creatives_df["creative_id"] == creative_id_str]

        if creative_row.empty:
            # Debug: show available IDs
            available_ids = creatives_df["creative_id"].unique()[:10].tolist()
            logger.warning(f"Creative {creative_id_str} not found. Sample available IDs: {available_ids}")
            raise HTTPException(status_code=404, detail=f"Creative {creative_id_str} not found")

        # Convert to Creative model
        row = creative_row.iloc[0]
        creative = Creative(
            creative_id=str(row.get("creative_id")),
            platform=str(row.get("platform", platform)),
            title=row.get("title"),
            text=row.get("text"),
            hook=row.get("hook"),
            overlay_text=row.get("overlay_text"),
            frame_desc=row.get("frame_desc"),
            asset_uri=row.get("asset_uri", ""),
            status=row.get("status", "active")
        )

        # Score using OpenAI
        score_result = score_creative(settings, creative)

        return {
            "creative_id": creative_id,
            "score": score_result if isinstance(score_result, (int, float)) else 0,
            "platform": platform,
            "analysis": "Creative scored using GPT-4o-mini"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scoring creative: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# VARIANT GENERATION ROUTES
# ========================================

@app.post("/variants/generate", response_model=List[VariantResponse], tags=["Variants"])
async def generate_variants(request: VariantRequest):
    """
    **Generate Creative Variants with AI**

    Use GPT-4o-mini to generate new ad copy variants based on an existing creative.

    The AI will:
    - Analyze the original creative
    - Generate diverse variants with different angles
    - Estimate potential performance uplift
    - Provide reasoning for each variant

    **Parameters:**
    - **creative_id**: ID of the creative to use as a base
    - **platform**: Platform name
    - **client_id**: Client identifier
    - **n_variants**: Number of variants to generate (1-10, default: 3)
    - **brand_guidelines**: Optional brand voice/guidelines text

    **Returns:** Array of variant proposals with:
    - title, text, hook (new copy)
    - reasoning (why this might perform better)
    - estimated_uplift (0.0-0.2 = 0%-20% improvement)

    **Note:** Requires OpenAI API key configured in environment.
    """
    try:
        # Fetch creative data
        creatives_df, perf_df = fetch_platform_data(
            platform=request.platform,
            client_id=request.client_id,
            use_mock=False
        )

        if creatives_df.empty:
            raise HTTPException(status_code=404, detail="No creatives found")

        # Find the specific creative (convert both to strings for comparison)
        creatives_df["creative_id"] = creatives_df["creative_id"].astype(str)
        request_id = str(request.creative_id)
        creative_row = creatives_df[creatives_df["creative_id"] == request_id]

        if creative_row.empty:
            # Debug: show available IDs
            available_ids = creatives_df["creative_id"].unique()[:10].tolist()
            logger.warning(f"Creative {request_id} not found. Sample available IDs: {available_ids}")
            raise HTTPException(status_code=404, detail=f"Creative {request_id} not found")

        row = creative_row.iloc[0]
        creative = Creative(
            creative_id=str(row.get("creative_id")),
            platform=str(row.get("platform", request.platform)),
            title=row.get("title"),
            text=row.get("text"),
            hook=row.get("hook"),
            overlay_text=row.get("overlay_text"),
            frame_desc=row.get("frame_desc"),
            asset_uri=row.get("asset_uri", ""),
            status=row.get("status", "active")
        )

        # Generate variants using GPT
        variants = propose_next_best_concepts(
            settings=settings,
            creative=creative,
            all_creatives=creatives_df,
            perf=perf_df,
            brand_guidelines=request.brand_guidelines,
            n=request.n_variants
        )

        # Convert to response model
        result = []
        for variant in variants:
            result.append(VariantResponse(
                title=variant.idea_title,
                text=variant.new_body_text,
                hook=variant.new_hook,
                reasoning=variant.rationale,
                estimated_uplift=variant.estimated_uplift
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating variants: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/variants/approve", tags=["Variants"])
async def approve_variant_endpoint(
    variant: VariantResponse = Body(...),
    platform: str = Body(...),
    brand_guidelines: Optional[str] = Body(None)
):
    """
    **Approve Creative Variant**

    Run safety checks and brand compliance on a generated variant.

    Checks for:
    - Brand guideline violations
    - Inappropriate content
    - Regulatory compliance
    - Platform policy adherence

    **Parameters:**
    - **variant**: The variant proposal to approve (VariantResponse object)
    - **platform**: Platform name (for platform-specific rules)
    - **brand_guidelines**: Optional brand guidelines text

    **Returns:** Approval result with:
    - approved: boolean
    - reasons: List of approval/rejection reasons
    - variant: The checked variant
    """
    try:
        # Convert to VariantProposal
        variant_proposal = VariantProposal(
            title=variant.title,
            text=variant.text,
            hook=variant.hook,
            reasoning=variant.reasoning,
            estimated_uplift=variant.estimated_uplift
        )

        # Run approval check
        approved_variant = approve_variant(settings, variant_proposal, platform, brand_guidelines)

        return {
            "approved": True,  # If it passes approve_variant function
            "variant": asdict(approved_variant),
            "message": "Variant passed safety and compliance checks"
        }

    except Exception as e:
        logger.error(f"Error approving variant: {str(e)}")
        return {
            "approved": False,
            "variant": variant.dict(),
            "message": f"Approval check failed: {str(e)}"
        }


# ========================================
# ACTION QUEUE ROUTES
# ========================================

@app.post("/actions/generate-from-fatigue", response_model=List[ActionResponse], tags=["Actions"])
async def generate_actions_from_fatigue(request: DataRequest):
    """
    **Generate Actions from Fatigue Detection**

    Automatically create recommended actions based on fatigue analysis.

    Actions created:
    - **pause_ad**: For fatigued creatives
    - **update_copy**: For fatigue-risk creatives

    These actions are added to the approval queue and can be approved/executed later.

    **Parameters:**
    - **client_id**: Client identifier
    - **platform**: Platform name
    - **start_date/end_date**: Date range for fatigue analysis
    - **use_mock**: Use sample data

    **Returns:** List of generated actions (not yet approved)
    """
    try:
        start_date = datetime.fromisoformat(request.start_date) if request.start_date else None
        end_date = datetime.fromisoformat(request.end_date) if request.end_date else None

        _, perf_df = fetch_platform_data(
            platform=request.platform,
            client_id=request.client_id,
            use_mock=request.use_mock,
            start_date=start_date,
            end_date=end_date
        )

        if perf_df.empty:
            return []

        # Detect fatigue
        flags = detect_fatigue(perf_df)

        # Generate actions
        actions = actions_from_fatigue(flags, platform=request.platform)

        # Add to queue
        queue = ApprovalQueue(settings)
        for action in actions:
            queue.add(action)

        # Convert to response
        result = []
        for action in actions:
            result.append(ActionResponse(
                action_type=action.action_type,
                target_platform=action.target_platform,
                target_id=action.target_id,
                params=action.params,
                approved=action.approved,
                executed=action.executed,
                result_message=action.result_message
            ))

        return result

    except Exception as e:
        logger.error(f"Error generating actions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/actions/queue", response_model=List[ActionResponse], tags=["Actions"])
async def list_actions_queue():
    """
    **List All Actions in Queue**

    Retrieve all pending, approved, and executed actions from the approval queue.

    Returns actions with:
    - action_type: pause_ad, update_copy, boost_partnership_ad, etc.
    - target_platform: Platform the action applies to
    - target_id: Creative/Campaign/Ad ID
    - params: Additional action parameters
    - approved: Whether action has been approved
    - executed: Whether action has been executed
    - result_message: Execution result (if executed)
    """
    try:
        queue = ApprovalQueue(settings)
        actions = queue.list()

        result = []
        for action in actions:
            result.append(ActionResponse(
                action_type=action.action_type,
                target_platform=action.target_platform,
                target_id=action.target_id,
                params=action.params,
                approved=action.approved,
                executed=action.executed,
                result_message=action.result_message
            ))

        return result

    except Exception as e:
        logger.error(f"Error listing queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/actions/queue/add", tags=["Actions"])
async def add_action_to_queue(request: ActionRequest):
    """
    **Add Action to Queue**

    Manually add a custom action to the approval queue.

    **Parameters:**
    - **action_type**: Type of action (pause_ad, update_copy, boost_partnership_ad, etc.)
    - **target_platform**: Platform (meta, google, tiktok, etc.)
    - **target_id**: Creative/Campaign/Ad ID to act on
    - **params**: Additional parameters (JSON object)

    **Example:**
    ```json
    {
      "action_type": "pause_ad",
      "target_platform": "google",
      "target_id": "12345678",
      "params": {"reason": "manual_pause"}
    }
    ```
    """
    try:
        action = AgentAction(
            action_type=request.action_type,
            target_platform=request.target_platform,
            target_id=request.target_id,
            params=request.params
        )

        queue = ApprovalQueue(settings)
        queue.add(action)

        return {
            "message": "Action added to queue",
            "action": asdict(action)
        }

    except Exception as e:
        logger.error(f"Error adding action: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/actions/queue/{index}/approve", tags=["Actions"])
async def approve_action(index: int, approved: bool = Body(True)):
    """
    **Approve or Reject Action**

    Approve or reject a queued action by its index.

    **Parameters:**
    - **index**: Position in queue (0-based)
    - **approved**: True to approve, False to reject

    **Note:** Actions must be approved before they can be executed.
    """
    try:
        queue = ApprovalQueue(settings)
        action = queue.approve(index, approved=approved)

        if action is None:
            raise HTTPException(status_code=404, detail="Action not found at index")

        return {
            "message": f"Action {'approved' if approved else 'rejected'}",
            "action": asdict(action)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving action: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/actions/queue/{index}/execute", tags=["Actions"])
async def execute_action(index: int):
    """
    **Execute Approved Action**

    Execute an action from the queue (must be approved first).

    **Parameters:**
    - **index**: Position in queue (0-based)

    **Note:** Currently simulates execution (dry-run mode).
    To enable real execution, configure platform API credentials and disable dry_run in settings.
    """
    try:
        queue = ApprovalQueue(settings)
        action = queue.execute(index)

        if action is None:
            raise HTTPException(status_code=404, detail="Action not found at index")

        return {
            "message": "Action executed",
            "action": asdict(action),
            "result": action.result_message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/actions/queue/clear", tags=["Actions"])
async def clear_actions_queue():
    """
    **Clear Action Queue**

    Remove all actions from the queue (pending, approved, and executed).

    **Warning:** This action cannot be undone!
    """
    try:
        queue = ApprovalQueue(settings)
        queue.clear()

        return {"message": "Queue cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# A/B TESTING ROUTES
# ========================================

@app.post("/ab-test/create", tags=["A/B Testing"])
async def create_ab_test(request: ABTestRequest):
    """
    **Create A/B Test**

    Set up an A/B test to compare two creative variants.

    **Parameters:**
    - **test_name**: Descriptive name for the test
    - **variant_a_id**: Creative ID for control (variant A)
    - **variant_b_id**: Creative ID for test (variant B)
    - **platform**: Platform name
    - **client_id**: Client identifier

    The test will track performance metrics for both variants and calculate statistical significance.
    """
    try:
        test = ab_test_manager.create_test(
            client_id=request.client_id,
            platform=request.platform,
            test_name=request.test_name,
            test_type=request.test_type,
            variant_a_id=request.variant_a_id,
            variant_b_id=request.variant_b_id,
        )

        return {
            "test_id": test.test_id,
            "test_name": request.test_name,
            "test_type": request.test_type,
            "variant_a": request.variant_a_id,
            "variant_b": request.variant_b_id,
            "platform": request.platform,
            "client_id": request.client_id,
            "status": test.status
        }

    except Exception as e:
        logger.error(f"Error creating A/B test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def convert_numpy_types(val):
    """Convert numpy types to native Python types recursively"""
    import numpy as np

    if isinstance(val, (np.integer, np.int64, np.int32)):
        return int(val)
    elif isinstance(val, (np.floating, np.float64, np.float32)):
        return float(val)
    elif isinstance(val, np.ndarray):
        return val.tolist()
    elif isinstance(val, dict):
        return {k: convert_numpy_types(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [convert_numpy_types(v) for v in val]
    elif isinstance(val, datetime):
        return val.isoformat()
    return val


def serialize_test(test: ABTest) -> dict:
    """Serialize ABTest dataclass to JSON-compatible dict, handling numpy types"""
    test_dict = asdict(test)
    # Convert all values in the dict
    return {k: convert_numpy_types(v) for k, v in test_dict.items()}


@app.get("/ab-test/list", tags=["A/B Testing"])
async def list_ab_tests():
    """
    **List All A/B Tests**

    Get all A/B tests with their current status and results.

    Returns test details including:
    - test_id, test_name
    - variant A and B IDs
    - performance metrics for each variant
    - statistical significance
    - winner (if determined)
    """
    try:
        tests = [serialize_test(t) for t in ab_test_manager.list_tests()]

        return {"tests": tests, "count": len(tests)}

    except Exception as e:
        logger.error(f"Error listing A/B tests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ab-test/{test_id}/results", tags=["A/B Testing"])
async def get_ab_test_results(test_id: str):
    """
    **Get A/B Test Results**

    Retrieve detailed results for a specific A/B test.

    **Parameters:**
    - **test_id**: The test identifier

    Returns:
    - Performance metrics for each variant
    - Statistical significance (p-value)
    - Confidence interval
    - Winner (if statistically significant)
    - Recommended action
    """
    try:
        test = ab_test_manager.get_test(test_id)

        if not test:
            raise HTTPException(status_code=404, detail=f"Test {test_id} not found")

        # Fetch actual performance data for the variant creatives
        try:
            _, perf_df = fetch_platform_data(
                platform=test.platform,
                client_id=test.client_id,
                use_mock=False
            )

            # Filter to only the variant creatives
            variant_ids = [test.variant_a_id, test.variant_b_id]
            if test.variant_c_id:
                variant_ids.append(test.variant_c_id)
            if test.variant_d_id:
                variant_ids.append(test.variant_d_id)

            # Convert both to strings for comparison
            variant_ids_str = [str(vid) for vid in variant_ids]
            perf_df["creative_id"] = perf_df["creative_id"].astype(str)

            variant_perf = perf_df[perf_df["creative_id"].isin(variant_ids_str)]

            logger.info(f"Looking for variant IDs: {variant_ids_str}")
            logger.info(f"Performance data has {len(perf_df)} records")
            logger.info(f"Filtered to {len(variant_perf)} records for variants")
            if not variant_perf.empty:
                logger.info(f"Found data for creative IDs: {variant_perf['creative_id'].unique().tolist()}")
            else:
                # Debug: show sample of available IDs
                sample_ids = perf_df["creative_id"].unique()[:10].tolist()
                logger.warning(f"No match found. Sample available IDs: {sample_ids}")

            # Run statistical analysis
            if not variant_perf.empty:
                analysis = ab_test_manager.analyze_test(
                    test_id=test_id,
                    performance_data=variant_perf,
                    metric="ctr",
                    confidence_level=0.95
                )

                # Return analysis results with test metadata (serialize numpy types)
                return {
                    "test_id": test.test_id,
                    "test_name": test.test_name,
                    "platform": test.platform,
                    "status": test.status,
                    "winner": analysis.get("winner"),
                    "confidence_level": float(analysis.get("confidence_level")) if analysis.get("confidence_level") else None,
                    "metrics": convert_numpy_types(analysis.get("variants", {})),  # Serialize numpy types
                    "p_value": float(analysis.get("p_value")) if analysis.get("p_value") else None,
                    "recommendation": analysis.get("recommendation"),
                    "start_date": test.start_date.isoformat() if test.start_date else None,
                    "end_date": test.end_date.isoformat() if test.end_date else None,
                }
            else:
                # No performance data found
                logger.warning(f"No performance data found for test {test_id} variants")

        except Exception as e:
            logger.warning(f"Could not fetch performance data for test {test_id}: {str(e)}")

        # Fallback to basic summary if analysis fails
        summary = ab_test_manager.get_test_summary(test_id)
        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting test results: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# VISUAL ANALYSIS ROUTES
# ========================================

@app.post("/visual/compute-features", tags=["Visual Analysis"])
async def compute_visual_features_endpoint(
    creative_id: str = Body(...),
    platform: str = Body(...),
    client_id: str = Body(...),
    use_mock: bool = Body(False)
):
    """
    **Compute Visual Features**

    Extract visual features from an image/video creative using computer vision.

    Analyzes:
    - Color histogram
    - Dominant colors
    - Brightness/contrast
    - Edge detection
    - Object detection (if enabled)

    **Parameters:**
    - **creative_id**: ID of the creative with visual asset
    - **platform**: Platform name
    - **client_id**: Client identifier
    - **use_mock**: Use sample data

    **Note:**
    - Requires visual asset URL (asset_uri)
    - Google Ads (text-only) will return error
    - Works best with Meta, TikTok, Pinterest (image/video platforms)
    """
    try:
        creatives_df, _ = fetch_platform_data(
            platform=platform,
            client_id=client_id,
            use_mock=use_mock
        )

        if creatives_df.empty:
            raise HTTPException(status_code=404, detail="No creatives found")

        creative_row = creatives_df[creatives_df["creative_id"] == creative_id]
        if creative_row.empty:
            raise HTTPException(status_code=404, detail=f"Creative {creative_id} not found")

        row = creative_row.iloc[0]
        asset_uri = row.get("asset_uri", "")

        if not asset_uri:
            raise HTTPException(
                status_code=400,
                detail="Creative has no visual asset (asset_uri is empty). Visual analysis only works for image/video ads."
            )

        # Compute features
        features = compute_visual_features(asset_uri)

        return {
            "creative_id": creative_id,
            "features": features,
            "asset_uri": asset_uri
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing visual features: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/visual/novelty-score", tags=["Visual Analysis"])
async def compute_novelty_score_endpoint(
    creative_id: str = Body(...),
    platform: str = Body(...),
    client_id: str = Body(...),
    use_mock: bool = Body(False)
):
    """
    **Compute Novelty Score**

    Calculate how different/novel this creative is compared to others in the campaign.

    Uses visual features to measure:
    - Visual similarity to other ads
    - Uniqueness score (0-100)
    - Recommendations for differentiation

    **Parameters:**
    - **creative_id**: ID of the creative to analyze
    - **platform**: Platform name
    - **client_id**: Client identifier
    - **use_mock**: Use sample data

    Higher novelty scores indicate more unique/distinctive creatives.
    """
    try:
        creatives_df, _ = fetch_platform_data(
            platform=platform,
            client_id=client_id,
            use_mock=use_mock
        )

        if creatives_df.empty:
            raise HTTPException(status_code=404, detail="No creatives found")

        creative_row = creatives_df[creatives_df["creative_id"] == creative_id]
        if creative_row.empty:
            raise HTTPException(status_code=404, detail=f"Creative {creative_id} not found")

        row = creative_row.iloc[0]
        asset_uri = row.get("asset_uri", "")

        if not asset_uri:
            raise HTTPException(
                status_code=400,
                detail="Creative has no visual asset. Novelty score requires image/video."
            )

        # Get features for this creative
        features = compute_visual_features(asset_uri)

        # Get features for all other creatives to compare
        all_features = []
        for _, other_row in creatives_df.iterrows():
            if other_row["creative_id"] != creative_id and other_row.get("asset_uri"):
                try:
                    other_features = compute_visual_features(other_row["asset_uri"])
                    all_features.append(other_features)
                except:
                    continue

        # Calculate novelty
        score = novelty_score(features, all_features)

        return {
            "creative_id": creative_id,
            "novelty_score": score,
            "interpretation": "Higher scores indicate more unique/novel creatives"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing novelty: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# META PARTNERSHIP ADS (Special)
# ========================================

@app.get("/meta/partnership/recommended-medias", tags=["Meta Partnership"])
async def get_meta_recommended_medias(instagram_id: str = Query(..., description="Instagram business account ID")):
    """
    **Get Meta Partnership Recommended Media**

    Fetch recommended Instagram posts for partnership ads (Meta-specific feature).

    **Parameters:**
    - **instagram_id**: Instagram business account ID

    Returns recent posts suitable for boosting as partnership ads.

    **Note:** Requires Meta credentials and partnership ads access.
    """
    try:
        medias = meta_pa.fetch_recommended_medias(
            instagram_id=instagram_id,
            access_token=settings.meta_access_token
        )

        return {
            "instagram_id": instagram_id,
            "medias": medias,
            "count": len(medias)
        }

    except Exception as e:
        logger.error(f"Error fetching recommended medias: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# RUN SERVER
# ========================================

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
