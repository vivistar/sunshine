"""Test configuration: isolate the database before the app is imported."""

import os
import tempfile

# Must run before any `app.*` import so the settings singleton picks it up.
_TMPDIR = tempfile.mkdtemp(prefix="sunshine-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"
os.environ["BASE_URL"] = "http://testserver"
os.environ["SMTP_HOST"] = ""  # force console email mode in tests
