from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

ENV_VARS = "export PG_HOST=edp_postgres PG_PORT=5432 MINIO_ENDPOINT=edp_minio:9000 && "

default_args = {
    "owner": "mohamed_elkalaf",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="enterprise_data_platform_e2e",
    default_args=default_args,
    description="End-to-End Medallion Data Platform Pipeline",
    schedule_interval="@daily",
    start_date=datetime(2026, 11, 10),
    catchup=False,
    tags=["enterprise", "medallion", "dw", "bi"],
) as dag:

    t1 = BashOperator(
        task_id="1_ingest_7_dbs_to_bronze",
        bash_command=ENV_VARS + "python /opt/airflow/pipelines/ingest_to_bronze.py",
    )

    t2 = BashOperator(
        task_id="2_cleanse_and_standardize_silver",
        bash_command=ENV_VARS + "python /opt/airflow/pipelines/transform_to_silver.py",
    )

    t3 = BashOperator(
        task_id="3_build_gold_dw_facts",
        bash_command=ENV_VARS + "python /opt/airflow/pipelines/build_gold_layer.py",
    )

    t4 = BashOperator(
        task_id="4_generate_department_pdf_reports",
        bash_command=ENV_VARS + "python /opt/airflow/pipelines/generate_department_reports.py",
    )

    t1 >> t2 >> t3 >> t4
