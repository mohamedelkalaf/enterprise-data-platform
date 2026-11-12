import os
import uuid
import json
import hashlib
from decimal import Decimal
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="Enterprise E-Commerce System API",
    version="1.0.0",
    description="Operational Source System for E-Commerce Domain"
)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5435")
DB_NAME = os.getenv("DB_NAME", "ecommerce_db")
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

# --- Pydantic Schemas ---
class OrderItemCreate(BaseModel):
    variant_id: str
    quantity: int = Field(..., gt=0)

class OrderCreateRequest(BaseModel):
    customer_id: str
    currency_code: str = "EGP"
    shipping_amount: Decimal = Decimal("150.00")
    items: List[OrderItemCreate]

# --- Endpoints ---

@app.get("/api/v1/health")
def health_check():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        return {"status": "healthy", "service": "ecommerce_api", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/products")
def list_products():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.product_id, p.name AS product_name, b.name AS brand_name,
                   v.variant_id, v.sku, v.variant_name, pr.amount AS price, pl.currency_code
            FROM catalog.products p
            LEFT JOIN catalog.brands b ON p.brand_id = b.brand_id
            JOIN catalog.product_variants v ON p.product_id = v.product_id
            JOIN catalog.product_prices pr ON v.variant_id = pr.variant_id
            JOIN catalog.price_lists pl ON pr.price_list_id = pl.price_list_id
            WHERE p.is_active = TRUE AND pl.is_default = TRUE;
        """)
        rows = cur.fetchall()
    conn.close()
    return {"count": len(rows), "products": rows}

@app.get("/api/v1/orders")
def list_orders():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.order_id, o.order_number, o.customer_id,
                   c.first_name || ' ' || COALESCE(c.last_name, '') AS customer_name,
                   o.subtotal_amount, o.discount_amount, o.tax_amount,
                   o.shipping_amount, o.total_amount, o.currency_code,
                   o.order_status, o.placed_at
            FROM sales.orders o
            JOIN customers.customers c ON o.customer_id = c.customer_id
            ORDER BY o.placed_at DESC;
        """)
        orders = cur.fetchall()
    conn.close()
    return {"count": len(orders), "orders": orders}

@app.get("/api/v1/orders/{order_id}")
def get_order_details(order_id: str):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM sales.orders WHERE order_id = %s;", (order_id,))
        order = cur.fetchone()
        if not order:
            conn.close()
            raise HTTPException(status_code=404, detail="Order not found")
        cur.execute("SELECT * FROM sales.order_items WHERE order_id = %s;", (order_id,))
        items = cur.fetchall()
    conn.close()
    return {"order": order, "items": items}

