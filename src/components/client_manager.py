"""Client Management Module - Handles multi-client operations"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import asdict

from .models import Client
from .db.bq_client import BigQueryClient
from .config import Settings
from .utils.logging import get_logger

log = get_logger(__name__)


class ClientManager:
    """Manages multiple client configurations"""

    def __init__(self, bq_client: BigQueryClient):
        self.bq = bq_client
        self._cache: Dict[str, Client] = {}
        self._mock_clients: List[Client] = self._get_mock_clients()
        self._env_clients: Optional[List[Client]] = None

    def _get_mock_clients(self) -> List[Client]:
        """Default mock clients for testing"""
        return [
            Client(
                client_id="demo_client_1",
                client_name="Demo Client 1",
                is_active=True,
                notes="Mock client for testing",
                created_at=datetime.now(),
            ),
            Client(
                client_id="demo_client_2",
                client_name="Demo Client 2",
                is_active=True,
                notes="Another mock client",
                created_at=datetime.now(),
            )
        ]

    def _load_clients_from_env(self) -> List[Client]:
        """
        Load clients from environment variables

        Supports pattern: CLIENT_{N}_{PLATFORM}_{FIELD}
        Example: CLIENT_1_META_ACCESS_TOKEN, CLIENT_2_GOOGLE_ADS_CLIENT_ID
        """
        if self._env_clients is not None:
            return self._env_clients

        clients = []
        client_numbers = set()

        # Find all CLIENT_N_ prefixes
        for key in os.environ.keys():
            if key.startswith("CLIENT_") and "_NAME" in key:
                # Extract client number
                try:
                    num_str = key.split("_")[1]
                    client_numbers.add(int(num_str))
                except (IndexError, ValueError):
                    continue

        # Load each client
        for num in sorted(client_numbers):
            prefix = f"CLIENT_{num}_"

            client_name = os.getenv(f"{prefix}NAME")
            if not client_name:
                log.warning(f"Skipping client {num}: no name found")
                continue

            # Generate consistent client_id from environment
            client_id = f"env_client_{num}"

            is_active_str = os.getenv(f"{prefix}IS_ACTIVE", "true").lower()
            is_active = is_active_str in ["true", "1", "yes"]

            client = Client(
                client_id=client_id,
                client_name=client_name,
                is_active=is_active,
                # Meta
                meta_access_token=os.getenv(f"{prefix}META_ACCESS_TOKEN"),
                meta_ad_account_id=os.getenv(f"{prefix}META_AD_ACCOUNT_ID"),
                meta_api_version=os.getenv(f"{prefix}META_API_VERSION", "v19.0"),
                # Google Ads
                google_ads_developer_token=os.getenv(f"{prefix}GOOGLE_ADS_DEVELOPER_TOKEN"),
                google_ads_client_id=os.getenv(f"{prefix}GOOGLE_ADS_CLIENT_ID"),
                google_ads_client_secret=os.getenv(f"{prefix}GOOGLE_ADS_CLIENT_SECRET"),
                google_ads_refresh_token=os.getenv(f"{prefix}GOOGLE_ADS_REFRESH_TOKEN"),
                google_ads_customer_id=os.getenv(f"{prefix}GOOGLE_ADS_CUSTOMER_ID"),
                google_ads_mcc_id=os.getenv(f"{prefix}GOOGLE_ADS_MCC_ID"),
                # TikTok
                tiktok_access_token=os.getenv(f"{prefix}TIKTOK_ACCESS_TOKEN"),
                tiktok_app_id=os.getenv(f"{prefix}TIKTOK_APP_ID"),
                tiktok_secret=os.getenv(f"{prefix}TIKTOK_SECRET"),
                tiktok_advertiser_id=os.getenv(f"{prefix}TIKTOK_ADVERTISER_ID"),
                # Pinterest
                pinterest_access_token=os.getenv(f"{prefix}PINTEREST_ACCESS_TOKEN"),
                pinterest_ad_account_id=os.getenv(f"{prefix}PINTEREST_AD_ACCOUNT_ID"),
                # LinkedIn
                linkedin_access_token=os.getenv(f"{prefix}LINKEDIN_ACCESS_TOKEN"),
                linkedin_ad_account_id=os.getenv(f"{prefix}LINKEDIN_AD_ACCOUNT_ID"),
                # Metadata
                notes=os.getenv(f"{prefix}NOTES"),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            clients.append(client)
            log.info(f"Loaded client from environment: {client_name} (ID: {client_id})")

        self._env_clients = clients
        return clients

    def list_clients(self, active_only: bool = True, use_mock: bool = False) -> List[Client]:
        """
        Get all clients from environment variables or mock data.

        Priority:
        1. Environment variables (production/local with .env)
        2. Mock clients (testing only)
        """
        # Use mock clients for testing
        if use_mock:
            clients = [c for c in self._mock_clients if not active_only or c.is_active]
            log.info("Using mock clients: %d clients", len(clients))
            return clients

        # Load from environment variables (production/local)
        env_clients = self._load_clients_from_env()
        if env_clients:
            clients = [c for c in env_clients if not active_only or c.is_active]
            log.info("Using clients from environment variables: %d clients", len(clients))
            return clients

        # No environment variables found, fallback to mock
        log.warning("No CLIENT_N_NAME environment variables found, using mock clients")
        clients = [c for c in self._mock_clients if not active_only or c.is_active]
        return clients

    def get_client(self, client_id: str, use_mock: bool = False) -> Optional[Client]:
        """Get a single client by ID from environment variables or mock data"""
        # Get all clients
        clients = self.list_clients(active_only=False, use_mock=use_mock)

        # Find the requested client
        for client in clients:
            if client.client_id == client_id:
                return client

        return None

    def get_client_for_platform(self, client_id: str, platform: str, use_mock: bool = False) -> Optional[Dict[str, Any]]:
        """Get platform-specific credentials for a client"""
        client = self.get_client(client_id, use_mock=use_mock)
        if not client:
            return None

        credentials = {}

        if platform == "meta":
            credentials = {
                "access_token": client.meta_access_token,
                "ad_account_id": client.meta_ad_account_id,
                "api_version": client.meta_api_version,
            }
        elif platform == "google":
            credentials = {
                "developer_token": client.google_ads_developer_token,
                "client_id": client.google_ads_client_id,
                "client_secret": client.google_ads_client_secret,
                "refresh_token": client.google_ads_refresh_token,
                "customer_id": client.google_ads_customer_id,
                "mcc_id": client.google_ads_mcc_id,
            }
        elif platform == "tiktok":
            credentials = {
                "access_token": client.tiktok_access_token,
                "app_id": client.tiktok_app_id,
                "secret": client.tiktok_secret,
                "advertiser_id": client.tiktok_advertiser_id,
            }
        elif platform == "pinterest":
            credentials = {
                "access_token": client.pinterest_access_token,
                "ad_account_id": client.pinterest_ad_account_id,
            }
        elif platform == "linkedin":
            credentials = {
                "access_token": client.linkedin_access_token,
                "ad_account_id": client.linkedin_ad_account_id,
            }

        return credentials if any(credentials.values()) else None
