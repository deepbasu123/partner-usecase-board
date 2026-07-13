"""Populate the partner-board Lakebase with realistic demo data.

Idempotent: skips use cases (by title) and partners (by email) that already
exist, and skips responses that already exist (by use_case+partner). Safe to
re-run. All partner firms are fictional to avoid implying any real partner
relationship.
"""
import psycopg
from databricks.sdk import WorkspaceClient

INST = "partner-board-db"
ADMIN = "admin@example.com"

# --- use cases (title, description, industry, region, status) ---
USE_CASES = [
    ("Legacy EDW migration to Lakehouse — retail",
     "A national retailer wants to migrate a legacy Teradata warehouse to the Databricks Lakehouse. Looking for a partner with a proven migration accelerator, code-conversion tooling, and experience cutting over BI workloads with minimal downtime.",
     "Retail", "ANZ", "open"),
    ("Real-time fraud detection — retail banking",
     "A retail bank needs sub-second fraud scoring on card transactions using Structured Streaming and MLflow. Seeking a partner with prior streaming-ML delivery and a reference architecture we can stand up quickly.",
     "Financial Services", "ANZ", "open"),
    ("Predictive maintenance on manufacturing IoT",
     "A heavy-equipment manufacturer wants to predict failures from sensor telemetry. Looking for a partner experienced in IoT ingestion, feature engineering on Delta, and deploying models to reduce unplanned downtime.",
     "Manufacturing", "APAC", "open"),
    ("Unity Catalog governance rollout — healthcare",
     "A hospital network is consolidating data governance under Unity Catalog with fine-grained access controls and lineage for sensitive patient data. Seeking a partner with healthcare data-governance experience.",
     "Healthcare", "ANZ", "open"),
    ("GenAI customer-support agent",
     "An insurer wants a governed GenAI assistant over its policy and claims knowledge base, built with Agent Bricks / Mosaic AI. Looking for a partner who has shipped a RAG assistant to production with evaluation and guardrails.",
     "Insurance", "ANZ", "open"),
    ("Supply-chain demand forecasting",
     "A grocery distributor needs SKU-level demand forecasting to cut waste and stockouts. Seeking a partner with forecasting accelerators and experience operationalising models with Lakeflow Jobs.",
     "Logistics", "APAC", "open"),
    ("Government open-data platform",
     "A state government agency wants a governed open-data platform on Databricks with Delta Sharing for public datasets. Looking for a partner with public-sector delivery experience and security clearances.",
     "Public Sector", "ANZ", "open"),
    ("Marketing attribution & CDP",
     "A telco wanted a unified customer profile and multi-touch attribution on the Lakehouse. This engagement has been staffed — thanks to all who responded.",
     "Telecommunications", "ANZ", "closed"),
]

# --- partners (email, company, contact_name) — all fictional ---
PARTNERS = [
    ("hello@southerncrossdata.example", "Southern Cross Data Co", "Priya Nair"),
    ("team@tasmananalytics.example", "Tasman Analytics Group", "Liam O'Connor"),
    ("contact@meridiandata.example", "Meridian Data Partners", "Sarah Chen"),
    ("info@koalacloud.example", "Koala Cloud Consulting", "James Whitfield"),
    ("partnerships@aurorainsights.example", "Aurora Insights", "Fatima Al-Rashid"),
    ("hello@reefdatalabs.example", "Reef Data Labs", "Marcus Webb"),
    ("engage@harbourbridgeanalytics.example", "Harbour Bridge Analytics", "Emily Zhang"),
    ("kiaora@southernlightsdata.example", "Southern Lights Data", "Tane Wiremu"),
    ("hello@pinnaclelakehouse.example", "Pinnacle Lakehouse Partners", "David Kowalski"),
    ("team@outbackai.example", "Outback AI", "Georgia Sutton"),
]

