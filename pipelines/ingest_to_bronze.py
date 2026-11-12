import os
import json
import io
import psycopg2
from psycopg2.extras import RealDictCursor
from minio import Minio

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "edp_password_2026")
BUCKET_NAME = "bronze"

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "edp_password_2026")

DATABASES = ["ecommerce_db", "billing_db", "inventory_db", "hr_db", "marketing_db", "logistics_db", "crm_db"]

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

if not client.bucket_exists(BUCKET_NAME):
    client.make_bucket(BUCKET_NAME)
    print(f"Bucket '{BUCKET_NAME}' created successfully in MinIO.")

def ingest_all():
    print("--- Starting Bronze Layer Ingestion from 7 Operational Databases ---")
    for db_name in DATABASES:
        try:
            conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=db_name)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT table_schema, table_name 
                FROM information_schema.tables 
                WHERE table_type = 'BASE TABLE' 
                  AND table_schema NOT IN ('pg_catalog', 'information_schema');
            """)
            tables = cur.fetchall()
            for t in tables:
                schema = t['table_schema']
                table = t['table_name']
                cur.execute(f'SELECT * FROM "{schema}"."{table}"')
                rows = cur.fetchall()
                if rows:
                    data_bytes = json.dumps(rows, default=str, ensure_ascii=False, indent=2).encode('utf-8')
                    obj_path = f"{db_name}/{schema}/{table}.json"
                    client.put_object(BUCKET_NAME, obj_path, io.BytesIO(data_bytes), length=len(data_bytes), content_type="application/json")
                    print(f"[SUCCESS] Ingested {db_name}.{schema}.{table} ({len(rows)} rows) -> MinIO s3://{BUCKET_NAME}/{obj_path}")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[WARNING] Skipping {db_name}: {e}")

if __name__ == "__main__":
    ingest_all()
