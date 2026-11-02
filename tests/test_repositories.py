"""Public reads, session ownership, and data minimization with synthetic records."""

from decimal import Decimal

from timbre.authorization import AccessDenied
from timbre.database.repositories import CatalogRepository, OrderNotFound, OrderRepository
from tests.support import DatabaseTestCase, SimulatedAuthorizer


class CatalogTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.catalog = CatalogRepository(self.database)

    def test_public_reads_need_no_authentication(self):
        self.assertEqual(len(self.catalog.list_categories()), 2)
        results = self.catalog.search_products("violao", max_price_brl="500")
        self.assertEqual([row["product_id"] for row in results], [101])
        self.assertEqual(results[0]["price_brl"], Decimal("449.90"))
        self.assertTrue(results[0]["available"])
        self.assertEqual(self.catalog.get_product_details(101)["specs"]["strings"], "6")
        self.assertIsNone(self.catalog.get_product_details(9999))

    def test_availability_uses_status_and_registered_stock(self):
        self.assertEqual([row["product_id"] for row in self.catalog.search_products()], [101, 106])
        for product_id in [102, 103, 104, 105]:
            self.assertFalse(self.catalog.get_product_details(product_id)["available"])
        self.assertEqual(len(self.catalog.search_products(available_only=False)), 6)

    def test_only_flagged_and_sellable_promotions_are_public_offers(self):
        results = self.catalog.get_active_promotions()
        self.assertEqual([row["promotion_id"] for row in results], [1, 5])
        self.assertEqual(results[1]["discount_percent"], Decimal("12.50"))
        self.assertEqual(self.catalog.get_active_promotions(102), [])

    def test_filters_and_pagination_are_deterministic(self):
        self.assertEqual(self.catalog.search_products(category_id=2), [])
        self.assertEqual([row["product_id"] for row in self.catalog.search_products(limit=1, offset=1)], [106])
        self.assertEqual([row["product_id"] for row in self.catalog.search_products(max_price_brl="0.10")], [106])
        with self.assertRaises(ValueError):
            self.catalog.search_products(limit=101)

    def test_sql_and_like_injection_are_literal_inputs(self):
        for query in ["%' OR 1=1 --", "%", "_", "' UNION SELECT * FROM customers --"]:
            self.assertEqual(self.catalog.search_products(query), [])
        with self.assertRaises(ValueError):
            self.catalog.get_product_details("101 OR 1=1")

    def test_public_results_do_not_contain_private_fields(self):
        forbidden = {"customer_id", "phone", "email", "notes", "tracking_code", "order_id", "payment_method"}
        results = self.catalog.search_products(available_only=False)
        results += self.catalog.get_active_promotions()
        results += [self.catalog.get_product_details(101)]
        for result in results:
            self.assertTrue(forbidden.isdisjoint(result))


class SecurityTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.issuer = SimulatedAuthorizer()
        self.session_a = self.issuer.issue_for_test(9001)
        self.session_b = self.issuer.issue_for_test(9002)
        self.orders = OrderRepository(self.database, authorizer=self.issuer)

    def test_production_default_denies_every_private_request(self):
        default = OrderRepository(self.database)
        for context in [None, self.session_a, {"customer_id": 9001}, 9001, "Fixture Customer A", "+550000000001"]:
            with self.assertRaises(AccessDenied):
                default.get_order_for_customer(5001, context=context)
            with self.assertRaises(AccessDenied):
                default.get_my_orders(context=context)

    def test_unauthenticated_and_forged_contexts_are_denied(self):
        for context in [None, object(), {"customer_id": 9001}, {"authenticated": True, "customer_id": 9001}]:
            with self.assertRaises(AccessDenied):
                self.orders.get_order_for_customer(5001, context=context)

    def test_authorized_owner_receives_only_status_fields(self):
        result = self.orders.get_order_for_customer(5001, context=self.session_a)
        self.assertEqual(result["status"], "shipped")
        self.assertEqual(set(result), {"order_id", "order_date", "status", "tracking_code", "estimated_delivery"})
        self.assertEqual([row["order_id"] for row in self.orders.get_my_orders(context=self.session_a)], [5001, 5003])

    def test_customer_a_cannot_read_customer_b_or_probe_order_existence(self):
        messages = []
        for order_id in [5002, 999999]:
            with self.assertRaises(OrderNotFound) as raised:
                self.orders.get_order_for_customer(order_id, context=self.session_a)
            messages.append(str(raised.exception))
        self.assertEqual(messages[0], messages[1])
        self.assertEqual(self.orders.get_order_for_customer(5002, context=self.session_b)["status"], "delivered")

    def test_user_supplied_customer_id_cannot_override_session(self):
        with self.assertRaises(TypeError):
            self.orders.get_order_for_customer(5002, context=self.session_a, customer_id=9002)
        with self.assertRaises(TypeError):
            self.orders.get_my_orders(context=self.session_a, customer_id=9002)
        with self.assertRaises(OrderNotFound):
            self.orders.get_order_for_customer(5002, context=self.session_a)

    def test_default_denial_happens_before_database_access(self):
        with self.assertRaises(AccessDenied):
            OrderRepository(self.directory / "nonexistent.db").get_order_for_customer(5001)
