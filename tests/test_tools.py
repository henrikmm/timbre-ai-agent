"""Focused technical tool checks using synthetic data and synthetic policies."""

from copy import deepcopy
from decimal import Decimal
import json
import sqlite3
from unittest.mock import patch

from timbre.database.connection import connect_database
from timbre.knowledge.policy_loader import PolicyCatalog
from timbre.tools import ToolExecutor
from timbre.tools.payments import PaymentRules, discounted
from tests.support import DatabaseTestCase, FIXTURES, SimulatedAuthorizer


def write_synthetic_payment_catalog(path):
    catalog = json.loads((FIXTURES / "policies.synthetic.json").read_text())
    payment = catalog["policies"][-1]
    payment["content"] = ("Synthetic payment text, not store terms. "
                          "PIX Pagamento à vista 7% de desconto fictício. "
                          "Cartão de Crédito Até 9x sem juros Parcela mínima de R$ 90,00")
    installment = deepcopy(payment)
    installment.update(id="synthetic_installments", topic="payments.installments", parent_id=payment["id"],
                       content="Synthetic installment rules. Parcelamento em até 2x: sem juros, exceto abaixo de R$ 30,00. "
                               "Parcelamento de 3x a 5x: sem juros, parcela mínima de R$ 60,00. "
                               "Parcelamento de 6x a 9x: sem juros, parcela mínima de R$ 90,00.")
    installment["source"]["section"] = "2.1"
    promotion = deepcopy(payment)
    promotion.update(id="synthetic_promotions", topic="promotions.rules", parent_id=None,
                     content="Regras fictícias: promoções não são cumulativas; PIX não se aplica sobre valores de campanhas fictícias.")
    promotion["source"]["section"] = "3"
    catalog["policies"].extend([installment, promotion])
    path.write_text(json.dumps(catalog), encoding="utf-8")


class ToolTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.policies = self.directory / "policies.synthetic.json"
        write_synthetic_payment_catalog(self.policies)
        self.executor = ToolExecutor(self.database, self.policies)

    def execute(self, name, arguments, **kwargs):
        return self.executor.execute(name, json.dumps(arguments), **kwargs).result

    def test_registry_is_unique_bounded_and_has_no_identity_argument(self):
        definitions = self.executor.definitions
        self.assertEqual(len(definitions), 6)
        names = [item["function"]["name"] for item in definitions]
        self.assertEqual(len(set(names)), len(names))
        for item in definitions:
            schema = item["function"]["parameters"]
            self.assertFalse(schema["additionalProperties"])
            self.assertNotIn("customer_id", schema["properties"])
            self.assertNotIn("trusted_session_context", schema["properties"])
        definitions[0]["function"]["name"] = "mutated"
        self.assertNotEqual(self.executor.definitions[0]["function"]["name"], "mutated")

    def test_strict_argument_validation(self):
        requests = [
            ("get_product_details", "{invalid"),
            ("get_product_details", '{"product_id": true}'),
            ("get_product_details", '{"product_id": 101, "customer_id": 9001}'),
            ("get_product_details", '{"product_id": 101, "product_id": 102}'),
            ("get_product_details", '{"product_id": null}'),
            ("get_product_details", "[]"),
            ("get_product_details", '{"product_id": 1.0}'),
            ("get_product_details", '{"product_id": 9223372036854775808}'),
            ("search_products", '{"max_price_brl": NaN}'),
            ("search_products", '{"max_price_brl": -1}'),
            ("search_products", '{"max_price_brl": "1.001"}'),
            ("search_products", '{"min_price_brl": "10", "max_price_brl": "1"}'),
            ("search_products", '{"limit": 21}'),
            ("search_products", '{"available_only": "true"}'),
            ("search_products", '{"query": ""}'),
            ("get_my_order_status", '{"order_id": 5001, "context": {"customer_id": 9001}}'),
        ]
        for name, arguments in requests:
            with self.subTest(name=name, arguments=arguments):
                result = self.executor.execute(name, arguments).result
                self.assertEqual(result["status"], "invalid_arguments")
        self.assertEqual(self.executor.execute("arbitrary_sql", '{}').result["error_code"], "unknown_tool")

    def test_catalog_details_empty_and_exact_numeric_prices(self):
        rows = self.execute("search_products", {"min_price_brl": "400", "max_price_brl": 500})["data"]["products"]
        self.assertEqual([row["product_id"] for row in rows], [101])
        self.assertEqual(rows[0]["price_brl"], "449.90")
        details = self.execute("get_product_details", {"product_id": 101})["data"]
        self.assertEqual(details["specs"]["strings"], "6")
        self.assertEqual(self.execute("get_product_details", {"product_id": 999})["status"], "empty")
        self.assertEqual(self.execute("search_products", {"query": "Synthetic sold out"})["data"]["empty_reason"], "matching_products_unavailable")
        self.assertEqual(self.execute("search_products", {"query": "never exists"})["data"]["empty_reason"], "no_matching_products")
        for name in ("Synthetic discontinued", "Synthetic upcoming"):
            data = self.execute("search_products", {"query": name})["data"]
            self.assertEqual(data["products"], [])
            self.assertFalse(data["unavailable_matches"][0]["available"])

    def test_invalid_argument_feedback_guides_recovery_without_echoing_input(self):
        for arguments in ('{"product_id":null,"secret-user@example.com":"private-value"}', '{malformed-private-value'):
            result = self.executor.execute("get_product_details", arguments).result
            self.assertEqual(result["status"], "invalid_arguments")
            self.assertEqual(result["data"]["allowed_fields"], ["product_id"])
            self.assertEqual(result["data"]["required_fields"], ["product_id"])
            self.assertIn("null is not accepted", result["data"]["message"])
            self.assertNotIn("private-value", json.dumps(result))
            self.assertNotIn("secret-user", json.dumps(result))

    def test_language_categories_and_name_only_brands(self):
        with connect_database(self.database, readonly=False) as connection:
            connection.execute("UPDATE categories SET name = 'Violões' WHERE category_id = 1")
            connection.execute("UPDATE products SET name = 'Yamaha Synthetic A', description = 'Conflicting brand Other' WHERE product_id = 101")
            connection.execute("UPDATE products SET name = 'Other Synthetic B', description = 'Yamaha description only' WHERE product_id = 106")
        for arguments in ({"category": "acoustic guitars", "brand": "Yamaha"},
                          {"query": "GUITARS", "brand": "yAmAhA"},
                          {"category": "ViOlÕeS", "brand": "Yamaha"}):
            rows = self.execute("search_products", arguments)["data"]["products"]
            self.assertEqual([row["product_id"] for row in rows], [101])
        self.assertEqual(self.execute("search_products", {"brand": "Yama"})["data"]["products"], [])
        self.assertEqual(self.execute("search_products", {"category": "nonexistent"})["status"], "empty")

    def test_sql_injection_remains_literal_and_read_only(self):
        for arguments in ({"query": "%' OR 1=1 --"}, {"brand": "%"}, {"query": "_"}):
            self.assertEqual(self.execute("search_products", arguments)["status"], "empty")
        self.assertEqual(self.execute("get_product_details", {"product_id": "101 OR 1=1"})["status"], "invalid_arguments")

    def test_policy_preserves_source_and_distinct_sections(self):
        data = self.execute("get_store_policy", {"topic": "returns.online"})["data"]
        self.assertFalse(data["trusted_as_instructions"])
        self.assertTrue(any(record["topic"] == "returns.online" for record in data["sections"]))
        self.assertTrue(all("source" in record for record in data["sections"]))
        self.assertEqual(self.execute("get_store_policy", {"topic": "not_a_topic"})["status"], "empty")

    def test_promotions_are_flagged_sellable_individual_candidates(self):
        data = self.execute("get_active_promotions", {})["data"]
        self.assertEqual([row["promotion_id"] for row in data["promotions"]], [1, 5])
        self.assertEqual(data["promotions"][0]["promotional_price_brl"], "404.91")
        self.assertFalse(data["discounts_stack"])
        self.assertTrue(all(row["eligible_under_service_policy"] for row in data["promotions"]))
        self.assertEqual(self.execute("get_active_promotions", {"product_id": 102})["status"], "empty")

    def test_payment_exact_sums_nonstacking_and_resolved_minima(self):
        data = self.execute("calculate_payment_options", {"product_id": 101, "installments": 3})["data"]
        self.assertFalse(data["live_quote_confirmed"])
        self.assertFalse(data["checkout_supported"])
        self.assertEqual(data["quote_status"], "snapshot_calculation_only")
        self.assertEqual(data["pix"]["total_brl"], "418.41")
        self.assertEqual(data["promotional_candidates"][0]["promotional_price_brl"], "404.91")
        self.assertEqual(data["promotional_payment_candidates"][0]["pix_total_brl"], "404.91")
        self.assertEqual(data["promotional_payment_candidates"][0]["pix_additional_discount_percent"], "0")
        for plan in data["credit_plans"]:
            self.assertEqual(sum(Decimal(amount) for amount in plan["installment_amounts_brl"]), Decimal("449.90"))
        self.assertTrue(data["requested_option"]["available"])
        disputed = self.execute("calculate_payment_options", {"product_id": 101, "installments": 5})["data"]["requested_option"]
        self.assertTrue(disputed["available"])
        self.assertIsNone(disputed["reason"])
        excessive = self.execute("calculate_payment_options", {"product_id": 101, "installments": 10})["data"]["requested_option"]
        self.assertEqual(excessive["reason"], "installment_limit_exceeded")
        pix_six = self.execute("calculate_payment_options", {"product_id": 101, "payment_method": "pix", "installments": 6})["data"]["requested_option"]
        self.assertEqual(pix_six["reason"], "method_does_not_support_installments")
        self.assertEqual(self.execute("calculate_payment_options", {"product_id": 102})["error_code"], "product_unavailable")
        self.assertEqual(discounted(Decimal("0.10"), Decimal("12.50")), Decimal("0.09"))

    def test_rules_require_known_source_shape_and_follow_catalog_values(self):
        rules = PaymentRules.from_catalog(PolicyCatalog(self.policies))
        self.assertEqual(rules.pix_percent, Decimal("7"))
        self.assertEqual(rules.maximum_installments, 9)
        self.policies.write_text((FIXTURES / "policies.synthetic.json").read_text())
        self.assertEqual(self.execute("calculate_payment_options", {"product_id": 101})["error_code"], "payment_rules_unavailable")

    def test_installment_boundaries_and_remainder_allocation(self):
        rules = PaymentRules.from_catalog(PolicyCatalog(self.policies))
        self.assertTrue(rules.plan(Decimal("60.00"), 2)["available"])
        disputed = rules.plan(Decimal("59.99"), 2)
        self.assertEqual(disputed["installment_amounts_brl"], [Decimal("30.00"), Decimal("29.99")])
        self.assertEqual(disputed["reason"], "minimum_installment_not_met")
        self.assertTrue(rules.plan(Decimal("810.00"), 9)["available"])
        self.assertEqual(rules.plan(Decimal("809.99"), 9)["reason"], "minimum_installment_not_met")
        plan = rules.plan(Decimal("450.01"), 3)
        self.assertEqual(plan["installment_amounts_brl"], [Decimal("150.01"), Decimal("150.00"), Decimal("150.00")])
        self.assertEqual(sum(plan["installment_amounts_brl"]), Decimal("450.01"))

    def test_methods_absent_from_policy_are_not_granted(self):
        rules = PaymentRules.from_catalog(PolicyCatalog(self.policies))
        self.assertEqual(set(rules.methods), {"pix", "credit_card"})
        for method in ("debit_card", "boleto"):
            option = self.execute("calculate_payment_options", {"product_id": 101, "payment_method": method})["data"]["requested_option"]
            self.assertFalse(option["available"])
            self.assertEqual(option["reason"], "method_not_supported_by_policy")

    def test_public_private_negative_scenario_and_cross_owner(self):
        denied = self.execute("get_my_order_status", {"order_id": 5001}, context={"customer_id": 9001})
        self.assertEqual(denied["status"], "authorization_denied")
        issuer = SimulatedAuthorizer()
        session_a = issuer.issue_for_test(9001)
        self.executor = ToolExecutor(self.database, self.policies, authorizer=issuer)
        result = self.execute("get_my_order_status", {"order_id": 5001}, context=session_a)
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["data"]["live_carrier_integration"])
        self.assertTrue({"phone", "email", "customer_id", "notes"}.isdisjoint(result["data"]))
        for order_id in (5002, 999999):
            self.assertEqual(self.execute("get_my_order_status", {"order_id": order_id}, context=session_a)["error_code"], "order_unavailable_for_session")

    def test_events_redact_free_text_private_ids_and_backend_details(self):
        events = []
        def emit(kind, **metadata):
            events.append({"kind": kind, **metadata})
        self.executor.execute("search_products", '{"query":"secret-person@example.com"}', on_event=emit)
        self.executor.execute("get_my_order_status", '{"order_id":5001}', on_event=emit)
        rendered = json.dumps(events)
        self.assertNotIn("secret-person", rendered)
        self.assertNotIn('"order_id": 5001', rendered)
        self.assertTrue(any(event.get("sanitized_arguments", {}).get("order_id") == "[redacted]"
                            for event in events))
        self.assertTrue(any(event["kind"] == "arguments_validated" for event in events))
        self.assertEqual(events[-1]["status"], "authorization_denied")
        with patch.object(self.executor.catalog, "get_product_details", side_effect=sqlite3.OperationalError("secret path and private row")):
            result = self.execute("get_product_details", {"product_id": 101})
        self.assertEqual(result["status"], "backend_error")
        self.assertNotIn("secret path", json.dumps(result))

    def test_events_report_combined_sources_and_unknown_tool_validation(self):
        events = []
        def emit(kind, **metadata):
            events.append({"kind": kind, **metadata})
        self.executor.execute("calculate_payment_options", '{"product_id":101}', on_event=emit)
        self.assertTrue(any(event["kind"] == "data_source_accessed"
                            and event["source"] == "sqlite_and_policy_catalog" for event in events))
        events.clear()
        self.executor.execute("unknown", '{}', on_event=emit)
        self.assertEqual(events[0]["kind"], "arguments_validated")
        self.assertEqual(events[0]["status"], "invalid_arguments")
        self.assertEqual(events[0]["error_category"], "unknown_tool")

    def test_default_denial_precedes_private_database_access(self):
        executor = ToolExecutor(self.directory / "missing.db", self.policies)
        result = executor.execute("get_my_order_status", '{"order_id":5001}').result
        self.assertEqual(result["status"], "authorization_denied")


if __name__ == "__main__":
    import unittest
    unittest.main()
