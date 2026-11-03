"""Synthetic checks for adopted service decisions and unchanged policy sources."""

from copy import deepcopy
import json
from decimal import Decimal

from timbre.knowledge.customer_policy import customer_policy
from timbre.knowledge.policy_loader import PolicyCatalog
from timbre.tools import ToolExecutor
from tests.support import DatabaseTestCase
from test_tools import write_synthetic_payment_catalog


class CustomerPolicyTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.directory / "synthetic-policy.json"
        write_synthetic_payment_catalog(self.path)
        self.executor = ToolExecutor(self.database, self.path)

    def add_section(self, topic, content, section):
        payload = json.loads(self.path.read_text())
        record = deepcopy(payload["policies"][0])
        record.update(id="synthetic_" + topic.replace(".", "_"), topic=topic,
                      parent_id=None, related_topics=[], content=content)
        record["source"]["section"] = section
        payload["policies"].append(record)
        self.path.write_text(json.dumps(payload))

    def test_contact_alternatives_are_source_derived_deduplicated_and_preserved(self):
        self.add_section("store", "Synthetic contacts only: (11) 4000-1001; help@synthetic.invalid", "S1")
        self.add_section("store.contacts", "Synthetic company: (11) 4000-1001; help@synthétic.invalid", "S2")
        self.add_section("whatsapp", "Synthetic WhatsApp: (11) 4000-1002", "S3")
        original = self.path.read_bytes()
        for topic in ("store.contacts", "whatsapp"):
            result = self.executor.execute("get_store_policy", json.dumps({"topic": topic})).result
            contacts = result["data"]["customer_policy"]["resolved"]["contact_channels"]
            self.assertEqual(contacts["phones"], ["(11) 4000-1001", "(11) 4000-1002"])
            self.assertEqual(contacts["emails"], ["help@synthetic.invalid", "help@synthétic.invalid"])
            self.assertTrue(result["data"]["customer_policy"]["sources"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_resolved_shipping_includes_exact_threshold_and_keeps_source_text(self):
        self.add_section("shipping.local", "Synthetic: Frete grátis acima de R$ 700,00. "
                         "Abaixo, taxa fixa de R$ 19,00.", "S4")
        original = self.path.read_bytes()
        result = customer_policy(PolicyCatalog(self.path), "shipping.local")
        self.assertEqual(result["resolved"]["local_shipping"],
                         {"free_from_brl": Decimal("700.00"), "fee_below_brl": Decimal("19.00")})
        self.assertEqual(self.path.read_bytes(), original)

    def test_detailed_payment_minimum_replaces_summary_and_no_disputed_option_remains(self):
        resolved = customer_policy(PolicyCatalog(self.path), "payments")
        self.assertEqual(resolved["resolved"]["installments"][0]["minimum_installment_brl"], Decimal("30"))
        result = self.executor.execute("calculate_payment_options", '{"product_id":101,"installments":5}').result
        self.assertTrue(result["data"]["requested_option"]["available"])
        self.assertNotIn("policy_confirmation_required", json.dumps(result))
        self.assertEqual(result["data"]["best_pix_option"]["total_brl"], "404.91")
        self.assertFalse(result["data"]["discounts_stack"])
        self.assertFalse(result["data"]["checkout_supported"])

    def test_returns_exclusions_do_not_automatically_deny_other_channels(self):
        resolved = customer_policy(PolicyCatalog(self.path), "returns.online")["resolved"]
        self.assertEqual(resolved["preference_exchange_window_starts_at"], "receipt")
        self.assertEqual(resolved["exclusions_scope"], "discretionary_preference_exchange")

    def test_live_callback_cannot_mutate_recorded_sanitized_events(self):
        from dataclasses import replace
        from llm_support import ScriptedClient, offline_config, synthetic_reply
        from timbre.conversation import Conversation
        from timbre.llm.types import LLMEvent, ToolCall

        request = [LLMEvent(tool_calls=(ToolCall(0, "synthetic", "get_my_order_status", '{"order_id":5001}'),)),
                   LLMEvent(finish_reason="tool_calls")]
        config = offline_config()
        config = replace(config, observability=replace(config.observability, record_latency=False))
        conversation = Conversation(ScriptedClient([request, synthetic_reply()]), config, executor=self.executor)
        events = []
        def callback(event):
            self.assertIsNone(event.duration_seconds)
            self.assertNotIn('"order_id": 5001', json.dumps(event.to_dict()))
            events.append(event)
            if event.sanitized_arguments:
                event.sanitized_arguments["order_id"] = "tampered"
        result = conversation.send("Synthetic private order", on_event=callback)
        self.assertEqual(result.metrics.authorization_denial_count, 1)
        self.assertEqual(len(events), len(result.events))
        self.assertNotIn("tampered", str(result.events))
