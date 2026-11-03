"""Specialized read interfaces; no arbitrary SQL or customer-directory API."""

import json
from pathlib import Path

from timbre.authorization import AccessDenied, CustomerAuthorizer, DenyAllAuthorizer
from timbre.database.connection import connect_database, search_key
from timbre.database.values import from_cents, to_cents


class OrderNotFound(LookupError):
    """Uniform response for nonexistent orders and orders owned by another customer."""


def _positive_id(value: int) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError("identifier must be a positive SQLite integer")
    return value


def _pagination(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if type(offset) is not int or not 0 <= offset < 2**63:
        raise ValueError("offset must be a non-negative SQLite integer")


def _product(row) -> dict:
    return {
        "product_id": row["product_id"], "name": row["name"],
        "category_id": row["category_id"], "category_name": row["category_name"],
        "price_brl": from_cents(row["price_cents"]),
        "stock_quantity": row["stock_quantity"], "status": row["status"],
        "available": row["status"] == "active" and row["stock_quantity"] > 0,
    }


class CatalogRepository:
    """Public catalog reads over a local snapshot, not a live ERP."""

    def __init__(self, database_path: str | Path):
        self._database_path = Path(database_path)

    def list_categories(self) -> list[dict]:
        with connect_database(self._database_path) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT category_id, name, description FROM categories ORDER BY category_id"
            )]

    def search_products(self, query: str = "", *, category_id: int | None = None,
                        category_ids: list[int] | None = None, brand: str | None = None,
                        min_price_brl=None, max_price_brl=None, available_only: bool = True,
                        limit: int = 20, offset: int = 0) -> list[dict]:
        _pagination(limit, offset)
        if not isinstance(query, str) or len(query) > 300:
            raise ValueError("query must be a string of at most 300 characters")
        if type(available_only) is not bool:
            raise ValueError("available_only must be a boolean")
        conditions, parameters = [], []
        if query:
            # Escape LIKE metacharacters as well as parameterizing the query.
            literal = search_key(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("search_key(p.name || ' ' || coalesce(p.description, '')) LIKE ? ESCAPE '\\'")
            parameters.append(f"%{literal}%")
        if category_id is not None:
            conditions.append("p.category_id = ?")
            parameters.append(_positive_id(category_id))
        if category_ids is not None:
            if not category_ids:
                return []
            conditions.append("p.category_id IN (" + ",".join("?" for _ in category_ids) + ")")
            parameters.extend(_positive_id(value) for value in category_ids)
        if brand is not None:
            if not isinstance(brand, str) or not brand.strip() or len(brand) > 100:
                raise ValueError("brand must be nonempty text of at most 100 characters")
            # The source has no brand column. Match name tokens, never infer a
            # brand from potentially conflicting descriptions/specifications.
            literal = search_key(brand.strip()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(' ' || search_key(p.name) || ' ') LIKE ? ESCAPE '\\'")
            parameters.append(f"% {literal} %")
        if min_price_brl is not None:
            conditions.append("p.price_cents >= ?")
            parameters.append(to_cents(min_price_brl))
        if max_price_brl is not None:
            conditions.append("p.price_cents <= ?")
            parameters.append(to_cents(max_price_brl))
        if available_only:
            conditions.append("p.status = 'active' AND p.stock_quantity > 0")
        where = " AND ".join(conditions) if conditions else "1 = 1"
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                f"""SELECT p.product_id, p.name, p.category_id, c.name AS category_name,
                           p.price_cents, p.stock_quantity, p.status, p.description
                    FROM products p JOIN categories c ON c.category_id = p.category_id
                    WHERE {where} ORDER BY p.product_id LIMIT ? OFFSET ?""",
                [*parameters, limit, offset],
            )
            return [{**_product(row), "description": row["description"]} for row in rows]

    def get_product_details(self, product_id: int) -> dict | None:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """SELECT p.product_id, p.name, p.category_id, c.name AS category_name,
                          p.price_cents, p.stock_quantity, p.status, p.description, p.specs
                   FROM products p JOIN categories c ON c.category_id = p.category_id
                   WHERE p.product_id = ?""", (_positive_id(product_id),)
            ).fetchone()
            if row is None:
                return None
            return {**_product(row), "description": row["description"],
                    "specs": json.loads(row["specs"]) if row["specs"] is not None else None}

    def get_active_promotions(self, product_id: int | None = None, *,
                              limit: int = 20, offset: int = 0) -> list[dict]:
        """Only flagged campaigns for sellable products; dates are absent in the source."""
        _pagination(limit, offset)
        condition, parameters = "", []
        if product_id is not None:
            condition = " AND p.product_id = ?"
            parameters.append(_positive_id(product_id))
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                f"""SELECT r.promotion_id, r.product_id, r.discount_basis_points, r.description,
                           p.name, p.price_cents
                    FROM promotions r JOIN products p ON p.product_id = r.product_id
                    WHERE r.is_active = 1 AND p.status = 'active' AND p.stock_quantity > 0
                    {condition} ORDER BY r.promotion_id LIMIT ? OFFSET ?""",
                [*parameters, limit, offset],
            )
            return [{"promotion_id": row["promotion_id"], "product_id": row["product_id"],
                     "product_name": row["name"], "original_price_brl": from_cents(row["price_cents"]),
                     "discount_percent": from_cents(row["discount_basis_points"]),
                     "description": row["description"], "active_in_snapshot": True}
                    for row in rows]


ORDER_STATUS_COLUMNS = "order_id, order_date, status, tracking_code, estimated_delivery"


class OrderRepository:
    """Private status reads; bind session context outside any future model arguments."""

    def __init__(self, database_path: str | Path, *, authorizer: CustomerAuthorizer | None = None):
        self._database_path = Path(database_path)
        self._authorizer = authorizer if authorizer is not None else DenyAllAuthorizer()

    def _customer_id(self, context: object | None) -> int:
        customer_id = self._authorizer.require_customer_id(context)
        if type(customer_id) is not int or not 0 < customer_id < 2**63:
            raise AccessDenied("authentication provider did not return a valid verified identity")
        return customer_id

    def get_order_for_customer(self, order_id: int, *, context: object | None = None) -> dict:
        customer_id = self._customer_id(context)
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                f"SELECT {ORDER_STATUS_COLUMNS} FROM orders WHERE order_id = ? AND customer_id = ?",
                (_positive_id(order_id), customer_id),
            ).fetchone()
            if row is None:
                raise OrderNotFound("order unavailable for this session")
            return dict(row)

    def get_my_orders(self, *, context: object | None = None, limit: int = 20, offset: int = 0) -> list[dict]:
        customer_id = self._customer_id(context)
        _pagination(limit, offset)
        with connect_database(self._database_path) as connection:
            return [dict(row) for row in connection.execute(
                f"SELECT {ORDER_STATUS_COLUMNS} FROM orders WHERE customer_id = ? ORDER BY order_id LIMIT ? OFFSET ?",
                (customer_id, limit, offset),
            )]
