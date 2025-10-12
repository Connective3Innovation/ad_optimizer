Ad Creative Auto-Optimizer (LLM + Vision + Guardrailed Agent)

Overview

- Pulls creative + performance from ad platforms (Meta/TikTok/Google) and analytics (GA4/MMP) via connectors (mockable locally).
- Detects creative fatigue/wear-out and predicts next best concepts.
- LLM + vision scores hooks, framing, and text overlays; generates compliant variants.
- Guardrailed agent queues safe changes (rotate assets, update copy, pause losers) behind approval toggles.
- BigQuery (BQ) is the primary DB; GCS used for assets. OpenAI used for LLM and embeddings.
- Streamlit app provided to showcase the workflow end-to-end.
- Vision module adds visual-fatigue signals (hashes, colors, OCR-based overlay density) and novelty scores.

Quick Start (Local Mock Mode)

1) Python 3.10+
2) Create and activate a virtual environment
   - Windows: `python -m venv .venv && .\.venv\Scripts\activate`
   - macOS/Linux: `python -m venv .venv && source .venv/bin/activate`
3) Install dependencies: `pip install -r requirements.txt`
4) Run the app in mock mode: `streamlit run src/app.py`

- The app defaults to mock data from `data/sample/`. No cloud creds required.
- If you have no OpenAI key, the app will use deterministic heuristic scoring as a fallback.
- Vision features work without cloud; remote image URLs require internet. OCR is optional (needs Tesseract + `pytesseract`).

Configure Real Integrations

- Streamlit secrets (recommended): copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill values.
  - `openai_api_key`
  - `gcp_project_id`
  - `bigquery_dataset`
  - `gcp_credentials_json` (path or raw JSON; optional if using ADC)

- Environment variables: copy `.env.example` to `.env` and fill values.

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
- In your GitHub repo, add Secrets:
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
