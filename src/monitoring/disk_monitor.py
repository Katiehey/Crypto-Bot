import shutil
from src.monitoring.logger import setup_logger
from src.monitoring.alerts import AlertManager

def check_disk_usage(threshold_pct=80):
    logger = setup_logger("DiskMonitor", "disk_monitor.log")
    alerts = AlertManager(logger)

    total, used, free = shutil.disk_usage("/")
    usage_pct = used / total * 100

    if usage_pct > threshold_pct:
        alerts.send("WARNING", f"⚠️ Disk usage {usage_pct:.1f}% on EC2")
    else:
        logger.info(f"Disk usage healthy: {usage_pct:.1f}%")
