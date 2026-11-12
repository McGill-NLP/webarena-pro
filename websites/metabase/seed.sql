-- ============================================================
-- E-Commerce Sample Data Seed
-- Compatible with PostgreSQL
-- Usage: psql -U sample -d sample_data -f seed.sql
-- ============================================================

-- Make generated data deterministic across fresh DB initializations.
SELECT setseed(0.12345);

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS people (
  id         SERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  email      TEXT NOT NULL UNIQUE,
  city       TEXT,
  state      TEXT,
  zip        TEXT,
  latitude   FLOAT,
  longitude  FLOAT,
  source     TEXT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
  id         SERIAL PRIMARY KEY,
  title      TEXT NOT NULL,
  category   TEXT,
  vendor     TEXT,
  price      NUMERIC(10,2),
  rating     FLOAT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
  id         SERIAL PRIMARY KEY,
  user_id    INT REFERENCES people(id),
  created_at TIMESTAMP DEFAULT now(),
  status     TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS order_items (
  id          SERIAL PRIMARY KEY,
  order_id    INT REFERENCES orders(id),
  product_id  INT REFERENCES products(id),
  quantity    INT DEFAULT 1,
  unit_price  NUMERIC(10,2),
  discount    NUMERIC(10,2) DEFAULT 0,
  subtotal    NUMERIC(10,2)
);

CREATE TABLE IF NOT EXISTS reviews (
  id         SERIAL PRIMARY KEY,
  product_id INT REFERENCES products(id),
  reviewer   TEXT,
  rating     INT CHECK (rating BETWEEN 1 AND 5),
  body       TEXT,
  created_at TIMESTAMP DEFAULT now()
);

-- ============================================================
-- PEOPLE
-- ============================================================

INSERT INTO people (name, email, city, state, zip, latitude, longitude, source) VALUES
('Alice Martin',    'alice.martin@example.com',    'New York',      'NY', '10001', 40.7128,  -74.0060,  'organic'),
('Bob Chen',        'bob.chen@example.com',        'Los Angeles',   'CA', '90001', 34.0522, -118.2437,  'google'),
('Carol Davis',     'carol.davis@example.com',     'Chicago',       'IL', '60601', 41.8781,  -87.6298,  'organic'),
('Daniel Kim',      'daniel.kim@example.com',      'Houston',       'TX', '77001', 29.7604,  -95.3698,  'facebook'),
('Eva Rodriguez',   'eva.rodriguez@example.com',   'Phoenix',       'AZ', '85001', 33.4484, -112.0740,  'google'),
('Frank Wilson',    'frank.wilson@example.com',    'Philadelphia',  'PA', '19101', 39.9526,  -75.1652,  'organic'),
('Grace Lee',       'grace.lee@example.com',       'San Antonio',   'TX', '78201', 29.4241,  -98.4936,  'referral'),
('Henry Brown',     'henry.brown@example.com',     'San Diego',     'CA', '92101', 32.7157, -117.1611,  'google'),
('Isabella Jones',  'isabella.jones@example.com',  'Dallas',        'TX', '75201', 32.7767,  -96.7970,  'facebook'),
('James Taylor',    'james.taylor@example.com',    'San Jose',      'CA', '95101', 37.3382, -121.8863,  'organic'),
('Karen White',     'karen.white@example.com',     'Austin',        'TX', '78701', 30.2672,  -97.7431,  'organic'),
('Liam Harris',     'liam.harris@example.com',     'Jacksonville',  'FL', '32201', 30.3322,  -81.6557,  'google'),
('Mia Clark',       'mia.clark@example.com',       'San Francisco', 'CA', '94101', 37.7749, -122.4194,  'referral'),
('Noah Lewis',      'noah.lewis@example.com',      'Columbus',      'OH', '43201', 39.9612,  -82.9988,  'organic'),
('Olivia Walker',   'olivia.walker@example.com',   'Charlotte',     'NC', '28201', 35.2271,  -80.8431,  'facebook'),
('Paul Hall',       'paul.hall@example.com',       'Indianapolis',  'IN', '46201', 39.7684,  -86.1581,  'google'),
('Quinn Allen',     'quinn.allen@example.com',     'Seattle',       'WA', '98101', 47.6062, -122.3321,  'organic'),
('Rachel Young',    'rachel.young@example.com',    'Denver',        'CO', '80201', 39.7392, -104.9903,  'referral'),
('Samuel King',     'samuel.king@example.com',     'Nashville',     'TN', '37201', 36.1627,  -86.7816,  'google'),
('Tina Scott',      'tina.scott@example.com',      'Oklahoma City', 'OK', '73101', 35.4676,  -97.5164,  'organic'),
('Ursula Green',    'ursula.green@example.com',    'El Paso',       'TX', '79901', 31.7619, -106.4850,  'facebook'),
('Victor Adams',    'victor.adams@example.com',    'Boston',        'MA', '02101', 42.3601,  -71.0589,  'organic'),
('Wendy Nelson',    'wendy.nelson@example.com',    'Portland',      'OR', '97201', 45.5051, -122.6750,  'google'),
('Xander Carter',   'xander.carter@example.com',   'Las Vegas',     'NV', '89101', 36.1699, -115.1398,  'referral'),
('Yara Mitchell',   'yara.mitchell@example.com',   'Memphis',       'TN', '38101', 35.1495,  -90.0490,  'organic'),
('Zoe Perez',       'zoe.perez@example.com',       'Louisville',    'KY', '40201', 38.2527,  -85.7585,  'google'),
('Aaron Roberts',   'aaron.roberts@example.com',   'Baltimore',     'MD', '21201', 39.2904,  -76.6122,  'facebook'),
('Bella Turner',    'bella.turner@example.com',    'Milwaukee',     'WI', '53201', 43.0389,  -87.9065,  'organic'),
('Carlos Phillips', 'carlos.phillips@example.com', 'Albuquerque',   'NM', '87101', 35.0844, -106.6504,  'google'),
('Diana Campbell',  'diana.campbell@example.com',  'Tucson',        'AZ', '85701', 32.2226, -110.9747,  'organic');

-- ============================================================
-- PRODUCTS
-- ============================================================

INSERT INTO products (title, category, vendor, price, rating) VALUES
('Aerodynamic Bronze Hat',      'Accessories', 'Gorczany-Gottlieb',  29.99, 4.2),
('Lightweight Steel Keyboard',  'Electronics', 'Barrows and Sons',   89.99, 4.5),
('Fantastic Wooden Bag',        'Bags',        'Schneider LLC',      59.99, 3.8),
('Enormous Marble Shirt',       'Apparel',     'Hyatt Group',        34.99, 4.0),
('Rustic Plastic Shoes',        'Footwear',    'Legros-Gleason',     49.99, 3.5),
('Incredible Iron Watch',       'Accessories', 'Gottlieb-Pagac',    129.99, 4.7),
('Sleek Granite Pants',         'Apparel',     'Jast Group',         44.99, 4.1),
('Practical Rubber Gloves',     'Accessories', 'Nienow Inc',         14.99, 3.9),
('Synergistic Silk Lamp',       'Home',        'Berge LLC',          79.99, 4.3),
('Small Concrete Shoes',        'Footwear',    'Legros-Gleason',     39.99, 3.6),
('Gorgeous Cotton Wallet',      'Accessories', 'Gorczany-Gottlieb',  24.99, 4.4),
('Heavy Duty Steel Table',      'Home',        'Berge LLC',         199.99, 4.6),
('Comfortable Linen Pillow',    'Home',        'Nienow Inc',         29.99, 4.0),
('Durable Plastic Bottle',      'Sports',      'Hyatt Group',        19.99, 3.7),
('Ultra-Soft Wool Scarf',       'Accessories', 'Jast Group',         34.99, 4.5),
('Recycled Glass Vase',         'Home',        'Schneider LLC',      49.99, 4.2),
('Ergonomic Wood Chair',        'Furniture',   'Barrows and Sons',  249.99, 4.8),
('Waterproof Canvas Backpack',  'Bags',        'Gorczany-Gottlieb',  74.99, 4.6),
('Handmade Ceramic Mug',        'Kitchen',     'Berge LLC',          18.99, 4.3),
('Professional Chef Knife',     'Kitchen',     'Jast Group',         89.99, 4.9),
('Wireless Noise-Cancel Headphones', 'Electronics', 'Barrows and Sons', 149.99, 4.7),
('Bamboo Cutting Board',        'Kitchen',     'Nienow Inc',         32.99, 4.1),
('Memory Foam Mattress',        'Furniture',   'Hyatt Group',       499.99, 4.5),
('Running Shoes Pro',           'Footwear',    'Legros-Gleason',     99.99, 4.4),
('Yoga Mat Premium',            'Sports',      'Schneider LLC',      45.99, 4.6),
('Stainless Steel Water Bottle','Sports',      'Gorczany-Gottlieb',  27.99, 4.3),
('Smart LED Desk Lamp',         'Electronics', 'Gottlieb-Pagac',     59.99, 4.2),
('Leather Bifold Wallet',       'Accessories', 'Jast Group',         39.99, 4.5),
('Cast Iron Skillet',           'Kitchen',     'Barrows and Sons',   54.99, 4.8),
('Collapsible Camping Chair',   'Sports',      'Hyatt Group',        69.99, 4.0);

-- ============================================================
-- ORDERS + ORDER ITEMS
-- ============================================================

DO $$
DECLARE
  uid     INT;
  pid     INT;
  oid     INT;
  uprice  NUMERIC(10,2);
  qty     INT;
  disc    NUMERIC(10,2);
  statuses TEXT[] := ARRAY['pending','paid','shipped','completed','returned'];
  ts      TIMESTAMP;
  base_ts TIMESTAMP := TIMESTAMP '2025-01-01 00:00:00';
BEGIN
  FOR i IN 1..200 LOOP
    uid := (SELECT id FROM people  ORDER BY random() LIMIT 1);
    ts  := base_ts - (random() * INTERVAL '365 days');

    INSERT INTO orders (user_id, created_at, status)
    VALUES (uid, ts, statuses[1 + floor(random()*5)::INT])
    RETURNING id INTO oid;

    -- Each order gets 1-4 items
    FOR j IN 1..(1 + floor(random()*3)::INT) LOOP
      pid    := (SELECT id    FROM products ORDER BY random() LIMIT 1);
      uprice := (SELECT price FROM products WHERE id = pid);
      qty    := 1 + floor(random()*4)::INT;
      disc   := ROUND((random() * 10)::NUMERIC, 2);

      INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount, subtotal)
      VALUES (oid, pid, qty, uprice, disc, ROUND((uprice * qty) - disc, 2));
    END LOOP;
  END LOOP;
