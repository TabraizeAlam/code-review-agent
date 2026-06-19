# AI Code Review Agent — Meridian Capital Data Engineering

An automated multi-agent system that reviews Python code for bugs, security vulnerabilities, and test coverage gaps. Built to support Meridian Capital's data engineering workflows — Databricks pipelines, dbt reporting models, and custodian data integrations.

---

## Business Problem

Meridian Capital's data engineering team manages critical pipelines handling $160B+ in investment data across client funds including LAPP, ATRF, HPSP, and others. Code issues in these pipelines — SQL injection vulnerabilities, resource leaks, missing error handling — can cause data quality failures, compliance exposure, and reprocessing costs.

Manual code review is time-consuming, inconsistent across reviewers, and often skips security checks entirely under delivery pressure.

This tool automates the first pass of every review, ensuring every pipeline — whether a Databricks ETL, a dbt reporting model, or a custodian integration — is checked for the same set of risks before it reaches production.

---

## How It Works

Three specialized AI agents run in sequence, each focused on a specific risk area:

```
Python file (pipeline / dbt model / integration script)
         │
         ▼
   [Bug Agent]          → finds logic errors, anti-patterns, resource leaks
         │
         ▼
   [Security Agent]     → finds hardcoded credentials, SQL injection, data exposure
         │
         ▼
   [Test Agent]         → identifies missing edge case and error path coverage
         │
         ▼
   [Orchestrator]       → compiles a prioritized findings report
         │
         ▼
   ⏸  Developer reviews and approves
         │
         ▼
   Saved Markdown report
```

The pipeline is built on **LangGraph** — a Python framework for multi-step AI workflows. The LLM is **Llama 3.3 70B** running on **Nebius AI Studio**.

A human-in-the-loop checkpoint ensures no report is saved without developer sign-off.

---

## Sample Output

Running against `custodian_pipeline.py`:

```
============================================================
  CODE REVIEW AGENT  |  custodian_pipeline.py
============================================================

[Bug Agent] Scanning for bugs and anti-patterns...
  3 issue(s) found

[Security Agent] Scanning for vulnerabilities...
  4 issue(s) found

[Test Agent] Checking test coverage gaps...
  3 issue(s) found

[Orchestrator] Compiling final report...
  Done

============================================================
# Code Review Report: custodian_pipeline.py

## Executive Summary
The file contains critical SQL injection vulnerabilities across all
database operations and two hardcoded production credentials. The
reconciliation function also contains a list-mutation bug that will
silently miss holding breaks. Address security findings immediately.

## HIGH Priority Findings
### Security
1. [HIGH] DB_CONN contains a hardcoded production password in source code...
2. [HIGH] SQL query uses f-string with portfolio_id — SQL injection risk...

### Bugs
3. [HIGH] reconcile_holdings() removes items from `breaks` while iterating it...
...
```

---

## Setup

**Requirements:** Python 3.10+, a Nebius API key (free at studio.nebius.com)

```bash
git clone <repo-url>
cd code_review_agent
pip install -r requirements.txt
cp .env.example .env
# Paste your NEBIUS_API_KEY into .env
```

---

## Usage

**Review any pipeline script:**
```bash
python main.py sample_code/custodian_pipeline.py
python main.py sample_code/performance_attribution.py
python main.py sample_code/databricks_etl.py
python main.py sample_code/dbt_reporting_models.py
```

**Run the built-in demo (no file needed):**
```bash
python main.py
```

When the report appears, press **Enter** to approve and save, or type a note before saving.

---

## Included Sample Files

| File | What it simulates | Has bugs? |
|---|---|---|
| `custodian_pipeline.py` | State Street position file ingestion | Yes |
| `performance_attribution.py` | Alpha and tracking error calculations for LAPP/ATRF/HPSP | Yes |
| `databricks_etl.py` | Bronze → Silver → Gold pipeline on ADLS | Yes |
| `databricks_etl_clean.py` | Same pipeline, production-ready patterns | Clean |
| `dbt_reporting_models.py` | dbt models for portfolio summary and performance reporting | Yes |
| `dbt_reporting_models_clean.py` | Same models, correct dbt patterns | Clean |

---

## Project Structure

```
code_review_agent/
├── main.py          # Entry point
├── graph.py         # LangGraph pipeline
├── agents.py        # Four agent functions
├── state.py         # Shared state
├── prompts.py       # Agent system prompts
├── requirements.txt
├── .env.example
└── sample_code/     # Meridian Capital review targets
```

---

## Scaling Within Meridian Capital

This runs locally against any Python file today. Paths to scale across the team:

- **CI/CD integration** — trigger the agent automatically on every pull request in Azure DevOps
- **Databricks integration** — run as a Databricks job that reviews notebooks before promotion to production
- **Slack/Teams notifications** — post the findings report to the team channel on each pipeline deployment
- **Custom rule sets** — extend the agent prompts with Meridian-specific rules (e.g., flag any direct ADLS key usage, enforce naming conventions for Delta tables)

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent framework | LangGraph |
| LLM | Llama 3.3 70B via Nebius AI Studio |
| LLM client | LangChain + ChatOpenAI |
| State persistence | LangGraph MemorySaver |
| Human-in-the-loop | LangGraph interrupt / Command(resume) |
| Language | Python 3.10+ |
