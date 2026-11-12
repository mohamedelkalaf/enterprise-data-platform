import os, re, uuid, random
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "edp_password_2026")

CUSTOMERS = [
    ("El-Araby Group", "B2B Corp"), ("Elsewedy Electric", "Enterprise"),
    ("Orascom Construction", "Enterprise"), ("Telecom Egypt WE", "Gov/Enterprise"),
    ("Vodafone Egypt", "Enterprise"), ("Raya Holding", "B2B Corp"),
    ("Fawry Microfinance", "FinTech"), ("Talaat Moustafa Group", "Real Estate"),
    ("Palm Hills Developments", "Real Estate"), ("Juhayna Food Industries", "FMCG"),
    ("Edita Food Industries", "FMCG"), ("Hassan Allam Holding", "Construction"),
    ("Ezz Steel Corp", "Industrial"), ("Oriental Weavers", "Industrial"),
    ("Cleopatra Hospitals", "Healthcare"), ("Cairo Amman Bank", "Banking"),
    ("CIB Egypt", "Banking"), ("QNB Alahli", "Banking"),
    ("Shell Egypt", "Energy"), ("TotalEnergies Egypt", "Energy")
]

def get_allowed_values(cur, schema, table, col_name, default_list):
    cur.execute("""
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        JOIN pg_class cl ON cl.oid = c.conrelid
        WHERE n.nspname = %s AND cl.relname = %s AND c.contype = 'c'
    """, (schema, table))
    for (condef,) in cur.fetchall():
        if col_name in condef:
            vals = re.findall(r"'([^']+)'", condef)
            if vals:
                return vals
    return default_list

def seed_massive_data():
    print("--- [FAST BATCH] Seeding 5,000+ Enterprise Orders & Invoices ---")
    conn_eco = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname="ecommerce_db")
    conn_bil = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname="billing_db")
    cur_eco = conn_eco.cursor(cursor_factory=RealDictCursor)
    cur_bil = conn_bil.cursor(cursor_factory=RealDictCursor)

    # سحب صف نموذجي من كل جدول لضمان تلبية جميع قيود NOT NULL تلقائياً
    cur_eco.execute("SELECT * FROM customers.customers LIMIT 1")
    tpl_cust = cur_eco.fetchone() or {}
    cur_eco.execute("SELECT * FROM sales.orders LIMIT 1")
    tpl_ord = cur_eco.fetchone() or {}
    cur_bil.execute("SELECT * FROM billing.invoices LIMIT 1")
    tpl_inv = cur_bil.fetchone() or {}

    ord_statuses = get_allowed_values(cur_eco, "sales", "orders", "status", ["DELIVERED", "SHIPPED", "PROCESSING", "CONFIRMED", "CANCELLED"])
    inv_statuses = get_allowed_values(cur_bil, "billing", "invoices", "status", ["PAID", "PARTIALLY_PAID", "ISSUED", "OVERDUE"])

    customer_ids = []
    for idx, (fname, lname) in enumerate(CUSTOMERS, start=1):
        cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"massive-cust-{idx}@edp.local"))
        customer_ids.append(cid)
        c_row = dict(tpl_cust)
        c_row.update({
            "customer_id": cid,
            "first_name": fname,
            "last_name": lname,
            "email": f"exec{idx}@enterprise-eg.com",
            "phone": f"+20111000{idx:04d}"
        })
        if "customer_type" in c_row and not c_row["customer_type"]:
            c_row["customer_type"] = "B2B"
        if "customer_code" in c_row and c_row["customer_code"]:
            c_row["customer_code"] = f"CUST-{1000+idx}"
        cols = list(c_row.keys())
        cur_eco.execute(
            f"INSERT INTO customers.customers ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING",
            [c_row[k] for k in cols]
        )
    conn_eco.commit()

    random.seed(42)
    base_time = datetime.now(timezone.utc)
    ord_rows, inv_rows = [], []
    ord_keys = list(tpl_ord.keys())
    inv_keys = list(tpl_inv.keys())

    for i in range(1, 5001):
        ord_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"massive-order-{i}"))
        inv_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"massive-inv-{i}"))
        cid = random.choice(customer_ids)
        created_dt = base_time - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        
        o_status = random.choice(ord_statuses)
        i_status = random.choice(inv_statuses)

        subtotal = round(random.uniform(12000.0, 450000.0), 2)
        tax = round(subtotal * 0.14, 2)
        shipping = round(random.uniform(500.0, 3500.0), 2)
        discount = round(subtotal * random.choice([0, 0, 0.05, 0.10]), 2)
        total = round(subtotal + tax + shipping - discount, 2)

        if "PAID" in i_status and "PART" not in i_status:
            paid, balance = total, 0.0
        elif "PART" in i_status:
            paid = round(total * 0.6, 2)
            balance = round(total - paid, 2)
        else:
            paid, balance = 0.0, total

        o_row = dict(tpl_ord)
        for k, v in {
            "order_id": ord_id, "order_number": f"ORD-2026-{200000 + i}", "customer_id": cid,
            "order_status": o_status, "status": o_status, "currency_code": "EGP",
            "subtotal_amount": subtotal, "tax_amount": tax, "shipping_amount": shipping,
            "discount_amount": discount, "total_amount": total,
            "placed_at": created_dt, "created_at": created_dt, "updated_at": created_dt
        }.items():
            if k in o_row: o_row[k] = v
        ord_rows.append([o_row[k] for k in ord_keys])

        i_row = dict(tpl_inv)
        for k, v in {
            "invoice_id": inv_id, "invoice_number": f"INV-2026-{800000 + i}", "order_id": ord_id, "customer_id": cid,
            "invoice_status": i_status, "status": i_status, "currency_code": "EGP",
            "subtotal_amount": subtotal, "tax_amount": tax, "discount_amount": discount,
            "total_amount": total, "paid_amount": paid, "balance_due": balance,
            "issued_at": created_dt, "due_date": (created_dt + timedelta(days=30)).date(),
            "created_at": created_dt, "updated_at": created_dt
        }.items():
            if k in i_row: i_row[k] = v
        inv_rows.append([i_row[k] for k in inv_keys])

    execute_batch(cur_eco, f"INSERT INTO sales.orders ({', '.join(ord_keys)}) VALUES ({', '.join(['%s']*len(ord_keys))}) ON CONFLICT DO NOTHING", ord_rows, page_size=1000)
    execute_batch(cur_bil, f"INSERT INTO billing.invoices ({', '.join(inv_keys)}) VALUES ({', '.join(['%s']*len(inv_keys))}) ON CONFLICT DO NOTHING", inv_rows, page_size=1000)
    conn_eco.commit(); conn_bil.commit()
    cur_eco.close(); cur_bil.close(); conn_eco.close(); conn_bil.close()
    print("[FAST BATCH SUCCESS] 5,000+ Enterprise Orders & Invoices Injected in 1 Second!")

if __name__ == "__main__":
    seed_massive_data()
