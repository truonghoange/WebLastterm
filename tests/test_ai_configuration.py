import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
from google.genai.errors import APIError

from backend.config import Settings
from backend.ai_response_models import AISemanticResponse
from backend.exceptions import LLMFailureReason, LLMUnavailableError
from backend.providers.gemini_provider import GeminiProvider
from backend.services.analysis_service import AI_FALLBACK_WARNING, AnalysisService
from tests.helpers import document, semantic_payload


class AIConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.home = Path(self.temp.name) / "home"
        self.root.mkdir()
        self.home.mkdir()
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def settings(self):
        return Settings.from_env(project_root=self.root, user_home=self.home)

    def secrets(self, root, text):
        directory = root / ".streamlit"
        directory.mkdir(exist_ok=True)
        (directory / "secrets.toml").write_text(text, encoding="utf-8")

    def test_dotenv_loaded_from_project_independent_of_cwd(self):
        (self.root / ".env").write_text('GEMINI_API_KEY="test-local-key"\nGEMINI_MODEL=test-model\n', encoding="utf-8")
        settings = self.settings()
        self.assertEqual(settings.gemini_api_key, "test-local-key")
        self.assertEqual(settings.gemini_model, "test-model")
        self.assertNotIn("GEMINI_API_KEY", os.environ)
        self.assertNotIn("test-local-key", repr(settings))

    def test_environment_overrides_all_files(self):
        (self.root / ".env").write_text("GEMINI_API_KEY=dotenv-key", encoding="utf-8")
        self.secrets(self.root, 'GEMINI_API_KEY="project-key"')
        self.secrets(self.home, 'GEMINI_API_KEY="user-key"')
        os.environ["GEMINI_API_KEY"] = "process-key"
        self.assertEqual(self.settings().gemini_api_key, "process-key")

    def test_streamlit_project_secrets_override_user_secrets_and_dotenv(self):
        (self.root / ".env").write_text("GEMINI_API_KEY=dotenv-key", encoding="utf-8")
        self.secrets(self.home, 'GEMINI_API_KEY="user-key"')
        self.assertEqual(self.settings().gemini_api_key, "user-key")
        self.secrets(self.root, 'GEMINI_API_KEY="project-key"')
        self.assertEqual(self.settings().gemini_api_key, "project-key")

    def test_google_api_key_alias_and_gemini_key_precedence(self):
        os.environ["GOOGLE_API_KEY"] = "google-key"
        self.assertEqual(self.settings().gemini_api_key, "google-key")
        os.environ["GEMINI_API_KEY"] = "gemini-key"
        self.assertEqual(self.settings().gemini_api_key, "gemini-key")

    def test_empty_environment_key_explicitly_disables_ai(self):
        (self.root / ".env").write_text("GEMINI_API_KEY=dotenv-key", encoding="utf-8")
        os.environ["GEMINI_API_KEY"] = ""
        self.assertEqual(self.settings().gemini_api_key, "")

    def test_blank_or_template_key_is_not_sent_to_gemini(self):
        for key in ("", "-", "your-key", "YOUR-API-KEY", "replace-me"):
            with self.subTest(key=key):
                os.environ["GEMINI_API_KEY"] = key
                client = MagicMock()
                settings = self.settings()
                service = AnalysisService(settings=settings, provider=GeminiProvider(settings, client=client))
                with self.assertLogs("backend", level="WARNING") as logs:
                    result = service.analyze_cv(document())
                client.models.generate_content.assert_not_called()
                self.assertFalse(result.ai_available)
                self.assertIn("reason=missing_api_key", " ".join(logs.output))
                self.assertTrue(any("not configured" in warning for warning in result.warnings))
                self.assertNotIn(AI_FALLBACK_WARNING, result.warnings)

    def test_configuration_changes_loaded_on_next_analysis(self):
        self.assertEqual(self.settings().gemini_api_key, "")
        (self.root / ".env").write_text("GEMINI_API_KEY=test-added-key", encoding="utf-8")
        self.assertEqual(self.settings().gemini_api_key, "test-added-key")

    def test_malformed_secret_file_does_not_leak_key_or_break_fallback(self):
        self.secrets(self.root, 'GEMINI_API_KEY="private-secret-without-closing-quote')
        with self.assertLogs("backend", level="WARNING") as logs:
            settings = self.settings()
        self.assertEqual(settings.gemini_api_key, "")
        self.assertNotIn("private-secret", " ".join(logs.output))

    def test_dotenv_key_reaches_sdk_and_validated_application_result(self):
        (self.root / ".env").write_text("GEMINI_API_KEY=test-local-key", encoding="utf-8")
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(semantic_payload(None)))
        with patch("google.genai.Client", return_value=client) as factory:
            service = AnalysisService(settings=self.settings())
            result = service.analyze_cv(document())
            service.close()
        self.assertEqual(factory.call_args.kwargs["api_key"], "test-local-key")
        client.models.generate_content.assert_called_once()
        client.close.assert_called_once()
        self.assertTrue(result.ai_available)
        self.assertEqual(result.analysis_metadata.model, "gemini-2.5-flash")


class AIFallbackDiagnosticsTests(unittest.TestCase):
    def test_sdk_errors_have_safe_specific_reasons(self):
        cases = ((401, LLMFailureReason.AUTHENTICATION), (403, LLMFailureReason.AUTHENTICATION),
                 (429, LLMFailureReason.QUOTA), (404, LLMFailureReason.MODEL_UNAVAILABLE),
                 (400, LLMFailureReason.REQUEST_REJECTED), (500, LLMFailureReason.SERVICE_UNAVAILABLE),
                 (503, LLMFailureReason.SERVICE_UNAVAILABLE), (504, LLMFailureReason.TIMEOUT))
        for code, reason in cases:
            with self.subTest(code=code):
                client = MagicMock()
                client.models.generate_content.side_effect = APIError(code, {"error": {"message": "private-key private-CV"}})
                provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
                with self.assertLogs("backend", level="WARNING") as logs:
                    result = AnalysisService(provider=provider).analyze_cv(document())
                self.assertFalse(result.ai_available)
                self.assertIn(f"reason={reason.value}", " ".join(logs.output))
                self.assertIn(AI_FALLBACK_WARNING, result.warnings)
                self.assertGreater(len(result.warnings), 2)
                for private in ("private-key", "private-CV"):
                    self.assertNotIn(private, " ".join(logs.output + result.warnings))
                client.models.generate_content.assert_called_once()

    def test_sdk_network_and_timeout_errors_have_specific_reasons(self):
        for error, reason in ((httpx.ReadTimeout("private-CV"), LLMFailureReason.TIMEOUT),
                              (httpx.ConnectError("private-key"), LLMFailureReason.NETWORK)):
            with self.subTest(reason=reason):
                client = MagicMock()
                client.models.generate_content.side_effect = error
                provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
                with self.assertRaises(LLMUnavailableError) as caught:
                    provider.analyze("synthetic CV", AISemanticResponse)
                self.assertEqual(caught.exception.reason, reason)
                self.assertNotIn("private", str(caught.exception))

    def test_invalid_response_reports_validation_reason(self):
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text="malformed private response")
        provider = GeminiProvider(Settings(gemini_api_key="test-only"), client=client)
        with self.assertLogs("backend", level="WARNING") as logs:
            result = AnalysisService(provider=provider).analyze_cv(document())
        self.assertFalse(result.ai_available)
        self.assertIn("reason=invalid_response", " ".join(logs.output))
        self.assertTrue(any("could not be validated" in warning for warning in result.warnings))
        self.assertNotIn("private", " ".join(logs.output + result.warnings))
