-- ============================================================================
-- ENTERPRISE E-COMMERCE SEED DATA & END-TO-END TRANSACTION TEST
-- ============================================================================

BEGIN;

-- 1. العملات وأسعار الصرف (Reference)
INSERT INTO reference.currencies (currency_code, currency_name, symbol, decimal_places)
VALUES 
    ('EGP', 'Egyptian Pound', 'E£', 2),
    ('USD', 'US Dollar', '$', 2),
    ('SAR', 'Saudi Riyal', 'SR', 2)
ON CONFLICT (currency_code) DO NOTHING;

INSERT INTO reference.exchange_rates (base_currency, quote_currency, exchange_rate, rate_source, effective_at)
VALUES 
    ('USD', 'EGP', 50.0000000000, 'Central_Bank_Feed', NOW()),
    ('SAR', 'EGP', 13.3300000000, 'Central_Bank_Feed', NOW());

-- 2. البراندات والأقسام والمنتجات (Catalog)
WITH ins_brand AS (
    INSERT INTO catalog.brands (brand_id, name, slug, description)
    VALUES ('11111111-1111-1111-1111-111111111111', 'Dell', 'dell', 'Dell Computers & Laptops')
    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
    RETURNING brand_id
),
ins_cat AS (
    INSERT INTO catalog.categories (category_id, name, slug, description, sort_order)
    VALUES ('22222222-2222-2222-2222-222222222222', 'Laptops', 'laptops', 'Business & Gaming Laptops', 1)
    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
    RETURNING category_id
),
ins_prod AS (
    INSERT INTO catalog.products (product_id, brand_id, name, slug, description, product_type, status)
    SELECT '33333333-3333-3333-3333-333333333333', brand_id, 'Dell Latitude 5540', 'dell-latitude-5540', 'Enterprise Laptop Core i5', 'VARIABLE', 'ACTIVE'
    FROM ins_brand
    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
    RETURNING product_id
)
INSERT INTO catalog.product_categories (product_id, category_id, is_primary)
SELECT product_id, category_id, TRUE FROM ins_prod, ins_cat
ON CONFLICT DO NOTHING;

-- إضافة 2 Variants للمنتج
INSERT INTO catalog.product_variants (variant_id, product_id, sku, variant_name, is_default, barcode, weight, status)
VALUES 
    ('44444444-4444-4444-4444-444444444441', '33333333-3333-3333-3333-333333333333', 'DELL-5540-16G-512', 'Dell 5540 - 16GB RAM / 512GB SSD', TRUE, '622100000001', 1.650, 'ACTIVE'),
    ('44444444-4444-4444-4444-444444444442', '33333333-3333-3333-3333-333333333333', 'DELL-5540-32G-1TB', 'Dell 5540 - 32GB RAM / 1TB SSD', FALSE, '622100000002', 1.680, 'ACTIVE')
ON CONFLICT (sku) DO NOTHING;

-- قائمة الأسعار وأسعار الـ Variants
INSERT INTO catalog.price_lists (price_list_id, name, currency_code, is_default, valid_from)
VALUES ('55555555-5555-5555-5555-555555555555', 'Standard Egypt Retail', 'EGP', TRUE, NOW() - INTERVAL '30 days')
ON CONFLICT (price_list_id) DO NOTHING;

INSERT INTO catalog.product_prices (variant_id, price_list_id, amount, valid_from)
VALUES 
    ('44444444-4444-4444-4444-444444444441', '55555555-5555-5555-5555-555555555555', 35000.0000, NOW() - INTERVAL '30 days'),
    ('44444444-4444-4444-4444-444444444442', '55555555-5555-5555-5555-555555555555', 45000.0000, NOW() - INTERVAL '30 days');

