import os
import json
import io
import psycopg2
from minio import Minio

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "edp_password_2026")
SILVER_BUCKET = "silver"
GOLD_BUCKET = "gold"

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "edp_password_2026")
DW_DB = "edp_dw"

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

if not client.bucket_exists(GOLD_BUCKET):
    client.make_bucket(GOLD_BUCKET)

def init_dw_database():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname="postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DW_DB}'")
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {DW_DB}")
    cur.close()
    conn.close()

def run_gold_aggregation():
    print("--- Starting Gold Layer Aggregation (MinIO + PostgreSQL DW) ---")
    init_dw_database()
    
    resp_ord = client.get_object(SILVER_BUCKET, "cleaned/ecommerce_db/sales/orders.json")
    orders = json.loads(resp_ord.read().decode('utf-8'))
    resp_ord.close()
    
    resp_inv = client.get_object(SILVER_BUCKET, "cleaned/billing_db/billing/invoices.json")
    invoices = json.loads(resp_inv.read().decode('utf-8'))
    resp_inv.close()

    resp_cust = client.get_object(SILVER_BUCKET, "cleaned/ecommerce_db/customers/customers.json")
    customers = json.loads(resp_cust.read().decode('utf-8'))
    resp_cust.close()

    inv_map = {str(inv.get('order_id')): inv for inv in invoices}
    cust_map = {str(c.get('customer_id')): c for c in customers}

    fact_sales = []
    for order in orders:
        oid = str(order.get('order_id'))
        cid = str(order.get('customer_id'))
        matching_inv = inv_map.get(oid, {})
        matching_cust = cust_map.get(cid, {})
        
        cust_name = f"{matching_cust.get('first_name', 'Enterprise')} {matching_cust.get('last_name', 'Client')}".strip()
        raw_status = order.get('order_status') or order.get('status') or 'CONFIRMED'
        if str(raw_status).upper() in ('NONE', 'NULL', ''):
            raw_status = 'CONFIRMED'

        raw_inv_status = matching_inv.get('invoice_status') or matching_inv.get('status') or 'ISSUED'
        
        fact_row = {
            "order_id": oid,
            "order_number": str(order.get('order_number')),
            "customer_name": cust_name,
            "currency": str(order.get('currency_code', 'EGP')),
            "order_status": str(raw_status).upper(),
            "total_amount": float(order.get('total_amount') or 0.0),
            "invoice_number": str(matching_inv.get('invoice_number', 'INV-PENDING')),
            "invoice_status": str(raw_inv_status).upper(),
            "paid_amount": float(matching_inv.get('paid_amount') or 0.0),
            "balance_due": float(matching_inv.get('balance_due') or 0.0),
            "created_at": str(order.get('created_at') or order.get('placed_at'))
        }
        fact_sales.append(fact_row)
        
    gold_bytes = json.dumps(fact_sales, default=str, ensure_ascii=False, indent=2).encode('utf-8')
    client.put_object(GOLD_BUCKET, "facts/fact_sales_summary.json", io.BytesIO(gold_bytes), length=len(gold_bytes), content_type="application/json")
    print(f"[GOLD MINIO] Saved -> s3://{GOLD_BUCKET}/facts/fact_sales_summary.json ({len(fact_sales)} rows)")

    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=DW_DB)
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    cur.execute("""
        DROP TABLE IF EXISTS gold.fact_sales_summary;
        CREATE TABLE gold.fact_sales_summary (
            order_id VARCHAR(100) PRIMARY KEY,
            order_number VARCHAR(100),
            customer_name VARCHAR(200),
            currency VARCHAR(20),
            order_status VARCHAR(50),
            total_amount NUMERIC(15,2),
            invoice_number VARCHAR(100),
            invoice_status VARCHAR(50),
            paid_amount NUMERIC(15,2),
            balance_due NUMERIC(15,2),
            created_at TIMESTAMP
        );
    """)
    for r in fact_sales:
        cur.execute("""
            INSERT INTO gold.fact_sales_summary 
            (order_id, order_number, customer_name, currency, order_status, total_amount, invoice_number, invoice_status, paid_amount, balance_due, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (r["order_id"], r["order_number"], r["customer_name"], r["currency"], r["order_status"], r["total_amount"], r["invoice_number"], r["invoice_status"], r["paid_amount"], r["balance_due"], r["created_at"]))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"[GOLD DW] Loaded {len(fact_sales)} rows into PostgreSQL -> edp_dw.gold.fact_sales_summary")

if __name__ == "__main__":
    run_gold_aggregation()
