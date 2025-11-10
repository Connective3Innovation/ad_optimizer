"""
Google Ads OAuth Setup Helper

This script helps you generate the refresh token needed for Google Ads API access.
Run this once to get your refresh token, then save it in your .env file.

Prerequisites:
1. Google Cloud Project with Google Ads API enabled
2. OAuth 2.0 Client ID credentials downloaded as JSON
3. Developer Token from Google Ads API Center

Usage:
    python scripts/setup_google_ads_oauth.py --client-secrets path/to/client_secrets.json
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    print("ERROR: Required packages not installed.")
    print("\nInstall with:")
    print("  pip install google-auth-oauthlib google-auth-httplib2 google-ads")
    sys.exit(1)


# Google Ads API scope
SCOPES = ['https://www.googleapis.com/auth/adwords']


def generate_refresh_token(client_secrets_path: str) -> dict:
    """
    Run OAuth flow to generate refresh token.

    Args:
        client_secrets_path: Path to client_secrets.json from Google Cloud Console

    Returns:
        Dictionary with OAuth credentials
    """
    print("\n" + "="*60)
    print("Google Ads OAuth Setup")
    print("="*60)

    # Check if file exists
    secrets_file = Path(client_secrets_path)
    if not secrets_file.exists():
        print(f"\nERROR: File not found: {client_secrets_path}")
        print("\nMake sure you've downloaded your OAuth 2.0 Client ID credentials")
        print("from Google Cloud Console > APIs & Services > Credentials")
        sys.exit(1)

    print(f"\n✓ Found client secrets file: {secrets_file}")

    # Run OAuth flow
    print("\n📝 Starting OAuth authorization flow...")
    print("   Your browser will open automatically.")
    print("   Sign in with the Google account that has access to Google Ads.")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_file),
            scopes=SCOPES
        )

        # Run local server for OAuth callback
        credentials = flow.run_local_server(
            port=8080,
            prompt='consent',
            success_message='Authorization successful! You can close this window.'
        )

        print("\n✓ Authorization successful!")

        # Extract credentials
        result = {
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'refresh_token': credentials.refresh_token,
            'access_token': credentials.token,
        }

        return result

    except Exception as e:
        print(f"\n❌ OAuth flow failed: {e}")
        print("\nCommon issues:")
        print("  1. Make sure the redirect URI http://localhost:8080 is added")
        print("     to your OAuth client in Google Cloud Console")
        print("  2. Check that you're using the correct Google account")
        print("  3. Ensure Google Ads API is enabled in your project")
        sys.exit(1)


def test_credentials(developer_token: str, customer_id: str, credentials: dict):
    """
    Test the credentials by fetching account info.

    Args:
        developer_token: Your Google Ads developer token
        customer_id: Customer ID to test (format: 123-456-7890)
        credentials: OAuth credentials dict
    """
    print("\n" + "="*60)
    print("Testing Credentials")
    print("="*60)

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("\n⚠️  google-ads package not installed. Skipping test.")
        print("   Install with: pip install google-ads")
        return

    try:
        # Create client configuration
        config = {
            "developer_token": developer_token,
            "client_id": credentials['client_id'],
            "client_secret": credentials['client_secret'],
            "refresh_token": credentials['refresh_token'],
            "login_customer_id": customer_id.replace("-", ""),
            "use_proto_plus": True,
        }

        print(f"\n🔍 Testing connection to Customer ID: {customer_id}")

        # Initialize client
        client = GoogleAdsClient.load_from_dict(config)

        # Try a simple query
        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code
            FROM customer
            LIMIT 1
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)

        for row in response:
            print(f"\n✓ Connection successful!")
            print(f"  Account Name: {row.customer.descriptive_name}")
            print(f"  Customer ID: {row.customer.id}")
            print(f"  Currency: {row.customer.currency_code}")
            return

    except Exception as e:
        print(f"\n❌ Connection test failed: {e}")
        print("\nThis might be okay - save the credentials and try in your app.")
        print("Common issues:")
        print("  1. Wrong Customer ID format (use 123-456-7890)")
        print("  2. Developer token not approved yet (use test account)")
        print("  3. Account doesn't have API access enabled")


def main():
    parser = argparse.ArgumentParser(
        description='Generate Google Ads API refresh token',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate refresh token
    python scripts/setup_google_ads_oauth.py --client-secrets client_secrets.json

    # Generate and test
    python scripts/setup_google_ads_oauth.py \\
        --client-secrets client_secrets.json \\
        --developer-token YOUR_TOKEN \\
        --customer-id 123-456-7890
        """
    )

    parser.add_argument(
        '--client-secrets',
        required=True,
        help='Path to client_secrets.json from Google Cloud Console'
    )

    parser.add_argument(
        '--developer-token',
        help='Your Google Ads developer token (for testing connection)'
    )

    parser.add_argument(
        '--customer-id',
        help='Customer ID to test (format: 123-456-7890)'
    )

    args = parser.parse_args()

    # Generate refresh token
    credentials = generate_refresh_token(args.client_secrets)

    # Display results
    print("\n" + "="*60)
    print("🎉 Success! Save these credentials:")
    print("="*60)

    print("\nAdd to your .env file:")
    print("-" * 60)
    print(f"CLIENT_1_GOOGLE_ADS_CLIENT_ID={credentials['client_id']}")
    print(f"CLIENT_1_GOOGLE_ADS_CLIENT_SECRET={credentials['client_secret']}")
    print(f"CLIENT_1_GOOGLE_ADS_REFRESH_TOKEN={credentials['refresh_token']}")
    print("-" * 60)

    # Test if credentials provided
    if args.developer_token and args.customer_id:
        test_credentials(args.developer_token, args.customer_id, credentials)
    else:
        print("\n💡 Tip: Run with --developer-token and --customer-id to test")
        print("   the connection immediately.")

    print("\n" + "="*60)
    print("Next Steps:")
    print("="*60)
    print("\n1. Add the credentials above to your .env file")
    print("2. Add your developer token:")
    print("   CLIENT_1_GOOGLE_ADS_DEVELOPER_TOKEN=your_token")
    print("3. Add Wren's customer ID:")
    print("   CLIENT_1_GOOGLE_ADS_CUSTOMER_ID=123-456-7890")
    print("4. Restart your app and test!")
    print("\n")


if __name__ == "__main__":
    main()
