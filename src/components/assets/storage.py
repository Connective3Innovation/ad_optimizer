from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from ..config import Settings, configure_google_credentials
from ..utils.logging import get_logger


log = get_logger(__name__)


@dataclass
class GCSStorage:
    settings: Settings
    _client: Optional[object] = None  # google.cloud.storage.Client

    def __post_init__(self):
        self._maybe_init()

    def _maybe_init(self) -> None:
        try:
            from google.cloud import storage  # type: ignore
        except Exception:
            log.warning("google-cloud-storage not installed; storage disabled")
            self._client = None
            return
        if not self.settings.gcp_project_id or not self.settings.gcs_bucket:
            log.info("GCS not configured; storage disabled")
            self._client = None
            return
        try:
            configure_google_credentials(self.settings)
            self._client = storage.Client(project=self.settings.gcp_project_id)
        except Exception as e:
            log.warning("Failed to init GCS client: %s", e)
            self._client = None

    def generate_signed_url(self, blob_name: str, minutes: int = 60) -> Optional[str]:
        if not self._client:
            return None
        try:
            from datetime import timedelta
            bucket = self._client.bucket(self.settings.gcs_bucket)
            blob = bucket.blob(blob_name)
            return blob.generate_signed_url(expiration=timedelta(minutes=minutes))
        except Exception as e:
            log.error("Failed to sign URL: %s", e)
            return None

