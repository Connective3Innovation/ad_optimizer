# Ad Creative Auto-Optimizer

## Multi-Platform, Multi-Client Advertising Optimization System

A comprehensive solution for managing advertising campaigns across Meta, Google Ads, TikTok, Pinterest, and LinkedIn with AI-powered insights, statistical A/B testing, and automated optimization.

### 🎯 Key Features

- **5 Platform Integrations**: Meta, Google Ads, TikTok, Pinterest, LinkedIn
- **Multi-Client Management**: Unlimited clients with separate credentials
- **A/B Testing**: Statistical significance testing with confidence levels
- **Creative Fatigue Detection**: Automatically identify underperforming ads
- **LLM + Vision Scoring**: AI-powered creative analysis and variant generation
- **Guardrailed Agent**: Safe, approval-based automated actions
- **BigQuery Integration**: Enterprise-grade data warehousing
- **Mock Mode**: Test all features without API credentials

---

## 🚀 Quick Start (5 Minutes)

See [docs/QUICK_START.md](docs/QUICK_START.md) for detailed instructions.

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the App

```bash
streamlit run src/app.py
```

### 3. Test with Mock Data (No Credentials Needed)

1) Python 3.11+
2) Create and activate a virtual environment
   - Windows: `python -m venv .venv && .\.venv\Scripts\activate`
   - macOS/Linux: `python -m venv .venv && source .venv/bin/activate`
3) Install dependencies: `pip install -r requirements.txt`
4) Run the app: `streamlit run src/app.py`
5) Toggle "Use mock data" ON in sidebar
6) Select a demo client and platform
7) Explore all features!

- The app defaults to mock data from `data/sample/`. No cloud creds required.
- If you have no OpenAI key, the app will use deterministic heuristic scoring as a fallback.
- Vision features work without cloud; remote image URLs require internet. OCR is optional (needs Tesseract + `pytesseract`).

---

## 🔐 Credential Management

### Recommended: Environment Variables (.env file)

**For local development and GCP deployment** (matches your workflow!)

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your credentials
nano .env

# 3. Add your clients
CLIENT_1_NAME=My Company
CLIENT_1_META_ACCESS_TOKEN=EAABsbCS...
CLIENT_1_GOOGLE_ADS_DEVELOPER_TOKEN=abc123...

# 4. Run
streamlit run src/app.py
```

**See [ENV_SETUP_QUICKSTART.md](ENV_SETUP_QUICKSTART.md)** for complete guide.

### Alternative: UI-Based Client Management

Add clients directly in the app:
1. Go to "👥 Client Management" tab
2. Click "➕ Add New Client"
3. Fill in credentials
4. Saved to BigQuery (requires GCP setup)

### Alternative: Streamlit Secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill values.

BigQuery Setup (Optional for cloud mode)

- Create a dataset (default: `ad_creative_auto_optimizer`)
- Grant BigQuery Admin/Editor to your service account or use ADC
- The app will attempt to create tables if missing:
  - `creatives`
  - `performance`
  - `embeddings`
  - `actions`

Project Structure

- `src/app.py` — Streamlit showcase app
- `src/components` — Modular components
  - `config.py` — settings and secrets handling
  - `models.py` — core data models
  - `utils/logging.py` — logging setup
  - `db/bq_client.py` — BigQuery client + fallbacks
  - `data_sources/` — platform/analytics connectors (mockable)
  - `assets/storage.py` — GCS access (optional)
  - `llm/openai_client.py` — LLM + vision wrappers with fallbacks
  - `optimizer/` — fatigue detection + concept generation
  - `vision/` — image features (aHash/dHash, colors, brightness, OCR overlay)
  - `guardrails/safety.py` — brand safety and compliance checks
  - `agent/actions.py` — approval queue + execution stubs
- `data/sample/` — mock creatives and performance CSVs

Running With Real Keys

- OpenAI: set `OPENAI_API_KEY` or fill `openai_api_key` in Streamlit secrets.
- GCP: set `GOOGLE_APPLICATION_CREDENTIALS` to a service account JSON or supply `gcp_credentials_json` in secrets.
- BigQuery: set `GCP_PROJECT_ID` and `BIGQUERY_DATASET` (secrets or env).

Notes

- Network calls are optional at runtime. In environments without credentials or network access, the app uses mocks/heuristics.
- Extend the platform connectors in `src/components/data_sources/ads/` to call real APIs.
- Extend `optimizer/next_best_concepts.py` to incorporate your proprietary “creative → lift” embeddings.
- Vision: Install Tesseract locally if you want OCR overlay text/density (optional). Without it, features still compute except OCR.

Deploy to GCP (Cloud Run)

- Container build is provided by `Dockerfile`.
- GitHub Actions workflow `.github/workflows/cicd.yml` builds, pushes to Artifact Registry, and deploys to Cloud Run.

Prereqs

- Enable APIs in your GCP project: Cloud Run, Artifact Registry, IAM, Secret Manager, BigQuery.
- Create an Artifact Registry repository (format: Docker):
  - Example: `gcloud artifacts repositories create ad-optimizer --repository-format=docker --location=us-central1`
- Create a Secret Manager secret for your OpenAI key:
  - `echo -n "$OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-`
  - Grant your Cloud Run runtime service account Secret Manager Accessor.
