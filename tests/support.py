"""Synthetic fixtures and test-only authentication simulation; never production auth."""

from pathlib import Path
import shutil
import tempfile
import unittest

from timbre.authorization import AccessDenied
from timbre.database.import_data import import_csvs

FIXTURES = Path(__file__).parent / "fixtures"


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.raw = self.directory / "raw"
        shutil.copytree(FIXTURES, self.raw)
        self.database = self.directory / "store.db"
        self.report = import_csvs(self.raw, self.database)


class SimulatedAuthorizer:
    """An isolated issuer for security tests, not a production authentication shortcut.

    The registry binds object identity to a customer ID. Claimed fields, names,
    phone numbers, and fabricated objects cannot override that binding.
    """

    def __init__(self):
        self._sessions = {}

    def issue_for_test(self, customer_id: int) -> object:
        token = object()
        self._sessions[token] = customer_id
        return token

    def require_customer_id(self, context: object | None) -> int:
        for token, customer_id in self._sessions.items():
            if token is context:
                return customer_id
        raise AccessDenied("unrecognized simulated session")