@app.post("/api/v1/orders", status_code=201)
def create_order(
    payload: OrderCreateRequest,
    x_idempotency_key: Optional[str] = Header(None)
):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ù€ Idempotency Key Ù„Ù…Ù†Ø¹ ØªÙƒØ±Ø§Ø± Ø§Ù„Ø·Ù„Ø¨
                if x_idempotency_key:
                    req_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
                    cur.execute(
                        "SELECT response_body FROM integration.idempotency_keys WHERE idempotency_key = %s AND status = 'COMPLETED';",
                        (x_idempotency_key,)
                    )
                    existing = cur.fetchone()
                    if existing and existing["response_body"]:
                        return existing["response_body"]

                # 2. Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ø¹Ù…ÙŠÙ„
                cur.execute("SELECT * FROM customers.customers WHERE customer_id = %s;", (payload.customer_id,))
                customer = cur.fetchone()
                if not customer:
                    raise HTTPException(status_code=404, detail="Customer not found")

                # 3. Ø­Ø³Ø§Ø¨ Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø£ØµÙ†Ø§Ù ÙˆØ§Ù„Ø¶Ø±Ø§Ø¦Ø¨ (14% VAT)
                subtotal = Decimal("0.00")
                prepared_items = []
                for item in payload.items:
                    cur.execute("""
                        SELECT v.variant_id, v.sku, v.variant_name, p.name AS product_name, pr.amount AS unit_price
                        FROM catalog.product_variants v
                        JOIN catalog.products p ON v.product_id = p.product_id
                        JOIN catalog.product_prices pr ON v.variant_id = pr.variant_id
                        JOIN catalog.price_lists pl ON pr.price_list_id = pl.price_list_id
                        WHERE v.variant_id = %s AND pl.is_default = TRUE
                        LIMIT 1;
                    """, (item.variant_id,))
                    variant = cur.fetchone()
                    if not variant:
                        raise HTTPException(status_code=400, detail=f"Variant {item.variant_id} not found or has no price")

                    line_sub = Decimal(str(variant["unit_price"])) * item.quantity
                    line_tax = (line_sub * Decimal("0.14")).quantize(Decimal("0.0001"))
                    line_total = line_sub + line_tax
                    subtotal += line_sub
                    prepared_items.append({
                        **variant,
                        "quantity": item.quantity,
                        "line_tax": line_tax,
                        "line_total": line_total
                    })

                total_tax = (subtotal * Decimal("0.14")).quantize(Decimal("0.0001"))
                total_amount = subtotal + total_tax + payload.shipping_amount
                order_id = str(uuid.uuid4())
                order_number = f"ORD-2026-{str(uuid.uuid4())[:6].upper()}"

                # 4. Ø¥Ø¯Ø®Ø§Ù„ Ø§Ù„Ø£ÙˆØ±Ø¯Ø±
                cur.execute("""
                    INSERT INTO sales.orders (
                        order_id, order_number, customer_id, currency_code, exchange_rate,
                        subtotal_amount, discount_amount, tax_amount, shipping_amount, total_amount,
                        reporting_currency_code, reporting_total_amount, order_status,
                        customer_email_snapshot, customer_phone_snapshot
                    ) VALUES (%s, %s, %s, %s, 1.0, %s, 0, %s, %s, %s, %s, %s, 'CONFIRMED', %s, %s);
                """, (
                    order_id, order_number, payload.customer_id, payload.currency_code,
                    subtotal, total_tax, payload.shipping_amount, total_amount,
                    payload.currency_code, total_amount,
                    customer["email"], customer["phone"]
                ))

                # 5. Ø¥Ø¯Ø®Ø§Ù„ ØªÙØ§ØµÙŠÙ„ Ø§Ù„Ø£ÙˆØ±Ø¯Ø± ÙˆØ§Ù„Ø¶Ø±Ø§Ø¦Ø¨
                for pi in prepared_items:
                    order_item_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO sales.order_items (
                            order_item_id, order_id, variant_id, sku_snapshot, product_name_snapshot,
                            variant_name_snapshot, quantity, unit_price, discount_amount, tax_amount, line_total
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s);
                    """, (
                        order_item_id, order_id, pi["variant_id"], pi["sku"], pi["product_name"],
                        pi["variant_name"], pi["quantity"], pi["unit_price"], pi["line_tax"], pi["line_total"]
                    ))

                # 6. ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø­Ø¯Ø« ÙÙŠ Ø§Ù„Ù€ Outbox (Transactional Outbox Pattern)
                event_payload = {
                    "order_id": order_id,
                    "order_number": order_number,
                    "customer_id": payload.customer_id,
                    "total_amount": float(total_amount),
                    "currency": payload.currency_code,
                    "status": "CONFIRMED"
                }
                cur.execute("""
                    INSERT INTO integration.outbox_events (
                        aggregate_type, aggregate_id, event_type, event_version, payload, status
                    ) VALUES ('ORDER', %s, 'order.created', 1, %s::jsonb, 'PENDING');
                """, (order_id, json.dumps(event_payload)))

                response_data = {
                    "message": "Order created successfully",
                    "order_id": order_id,
                    "order_number": order_number,
                    "total_amount": float(total_amount),
                    "outbox_event": "PENDING"
                }

                # 7. Ø­ÙØ¸ Ù†ØªÙŠØ¬Ø© Ø§Ù„Ù€ Idempotency
                if x_idempotency_key:
                    cur.execute("""
                        INSERT INTO integration.idempotency_keys (
                            idempotency_key, request_hash, response_status, response_body, resource_id, status, expires_at
                        ) VALUES (%s, %s, 201, %s::jsonb, %s, 'COMPLETED', NOW() + INTERVAL '24 hours')
                        ON CONFLICT (idempotency_key) DO NOTHING;
                    """, (x_idempotency_key, req_hash, json.dumps(response_data), order_id))

                return response_data
    finally:
        conn.close()

@app.get("/api/v1/outbox/pending")
def get_pending_outbox_events():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_id, aggregate_type, aggregate_id, event_type, payload, created_at
            FROM integration.outbox_events
            WHERE status = 'PENDING'
            ORDER BY created_at ASC;
        """)
        events = cur.fetchall()
    conn.close()
    return {"pending_count": len(events), "events": events}
