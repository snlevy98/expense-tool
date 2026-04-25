# Expense Tracker

A self-hosted household expense tracking app with AI-powered transaction categorization, budget management, and multi-source import (CSV, Excel, Amazon order history).

**Stack:** FastAPI (Python) · PostgreSQL · React · Supabase Auth · Google Gemini · Groq · Cohere · Render · Vercel

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [External Services Overview](#external-services-overview)
3. [Step 1 — Supabase (Auth + Database)](#step-1--supabase-auth--database)
4. [Step 2 — Google Gemini (AI)](#step-2--google-gemini-ai)
5. [Step 3 — Groq (AI)](#step-3--groq-ai)
6. [Step 4 — Cohere (AI)](#step-4--cohere-ai)
7. [Step 5 — Deploy the Backend on Render](#step-5--deploy-the-backend-on-render)
8. [Step 6 — Deploy the Frontend on Vercel](#step-6--deploy-the-frontend-on-vercel)
9. [Step 7 — First Launch & Seed Data](#step-7--first-launch--seed-data)
10. [Running Locally](#running-locally)
11. [Customizing Categories](#customizing-categories)
12. [Environment Variable Reference](#environment-variable-reference)

---

## How It Works

1. You import bank transactions via CSV/Excel export from your bank, or upload your Amazon order history.
2. The backend uses AI to clean up raw bank descriptions into readable merchant names, then suggests a category for each transaction.
3. You review and confirm categories on the **Categorize** tab. Amazon orders can be itemized into individual line items.
4. The **Dashboard** and **Reports** tabs show spending breakdowns, budget vs. actual, trends over time, and recurring charges.
5. You manage budgets per category (or subcategory) on the **Budgets** tab.

---

## External Services Overview

| Service | Purpose | Free Tier |
|---|---|---|
| [Supabase](https://supabase.com) | User authentication & JWT tokens | Free (unlimited auth) |
| [Neon](https://neon.tech) or Supabase DB | PostgreSQL database | Free tier available |
| [Google AI Studio](https://aistudio.google.com) | Merchant name normalization | Free API key |
| [Groq](https://console.groq.com) | Transaction category suggestions | Free (100k tokens/day) |
| [Cohere](https://dashboard.cohere.com) | Recurring transaction detection | Free trial key |
| [Render](https://render.com) | Backend API hosting | Free tier (spins down when idle) |
| [Vercel](https://vercel.com) | Frontend hosting | Free |

All services have free tiers sufficient for personal use. You do not need to enter a credit card for any of them.

---

## Step 1 — Supabase (Auth + Database)

Supabase handles user login. It also provides the PostgreSQL database unless you use an alternative like Neon.

### 1a. Create a Supabase project

1. Go to [https://supabase.com](https://supabase.com) and click **Start your project**.
2. Sign up with GitHub or email.
3. Click **New project**.
4. Fill in:
   - **Name:** anything (e.g. `expense-tracker`)
   - **Database Password:** pick a strong password and save it — you'll need it for `DATABASE_URL`
   - **Region:** choose one close to you
5. Click **Create new project** and wait ~2 minutes for it to provision.

### 1b. Collect your Supabase credentials

In your project dashboard, go to **Project Settings → API**.

Copy and save these values:

| Value | Where to find it | Used as |
|---|---|---|
| Project URL | "Project URL" field | `SUPABASE_URL` and `VITE_SUPABASE_URL` |
| Anon public key | "Project API keys → anon public" | `VITE_SUPABASE_ANON_KEY` |
| JWT Secret | **Project Settings → API → JWT Settings → JWT Secret** | `SUPABASE_JWT_SECRET` |

### 1c. Get the database connection string

1. Go to **Project Settings → Database**.
2. Under **Connection string**, select the **URI** tab.
3. Copy the connection string. It looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```
4. Replace `[YOUR-PASSWORD]` with the database password you set in step 1a.
5. Change `postgresql://` to `postgresql+asyncpg://` — this is required for the async Python driver.

Your final `DATABASE_URL` will look like:
```
postgresql+asyncpg://postgres:mypassword@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

> **Alternative database:** You can use [Neon](https://neon.tech) instead of Supabase's built-in Postgres. Create a free project on Neon, copy its connection string, and apply the same `+asyncpg` prefix change. Supabase is still required for authentication regardless.

### 1d. Enable email authentication

1. In your Supabase project, go to **Authentication → Providers**.
2. Confirm **Email** is enabled (it is by default).
3. Optionally, go to **Authentication → Settings** and disable **"Enable email confirmations"** so you can log in immediately without verifying your email.

### 1e. Create your user account

1. Go to **Authentication → Users** in the Supabase dashboard.
2. Click **Add user → Create new user**.
3. Enter the email and password you want to use to log in to the app.
4. Click **Create user**.

This is the login you'll use on the app's login page.

---

## Step 2 — Google Gemini (AI)

Gemini normalizes raw bank transaction descriptions into clean merchant names (e.g. `SQ *COFFEE SHOP 1234 TX` → `Local Coffee Shop`). This is the only required AI key.

1. Go to [https://aistudio.google.com](https://aistudio.google.com).
2. Sign in with a Google account.
3. Click **Get API key** in the left sidebar.
4. Click **Create API key** → **Create API key in new project**.
5. Copy the key (starts with `AIza...`).

Save this as `GEMINI_API_KEY`.

---

## Step 3 — Groq (AI)

Groq suggests spending categories for each transaction. It has a generous free tier of 100,000 tokens per day. Without this key the app falls back to Gemini for categorization, which depletes the same rate-limit pool as merchant normalization.

1. Go to [https://console.groq.com](https://console.groq.com).
2. Sign up with Google or email.
3. Go to **API Keys** in the left sidebar.
4. Click **Create API Key**, give it a name, and copy the key (starts with `gsk_...`).

Save this as `GROQ_API_KEY`.

---

## Step 4 — Cohere (AI)

Cohere identifies recurring transactions such as subscriptions, utilities, and loan payments. Without this key the app falls back to Gemini.

1. Go to [https://dashboard.cohere.com](https://dashboard.cohere.com).
2. Sign up with Google or email.
3. Your **Trial API key** is shown on the dashboard home page. Copy it.

Save this as `COHERE_API_KEY`.

---

## Step 5 — Deploy the Backend on Render

### 5a. Create a Render account

1. Go to [https://render.com](https://render.com) and sign up. GitHub sign-in is easiest since you'll need to connect your repo.

### 5b. Create a new Web Service

1. In the Render dashboard, click **New → Web Service**.
2. Connect your GitHub account if prompted, then select your fork of this repository.
3. Configure the service:

   | Field | Value |
   |---|---|
   | **Name** | `expense-tracker-api` (or anything you like) |
   | **Region** | Choose one close to you |
   | **Branch** | `main` |
   | **Root Directory** | `backend` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | **Instance Type** | Free |

### 5c. Add environment variables

In the same setup screen (or later under **Environment → Environment Variables**), add the following. Click **Add Environment Variable** for each:

| Key | Value |
|---|---|
| `DATABASE_URL` | Your `postgresql+asyncpg://...` string from Step 1c |
| `SUPABASE_URL` | Your Supabase project URL from Step 1b |
| `SUPABASE_JWT_SECRET` | Your JWT secret from Step 1b |
| `GEMINI_API_KEY` | Your key from Step 2 |
| `GROQ_API_KEY` | Your key from Step 3 |
| `COHERE_API_KEY` | Your key from Step 4 |
| `ENVIRONMENT` | `production` |
| `ALLOWED_ORIGINS` | Your Vercel frontend URL — you'll get this in Step 6, so come back and add it after |

> `ALLOWED_ORIGINS` accepts a comma-separated list. If you have a custom domain, include both:
> `https://my-app.vercel.app,https://expenses.mydomain.com`

4. Click **Create Web Service**. Render will build and deploy automatically. The first deploy takes ~3 minutes.

### 5d. Copy your backend URL

Once deployed, Render shows a public URL at the top of the service page:
```
https://expense-tracker-api.onrender.com
```
Save this — you'll need it in Step 6.

> **Note on free tier:** Render's free tier spins down services after 15 minutes of inactivity. The first request after idle takes ~30 seconds to wake up. A paid plan ($7/month) keeps it always on.

---

## Step 6 — Deploy the Frontend on Vercel

### 6a. Create a Vercel account

1. Go to [https://vercel.com](https://vercel.com) and sign up. GitHub sign-in is easiest.

### 6b. Import the project

1. In the Vercel dashboard, click **Add New → Project**.
2. Import your GitHub repository.
3. Vercel will auto-detect it as a Vite project. Set the root directory:

   | Field | Value |
   |---|---|
   | **Root Directory** | `frontend` |
   | **Framework Preset** | `Vite` (auto-detected) |
   | **Build Command** | `npm run build` (auto-detected) |
   | **Output Directory** | `dist` (auto-detected) |

### 6c. Add environment variables

Before clicking **Deploy**, expand the **Environment Variables** section and add:

| Key | Value |
|---|---|
| `VITE_SUPABASE_URL` | Your Supabase project URL from Step 1b |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase anon key from Step 1b |
| `VITE_API_URL` | Your Render backend URL from Step 5d with `/api` appended: `https://expense-tracker-api.onrender.com/api` |

4. Click **Deploy**. Build takes ~1 minute.

### 6d. Update ALLOWED_ORIGINS on Render

Once Vercel finishes, copy your frontend URL (e.g. `https://my-app.vercel.app`).

Go back to Render → your service → **Environment**, update `ALLOWED_ORIGINS` to that URL, and click **Save Changes**. Render will redeploy automatically.

---

## Step 7 — First Launch & Seed Data

### 7a. Confirm migrations ran

The database tables are created automatically when the backend starts (the start command runs `alembic upgrade head`). After the first Render deploy completes successfully, your database is ready.

### 7b. Seed the default categories

The app needs a set of categories and subcategories before you can start categorizing transactions. You run this seed script once from your local machine.

1. Clone the repository if you haven't already:
   ```bash
   git clone https://github.com/your-username/expense-tool.git
   cd expense-tool/backend
   ```

2. Create a Python virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the `backend/` directory containing just your database URL:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:mypassword@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```

4. Run the seed script:
   ```bash
   python seed_categories.py
   ```

   You should see output like:
   ```
   + Category: Debt
       + Car Loan
       + Taxes (federal)
   ...
   Done. Created 13 categories and 34 subcategories.
   ```

> **Customize first:** Before running, open `seed_categories.py` and edit the `SEED` list to match your own spending categories. See [Customizing Categories](#customizing-categories) below.

### 7c. Log in

Open your Vercel frontend URL in a browser and log in with the email and password you created in Step 1e. You're ready to start importing transactions.

---

## Running Locally

### Prerequisites

- Python 3.12+
- Node.js 18+
- A PostgreSQL database (you can use your Supabase or Neon database, or run Postgres locally)

### Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create your environment file (see values below)
cp .env.example .env

# Run database migrations
alembic upgrade head

# Seed categories (first time only)
python seed_categories.py

# Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**`backend/.env`**
```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/expense_tracker
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_JWT_SECRET=your-jwt-secret
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=your-groq-key
COHERE_API_KEY=your-cohere-key
ENVIRONMENT=development
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Create your environment file (see values below)
cp .env.example .env.local

# Start the development server
npm run dev
```

The app will be available at `http://localhost:5173`. The Vite dev server automatically proxies `/api` requests to `http://localhost:8000` so no CORS configuration is needed locally.

**`frontend/.env.local`**
```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
VITE_API_URL=http://localhost:8000/api
```

---

## Customizing Categories

The default categories in `backend/seed_categories.py` reflect a specific household's budget structure. Edit the `SEED` list before running the seed script to use your own:

```python
SEED = [
    ("Category Name", "#hexcolor", ["Subcategory 1", "Subcategory 2"]),
    ("Housing",       "#3b82f6",   ["Rent", "Utilities", "Internet"]),
    ("Food",          "#f59e0b",   ["Groceries", "Restaurants", "Coffee"]),
    ("Transport",     "#10b981",   ["Gas", "Car Insurance", "Parking"]),
    # add as many as you need...
]
```

Each entry is:
- **Category name** — displayed throughout the app and in reports
- **Hex color** — used in charts and the color dot next to the category name
- **Subcategories** — optional sub-groupings; an empty list `[]` is fine if you don't need them

The seed script is safe to re-run — it skips anything that already exists.

---

## Environment Variable Reference

### Backend

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. Must start with `postgresql+asyncpg://`. |
| `SUPABASE_URL` | Yes | Your Supabase project URL (e.g. `https://xxxx.supabase.co`). |
| `SUPABASE_JWT_SECRET` | Yes | JWT secret from Supabase → Project Settings → API → JWT Settings. |
| `GEMINI_API_KEY` | Yes | Google AI Studio API key. Used for merchant normalization and as fallback for other AI tasks. |
| `GROQ_API_KEY` | No | Groq API key. Used for category suggestions. Falls back to Gemini if not set. |
| `COHERE_API_KEY` | No | Cohere API key. Used for recurring transaction detection. Falls back to Gemini if not set. |
| `ALLOWED_ORIGINS` | Yes (prod) | Comma-separated list of allowed frontend origins for CORS. Example: `https://my-app.vercel.app,https://expenses.mydomain.com`. Not needed for local development. |
| `ENVIRONMENT` | No | Set to `production` on Render. Defaults to `development`. |

### Frontend

| Variable | Required | Description |
|---|---|---|
| `VITE_SUPABASE_URL` | Yes | Your Supabase project URL. |
| `VITE_SUPABASE_ANON_KEY` | Yes | Supabase anon/public key. This key is safe to expose — it is designed to be public. |
| `VITE_API_URL` | Yes | Full URL to the backend API including the `/api` suffix. Example: `https://your-api.onrender.com/api`. |
