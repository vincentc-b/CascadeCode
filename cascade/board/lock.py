"""Process lock shared by board commits and the watchdog.

Re-entrant so write_doc, move_doc, and commit_paths can nest inside dispatch.
Boot hooks run only after the caller releases this lock.
"""

from __future__ import annotations

import threading

process_lock = threading.RLock()
