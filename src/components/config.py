import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Dict


def _get_streamlit_secrets() -> Dict[str, Any]:
    try:
        import streamlit as st
        return dict(st.secrets)
    except Exception:
        return {}


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


@dataclass
class Settings:
    # Cloud
    gcp_project_id: Optional[str] = None
    bigquery_dataset: str = "ad_creative_auto_optimizer"
    gcp_credentials_json: Optional[str] = None  # path or raw JSON
    gcs_bucket: Optional[str] = None

    # LLM
    openai_api_key: Optional[str] = None

    # Runtime
    use_mock_data: bool = True
    dry_run: bool = True
    require_approval: bool = True

    # Meta (Facebook/Instagram) Partnership Ads
    meta_access_token: Optional[str] = None
    meta_api_version: str = "v19.0"
    meta_ad_account_id: Optional[str] = None
    instagram_business_account_id: Optional[str] = None
    meta_default_adset_id: Optional[str] = None

    # Paths
    repo_root: Path = Path(__file__).resolve().parents[2]
    sample_data_dir: Path = Path(__file__).resolve().parents[2] / "data" / "sample"


def load_settings() -> Settings:
    _load_dotenv_if_available()
    secrets = _get_streamlit_secrets()

    def pick(*keys: str, default: Optional[str] = None) -> Optional[str]:
        for k in keys:
            if k in secrets and secrets[k]:
                return str(secrets[k])
            v = os.getenv(k)
            if v:
                return v
        return default

    use_mock_data = str(pick("USE_MOCK_DATA", default="true")).lower() in {"1", "true", "yes"}
    dry_run = str(pick("DRY_RUN", default="true")).lower() in {"1", "true", "yes"}
    require_approval = str(pick("REQUIRE_APPROVAL", default="true")).lower() in {"1", "true", "yes"}

    return Settings(
        gcp_project_id=pick("gcp_project_id", "GCP_PROJECT_ID"),
        bigquery_dataset=pick("bigquery_dataset", "BIGQUERY_DATASET", default="ad_creative_auto_optimizer"),
        gcp_credentials_json=pick("gcp_credentials_json", "GCP_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS"),
        gcs_bucket=pick("gcs_bucket", "GCS_BUCKET"),
        openai_api_key=pick("openai_api_key", "OPENAI_API_KEY"),
        use_mock_data=use_mock_data,
        dry_run=dry_run,
        require_approval=require_approval,
        meta_access_token=pick("meta_access_token", "META_ACCESS_TOKEN"),
        meta_api_version=pick("meta_api_version", "META_API_VERSION", default="v19.0"),
        meta_ad_account_id=pick("meta_ad_account_id", "META_AD_ACCOUNT_ID"),
        instagram_business_account_id=pick("instagram_business_account_id", "INSTAGRAM_BUSINESS_ACCOUNT_ID"),
        meta_default_adset_id=pick("meta_default_adset_id", "META_DEFAULT_ADSET_ID"),
    )


def configure_google_credentials(settings: Settings) -> None:
    # Accept either a file path or raw JSON in gcp_credentials_json
    if not settings.gcp_credentials_json:
        return
    raw = settings.gcp_credentials_json.strip()
    if raw.startswith("{"):
        # Write to a temp file for client libs that expect a path
        cache_dir = settings.repo_root / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cred_path = cache_dir / "gcp_sa.json"
        cred_path.write_text(raw, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
    else:
        # Assume it's a path
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = raw


def has_openai() -> bool:
    try:
        import openai  # noqa: F401
        return True
    except Exception:
        return False

