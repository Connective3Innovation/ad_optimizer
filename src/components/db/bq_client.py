from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import pandas as pd
from ..config import Settings, configure_google_credentials
from ..utils.logging import get_logger


log = get_logger(__name__)


@dataclass
class BigQueryClient:
    settings: Settings
    _client: Optional[object] = None  # google.cloud.bigquery.Client

    def __post_init__(self):
        self._maybe_init()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _maybe_init(self) -> None:
        try:
            from google.cloud import bigquery  # type: ignore
        except Exception:
            log.warning("google-cloud-bigquery not installed; running in local mock mode")
            self._client = None
            return

        if not self.settings.gcp_project_id:
            log.warning("GCP project not configured; running in local mock mode")
            self._client = None
            return

        try:
            configure_google_credentials(self.settings)
            self._client = bigquery.Client(project=self.settings.gcp_project_id)
        except Exception as e:
            log.warning("Failed to initialize BigQuery client: %s", e)
            self._client = None

    # Schema helpers
    def _table_ref(self, name: str) -> str:
        return f"{self.settings.gcp_project_id}.{self.settings.bigquery_dataset}.{name}"

    def ensure_dataset_and_tables(self) -> None:
        if not self.enabled:
            return
        try:
            from google.cloud import bigquery  # type: ignore
            client = self._client

            # Ensure dataset
            dataset_ref = bigquery.Dataset(f"{self.settings.gcp_project_id}.{self.settings.bigquery_dataset}")
            try:
                client.get_dataset(dataset_ref)
            except Exception:
                client.create_dataset(dataset_ref, exists_ok=True)

            # Ensure tables
            tables = {
                "creatives": [
                    bigquery.SchemaField("creative_id", "STRING"),
                    bigquery.SchemaField("platform", "STRING"),
                    bigquery.SchemaField("title", "STRING"),
                    bigquery.SchemaField("text", "STRING"),
                    bigquery.SchemaField("hook", "STRING"),
                    bigquery.SchemaField("overlay_text", "STRING"),
                    bigquery.SchemaField("frame_desc", "STRING"),
                    bigquery.SchemaField("asset_uri", "STRING"),
                    bigquery.SchemaField("status", "STRING"),
                ],
                "performance": [
                    bigquery.SchemaField("creative_id", "STRING"),
                    bigquery.SchemaField("dt", "DATE"),
                    bigquery.SchemaField("impressions", "INT64"),
                    bigquery.SchemaField("clicks", "INT64"),
                    bigquery.SchemaField("spend", "FLOAT64"),
                    bigquery.SchemaField("conversions", "INT64"),
                    bigquery.SchemaField("revenue", "FLOAT64"),
                    bigquery.SchemaField("platform", "STRING"),
                ],
                "embeddings": [
                    bigquery.SchemaField("creative_id", "STRING"),
                    bigquery.SchemaField("model", "STRING"),
                    bigquery.SchemaField("vector", "BYTES"),
                ],
                "visual_features": [
                    bigquery.SchemaField("creative_id", "STRING"),
                    bigquery.SchemaField("width", "INT64"),
                    bigquery.SchemaField("height", "INT64"),
                    bigquery.SchemaField("ahash", "STRING"),
                    bigquery.SchemaField("dhash", "STRING"),
                    bigquery.SchemaField("dominant_colors", "STRING"),  # JSON list
                    bigquery.SchemaField("avg_brightness", "FLOAT64"),
                    bigquery.SchemaField("entropy", "FLOAT64"),
                    bigquery.SchemaField("overlay_text", "STRING"),
                    bigquery.SchemaField("overlay_density", "FLOAT64"),
                    bigquery.SchemaField("ts", "TIMESTAMP"),
                ],
                "actions": [
                    bigquery.SchemaField("action_type", "STRING"),
                    bigquery.SchemaField("target_platform", "STRING"),
                    bigquery.SchemaField("target_id", "STRING"),
                    bigquery.SchemaField("params", "STRING"),
                    bigquery.SchemaField("approved", "BOOL"),
                    bigquery.SchemaField("executed", "BOOL"),
                    bigquery.SchemaField("result_message", "STRING"),
                    bigquery.SchemaField("created_at", "TIMESTAMP"),
                ],
            }

            for name, schema in tables.items():
                table_ref = bigquery.Table(self._table_ref(name), schema=schema)
                try:
                    client.get_table(table_ref)
                except Exception:
                    client.create_table(table_ref, exists_ok=True)
        except Exception as e:
            log.error("Error ensuring BigQuery dataset/tables: %s", e)

    def upsert_creatives(self, df: pd.DataFrame) -> None:
        if not self.enabled:
            log.info("BQ disabled; skipping creatives upsert")
            return
        if df.empty:
            return
        try:
            from google.cloud import bigquery  # type: ignore
            job = self._client.load_table_from_dataframe(df, self._table_ref("creatives"))
            job.result()
            log.info("Upserted %d creatives into BQ", len(df))
        except Exception as e:
            log.error("Failed to upsert creatives: %s", e)

    def upsert_performance(self, df: pd.DataFrame) -> None:
        if not self.enabled:
            log.info("BQ disabled; skipping performance upsert")
            return
        if df.empty:
            return
        try:
            job = self._client.load_table_from_dataframe(df, self._table_ref("performance"))
            job.result()
            log.info("Upserted %d performance rows into BQ", len(df))
        except Exception as e:
            log.error("Failed to upsert performance: %s", e)

    def read_performance(self) -> pd.DataFrame:
        if not self.enabled:
            log.info("BQ disabled; returning empty performance DataFrame")
            return pd.DataFrame()
        try:
            sql = f"""
            SELECT creative_id, dt, impressions, clicks, spend, conversions, revenue, platform
            FROM `{self._table_ref('performance')}`
            """
            df = self._client.query(sql).result().to_dataframe()
            return df
        except Exception as e:
            log.error("Failed to read performance: %s", e)
            return pd.DataFrame()

    def upsert_visual_features(self, df: pd.DataFrame) -> None:
        if not self.enabled:
            log.info("BQ disabled; skipping visual_features upsert")
            return
        if df.empty:
            return
        try:
            self.ensure_dataset_and_tables()
            job = self._client.load_table_from_dataframe(df, self._table_ref("visual_features"))
            job.result()
            log.info("Upserted %d visual feature rows into BQ", len(df))
        except Exception as e:
            log.error("Failed to upsert visual_features: %s", e)