- Recommended: Create a dedicated runtime service account for Cloud Run with minimal roles (BQ read/write if used).

GitHub Setup (Workload Identity Federation)

- Create a Workload Identity Pool + Provider and bind your GitHub repo to a GCP service account.
- In your Gitstreamlit run src/app.pyHub repo, add Secrets:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER` — resource name of the WIF provider
  - `GCP_SERVICE_ACCOUNT` — service account email (for deploy)
  - `GCP_PROJECT_ID` — your project id
  - `GCP_REGION` — e.g., `us-central1`
  - `GAR_REPOSITORY` — Artifact Registry repo name (e.g., `ad-optimizer`)
  - `CLOUD_RUN_SERVICE` — Cloud Run service name (e.g., `ad-creative-auto-optimizer`)
  - Optional: `BIGQUERY_DATASET` if not using the default

Deploy via GitHub Actions

- Push to `main` and the workflow will:
  - Build the Docker image
  - Push to `REGION-docker.pkg.dev/PROJECT/REPO/SERVICE:SHA`
  - Deploy to Cloud Run with:
    - `USE_MOCK_DATA=false`, `DRY_RUN=false`, `REQUIRE_APPROVAL=true`, and `GCP_PROJECT_ID` set
    - `OPENAI_API_KEY` sourced from Secret Manager (`OPENAI_API_KEY:latest`)

Manual Deploy (optional)

- Build and push locally (substitute values):
  - `docker build -t us-central1-docker.pkg.dev/PROJECT/REPO/SERVICE:dev .`
  - `gcloud auth configure-docker us-central1-docker.pkg.dev`
  - `docker push us-central1-docker.pkg.dev/PROJECT/REPO/SERVICE:dev`
- Deploy:
  - `gcloud run deploy SERVICE --image us-central1-docker.pkg.dev/PROJECT/REPO/SERVICE:dev --region us-central1 --platform managed --allow-unauthenticated --update-env-vars USE_MOCK_DATA=false,DRY_RUN=false,REQUIRE_APPROVAL=true,GCP_PROJECT_ID=PROJECT --update-secrets OPENAI_API_KEY=OPENAI_API_KEY:latest`

Git Hygiene

- `.gitignore` excludes local env/secrets and virtualenvs.
- `.dockerignore` keeps the image small and avoids bundling secrets.

---

## 📚 Documentation

### Getting Started
- **[Quick Start Guide](docs/QUICK_START.md)** - Get running in 5 minutes
- **[Environment Variables Setup](ENV_SETUP_QUICKSTART.md)** - Credential management (recommended)
- **[API Credentials Guide](API_CREDENTIALS_GUIDE.md)** - Get credentials for each platform
- **[Credentials Location Guide](CREDENTIALS_LOCATION.md)** - Where to put credential files

### Google Ads Specific
- **[Google Ads Quick Start](docs/GOOGLE_ADS_QUICKSTART.md)** - 15-minute setup guide
- **[Google Ads MCC Setup](docs/GOOGLE_ADS_MCC_SETUP.md)** - Detailed guide for MCC accounts
- **[OAuth Troubleshooting](docs/GOOGLE_ADS_OAUTH_TROUBLESHOOTING.md)** - Fix OAuth errors
- **[OAuth Setup Checklist](docs/GOOGLE_ADS_OAUTH_CHECKLIST.md)** - Pre-flight verification

### Deployment
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Deploy to GCP, Docker, K8s
- **[Implementation Details](docs/IMPLEMENTATION_COMPLETE.md)** - Complete feature list
- **[Multi-Platform Setup](docs/MULTI_PLATFORM_SETUP.md)** - Advanced configuration

### Files in Root
- `README.md` - This file
- `.env.example` - Template for environment variables
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration

---

## 🤝 Contributing

This is a production-ready advertising optimization platform. For questions or issues, please refer to the documentation above.
