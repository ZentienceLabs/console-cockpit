"""Alchemi constants and environment-based configuration."""
import os

ALCHEMI_AUDIT_LOG_RETENTION_DAYS = int(os.getenv("ALCHEMI_AUDIT_LOG_RETENTION_DAYS", "90"))
ALCHEMI_BRAND_NAME = "Alchemi Studio Console"
ALCHEMI_VERSION = "1.0.0"
