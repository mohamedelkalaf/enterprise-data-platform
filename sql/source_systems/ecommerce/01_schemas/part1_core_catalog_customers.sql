-- ============================================================================
-- ENTERPRISE E-COMMERCE DATABASE DDL - PART 1
-- Schemas, Extensions, Reference, Catalog, and Customers
-- ============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- لتوليد gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gist"; -- لمنع تداخل فترات الأسعار مستقبلاً

-- 2. SCHEMAS
CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS customers;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS promotions;
CREATE SCHEMA IF NOT EXISTS integration;

-- 3. UNIFIED UPDATED_AT TRIGGER FUNCTION
CREATE OR REPLACE FUNCTION reference.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- A. REFERENCE SCHEMA (2 Tables)
-- ============================================================================

-- 1. reference.currencies
CREATE TABLE IF NOT EXISTS reference.currencies (
    currency_code CHAR(3) PRIMARY KEY,
    currency_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    decimal_places SMALLINT NOT NULL DEFAULT 2 CHECK (decimal_places BETWEEN 0 AND 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. reference.exchange_rates
CREATE TABLE IF NOT EXISTS reference.exchange_rates (
    exchange_rate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base_currency CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    quote_currency CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    exchange_rate NUMERIC(20,10) NOT NULL CHECK (exchange_rate > 0),
    rate_source VARCHAR(100) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_different_currencies CHECK (base_currency <> quote_currency)
);

-- ============================================================================
-- B. CATALOG SCHEMA (10 Tables)
-- ============================================================================

-- 3. catalog.brands
CREATE TABLE IF NOT EXISTS catalog.brands (
    brand_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(180) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. catalog.categories
CREATE TABLE IF NOT EXISTS catalog.categories (
    category_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES catalog.categories(category_id) ON DELETE SET NULL,
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(180) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_category_not_self_parent CHECK (category_id <> parent_id)
);

-- 5. catalog.products
CREATE TABLE IF NOT EXISTS catalog.products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID REFERENCES catalog.brands(brand_id) ON DELETE SET NULL,
    name VARCHAR(250) NOT NULL,
    slug VARCHAR(280) NOT NULL UNIQUE,
    description TEXT,
    product_type VARCHAR(20) NOT NULL CHECK (product_type IN ('SIMPLE', 'VARIABLE')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. catalog.product_variants
CREATE TABLE IF NOT EXISTS catalog.product_variants (
    variant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES catalog.products(product_id) ON DELETE CASCADE,
    sku VARCHAR(100) NOT NULL UNIQUE,
    variant_name VARCHAR(200) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    barcode VARCHAR(100) UNIQUE,
    weight NUMERIC(12,3) CHECK (weight IS NULL OR weight >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'DISCONTINUED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. catalog.product_categories
CREATE TABLE IF NOT EXISTS catalog.product_categories (
    product_id UUID NOT NULL REFERENCES catalog.products(product_id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES catalog.categories(category_id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, category_id)
);

-- 8. catalog.product_images
CREATE TABLE IF NOT EXISTS catalog.product_images (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES catalog.products(product_id) ON DELETE CASCADE,
    variant_id UUID REFERENCES catalog.product_variants(variant_id) ON DELETE SET NULL,
    object_key TEXT NOT NULL,
    alt_text VARCHAR(250),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. catalog.product_attributes
CREATE TABLE IF NOT EXISTS catalog.product_attributes (
    attribute_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES catalog.products(product_id) ON DELETE CASCADE,
    attribute_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(20) NOT NULL CHECK (data_type IN ('STRING', 'NUMBER', 'BOOLEAN')),
    is_variant_attribute BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. catalog.variant_attribute_values
CREATE TABLE IF NOT EXISTS catalog.variant_attribute_values (
    variant_id UUID NOT NULL REFERENCES catalog.product_variants(variant_id) ON DELETE CASCADE,
    attribute_id UUID NOT NULL REFERENCES catalog.product_attributes(attribute_id) ON DELETE CASCADE,
    attribute_value VARCHAR(250) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (variant_id, attribute_id)
);

-- 11. catalog.price_lists
CREATE TABLE IF NOT EXISTS catalog.price_lists (
    price_list_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    currency_code CHAR(3) NOT NULL REFERENCES reference.currencies(currency_code),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_pricelist_dates CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- 12. catalog.product_prices
CREATE TABLE IF NOT EXISTS catalog.product_prices (
    product_price_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID NOT NULL REFERENCES catalog.product_variants(variant_id) ON DELETE CASCADE,
    price_list_id UUID NOT NULL REFERENCES catalog.price_lists(price_list_id) ON DELETE CASCADE,
    amount NUMERIC(19,4) NOT NULL CHECK (amount >= 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_product_price_dates CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- ============================================================================
-- C. CUSTOMERS SCHEMA (3 Tables)
-- ============================================================================

-- 13. customers.customers
CREATE TABLE IF NOT EXISTS customers.customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(254),
    phone VARCHAR(30),
    customer_type VARCHAR(20) NOT NULL CHECK (customer_type IN ('GUEST', 'REGISTERED')),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED')),
    email_verified_at TIMESTAMPTZ,
    phone_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. customers.customer_accounts
CREATE TABLE IF NOT EXISTS customers.customer_accounts (
    account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE REFERENCES customers.customers(customer_id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (account_status IN ('ACTIVE', 'LOCKED', 'DISABLED')),
    last_login_at TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 15. customers.customer_addresses
CREATE TABLE IF NOT EXISTS customers.customer_addresses (
    address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers.customers(customer_id) ON DELETE CASCADE,
    address_type VARCHAR(20) NOT NULL CHECK (address_type IN ('SHIPPING', 'BILLING', 'BOTH')),
    recipient_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    country_code CHAR(2) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    postal_code VARCHAR(20),
    address_line_1 VARCHAR(250) NOT NULL,
    address_line_2 VARCHAR(250),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);