-- 3. إضافة عميل وعنوانه (Customers)
INSERT INTO customers.customers (customer_id, first_name, last_name, email, phone, customer_type, status, email_verified_at)
VALUES ('66666666-6666-6666-6666-666666666666', 'Mohamed', 'Elkalaf', 'mohamed@example.com', '+201000000001', 'REGISTERED', 'ACTIVE', NOW())
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO customers.customer_addresses (address_id, customer_id, address_type, recipient_name, phone, country_code, city, address_line_1, is_default)
VALUES ('77777777-7777-7777-7777-777777777777', '66666666-6666-6666-6666-666666666666', 'BOTH', 'Mohamed Elkalaf', '+201000000001', 'EG', 'Alexandria', 'Smouha, Victor Emmanuel Sq', TRUE)
ON CONFLICT (address_id) DO NOTHING;

-- 4. إضافة كوبون خصم (Promotions)
INSERT INTO promotions.coupons (coupon_id, code, discount_type, discount_value, currency_code, minimum_order_amount, valid_from)
VALUES ('88888888-8888-8888-8888-888888888888', 'WELCOME1000', 'FIXED', 1000.0000, 'EGP', 10000.0000, NOW() - INTERVAL '10 days')
ON CONFLICT (code) DO NOTHING;

-- 5. إنشاء طلب مكتمل + تفاصيله + الضرائب + Outbox Event داخل نفس الـ Transaction
INSERT INTO sales.orders (
    order_id, order_number, customer_id, currency_code, exchange_rate,
    subtotal_amount, discount_amount, tax_amount, shipping_amount, total_amount,
    reporting_currency_code, reporting_total_amount, order_status,
    customer_email_snapshot, customer_phone_snapshot, placed_at
)
VALUES (
    '99999999-9999-9999-9999-999999999999', 'ORD-2026-000001', '66666666-6666-6666-6666-666666666666',
    'EGP', 1.0000000000,
    35000.0000, 1000.0000, 4760.0000, 150.0000, 38910.0000,
    'EGP', 38910.0000, 'CONFIRMED',
    'mohamed@example.com', '+201000000001', NOW()
)
ON CONFLICT (order_number) DO NOTHING;

INSERT INTO sales.order_items (
    order_item_id, order_id, variant_id, sku_snapshot, product_name_snapshot,
    variant_name_snapshot, quantity, unit_price, discount_amount, tax_amount, line_total
)
VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '99999999-9999-9999-9999-999999999999',
    '44444444-4444-4444-4444-444444444441', 'DELL-5540-16G-512', 'Dell Latitude 5540',
    'Dell 5540 - 16GB RAM / 512GB SSD', 1, 35000.0000, 1000.0000, 4760.0000, 38760.0000
)
ON CONFLICT (order_item_id) DO NOTHING;

INSERT INTO sales.order_addresses (
    order_id, address_type, recipient_name, phone, country_code, city, address_line_1
)
VALUES (
    '99999999-9999-9999-9999-999999999999', 'SHIPPING', 'Mohamed Elkalaf', '+201000000001', 'EG', 'Alexandria', 'Smouha, Victor Emmanuel Sq'
)
ON CONFLICT (order_id, address_type) DO NOTHING;

INSERT INTO sales.order_tax_lines (
    order_id, order_item_id, tax_name, tax_rate, taxable_amount, tax_amount, currency_code
)
VALUES (
    '99999999-9999-9999-9999-999999999999', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'Egypt VAT 14%', 0.140000, 34000.0000, 4760.0000, 'EGP'
);

INSERT INTO sales.order_status_history (order_id, old_status, new_status, change_reason)
VALUES ('99999999-9999-9999-9999-999999999999', 'PENDING', 'CONFIRMED', 'Initial seed order confirmation');

-- 6. تسجيل الحدث في الـ Transactional Outbox لإرساله إلى Kafka لاحقاً
INSERT INTO integration.outbox_events (
    aggregate_type, aggregate_id, event_type, event_version, payload, status
)
VALUES (
    'ORDER',
    '99999999-9999-9999-9999-999999999999',
    'order.created',
    1,
    '{"order_number": "ORD-2026-000001", "customer_id": "66666666-6666-6666-6666-666666666666", "total_amount": 38910.00, "currency": "EGP", "status": "CONFIRMED"}'::jsonb,
    'PENDING'
);

COMMIT;