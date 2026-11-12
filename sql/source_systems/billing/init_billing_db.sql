-- ============================================================================
-- ENTERPRISE BILLING & INVOICING DATABASE DDL + SEED DATA (billing_db)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS billing;
CREATE SCHEMA IF NOT EXISTS integration;

-- 1. billing.payment_methods
CREATE TABLE IF NOT EXISTS billing.payment_methods (
    payment_method_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    method_code VARCHAR(40) NOT NULL UNIQUE,
    method_name VARCHAR(100) NOT NULL,
    provider VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. billing.taxes
CREATE TABLE IF NOT EXISTS billing.taxes (
    tax_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_code VARCHAR(40) NOT NULL UNIQUE,
    tax_name VARCHAR(100) NOT NULL,
    tax_rate NUMERIC(9,6) NOT NULL CHECK (tax_rate >= 0),
    country_code CHAR(2) NOT NULL DEFAULT 'EG',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. billing.invoices
CREATE TABLE IF NOT EXISTS billing.invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(40) NOT NULL UNIQUE,
    order_id UUID NOT NULL UNIQUE,
    order_number VARCHAR(40) NOT NULL,
    customer_id UUID NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'EGP',
    subtotal_amount NUMERIC(19,4) NOT NULL CHECK (subtotal_amount >= 0),
    discount_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    shipping_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (shipping_amount >= 0),
    total_amount NUMERIC(19,4) NOT NULL CHECK (total_amount >= 0),
    paid_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    balance_due NUMERIC(19,4) NOT NULL CHECK (balance_due >= 0),
    invoice_status VARCHAR(30) NOT NULL CHECK (invoice_status IN ('DRAFT', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'OVERDUE', 'CANCELLED', 'VOID')),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. billing.invoice_items
CREATE TABLE IF NOT EXISTS billing.invoice_items (
    invoice_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES billing.invoices(invoice_id) ON DELETE CASCADE,
    sku VARCHAR(100) NOT NULL,
    description VARCHAR(250) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19,4) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total NUMERIC(19,4) NOT NULL CHECK (line_total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. billing.payments
CREATE TABLE IF NOT EXISTS billing.payments (
    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_reference VARCHAR(60) NOT NULL UNIQUE,
    invoice_id UUID NOT NULL REFERENCES billing.invoices(invoice_id),
    customer_id UUID NOT NULL,
    payment_method_id UUID NOT NULL REFERENCES billing.payment_methods(payment_method_id),
    currency_code CHAR(3) NOT NULL DEFAULT 'EGP',
    amount NUMERIC(19,4) NOT NULL CHECK (amount > 0),
    payment_status VARCHAR(30) NOT NULL CHECK (payment_status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'REFUNDED')),
    gateway_transaction_id VARCHAR(120),
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. billing.payment_allocations
CREATE TABLE IF NOT EXISTS billing.payment_allocations (
    allocation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL REFERENCES billing.payments(payment_id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL REFERENCES billing.invoices(invoice_id) ON DELETE CASCADE,
    allocated_amount NUMERIC(19,4) NOT NULL CHECK (allocated_amount > 0),
    allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. billing.refunds
CREATE TABLE IF NOT EXISTS billing.refunds (
    refund_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    refund_number VARCHAR(40) NOT NULL UNIQUE,
    payment_id UUID NOT NULL REFERENCES billing.payments(payment_id),
    invoice_id UUID NOT NULL REFERENCES billing.invoices(invoice_id),
    amount NUMERIC(19,4) NOT NULL CHECK (amount > 0),
    reason TEXT NOT NULL,
    refund_status VARCHAR(30) NOT NULL CHECK (refund_status IN ('PENDING', 'PROCESSED', 'FAILED')),
    refunded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. billing.credit_notes
CREATE TABLE IF NOT EXISTS billing.credit_notes (
    credit_note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    credit_note_number VARCHAR(40) NOT NULL UNIQUE,
    invoice_id UUID NOT NULL REFERENCES billing.invoices(invoice_id),
    amount NUMERIC(19,4) NOT NULL CHECK (amount > 0),
    reason TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('ISSUED', 'APPLIED', 'VOID')),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. billing.accounts_receivable
CREATE TABLE IF NOT EXISTS billing.accounts_receivable (
    ar_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    invoice_id UUID NOT NULL UNIQUE REFERENCES billing.invoices(invoice_id) ON DELETE CASCADE,
    original_amount NUMERIC(19,4) NOT NULL CHECK (original_amount >= 0),
    outstanding_amount NUMERIC(19,4) NOT NULL CHECK (outstanding_amount >= 0),
    due_date DATE NOT NULL,
    aging_bucket VARCHAR(20) NOT NULL DEFAULT 'CURRENT' CHECK (aging_bucket IN ('CURRENT', '1_30_DAYS', '31_60_DAYS', '61_90_DAYS', '90_PLUS_DAYS')),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'WRITTEN_OFF')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. integration.outbox_events
CREATE TABLE IF NOT EXISTS integration.outbox_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    event_version SMALLINT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')),
    retry_count INTEGER NOT NULL DEFAULT 0
);

-- 11. integration.idempotency_keys
CREATE TABLE IF NOT EXISTS integration.idempotency_keys (
    idempotency_key VARCHAR(200) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    status VARCHAR(20) NOT NULL CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON billing.invoices(customer_id, issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON billing.invoices(invoice_status);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON billing.payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_ar_status_due ON billing.accounts_receivable(status, due_date);
CREATE INDEX IF NOT EXISTS idx_billing_outbox_pending ON integration.outbox_events(status, created_at);

-- ============================================================================
-- SEED DATA FOR BILLING DB
-- ============================================================================
BEGIN;

INSERT INTO billing.payment_methods (payment_method_id, method_code, method_name, provider)
VALUES 
    ('b1111111-1111-1111-1111-111111111111', 'CARD', 'Credit / Debit Card', 'Paymob'),
    ('b1111111-1111-1111-1111-111111111112', 'INSTAPAY', 'InstaPay Egypt', 'EBE'),
    ('b1111111-1111-1111-1111-111111111113', 'COD', 'Cash on Delivery', 'Internal')
ON CONFLICT (method_code) DO NOTHING;

INSERT INTO billing.taxes (tax_code, tax_name, tax_rate, country_code)
VALUES ('EG_VAT_14', 'Egypt Value Added Tax 14%', 0.140000, 'EG')
ON CONFLICT (tax_code) DO NOTHING;

-- إصدار فاتورة للأوردر الأول ORD-2026-000001 وتسجيل دفعتها
INSERT INTO billing.invoices (
    invoice_id, invoice_number, order_id, order_number, customer_id, currency_code,
    subtotal_amount, discount_amount, tax_amount, shipping_amount, total_amount,
    paid_amount, balance_due, invoice_status, issued_at, due_at, paid_at
)
VALUES (
    'b2222222-2222-2222-2222-222222222222', 'INV-2026-000001',
    '99999999-9999-9999-9999-999999999999', 'ORD-2026-000001',
    '66666666-6666-6666-6666-666666666666', 'EGP',
    35000.0000, 1000.0000, 4760.0000, 150.0000, 38910.0000,
    38910.0000, 0.0000, 'PAID', NOW(), NOW() + INTERVAL '7 days', NOW()
)
ON CONFLICT (invoice_number) DO NOTHING;

INSERT INTO billing.invoice_items (
    invoice_id, sku, description, quantity, unit_price, discount_amount, tax_amount, line_total
)
VALUES (
    'b2222222-2222-2222-2222-222222222222', 'DELL-5540-16G-512',
    'Dell Latitude 5540 - 16GB RAM / 512GB SSD', 1, 35000.0000, 1000.0000, 4760.0000, 38760.0000
);

INSERT INTO billing.payments (
    payment_id, payment_reference, invoice_id, customer_id, payment_method_id,
    currency_code, amount, payment_status, gateway_transaction_id
)
VALUES (
    'b3333333-3333-3333-3333-333333333333', 'PAY-2026-000001',
    'b2222222-2222-2222-2222-222222222222', '66666666-6666-6666-6666-666666666666',
    'b1111111-1111-1111-1111-111111111112', 'EGP', 38910.0000, 'SUCCEEDED', 'INSTA-TXN-998877'
)
ON CONFLICT (payment_reference) DO NOTHING;

INSERT INTO billing.payment_allocations (payment_id, invoice_id, allocated_amount)
VALUES ('b3333333-3333-3333-3333-333333333333', 'b2222222-2222-2222-2222-222222222222', 38910.0000);

INSERT INTO billing.accounts_receivable (
    customer_id, invoice_id, original_amount, outstanding_amount, due_date, aging_bucket, status
)
VALUES (
    '66666666-6666-6666-6666-666666666666', 'b2222222-2222-2222-2222-222222222222',
    38910.0000, 0.0000, CURRENT_DATE + 7, 'CURRENT', 'CLOSED'
)
ON CONFLICT (invoice_id) DO NOTHING;

INSERT INTO integration.outbox_events (aggregate_type, aggregate_id, event_type, payload, status)
VALUES (
    'INVOICE', 'b2222222-2222-2222-2222-222222222222', 'invoice.paid',
    '{"invoice_number": "INV-2026-000001", "order_number": "ORD-2026-000001", "paid_amount": 38910.0, "currency": "EGP", "status": "PAID"}'::jsonb,
    'PENDING'
);

COMMIT;
