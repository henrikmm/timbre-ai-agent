"""The six source tables; prices use integer cents and discounts basis points."""

SCHEMA_VERSION = 1

# Dependency order also determines insert order. Drop in reverse order.
TABLE_NAMES = ("categories", "products", "customers", "orders", "order_items", "promotions")

SCHEMA_STATEMENTS = (
    """CREATE TABLE categories (
        category_id INTEGER PRIMARY KEY CHECK (category_id > 0),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        description TEXT
    )""",
    """CREATE TABLE products (
        product_id INTEGER PRIMARY KEY CHECK (product_id > 0),
        price_cents INTEGER NOT NULL CHECK (price_cents >= 0 AND typeof(price_cents) = 'integer'),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        category_id INTEGER NOT NULL REFERENCES categories(category_id),
        description TEXT,
        stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0 AND typeof(stock_quantity) = 'integer'),
        status TEXT NOT NULL CHECK (length(trim(status)) > 0),
        specs TEXT CHECK (specs IS NULL OR (json_valid(specs) AND json_type(specs) = 'object')),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY CHECK (customer_id > 0),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        phone TEXT,
        email TEXT,
        city TEXT
    )""",
    """CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY CHECK (order_id > 0),
        customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
        order_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK (length(trim(status)) > 0),
        total_cents INTEGER NOT NULL CHECK (total_cents >= 0 AND typeof(total_cents) = 'integer'),
        payment_method TEXT,
        tracking_code TEXT,
        estimated_delivery TEXT,
        notes TEXT
    )""",
    """CREATE TABLE order_items (
        order_id INTEGER NOT NULL REFERENCES orders(order_id),
        quantity INTEGER NOT NULL CHECK (quantity > 0 AND typeof(quantity) = 'integer'),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        PRIMARY KEY (order_id, product_id)
    )""",
    """CREATE TABLE promotions (
        promotion_id INTEGER PRIMARY KEY CHECK (promotion_id > 0),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        discount_basis_points INTEGER NOT NULL CHECK (
            discount_basis_points BETWEEN 0 AND 10000 AND typeof(discount_basis_points) = 'integer'
        ),
        description TEXT,
        is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
    )""",
    "CREATE INDEX idx_products_category ON products(category_id)",
    "CREATE INDEX idx_orders_customer ON orders(customer_id, order_id)",
    "CREATE INDEX idx_order_items_product ON order_items(product_id)",
    "CREATE INDEX idx_promotions_product ON promotions(product_id, is_active)",
)
