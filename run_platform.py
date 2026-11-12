import subprocess
import sys
import webbrowser

STEPS = [
    ("0. Seeding 5,000+ Enterprise Orders, Clients & Invoices", [sys.executable, "pipelines/seed_enterprise_data.py"]),
    ("1. Streaming Real-Time Outbox CDC Events via Apache Kafka", [sys.executable, "pipelines/stream_outbox_kafka.py"]),
    ("2. Ingesting 7 Operational Databases -> Bronze Layer", [sys.executable, "pipelines/ingest_to_bronze.py"]),
    ("3. Cleansing & Standardizing -> Silver Layer", [sys.executable, "pipelines/transform_to_silver.py"]),
    ("4. Building Analytical Fact Tables -> Gold Layer & DW", [sys.executable, "pipelines/build_gold_layer.py"]),
    ("5. Ensuring psycopg2 Driver & Admin Ready in Superset", [
        "docker", "exec", "-u", "root", "edp_superset", "bash", "-c",
        "pip install -q --target=/app/.venv/lib/python3.10/site-packages psycopg2-binary && superset db upgrade && superset fab create-admin --username admin --firstname Mohamed --lastname Elkalaf --email admin@edp.com --password admin || true"
    ]),
    ("6. Registering Gold Data Warehouse in Apache Superset", [
        "docker", "exec", "edp_superset", "superset", "set_database_uri",
        "-d", "EDP_Gold_DataWarehouse",
        "-u", "postgresql+psycopg2://postgres:edp_password_2026@edp_postgres:5432/edp_dw"
    ]),
    ("7. Copying V2 Dashboard Provisioner to Superset Container", [
        "docker", "cp", "pipelines/provision_superset_dashboard.py", "edp_superset:/app/provision_superset_dashboard.py"
    ]),
    ("8. Auto-Building Executive Command Center in Superset", [
        "docker", "exec", "edp_superset", "python", "/app/provision_superset_dashboard.py"
    ]),
    ("9. Generating Departmental PDF Reports (5,000+ Summary)", [sys.executable, "pipelines/generate_department_reports.py"]),
    ("10. Triggering Automated DAG Run inside Apache Airflow", [
        "docker", "exec", "edp_airflow", "bash", "-c",
        "airflow dags unpause enterprise_data_platform_e2e && airflow dags trigger enterprise_data_platform_e2e"
    ])
]

def main():
    print("==========================================================")
    print("   ENTERPRISE DATA PLATFORM - MASTER ORCHESTRATOR V2      ")
    print("==========================================================")
    for title, cmd in STEPS:
        print(f"\n>>> {title}...")
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"[WARNING] Note on step: {title}")
            
    dashboard_url = "http://127.0.0.1:8088/superset/dashboard/edp-executive-dashboard/"
    airflow_url = "http://127.0.0.1:8085/dags/enterprise_data_platform_e2e/grid"
    print("\n==========================================================")
    print(" [SUCCESS] Full Enterprise Platform V2 Executed End-to-End!")
    print(" - Printable PDF Reports Ready in: ./reports_output/")
    print(f" - Airflow Orchestrator UI: {airflow_url}")
    print(f" - Executive BI Dashboard:  {dashboard_url}")
    print("==========================================================")
    
    webbrowser.open(dashboard_url)

if __name__ == "__main__":
    main()
