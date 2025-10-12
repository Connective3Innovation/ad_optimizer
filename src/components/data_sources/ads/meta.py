from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "meta"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "meta"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(api_token: str | None = None) -> pd.DataFrame:
    # Placeholder: implement real Meta Marketing API calls here
    log.info("Meta API token present: %s", bool(api_token))
    return pd.DataFrame()


def fetch_performance(start: datetime, end: datetime, api_token: str | None = None) -> pd.DataFrame:
    # Placeholder: implement real Meta Marketing API calls here
    log.info("Meta performance window %s..%s (token=%s)", start, end, bool(api_token))
    return pd.DataFrame()

