"""
Google Ads OAuth Setup - Manual Method

This is an alternative OAuth flow that works when the automated method fails.
Instead of opening a local server, you manually copy-paste the authorization code.

This method works around OAuth consent screen issues and is more reliable.

Prerequisites:
1. Google Cloud Project with Google Ads API enabled
2. OAuth 2.0 Client ID credentials downloaded as JSON
3. Developer Token from Google Ads API Center

Usage:
    python scripts/setup_google_ads_oauth_manual.py --client-secrets client_secrets.json
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed.")
    print("\nInstall with:")
    print("  pip install requests")
    sys.exit(1)


# Google Ads API scope
SCOPES = ['https://www.googleapis.com/auth/adwords']


def load_client_secrets(client_secrets_path: str) -> dict:
    """Load and parse client secrets JSON file"""
    secrets_file = Path(client_secrets_path)

    if not secrets_file.exists():
        print(f"\n❌ ERROR: File not found: {client_secrets_path}")
        print("\nMake sure you've downloaded your OAuth 2.0 Client ID credentials")
        print("from Google Cloud Console > APIs & Services > Credentials")
        sys.exit(1)

    try:
        with open(secrets_file, 'r') as f:
            data = json.load(f)

        # Handle both desktop app and web app formats
        if 'installed' in data:
            config = data['installed']
        elif 'web' in data:
            config = data['web']
        else:
            print("\n❌ ERROR: Invalid client_secrets.json format")
            print("Expected 'installed' or 'web' key in JSON")
            sys.exit(1)

        return config

    except json.JSONDecodeError as e:
        print(f"\n❌ ERROR: Invalid JSON in {client_secrets_path}")
        print(f"Error: {e}")
        sys.exit(1)


def generate_auth_url(client_id: str, redirect_uri: str) -> str:
    """Generate the authorization URL"""
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
    }

    auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urlencode(params)
    return auth_url


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for access token and refresh token"""

    token_url = 'https://oauth2.googleapis.com/token'

    data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }

    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Token exchange failed: {e}")
        if response.text:
            print(f"Response: {response.text}")
        return None
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return None


def manual_oauth_flow(client_secrets_path: str) -> dict:
    """
    Run manual OAuth flow where user copies and pastes the authorization code.

    Args:
        client_secrets_path: Path to client_secrets.json

    Returns:
        Dictionary with OAuth credentials
    """
    print("\n" + "="*70)
    print("Google Ads OAuth Setup - Manual Method")
    print("="*70)

    # Load client secrets
    print(f"\n📂 Loading client secrets from: {client_secrets_path}")
    config = load_client_secrets(client_secrets_path)

    client_id = config.get('client_id')
    client_secret = config.get('client_secret')
    redirect_uris = config.get('redirect_uris', [])

    if not client_id or not client_secret:
        print("\n❌ ERROR: Missing client_id or client_secret in file")
        sys.exit(1)

    # Use first redirect URI or default to localhost
    redirect_uri = redirect_uris[0] if redirect_uris else 'http://localhost:8080'

    print(f"✓ Client ID: {client_id[:20]}...")
    print(f"✓ Redirect URI: {redirect_uri}")

    # Generate authorization URL
    auth_url = generate_auth_url(client_id, redirect_uri)

    # Display instructions
    print("\n" + "="*70)
    print("STEP 1: Authorize the Application")
    print("="*70)
    print("\n📋 Instructions:")
    print("1. Copy the URL below")
    print("2. Paste it into your web browser")
    print("3. Sign in with your Google account (the one with MCC access)")
    print("4. Grant the requested permissions")
    print("5. You may see an error page - that's OK!")
    print("6. Look at the URL in your browser's address bar")
    print("7. Copy the authorization code from the URL")
    print("\n" + "-"*70)
    print("🔗 Authorization URL:")
    print("-"*70)
    print(auth_url)
    print("-"*70)

    print("\n" + "="*70)
    print("STEP 2: Extract Authorization Code")
    print("="*70)
    print("\nAfter authorizing, your browser will redirect to a URL like:")
    print(f"  {redirect_uri}/?code=4/0AY0e-g7XXXXXXXXX&scope=...")
    print("\n📝 Copy everything between 'code=' and '&scope'")
    print("   Example: 4/0AY0e-g7XXXXXXXXX")

    # Get authorization code from user
    print("\n" + "="*70)
    print("STEP 3: Enter Authorization Code")
    print("="*70)

    auth_code = input("\n👉 Paste the authorization code here: ").strip()

    if not auth_code:
        print("\n❌ No code entered. Exiting.")
        sys.exit(1)

    # Exchange code for tokens
    print("\n" + "="*70)
    print("STEP 4: Exchange Code for Tokens")
    print("="*70)
    print("\n🔄 Exchanging authorization code for refresh token...")

    tokens = exchange_code_for_token(client_id, client_secret, auth_code, redirect_uri)

    if not tokens:
        print("\n❌ Failed to get tokens")
        print("\nCommon issues:")
        print("  1. Authorization code expired (they expire quickly - try again)")
        print("  2. Code already used (get a new one)")
        print("  3. Wrong client_id or client_secret")
        print("  4. Redirect URI mismatch")
        sys.exit(1)

    # Extract tokens
    refresh_token = tokens.get('refresh_token')
    access_token = tokens.get('access_token')

    if not refresh_token:
        print("\n⚠️  WARNING: No refresh_token in response")
        print("This might happen if you've authorized before.")
        print("\nTry:")
        print("  1. Go to https://myaccount.google.com/permissions")
        print("  2. Remove your app")
        print("  3. Run this script again")

        if 'error' in tokens:
            print(f"\nError: {tokens.get('error')}")
            print(f"Description: {tokens.get('error_description')}")

        sys.exit(1)

    print("\n✓ Successfully obtained tokens!")

    return {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'access_token': access_token,
    }


