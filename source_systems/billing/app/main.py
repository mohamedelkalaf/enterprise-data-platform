import os
import uuid
import json
from decimal import Decimal
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="Enterprise Billing & Invoicing System API",
    version="1.0.0",
    description="Operational Source System for Finance, Billing, Payments & AR"
)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5435")
DB_NAME = os.getenv("DB_NAME", "billing_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "edp_password_2026")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor
    )

class InvoiceItemInput(BaseModel):
    sku: str
    description: str
    quantity: int = Field(..., gt=0)
    unit_price: Decimal

class InvoiceCreateRequest(BaseModel):
    order_id: str
    order_number: str
    customer_id: str
    currency_code: str = "EGP"
    shipping_amount: Decimal = Decimal("200.00")
    items: List[InvoiceItemInput]

class PaymentCreateRequest(BaseModel):
    invoice_id: str
    customer_id: str
    method_code: str = "INSTAPAY"
    amount: Decimal = Field(..., gt=0)

@app.get("/api/v1/health")
def health_check():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        return {"status": "healthy", "service": "billing_api", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/invoices")
def list_invoices():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT i.*, ar.aging_bucket, ar.status AS ar_status
            FROM billing.invoices i
            LEFT JOIN billing.accounts_receivable ar ON i.invoice_id = ar.invoice_id
            ORDER BY i.issued_at DESC;
        """)
        rows = cur.fetchall()
    conn.close()
    return {"count": len(rows), "invoices": rows}

@app.post("/api/v1/invoices", status_code=201)
def create_invoice(payload: InvoiceCreateRequest):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                subtotal = Decimal("0.00")
                prepared_items = []
                for item in payload.items:
                    line_sub = item.unit_price * item.quantity
                    line_tax = (line_sub * Decimal("0.14")).quantize(Decimal("0.0001"))
                    line_total = line_sub + line_tax
                    subtotal += line_sub
                    prepared_items.append({
                        "sku": item.sku,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "tax_amount": line_tax,
                        "line_total": line_total
                    })

                total_tax = (subtotal * Decimal("0.14")).quantize(Decimal("0.0001"))
                total_amount = subtotal + total_tax + payload.shipping_amount
                invoice_id = str(uuid.uuid4())
                invoice_number = f"INV-2026-{str(uuid.uuid4())[:6].upper()}"

                # 1. إنشاء الفاتورة
                cur.execute("""
                    INSERT INTO billing.invoices (
                        invoice_id, invoice_number, order_id, order_number, customer_id,
                        currency_code, subtotal_amount, discount_amount, tax_amount,
                        shipping_amount, total_amount, paid_amount, balance_due,
                        invoice_status, due_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, 0, %s, 'ISSUED', NOW() + INTERVAL '7 days'
                    );
                """, (
                    invoice_id, invoice_number, payload.order_id, payload.order_number,
                    payload.customer_id, payload.currency_code, subtotal, total_tax,
                    payload.shipping_amount, total_amount, total_amount
                ))

                # 2. عناصر الفاتورة
                for pi in prepared_items:
                    cur.execute("""
                        INSERT INTO billing.invoice_items (
                            invoice_id, sku, description, quantity, unit_price, discount_amount, tax_amount, line_total
                        ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s);
                    """, (
                        invoice_id, pi["sku"], pi["description"], pi["quantity"],
                        pi["unit_price"], pi["tax_amount"], pi["line_total"]
                    ))

                # 3. تسجيل المديونية في Accounts Receivable
                cur.execute("""
                    INSERT INTO billing.accounts_receivable (
                        customer_id, invoice_id, original_amount, outstanding_amount, due_date, aging_bucket, status
                    ) VALUES (%s, %s, %s, %s, CURRENT_DATE + 7, 'CURRENT', 'OPEN');
                """, (payload.customer_id, invoice_id, total_amount, total_amount))

                # 4. تسجيل الحدث في الـ Outbox
                event_payload = {
                    "invoice_id": invoice_id,
                    "invoice_number": invoice_number,
                    "order_id": payload.order_id,
                    "order_number": payload.order_number,
                    "customer_id": payload.customer_id,
                    "total_amount": float(total_amount),
                    "currency": payload.currency_code,
                    "status": "ISSUED"
                }
                cur.execute("""
                    INSERT INTO integration.outbox_events (
                        aggregate_type, aggregate_id, event_type, payload, status
                    ) VALUES ('INVOICE', %s, 'invoice.created', %s::jsonb, 'PENDING');
                """, (invoice_id, json.dumps(event_payload)))

                return {
                    "message": "Invoice issued successfully",
                    "invoice_id": invoice_id,
                    "invoice_number": invoice_number,
                    "order_number": payload.order_number,
                    "total_amount": float(total_amount),
                    "balance_due": float(total_amount),
                    "status": "ISSUED",
                    "outbox_event": "PENDING"
                }
    finally:
        conn.close()

@app.get("/api/v1/outbox/pending")
def get_pending_outbox():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT event_id, aggregate_type, event_type, payload, created_at FROM integration.outbox_events WHERE status = 'PENDING' ORDER BY created_at ASC;")
        events = cur.fetchall()
    conn.close()
    return {"pending_count": len(events), "events": events}
