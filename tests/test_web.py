"""Focused local UI checks using synthetic responses and the actual backend."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from llm_support import OfflineTestCase, ScriptedClient, offline_config, synthetic_reply
from support import DatabaseTestCase, FIXTURES
from timbre.conversation import Conversation
from timbre.llm.types import LLMEvent, ToolCall
from timbre.tools import ToolExecutor
from timbre.web import WebSession


APP = Path(__file__).resolve().parents[1] / "app.py"


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Install the optional web dependencies for UI checks.")
class WebTests(DatabaseTestCase, OfflineTestCase):
    def setUp(self):
        OfflineTestCase.setUp(self)
        DatabaseTestCase.setUp(self)

    def app(self, scripts, *, view="customer"):
        from streamlit.testing.v1 import AppTest

        client = ScriptedClient(scripts)
        executor = ToolExecutor(self.database, FIXTURES / "policies.synthetic.json")
        session = WebSession(Conversation(client, offline_config(), executor=executor, source="synthetic_fixture"), view=view)
        factory = patch("timbre.web.create_session", return_value=session)
        factory.start()
        self.addCleanup(factory.stop)
        app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.assertFalse(app.exception)
        return app, session, client

    def test_stream_history_model_and_rerenders_never_resubmit(self):
        app, session, client = self.app([
            [LLMEvent(text="Olá, "), LLMEvent(text="vamos conversar!", finish_reason="stop")],
            synthetic_reply("The same conversation continues.")])
        app.chat_input[0].set_value("Olá").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message), 2)
        self.assertEqual(session.turns[0].text, "Olá, vamos conversar!")
        self.assertEqual(session.turns[0].result.text, session.conversation.history[-1]["content"])
        identity = session.conversation.session_id
        app.query_params["view"] = "developer"
        app.run()
        self.assertEqual(len(app.get("segmented_control")), 1)
        self.assertFalse(app.expander)
        self.assertFalse(app.metric)
        self.assertEqual(len(client.calls), 1)
        app.get("segmented_control")[0].set_value("fast").run()
        self.assertEqual(len(client.calls), 1)
        app.chat_input[0].set_value("And now?").run()
        self.assertFalse(app.exception)
        self.assertEqual(client.calls[-1]["mode"], "fast")
        self.assertEqual(client.calls[-1]["messages"][1]["content"], "Olá")
        self.assertEqual(session.conversation.session_id, identity)
        self.assertEqual(len(app.chat_message), 4)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertFalse(session.turns)
        self.assertEqual(len(session.conversation.history), 1)
        self.assertEqual(len(client.calls), 2)

    def test_truncation_is_labelled_and_manual_retry_is_a_separate_attempt(self):
        app, session, client = self.app([
            [LLMEvent(text="Synthetic partial", finish_reason="length")],
            synthetic_reply("Synthetic complete answer")])
        app.chat_input[0].set_value("A synthetic question").run()
        self.assertFalse(app.exception)
        self.assertIn("Incomplete response", app.warning[0].value)
        self.assertEqual(len(session.conversation.history), 1)
        self.assertEqual(len(client.calls), 1)
        app.run()
        self.assertEqual(len(client.calls), 1)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].text, "Synthetic complete answer")
        self.assertEqual([m["content"] for m in session.conversation.history].count("A synthetic question"), 1)

    def test_developer_events_and_denials_come_from_the_backend(self):
        request = [LLMEvent(tool_calls=(ToolCall(0, "synthetic-call", "get_my_order_status", '{"order_id":5001}'),)),
                   LLMEvent(finish_reason="tool_calls")]
        app, session, client = self.app([request, synthetic_reply("Please authenticate through support.")], view="developer")
        app.chat_input[0].set_value("My order").run()
        self.assertFalse(app.exception)
        result = session.turns[0].result
        self.assertEqual(result.metrics.authorization_denial_count, 1)
        self.assertEqual(len(app.expander), len(result.events))
        self.assertTrue(any("authorization_denied" in event.label for event in app.expander))
        rendered = "\n".join(element.value for element in [*app.text, *app.code])
        for private in ("5001", "SYNTHETIC-A", "system_prompt", "SELECT"):
            self.assertNotIn(private, rendered)
        self.assertIn("[redacted]", rendered)
        app.run()
        self.assertEqual(len(client.calls), 2)

    def test_missing_metrics_render_as_unavailable(self):
        app, session, _ = self.app([[LLMEvent(text="Synthetic answer", finish_reason="stop")]], view="developer")
        app.chat_input[0].set_value("Hello").run()
        self.assertFalse(app.exception)
        self.assertIsNone(session.turns[0].result.metrics.cost_usd)
        self.assertEqual(app.metric[3].value, "N/A")
        self.assertTrue(any("Input tokens: N/A" in caption.value for caption in app.caption))

    def test_brl_prices_use_literal_markdown_without_changing_the_response(self):
        answer = "Synthetic prices: R$599.90 and R$849.00."
        app, session, _ = self.app([synthetic_reply(answer)])
        app.chat_input[0].set_value("Under R$1,000?").run()
        self.assertFalse(app.exception)
        self.assertIn("Synthetic prices: R\\$599.90 and R\\$849.00.", [m.value for m in app.markdown])
        self.assertEqual(session.turns[0].text, answer)
        self.assertEqual(session.conversation.history[-1]["content"], answer)

    def test_missing_key_displays_safe_setup_error_without_request(self):
        from streamlit.testing.v1 import AppTest
        from timbre.config import ConfigurationError

        with patch("timbre.web.create_session", side_effect=ConfigurationError("Set OPENROUTER_API_KEY privately.")):
            app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertIn("temporarily unavailable", app.error[0].value)
        self.assertNotIn("OPENROUTER_API_KEY", app.error[0].value)
        self.assertFalse(app.chat_input)

    def test_customer_has_no_internal_labels_or_view_switch(self):
        app, session, client = self.app([synthetic_reply("Synthetic customer answer")])
        rendered = "\n".join(m.value for m in [*app.caption, *app.markdown, *app.text])
        for internal in ("deepseek", "reflection", "Developer", "snapshot", "Local demonstration", "follows your language"):
            self.assertNotIn(internal, rendered)
        self.assertEqual(len(app.get("segmented_control")), 1)
        app.chat_input[0].set_value("Hello").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.expander)
        self.assertFalse(app.metric)
        self.assertFalse(app.text)
        self.assertEqual(session.view, "customer")

    def test_developer_receives_live_events_before_final_response(self):
        request = [LLMEvent(tool_calls=(ToolCall(0, "synthetic-call", "get_product_details", '{"product_id":101}'),)),
                   LLMEvent(finish_reason="tool_calls")]
        app, session, client = self.app([request, synthetic_reply("Synthetic details")], view="developer")
        observed = []
        original = session.execute

        def execute(on_text, on_event=None):
            def event(value):
                observed.append((value.event_type, len(client.calls), session.turns[-1].result))
                on_event(value)
            return original(on_text, on_event=event)

        with patch.object(session, "execute", side_effect=execute):
            app.chat_input[0].set_value("Details").run()
        self.assertFalse(app.exception)
        self.assertTrue(any(kind == "tool_result_returned" and calls == 1 and result is None
                            for kind, calls, result in observed))
        self.assertEqual(len(app.expander), len(session.turns[0].result.events))
        self.assertTrue(any("1 product returned" in m.value for m in app.caption))
        app.run()
        self.assertEqual(len(client.calls), 2)


class WebSessionTests(OfflineTestCase):
    def test_launch_view_is_chosen_by_server_environment_and_validated(self):
        from timbre.config import ConfigurationError
        from timbre.web import create_session

        client = ScriptedClient()
        with patch("timbre.web.load_config", return_value=offline_config()), \
             patch("timbre.web.OpenRouterClient.from_environment", return_value=client) as factory:
            with patch.dict(os.environ, {"TIMBRE_WEB_VIEW": "developer"}):
                developer = create_session()
                self.assertEqual(developer.view, "developer")
            with patch.dict(os.environ, {"TIMBRE_WEB_VIEW": "customer"}):
                customer = create_session()
                self.assertEqual(customer.view, "customer")
                self.assertEqual(developer.view, "developer")
                self.assertNotEqual(customer.conversation.session_id, developer.conversation.session_id)
            calls = factory.call_count
            with patch.dict(os.environ, {"TIMBRE_WEB_VIEW": "admin"}):
                with self.assertRaises(ConfigurationError):
                    create_session()
            self.assertEqual(factory.call_count, calls)
        self.assertFalse(client.calls)

    def test_callback_receives_progressive_text_and_never_changes_model_history(self):
        client = ScriptedClient([[LLMEvent(text="One "), LLMEvent(text="two", finish_reason="stop")]])
        session = WebSession(Conversation(client, offline_config(), source="synthetic_fixture"))
        session.queue("Hello")
        displayed = []
        turn = session.execute(displayed.append)
        self.assertEqual(displayed, ["One ", "One two"])
        self.assertEqual(turn.text, "One two")
        self.assertIsNone(session.pending)
        with self.assertRaises(RuntimeError):
            session.execute(displayed.append)
        self.assertEqual(len(client.calls), 1)