def test_credentials(developer_token: str, customer_id: str, credentials: dict):
    """Test the credentials by fetching account info"""
    print("\n" + "="*70)
    print("Testing Credentials")
    print("="*70)

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
        print(f"\n⚠️  Connection test failed: {e}")
        print("\nThis might be okay - save the credentials and try in your app.")


def main():
    parser = argparse.ArgumentParser(
        description='Generate Google Ads API refresh token (manual method)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate refresh token
    python scripts/setup_google_ads_oauth_manual.py --client-secrets client_secrets.json

    # Generate and test
    python scripts/setup_google_ads_oauth_manual.py \\
        --client-secrets client_secrets.json \\
        --developer-token YOUR_TOKEN \\
        --customer-id 123-456-7890

Why use this script?
    - Works when automated OAuth fails
    - Bypasses "Access blocked" errors
    - More reliable for debugging
    - No local server needed
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

    # Run manual OAuth flow
    credentials = manual_oauth_flow(args.client_secrets)

    # Display results
    print("\n" + "="*70)
    print("🎉 SUCCESS! Save These Credentials:")
    print("="*70)

    print("\nAdd to your .env file:")
    print("-" * 70)
    print(f"CLIENT_1_GOOGLE_ADS_CLIENT_ID={credentials['client_id']}")
    print(f"CLIENT_1_GOOGLE_ADS_CLIENT_SECRET={credentials['client_secret']}")
    print(f"CLIENT_1_GOOGLE_ADS_REFRESH_TOKEN={credentials['refresh_token']}")
    print("-" * 70)

    # Test if credentials provided
    if args.developer_token and args.customer_id:
        test_credentials(args.developer_token, args.customer_id, credentials)
    else:
        print("\n💡 Tip: Run with --developer-token and --customer-id to test")
        print("   the connection immediately.")

    print("\n" + "="*70)
    print("Next Steps:")
    print("="*70)
    print("\n1. Add the credentials above to your .env file")
    print("2. Add your developer token:")
    print("   CLIENT_1_GOOGLE_ADS_DEVELOPER_TOKEN=your_token")
    print("3. Add Wren's customer ID:")
    print("   CLIENT_1_GOOGLE_ADS_CUSTOMER_ID=123-456-7890")
    print("4. Test connection:")
    print("   python scripts/test_google_ads_connection.py")
    print("5. Run your app:")
    print("   streamlit run src/app.py")
    print("\n")


if __name__ == "__main__":
    main()
