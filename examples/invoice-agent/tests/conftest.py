import os

# Keep test runs in memory; the demo uses a local SQLite directory.
os.environ.setdefault("INVOICE_AGENT_DATA", ":memory:")
