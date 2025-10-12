from __future__ import annotations

import pandas as pd
from ...utils.logging import get_logger


log = get_logger(__name__)


def fetch_attribution_mock() -> pd.DataFrame:
    # Placeholder for GA4/MMP attribution; for MVP we focus on ad platform performance
    log.info("Using mock attribution (empty)")
    return pd.DataFrame()

