"""Linux process identity for publication claims; uncertainty never implies death."""
from pathlib import Path
import os


def process_identity(pid: int) -> dict:
    stat = Path(f'/proc/{pid}/stat').read_text()
    fields = stat[stat.rfind(')') + 2:].split()
    return {'pid': pid, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'start_ticks': fields[19], 'state': fields[0]}


def current_review_owner() -> dict | None:
    try:
        return process_identity(os.getpid())
    except (OSError, ValueError, IndexError):
        return None


def review_owner_exited(owner: object) -> bool:
    if not isinstance(owner, dict) or not all(k in owner for k in ('pid', 'boot_id', 'start_ticks')):
        return False
    if type(owner['pid']) is not int or owner['pid'] <= 0:
        return False
    try:
        current = process_identity(owner['pid'])
    except FileNotFoundError:
        return Path('/proc/sys/kernel/random/boot_id').is_file()
    except (OSError, ValueError, IndexError):
        return False
    return (current['state'] == 'Z' or current['boot_id'] != owner['boot_id']
            or current['start_ticks'] != owner['start_ticks'])
