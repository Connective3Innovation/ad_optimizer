"""
List All Google Ads Accounts Under MCC

This script lists all client accounts under your MCC (Manager) account.
Use this to find the correct customer_id to use for fetching campaigns and ads.

Usage:
    python scripts/list_google_ads_accounts.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def load_env():
    """Load .env file"""
    try:
        from dotenv import load_dotenv
        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return True
    except ImportError:
        pass
    return False


def list_accounts(developer_token, client_id, client_secret, refresh_token, mcc_customer_id):
    """List all accounts under MCC"""

    print("\n" + "="*80)
    print("Google Ads Account Hierarchy")
    print("="*80)

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
    except ImportError:
        print("\n❌ google-ads package not installed")
        print("\nInstall with: pip install google-ads")
        return False

    if not all([developer_token, client_id, client_secret, refresh_token, mcc_customer_id]):
        print("\n❌ Missing required credentials")
        return False

    # Create client
    credentials = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "login_customer_id": mcc_customer_id.replace("-", ""),
        "use_proto_plus": True,
    }

    try:
        client = GoogleAdsClient.load_from_dict(credentials)
        ga_service = client.get_service("GoogleAdsService")

        # Query for all client accounts
        print(f"\n🔍 Searching for accounts under MCC: {mcc_customer_id}\n")

        query = """
            SELECT
                customer_client.id,
                customer_client.descriptive_name,
                customer_client.manager,
                customer_client.currency_code,
                customer_client.status,
                customer_client.level
            FROM customer_client
            WHERE customer_client.status = 'ENABLED'
            ORDER BY customer_client.level, customer_client.descriptive_name
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = mcc_customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)

        accounts = list(response)

        if not accounts:
            print("⚠️  No client accounts found under this MCC")
            print("\nMake sure:")
            print("  1. You're using an MCC account ID")
            print("  2. The MCC has client accounts linked")
            print("  3. Your OAuth account has access to the MCC")
            return False

        print(f"📊 Found {len(accounts)} account(s):\n")
        print(f"{'Level':<7} {'Type':<10} {'Customer ID':<15} {'Currency':<10} {'Account Name':<40}")
        print("-" * 90)

        client_accounts = []
        mcc_accounts = []

        for row in accounts:
            customer = row.customer_client
            customer_id_formatted = str(customer.id)

            # Format with dashes: 123-456-7890
            if len(customer_id_formatted) == 10:
                customer_id_formatted = f"{customer_id_formatted[:3]}-{customer_id_formatted[3:6]}-{customer_id_formatted[6:]}"

            account_type = "MCC" if customer.manager else "Client"
            level = customer.level if hasattr(customer, 'level') else "N/A"

            print(f"{str(level):<7} {account_type:<10} {customer_id_formatted:<15} {customer.currency_code:<10} {customer.descriptive_name:<40}")

            if not customer.manager:
                client_accounts.append({
                    'id': customer_id_formatted,
                    'name': customer.descriptive_name,
                    'currency': customer.currency_code
                })
            else:
                mcc_accounts.append({
                    'id': customer_id_formatted,
                    'name': customer.descriptive_name
                })

        # Now check which accounts have campaigns
        print("\n" + "="*80)
        print("Checking for Active Campaigns")
        print("="*80 + "\n")

        if not client_accounts:
            print("⚠️  No client accounts found (only MCC accounts)")
            return False

        accounts_with_campaigns = []

        for account in client_accounts:
            try:
                campaign_query = """
                    SELECT campaign.id, campaign.name, campaign.status
                    FROM campaign
                    WHERE campaign.status IN ('ENABLED', 'PAUSED')
                    LIMIT 10
                """

                search_request = client.get_type("SearchGoogleAdsRequest")
                search_request.customer_id = account['id'].replace("-", "")
                search_request.query = campaign_query

                campaign_response = ga_service.search(request=search_request)
                campaigns = list(campaign_response)

                if campaigns:
                    print(f"✓ {account['name']:<40} ({account['id']})")
                    print(f"  └─ {len(campaigns)} campaign(s) found")

                    for idx, camp_row in enumerate(campaigns[:3], 1):
                        print(f"     {idx}. {camp_row.campaign.name} ({camp_row.campaign.status.name})")

                    if len(campaigns) > 3:
                        print(f"     ... and {len(campaigns) - 3} more")
                    print()

                    accounts_with_campaigns.append(account)

            except GoogleAdsException as ex:
                # Some accounts might not be accessible
                continue
            except Exception:
                continue

        # Summary
        print("="*80)
        print("📋 SUMMARY")
        print("="*80)
        print(f"\nYour MCC: {mcc_customer_id}")
        print(f"Total client accounts: {len(client_accounts)}")
        print(f"Accounts with campaigns: {len(accounts_with_campaigns)}")

        if accounts_with_campaigns:
            print("\n✅ RECOMMENDED: Update your .env with one of these accounts:")
            print("-" * 80)
            for account in accounts_with_campaigns:
                print(f"\n# For {account['name']}")
                print(f"CLIENT_1_GOOGLE_ADS_MCC_ID={mcc_customer_id}")
                print(f"CLIENT_1_GOOGLE_ADS_CUSTOMER_ID={account['id']}")
                print(f"# Keep your existing OAuth credentials the same")
        else:
            print("\n⚠️  No accounts with active campaigns found")
            print("\nPossible reasons:")
            print("  1. Campaigns are in REMOVED status")
            print("  2. No campaigns exist yet")
            print("  3. Access permissions issue")

        print("\n" + "="*80 + "\n")
        return True

    except GoogleAdsException as ex:
        print(f"\n❌ Google Ads API Error: {ex.failure.errors[0].message}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def main():
    load_env()

    # Get credentials from environment
    developer_token = os.getenv("CLIENT_1_GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id = os.getenv("CLIENT_1_GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("CLIENT_1_GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.getenv("CLIENT_1_GOOGLE_ADS_REFRESH_TOKEN")
    mcc_customer_id = os.getenv("CLIENT_1_GOOGLE_ADS_CUSTOMER_ID")

    success = list_accounts(
        developer_token=developer_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        mcc_customer_id=mcc_customer_id
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
