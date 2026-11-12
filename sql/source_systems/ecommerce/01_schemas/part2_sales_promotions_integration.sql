-- ============================================================================
-- ENTERPRISE E-COMMERCE DATABASE DDL - PART 2
-- Sales (with Tax & Adjustments), Promotions, Integration, and Indexes
-- ============================================================================

-- ============================================================================
-- D. SALES SCHEMA (11 Tables including Tax Lines & Adjustments)
-- ============================================================================

-- 16. sales.shopping_carts
CREATE TABLE IF NOT EXISTS sales.shopping_carts (
    cart_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers.customers(customer_id) ON DELETE SET NULL,
    guest_token_hash TEXT,
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CONVERTED', 'ABANDONED', 'EXPIRED')),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_cart_owner CHECK (customer_id IS NOT NULL OR guest_token_hash IS NOT NULL)
);

-- 17. sales.cart_items
CREATE TABLE IF NOT EXISTS sales.cart_items (
    cart_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES sales.shopping_carts(cart_id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES catalog.product_variants(variant_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cart_id, variant_id)
);

-- 18. sales.orders
CREATE TABLE IF NOT EXISTS sales.orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES customers.customers(customer_id),
    cart_id UUID REFERENCES sales.shopping_carts(cart_id),
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    exchange_rate NUMERIC(20,10) NOT NULL DEFAULT 1.0 CHECK (exchange_rate > 0),
    subtotal_amount NUMERIC(19,4) NOT NULL CHECK (subtotal_amount >= 0),
    discount_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    shipping_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (shipping_amount >= 0),
    total_amount NUMERIC(19,4) NOT NULL CHECK (total_amount >= 0),
    reporting_currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    reporting_total_amount NUMERIC(19,4) NOT NULL CHECK (reporting_total_amount >= 0),
    order_status VARCHAR(30) NOT NULL CHECK (
        order_status IN (
            'PENDING', 'CONFIRMED', 'PROCESSING', 'READY_TO_SHIP',
            'SHIPPED', 'DELIVERED', 'CANCELLED', 'ON_HOLD', 'FAILED'
        )
    ),
    customer_email_snapshot VARCHAR(254),
    customer_phone_snapshot VARCHAR(30),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 19. sales.order_items
CREATE TABLE IF NOT EXISTS sales.order_items (
    order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES catalog.product_variants(variant_id),
    sku_snapshot VARCHAR(100) NOT NULL,
    product_name_snapshot VARCHAR(250) NOT NULL,
    variant_name_snapshot VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19,4) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total NUMERIC(19,4) NOT NULL CHECK (line_total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 20. sales.order_addresses
CREATE TABLE IF NOT EXISTS sales.order_addresses (
    order_address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    address_type VARCHAR(20) NOT NULL CHECK (address_type IN ('SHIPPING', 'BILLING')),
    recipient_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    country_code CHAR(2) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    postal_code VARCHAR(20),
    address_line_1 VARCHAR(250) NOT NULL,
    address_line_2 VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (order_id, address_type)
);

-- 21. sales.order_status_history
CREATE TABLE IF NOT EXISTS sales.order_status_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    old_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    changed_by UUID,
    change_reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 22. sales.order_notes
CREATE TABLE IF NOT EXISTS sales.order_notes (
    note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    note_type VARCHAR(20) NOT NULL CHECK (note_type IN ('CUSTOMER', 'INTERNAL', 'SYSTEM')),
    content TEXT NOT NULL,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 23. sales.order_tax_lines (إضافة المراجعة النهائية)
CREATE TABLE IF NOT EXISTS sales.order_tax_lines (
    tax_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    order_item_id UUID REFERENCES sales.order_items(order_item_id) ON DELETE CASCADE,
    tax_name VARCHAR(100) NOT NULL,
    tax_rate NUMERIC(9,6) NOT NULL CHECK (tax_rate >= 0),
    taxable_amount NUMERIC(19,4) NOT NULL CHECK (taxable_amount >= 0),
    tax_amount NUMERIC(19,4) NOT NULL CHECK (tax_amount >= 0),
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 24. sales.order_adjustments (إضافة المراجعة النهائية)
CREATE TABLE IF NOT EXISTS sales.order_adjustments (
    adjustment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    adjustment_type VARCHAR(30) NOT NULL CHECK (adjustment_type IN ('DISCOUNT', 'FEE', 'SURCHARGE', 'MANUAL_OVERRIDE')),
    amount NUMERIC(19,4) NOT NULL,
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    reason TEXT NOT NULL,
    source_reference VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 25. sales.returns
CREATE TABLE IF NOT EXISTS sales.returns (
    return_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_number VARCHAR(40) NOT NULL UNIQUE,
    order_id UUID NOT NULL REFERENCES sales.orders(order_id),
    customer_id UUID NOT NULL REFERENCES customers.customers(customer_id),
    reason_code VARCHAR(50) NOT NULL,
    reason_details TEXT,
    status VARCHAR(30) NOT NULL CHECK (status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'RECEIVED', 'COMPLETED', 'CANCELLED')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 26. sales.return_items
CREATE TABLE IF NOT EXISTS sales.return_items (
    return_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id UUID NOT NULL REFERENCES sales.returns(return_id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES sales.order_items(order_item_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    condition_status VARCHAR(30) CHECK (condition_status IN ('UNOPENED', 'OPENED', 'DAMAGED', 'DEFECTIVE')),
    resolution_type VARCHAR(30) CHECK (resolution_type IN ('REFUND', 'REPLACEMENT', 'STORE_CREDIT')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- E. PROMOTIONS SCHEMA (4 Tables)
-- ============================================================================

-- 27. promotions.coupons
CREATE TABLE IF NOT EXISTS promotions.coupons (
    coupon_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(80) NOT NULL UNIQUE,
    discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('PERCENTAGE', 'FIXED')),
    discount_value NUMERIC(19,4) NOT NULL CHECK (discount_value > 0),
    currency_code CHAR(3) REFERENCES reference.currencies(currency_code),
    max_discount_amount NUMERIC(19,4) CHECK (max_discount_amount IS NULL OR max_discount_amount > 0),
    minimum_order_amount NUMERIC(19,4) NOT NULL DEFAULT 0 CHECK (minimum_order_amount >= 0),
    usage_limit INTEGER CHECK (usage_limit IS NULL OR usage_limit > 0),
    usage_per_customer INTEGER CHECK (usage_per_customer IS NULL OR usage_per_customer > 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_coupon_dates CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- 28. promotions.promotion_rules
CREATE TABLE IF NOT EXISTS promotions.promotion_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id UUID NOT NULL REFERENCES promotions.coupons(coupon_id) ON DELETE CASCADE,
    rule_type VARCHAR(40) NOT NULL,
    rule_value JSONB NOT NULL,
    operator VARCHAR(20) NOT NULL CHECK (operator IN ('IN', 'NOT_IN', 'GTE', 'LTE', 'EQ')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 29. promotions.order_coupons
CREATE TABLE IF NOT EXISTS promotions.order_coupons (
    order_id UUID NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    coupon_id UUID NOT NULL REFERENCES promotions.coupons(coupon_id),
    discount_amount NUMERIC(19,4) NOT NULL CHECK (discount_amount >= 0),
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (order_id, coupon_id)
);

-- 30. promotions.coupon_redemptions
CREATE TABLE IF NOT EXISTS promotions.coupon_redemptions (
    redemption_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id UUID NOT NULL REFERENCES promotions.coupons(coupon_id),
    customer_id UUID NOT NULL REFERENCES customers.customers(customer_id),
    order_id UUID NOT NULL UNIQUE REFERENCES sales.orders(order_id) ON DELETE CASCADE,
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    discount_amount NUMERIC(19,4) NOT NULL CHECK (discount_amount >= 0)
);

-- ============================================================================
-- F. INTEGRATION SCHEMA (4 Tables)
-- ============================================================================

-- 31. integration.outbox_events
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
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    last_error TEXT
);

-- 32. integration.idempotency_keys
CREATE TABLE IF NOT EXISTS integration.idempotency_keys (
    idempotency_key VARCHAR(200) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    resource_id UUID,
    status VARCHAR(20) NOT NULL CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 33. integration.webhook_subscriptions
CREATE TABLE IF NOT EXISTS integration.webhook_subscriptions (
    subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(120) NOT NULL,
    endpoint_url TEXT NOT NULL,
    secret_reference VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 34. integration.integration_logs
CREATE TABLE IF NOT EXISTS integration.integration_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id UUID NOT NULL,
    destination VARCHAR(100) NOT NULL,
    event_id UUID,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'RETRYING')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- G. STRATEGIC INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_products_status_active ON catalog.products(status, is_active);
CREATE INDEX IF NOT EXISTS idx_product_categories_cat_prod ON catalog.product_categories(category_id, product_id);
CREATE INDEX IF NOT EXISTS idx_product_prices_lookup ON catalog.product_prices(variant_id, price_list_id, valid_from);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers.customers(email);
CREATE INDEX IF NOT EXISTS idx_customer_addresses_default ON customers.customer_addresses(customer_id, is_default);
CREATE INDEX IF NOT EXISTS idx_orders_customer_placed ON sales.orders(customer_id, placed_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status_placed ON sales.orders(order_status, placed_at);
CREATE INDEX IF NOT EXISTS idx_orders_placed_at ON sales.orders(placed_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON sales.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_variant_order ON sales.order_items(variant_id, order_id);
CREATE INDEX IF NOT EXISTS idx_order_history_order_changed ON sales.order_status_history(order_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_returns_order_status ON sales.returns(order_id, status);
CREATE INDEX IF NOT EXISTS idx_outbox_polling ON integration.outbox_events(status, next_retry_at, created_at);
CREATE INDEX IF NOT EXISTS idx_integration_logs_corr ON integration.integration_logs(correlation_id, created_at);