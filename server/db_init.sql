-- Enterprise CRM Portal - Database Initialization
-- Creates tables and seeds demo data

-- Users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    password_hash VARCHAR(300) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    phone VARCHAR(50),
    company VARCHAR(200),
    industry VARCHAR(100),
    revenue FLOAT DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    price FLOAT NOT NULL,
    stock INTEGER DEFAULT 0,
    category VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    total FLOAT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    notes TEXT,
    shipping_address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Order Items
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price FLOAT NOT NULL
);

-- Invoices
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    amount FLOAT NOT NULL,
    tax FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'unpaid',
    due_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Support Tickets
CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    subject VARCHAR(300) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(50) DEFAULT 'open',
    assigned_to VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(200),
    details TEXT,
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    trace_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Reports
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    report_type VARCHAR(50),
    query TEXT,
    parameters TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Seed Data ────────────────────────────────────────────────────

-- Default users (passwords are bcrypt hashes of the plaintext shown in comments)
-- admin / admin123  |  user1 / password1  |  viewer / viewer123
INSERT INTO users (username, email, password_hash, role) VALUES
    ('admin', 'admin@crm-enterprise.local', '$2b$12$LJ3X5wKv7IfAzGMkVbHDneFQ3KQJXhHjqW/Tq3hXqp6NpXq8vU5Lm', 'admin'),
    ('user1', 'user1@crm-enterprise.local', '$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', 'user'),
    ('manager', 'manager@crm-enterprise.local', '$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', 'manager'),
    ('viewer', 'viewer@crm-enterprise.local', '$2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 'viewer')
ON CONFLICT DO NOTHING;

-- Customers
INSERT INTO customers (name, email, phone, company, industry, revenue) VALUES
    ('Acme Corporation', 'contact@acme.com', '+1-555-0101', 'Acme Corp', 'Manufacturing', 5200000),
    ('Globex Industries', 'info@globex.com', '+1-555-0102', 'Globex', 'Technology', 12800000),
    ('Initech Solutions', 'sales@initech.com', '+1-555-0103', 'Initech', 'Consulting', 3400000),
    ('Umbrella Corp', 'biz@umbrella.com', '+1-555-0104', 'Umbrella', 'Pharmaceuticals', 45000000),
    ('Stark Industries', 'tony@stark.com', '+1-555-0105', 'Stark Ind', 'Defense', 89000000),
    ('Wayne Enterprises', 'bruce@wayne.com', '+1-555-0106', 'Wayne Ent', 'Conglomerate', 120000000),
    ('Cyberdyne Systems', 'info@cyberdyne.com', '+1-555-0107', 'Cyberdyne', 'AI/Robotics', 8900000),
    ('Oscorp Industries', 'norman@oscorp.com', '+1-555-0108', 'Oscorp', 'Biotech', 22000000),
    ('LexCorp', 'lex@lexcorp.com', '+1-555-0109', 'LexCorp', 'Energy', 67000000),
    ('Weyland-Yutani', 'corp@weyland.com', '+1-555-0110', 'Weyland', 'Space/Mining', 150000000)
ON CONFLICT DO NOTHING;

-- Products
INSERT INTO products (name, sku, description, price, stock, category) VALUES
    ('Enterprise License', 'ENT-001', 'Full enterprise software license', 99999.00, 100, 'License'),
    ('Professional License', 'PRO-001', 'Professional tier license', 29999.00, 500, 'License'),
    ('Basic License', 'BAS-001', 'Basic tier license', 9999.00, 1000, 'License'),
    ('Premium Support', 'SUP-001', '24/7 premium support package', 14999.00, 200, 'Support'),
    ('Standard Support', 'SUP-002', 'Business hours support', 4999.00, 500, 'Support'),
    ('Cloud Hosting', 'CLD-001', 'Managed cloud hosting per year', 19999.00, 300, 'Infrastructure'),
    ('Data Migration', 'SRV-001', 'Data migration service', 24999.00, 50, 'Services'),
    ('Training Package', 'TRN-001', 'On-site training (5 days)', 7999.00, 100, 'Training'),
    ('API Access', 'API-001', 'API integration tier', 5999.00, 1000, 'Integration'),
    ('Security Audit', 'SEC-001', 'Comprehensive security audit', 34999.00, 20, 'Security')
ON CONFLICT DO NOTHING;

-- Orders
INSERT INTO orders (customer_id, total, status, shipping_address) VALUES
    (1, 129998.00, 'completed', '123 Industrial Way, Springfield'),
    (2, 44998.00, 'processing', '456 Tech Park, Silicon Valley'),
    (3, 39998.00, 'pending', '789 Consulting Blvd, New York'),
    (4, 99999.00, 'completed', '321 Pharma Drive, Raccoon City'),
    (5, 154998.00, 'shipped', '10880 Malibu Point, CA'),
    (1, 14999.00, 'completed', '123 Industrial Way, Springfield'),
    (6, 269997.00, 'processing', '1007 Mountain Drive, Gotham'),
    (7, 29999.00, 'pending', '18144 El Camino Real, Sunnyvale')
ON CONFLICT DO NOTHING;

-- Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1, 99999.00), (1, 4, 2, 14999.00),
    (2, 2, 1, 29999.00), (2, 4, 1, 14999.00),
    (3, 2, 1, 29999.00), (3, 8, 1, 7999.00),
    (4, 1, 1, 99999.00),
    (5, 1, 1, 99999.00), (5, 6, 1, 19999.00), (5, 10, 1, 34999.00),
    (6, 4, 1, 14999.00),
    (7, 1, 2, 99999.00), (7, 6, 1, 19999.00), (7, 10, 2, 34999.00),
    (8, 2, 1, 29999.00)
