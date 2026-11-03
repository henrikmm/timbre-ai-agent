"""Offline configuration and credential boundaries with synthetic values only."""

from dataclasses import replace
from importlib.resources import files
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from timbre.config import ConfigurationError, load_api_key, load_config, load_system_prompt
from timbre.llm.openrouter import OpenRouterClient, request_parameters
from llm_support import OfflineTestCase


class ConfigurationTests(OfflineTestCase):
    def test_defaults_and_parameter_mapping(self):
        config = load_config()
        self.assertEqual(config.default_mode, "standard")
        self.assertEqual(config.modes["standard"].model, "deepseek/deepseek-v4.1-flash-1017")
        standard = request_parameters([], config, "standard", cross_model_fallback=False)
        fast = request_parameters([], config, "fast", cross_model_fallback=False)
        self.assertNotIn("sort", standard["provider"])
        self.assertEqual(fast["provider"]["sort"], "latency")
        self.assertTrue(fast["provider"]["require_parameters"])
        self.assertEqual(fast["provider"]["data_collection"], "deny")
        self.assertNotIn("reasoning", standard)
        self.assertNotIn("temperature", fast)
        self.assertEqual(standard["max_tokens"], config.max_output_tokens)
        self.assertEqual(standard["timeout_ms"], 45000)
        self.assertNotIn("tools", standard)

    def test_fallback_has_an_explicit_model_order_and_can_be_disabled(self):
        config = load_config()
        for mode, other in (("standard", "fast"), ("fast", "standard")):
            enabled = request_parameters([], config, mode, cross_model_fallback=True)
            self.assertEqual(enabled["models"], [config.modes[mode].model, config.modes[other].model])
            self.assertNotIn("model", enabled)
            disabled = request_parameters([], config, mode, cross_model_fallback=False)
            self.assertNotIn("models", disabled)

    def test_custom_file_model_and_default_mode(self):
        default = files("timbre").joinpath("resources/default.toml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.toml"
            path.write_text(default.replace('default_mode = "standard"', 'default_mode = "fast"')
                             .replace('model = "openai/gpt-oss-120b"', 'model = "synthetic/custom-model"'))
            config = load_config(path)
        self.assertEqual(config.default_mode, "fast")
        self.assertEqual(config.modes["fast"].model, "synthetic/custom-model")

    def test_invalid_settings_are_rejected_with_actionable_safe_errors(self):
        default = files("timbre").joinpath("resources/default.toml").read_text()
        mutations = [default + '\nunknown_field = "synthetic-secret"', "[llm", "",
                     default.replace('default_mode = "standard"', 'default_mode = []'),
                     default.replace("timeout_seconds = 45", "timeout_seconds = true"),
                     default.replace("history_turn_limit = 12", "history_turn_limit = 0"),
                     default.replace("max_output_tokens = 512", "max_output_tokens = -1"),
                     default.replace('provider_sort = "latency"', 'provider_sort = "imaginary"'),
                     default.replace("store_conversation_content = false", "store_conversation_content = true"),
                     default.replace("require_parameters = true", "require_parameters = false"),
                     default.replace('reasoning_effort = "default"', 'reasoning_effort = "low"', 1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            for index, value in enumerate(mutations):
                with self.subTest(index=index):
                    path.write_text(value)
                    with self.assertRaises(ConfigurationError) as caught:
                        load_config(path)
                    self.assertNotIn("synthetic-secret", str(caught.exception))
            with self.assertRaises(ConfigurationError):
                load_config(Path(directory) / "missing.toml")

    def test_opt_in_reasoning_is_not_silently_applied_to_unsupported_fallback(self):
        config = load_config()
        modes = dict(config.modes)
        modes["fast"] = replace(modes["fast"], reasoning_effort="low")
        config = replace(config, modes=modes)
        parameters = request_parameters([], config, "fast", cross_model_fallback=False)
        self.assertEqual(parameters["reasoning"], {"effort": "low"})
        with self.assertRaises(ConfigurationError):
            request_parameters([], config, "fast", cross_model_fallback=True)

    def test_missing_and_placeholder_key_never_construct_a_client(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            missing = Path(directory) / ".env"
            with patch("openrouter.OpenRouter") as factory:
                with self.assertRaisesRegex(ConfigurationError, "OPENROUTER_API_KEY"):
                    OpenRouterClient.from_environment(load_config(), missing)
                factory.assert_not_called()
            for key in ("", " ", "replace-with-your-private-key"):
                with self.assertRaises(ConfigurationError):
                    load_api_key(missing, environ={"OPENROUTER_API_KEY": key})

    def test_explicit_dotenv_and_environment_precedence_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('OPENROUTER_API_KEY="synthetic-${DO_NOT_EXPAND}"\n')
            before = dict(os.environ)
            self.assertEqual(load_api_key(path, environ={}), "synthetic-${DO_NOT_EXPAND}")
            self.assertEqual(load_api_key(path, environ={"OPENROUTER_API_KEY": "synthetic-exported"}), "synthetic-exported")
            self.assertEqual(dict(os.environ), before)

    def test_packaged_prompt_contains_boundaries_without_the_manual_or_records(self):
        prompt = load_system_prompt()
        for phrase in ("Timbre", "Empório da Música", "English", "no database", "authentication", "untrusted data"):
            self.assertIn(phrase, prompt)
        self.assertLess(len(prompt), 4000)
        self.assertNotIn("@", prompt)
