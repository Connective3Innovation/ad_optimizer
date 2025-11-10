"""
Test Google Ads API Connection

Quick script to verify your Google Ads credentials are working.
Run this after setting up your .env file.

Usage:
    python scripts/test_google_ads_connection.py

    # Or specify credentials manually:
    python scripts/test_google_ads_connection.py \
        --developer-token YOUR_TOKEN \
        --client-id YOUR_ID \
        --client-secret YOUR_SECRET \
        --refresh-token YOUR_REFRESH \
        --customer-id 123-456-7890
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def load_env_if_available():
    """Try to load .env file"""
    try:
        from dotenv import load_dotenv
        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✓ Loaded environment from: {env_path}")
        else:
            print("⚠️  No .env file found, using command-line args or environment")
    except ImportError:
        print("⚠️  python-dotenv not installed, skipping .env loading")


def test_connection(developer_token, client_id, client_secret, refresh_token, customer_id, mcc_id=None):
    """Test Google Ads API connection"""

    print("\n" + "="*60)
    print("Testing Google Ads API Connection")
    print("="*60)

    # Check if google-ads is installed
    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
    except ImportError:
        print("\n❌ google-ads package not installed")
        print("\nInstall with:")
        print("  pip install google-ads")
        return False

    # Validate inputs
    if not all([developer_token, client_id, client_secret, refresh_token, customer_id]):
        print("\n❌ Missing required credentials")
        print("\nRequired:")
        print(f"  Developer Token: {'✓' if developer_token else '✗'}")
        print(f"  Client ID: {'✓' if client_id else '✗'}")
        print(f"  Client Secret: {'✓' if client_secret else '✗'}")
        print(f"  Refresh Token: {'✓' if refresh_token else '✗'}")
        print(f"  Customer ID: {'✓' if customer_id else '✗'}")
        print("\nProvide via .env file or command-line arguments")
        return False

    # Use MCC ID for authentication if provided
    login_id = mcc_id if mcc_id else customer_id

    print(f"\n📋 Configuration:")
    print(f"   Developer Token: {developer_token[:10]}...")
    print(f"   Client ID: {client_id[:20]}...")
    print(f"   Client Secret: {client_secret[:10]}...")
    print(f"   Refresh Token: {refresh_token[:20]}...")
    if mcc_id:
        print(f"   MCC ID (for auth): {mcc_id}")
        print(f"   Customer ID (for queries): {customer_id}")
    else:
        print(f"   Customer ID: {customer_id}")

    # Create client configuration
    credentials = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "login_customer_id": login_id.replace("-", ""),
        "use_proto_plus": True,
    }

    try:
        # Initialize client
        print(f"\n🔌 Connecting to Google Ads API...")
        client = GoogleAdsClient.load_from_dict(credentials)
        ga_service = client.get_service("GoogleAdsService")

        # Test 1: Get customer info
        print(f"\n📊 Test 1: Fetching account information...")
        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code,
                customer.time_zone,
                customer.manager
            FROM customer
            LIMIT 1
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)

        for row in response:
            customer = row.customer
            print(f"   ✓ Account Name: {customer.descriptive_name}")
            print(f"   ✓ Customer ID: {customer.id}")
            print(f"   ✓ Currency: {customer.currency_code}")
            print(f"   ✓ Time Zone: {customer.time_zone}")
            print(f"   ✓ Is Manager Account: {customer.manager}")

            if customer.manager:
                print(f"\n   ⚠️  This is an MCC (Manager) account!")
                print(f"   💡 MCC accounts don't have campaigns directly.")
                print(f"   💡 Run: python scripts/list_google_ads_accounts.py")
                print(f"   💡 to find child accounts with campaigns.")

        # Test 2: Count campaigns
        print(f"\n📊 Test 2: Counting campaigns...")
        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            LIMIT 10
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)

        campaigns = list(response)
        print(f"   ✓ Found {len(campaigns)} campaign(s)")

        if campaigns:
            print(f"\n   Sample campaigns:")
            for idx, row in enumerate(campaigns[:3], 1):
                print(f"   {idx}. {row.campaign.name} (ID: {row.campaign.id}, Status: {row.campaign.status.name})")

        # Test 3: Count ad groups
        print(f"\n📊 Test 3: Counting ad groups...")
        query = """
            SELECT
                ad_group.id,
                ad_group.name
            FROM ad_group
            WHERE ad_group.status != 'REMOVED'
            LIMIT 5
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)
        ad_groups = list(response)
        print(f"   ✓ Found {len(ad_groups)} ad group(s)")

        # Test 4: Count ads
        print(f"\n📊 Test 4: Counting ads...")
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.name,
                ad_group_ad.status
            FROM ad_group_ad
            WHERE ad_group_ad.status != 'REMOVED'
            LIMIT 5
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)
        ads = list(response)
        print(f"   ✓ Found {len(ads)} ad(s)")

        # Success!
        print("\n" + "="*60)
        print("🎉 SUCCESS! All tests passed!")
        print("="*60)
        print("\n✓ Your Google Ads credentials are working correctly")
        print("✓ You can now use Google Ads in your Ad Optimizer app")
        print("\nNext steps:")
        print("  1. Restart your Streamlit app: streamlit run src/app.py")
        print("  2. Select your client from the dropdown")
        print("  3. Choose 'Google Ads' as the platform")
        print("  4. Start optimizing!")
        print()

        return True

    except GoogleAdsException as ex:
        print(f"\n❌ Google Ads API Error")
        print(f"\nError: {ex.error.code().name}")
        print(f"Message: {ex.failure.errors[0].message}")

        # Common error handling
        error_code = ex.error.code().name

        if "AUTHENTICATION_ERROR" in error_code:
            print("\n💡 Troubleshooting:")
            print("  1. Check your developer token is correct")
            print("  2. Re-run OAuth flow to get new refresh token:")
            print("     python scripts/setup_google_ads_oauth.py --client-secrets client_secrets.json")
            print("  3. Verify OAuth credentials (client_id, client_secret)")

        elif "AUTHORIZATION_ERROR" in error_code:
            print("\n💡 Troubleshooting:")
            print("  1. Verify customer ID is correct (use format: 123-456-7890)")
            print("  2. Check that OAuth account has access to this customer")
            print("  3. For MCC accounts, make sure you're using the client's customer ID")

        elif "DEVELOPER_TOKEN" in error_code:
            print("\n💡 Troubleshooting:")
            print("  1. Check developer token from MCC > Tools > API Center")
            print("  2. Use test account if not approved for Standard Access")
            print("  3. Make sure token is from MCC account, not client account")

        return False

    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        print(f"\nError type: {type(e).__name__}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Test Google Ads API connection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use credentials from .env file
    python scripts/test_google_ads_connection.py

    # Use specific client from .env (default is CLIENT_1)
    python scripts/test_google_ads_connection.py --client-num 2

    # Provide credentials manually
    python scripts/test_google_ads_connection.py \\
        --developer-token YOUR_TOKEN \\
        --client-id YOUR_ID \\
        --client-secret YOUR_SECRET \\
        --refresh-token YOUR_REFRESH \\
        --customer-id 123-456-7890
        """
    )

    parser.add_argument('--developer-token', help='Google Ads developer token')
    parser.add_argument('--client-id', help='OAuth client ID')
    parser.add_argument('--client-secret', help='OAuth client secret')
    parser.add_argument('--refresh-token', help='OAuth refresh token')
    parser.add_argument('--customer-id', help='Customer ID (format: 123-456-7890)')
    parser.add_argument('--mcc-id', help='MCC ID for authentication (if using MCC account)')
    parser.add_argument('--client-num', type=int, default=1, help='Client number from .env (default: 1)')

    args = parser.parse_args()

    # Load .env if available
    load_env_if_available()

    # Get credentials from args or environment
    prefix = f"CLIENT_{args.client_num}_"

    developer_token = args.developer_token or os.getenv(f"{prefix}GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id = args.client_id or os.getenv(f"{prefix}GOOGLE_ADS_CLIENT_ID")
    client_secret = args.client_secret or os.getenv(f"{prefix}GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = args.refresh_token or os.getenv(f"{prefix}GOOGLE_ADS_REFRESH_TOKEN")
    customer_id = args.customer_id or os.getenv(f"{prefix}GOOGLE_ADS_CUSTOMER_ID")
    mcc_id = args.mcc_id or os.getenv(f"{prefix}GOOGLE_ADS_MCC_ID")

    # Run test
    success = test_connection(
        developer_token=developer_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        customer_id=customer_id,
        mcc_id=mcc_id
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