END $$;

-- ============================================================
-- REVIEWS
-- ============================================================

INSERT INTO reviews (product_id, reviewer, rating, body, created_at)
SELECT
  (SELECT id FROM products ORDER BY random() LIMIT 1),
  (SELECT name FROM people ORDER BY random() LIMIT 1),
  1 + floor(random()*5)::INT,
  (ARRAY[
    'Great product, exactly as described!',
    'Decent quality for the price.',
    'Would not recommend — broke after a week.',
    'Exceeded my expectations. Will buy again.',
    'Good but shipping took forever.',
    'Perfect gift. Everyone loved it.',
    'Meh. Nothing special.',
    'Absolutely love this! Five stars.',
    'Returned it. Did not match the description.',
    'Solid build quality, very happy with it.'
  ])[1 + floor(random()*10)::INT],
  TIMESTAMP '2025-01-01 00:00:00' - (random() * INTERVAL '365 days')
FROM generate_series(1, 80);

-- ============================================================
-- SUMMARY VIEW (optional, handy for Metabase)
-- ============================================================

CREATE OR REPLACE VIEW order_summary AS
SELECT
  o.id          AS order_id,
  o.created_at  AS order_date,
  o.status,
  p.name        AS customer_name,
  p.city,
  p.state,
  p.source      AS acquisition_source,
  SUM(oi.subtotal) AS order_total,
  COUNT(oi.id)     AS item_count
FROM orders o
JOIN people p       ON p.id = o.user_id
JOIN order_items oi ON oi.order_id = o.id
GROUP BY o.id, o.created_at, o.status, p.name, p.city, p.state, p.source;