# --- responses: (use_case_title, partner_company, approach) ---
RESPONSES = [
    ("Workforce Management solution — ANZ", "Southern Cross Data Co",
     "We've delivered a WFM solution on Databricks for two ANZ enterprises using Lakeflow for shift-data ingestion and a Lakeview scheduling dashboard. Accelerator and a 4-person team available; we can start within 3 weeks."),
    ("Workforce Management solution — ANZ", "Meridian Data Partners",
     "Our workforce-analytics accelerator covers rostering, demand forecasting and compliance reporting. Happy to run a 2-week discovery to scope a pilot."),
    ("Workforce Management solution — ANZ", "Koala Cloud Consulting",
     "We partner with a WFM ISV and can integrate their engine with the customer's Lakehouse. Reference architecture and a fixed-price PoC available."),

    ("Legacy EDW migration to Lakehouse — retail", "Pinnacle Lakehouse Partners",
     "We have a Teradata-to-Databricks migration factory: automated schema and SQL conversion, plus a BI-cutover playbook. Migrated 40+ TB for a retailer last year with zero downtime on the final switch."),
    ("Legacy EDW migration to Lakehouse — retail", "Harbour Bridge Analytics",
     "Our team has done three EDW modernisations in retail. We'd start with a workload assessment and a prioritised migration wave plan."),
    ("Legacy EDW migration to Lakehouse — retail", "Tasman Analytics Group",
     "We use BladeBridge + our own validation harness to de-risk conversion. Can provide references from a grocery client."),

    ("Real-time fraud detection — retail banking", "Aurora Insights",
     "We built a sub-200ms fraud-scoring pipeline on Structured Streaming with a feature store on Delta and MLflow model serving. Reference architecture ready; team of 5 available."),
    ("Real-time fraud detection — retail banking", "Meridian Data Partners",
     "Our financial-crime accelerator includes streaming features, a challenger-model framework, and drift monitoring. We'd propose a 6-week production-grade pilot."),

    ("Predictive maintenance on manufacturing IoT", "Reef Data Labs",
     "We've deployed predictive maintenance for a mining-equipment OEM: MQTT ingestion, Delta feature tables, and survival models scored via Lakeflow Jobs. Cut unplanned downtime ~18%."),
    ("Predictive maintenance on manufacturing IoT", "Outback AI",
     "IoT + ML is our core. We'd instrument the telemetry pipeline first, then iterate on failure-prediction models with the reliability team."),

    ("Unity Catalog governance rollout — healthcare", "Harbour Bridge Analytics",
     "We've led two UC rollouts in regulated healthcare, including ABAC row/column masking and lineage for auditors. Governance runbook and RACI available."),
    ("Unity Catalog governance rollout — healthcare", "Southern Lights Data",
     "Strong health-sector governance background in NZ. We'd map data domains, define the catalog/schema model, and stand up access policies with the data-protection officer."),

    ("GenAI customer-support agent", "Outback AI",
     "We've shipped a production RAG assistant with Mosaic AI evaluation, guardrails and human-in-the-loop review. Can demo a working reference agent next week."),
    ("GenAI customer-support agent", "Aurora Insights",
     "Our GenAI practice built a claims-triage assistant for an insurer. We'd start with an eval harness and a scoped knowledge base before scaling."),
    ("GenAI customer-support agent", "Southern Cross Data Co",
     "We can pair an Agent Bricks build with change-management for the support team. Fixed-price discovery available."),

    ("Supply-chain demand forecasting", "Tasman Analytics Group",
     "Our forecasting accelerator does hierarchical SKU/store forecasts with backtesting and automated retraining on Lakeflow. References from FMCG available."),

    ("Government open-data platform", "Pinnacle Lakehouse Partners",
     "We hold public-sector panel arrangements and have delivered a Delta Sharing open-data platform for a government agency, including IRAP-aligned controls."),
]


def main():
    w = WorkspaceClient(profile="deep-test-1")
    me = w.current_user.me().user_name
    host = w.database.get_database_instance(INST).read_write_dns
    tok = w.database.generate_database_credential(
        request_id="seed-sample", instance_names=[INST]).token
    conn = psycopg.connect(host=host, port=5432, dbname="partner_board",
                           user=me, password=tok, sslmode="require", autocommit=True)
    added = {"use_cases": 0, "partners": 0, "responses": 0}
    with conn.cursor() as cur:
        # use cases
        for title, desc, ind, reg, status in USE_CASES:
            cur.execute("SELECT 1 FROM use_cases WHERE title=%s", (title,))
            if cur.fetchone():
                continue
            closed = ", closed_at" if status == "closed" else ""
            closed_v = ", now()" if status == "closed" else ""
            cur.execute(
                f"INSERT INTO use_cases (title,description,industry,region,status,posted_by{closed}) "
                f"VALUES (%s,%s,%s,%s,%s,%s{closed_v})",
                (title, desc, ind, reg, status, ADMIN))
            added["use_cases"] += 1

        # partners
        for email, company, contact in PARTNERS:
            cur.execute("SELECT 1 FROM partners WHERE email=%s", (email,))
            if cur.fetchone():
                continue
            cur.execute("INSERT INTO partners (email,company,contact_name) VALUES (%s,%s,%s)",
                        (email, company, contact))
            added["partners"] += 1

        # responses (resolve ids by title/company)
        for uc_title, company, approach in RESPONSES:
            cur.execute("SELECT id FROM use_cases WHERE title=%s", (uc_title,))
            uc = cur.fetchone()
            cur.execute("SELECT id FROM partners WHERE company=%s", (company,))
            p = cur.fetchone()
            if not uc or not p:
                print(f"  skip response ({uc_title} / {company}): missing id")
                continue
            cur.execute("SELECT 1 FROM responses WHERE use_case_id=%s AND partner_id=%s",
                        (uc[0], p[0]))
            if cur.fetchone():
                continue
            cur.execute("INSERT INTO responses (use_case_id,partner_id,approach) VALUES (%s,%s,%s)",
                        (uc[0], p[0], approach))
            added["responses"] += 1

        # report totals
        totals = {}
        for t in ("use_cases", "partners", "responses"):
            cur.execute(f"SELECT count(*) FROM {t}")
            totals[t] = cur.fetchone()[0]
    print("added:", added)
    print("totals:", totals)


if __name__ == "__main__":
    main()
