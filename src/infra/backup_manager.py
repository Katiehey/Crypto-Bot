import tarfile
import time
from pathlib import Path

BACKUP_ROOT = Path("backups")
STATE_DIR = Path("state")
CONFIG_DIR = Path("config")

BACKUP_ROOT.mkdir(exist_ok=True)

def create_backup(max_keep=10):
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_ROOT / f"bot_backup_{ts}.tar.gz"

    try:
        with tarfile.open(backup_file, "w:gz") as tar:
            if STATE_DIR.exists() and any(STATE_DIR.iterdir()):
                tar.add(STATE_DIR, arcname="state")
            if CONFIG_DIR.exists() and any(CONFIG_DIR.iterdir()):
                tar.add(CONFIG_DIR, arcname="config")
    except Exception as e:
        print(f"Backup failed: {e}")
        return None

    cleanup_old_backups(max_keep=max_keep)
    return backup_file

def cleanup_old_backups(max_keep=10):
    backups = sorted(BACKUP_ROOT.glob("bot_backup_*.tar.gz"), key=lambda f: f.stat().st_mtime)
    for old in backups[:-max_keep]:
        try:
            old.unlink()
        except Exception as e:
            print(f"Failed to delete {old}: {e}")