ON CONFLICT DO NOTHING;

-- Invoices
INSERT INTO invoices (order_id, invoice_number, amount, tax, status, due_date) VALUES
    (1, 'INV-2024-001', 129998.00, 10399.84, 'paid', '2024-02-15'),
    (2, 'INV-2024-002', 44998.00, 3599.84, 'paid', '2024-03-01'),
    (3, 'INV-2024-003', 39998.00, 3199.84, 'overdue', '2024-01-15'),
    (4, 'INV-2024-004', 99999.00, 7999.92, 'paid', '2024-04-01'),
    (5, 'INV-2024-005', 154998.00, 12399.84, 'unpaid', '2024-05-01'),
    (6, 'INV-2024-006', 14999.00, 1199.92, 'paid', '2024-03-15'),
    (7, 'INV-2024-007', 269997.00, 21599.76, 'unpaid', '2024-06-01'),
    (8, 'INV-2024-008', 29999.00, 2399.92, 'pending', '2024-06-15')
ON CONFLICT DO NOTHING;

-- Support Tickets
INSERT INTO support_tickets (customer_id, subject, description, priority, status, assigned_to) VALUES
    (1, 'License activation failed', 'Cannot activate enterprise license on new server', 'high', 'open', 'user1'),
    (2, 'API rate limiting', 'Getting 429 errors when calling batch API', 'medium', 'in_progress', 'admin'),
    (3, 'Slow dashboard loading', 'Dashboard takes 30+ seconds to load', 'high', 'open', 'user1'),
    (4, 'Data export issue', 'CSV export corrupts unicode characters', 'low', 'resolved', 'manager'),
    (5, 'SSO integration', 'Need help configuring SAML SSO', 'medium', 'open', 'admin'),
    (1, 'Billing discrepancy', 'Invoice amount does not match order total', 'high', 'open', 'manager'),
    (6, 'Custom report builder', 'Report builder crashes on large datasets', 'critical', 'in_progress', 'admin'),
    (7, 'Migration stuck at 80%', 'Data migration process hung', 'critical', 'open', 'user1')
ON CONFLICT DO NOTHING;
