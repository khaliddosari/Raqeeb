import os
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "test_raqeeb.db"
_TEST_DB.unlink(missing_ok=True)

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("TELEPHONY_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
# graph state in memory so each run starts clean and leaves no file behind
os.environ.setdefault("CHECKPOINT_DB", ":memory:")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "test-sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
# the shared admin password, which gates every action that spends telephony money
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
# Empty on purpose, and set rather than left unset: agent/config.py reads the developer's own
# .env, so without this a machine that can really place calls would test something else.
os.environ.setdefault("ADMIN_CALL_NUMBERS", "")
