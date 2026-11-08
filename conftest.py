"""Repository-wide test settings.

The support lab's refund service really waits on a socket timeout during the
timeout-after-commit scenario; keep it short in tests (production default: 1200 ms).
"""

import os

os.environ.setdefault("GHOSTREPLAY_SUPPORT_CLIENT_TIMEOUT_MS", "300")
