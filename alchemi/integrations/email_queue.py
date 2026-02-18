"""
Push email jobs to the alchemi-worker BullMQ queue.

The alchemi-worker project processes the ``{email-notifications}`` queue
and sends emails via Azure Communication Services.  This module lets
console-cockpit enqueue email jobs from Python so we reuse the same
worker/templates infrastructure that alchemi-web already uses.

Azure Managed Redis uses OSS Cluster mode, so we create a
``redis.asyncio.RedisCluster`` client and wire it into BullMQ manually
(BullMQ's ``RedisConnection`` only does an ``isinstance(…, redis.Redis)``
check, which ``RedisCluster`` does not satisfy).
"""

import os
import traceback
from typing import Dict, Optional

from litellm._logging import verbose_proxy_logger

# Lazy-initialised queue instance (created on first use)
_queue = None


def _create_cluster_queue(host: str, port: int, password: str, use_ssl: bool, prefix: str):
    """
    Build a BullMQ Queue backed by a ``redis.asyncio.RedisCluster`` connection.
    """
    import redis.asyncio as redis_async
    from bullmq import Queue
    from bullmq.redis_connection import RedisConnection
    from bullmq.scripts import Scripts

    rc = redis_async.RedisCluster(
        host=host,
        port=port,
        password=password,
        ssl=use_ssl,
        ssl_cert_reqs=None,
        decode_responses=True,
    )

    queue_name = "{email-notifications}"

    # Bypass BullMQ's type-check by constructing objects manually
    q = Queue.__new__(Queue)
    q.name = queue_name
    q.opts = {"prefix": prefix}
    q.jobsOpts = {}
    q.prefix = prefix

    redis_conn = RedisConnection.__new__(RedisConnection)
    redis_conn.conn = rc
    redis_conn.version = None
    redis_conn.commands = {}
    redis_conn.loadCommands()

    q.redisConnection = redis_conn
    q.client = rc
    q.scripts = Scripts(q.prefix, q.name, redis_conn)
    q.keys = q.scripts.queue_keys.getKeys(queue_name)
    q.qualifiedName = q.scripts.queue_keys.getQueueQualifiedName(queue_name)

    return q


async def _get_queue():
    """Return (or create) the shared BullMQ Queue instance."""
    global _queue
    if _queue is not None:
        return _queue

    host = os.getenv("EMAIL_REDIS_HOST")
    if not host:
        return None

    port = int(os.getenv("EMAIL_REDIS_PORT", "10000"))
    password = os.getenv("EMAIL_REDIS_PASSWORD", "")
    use_ssl = os.getenv("EMAIL_REDIS_TLS", "true").lower() in ("true", "1", "yes")
    env = os.getenv("EMAIL_REDIS_ENVIRONMENT", "dev")
    prefix = f"bull:{env}"

    try:
        _queue = _create_cluster_queue(host, port, password, use_ssl, prefix)
        verbose_proxy_logger.info(
            f"Email queue connected to {host}:{port} (prefix={prefix}, cluster mode)"
        )
        return _queue
    except Exception:
        traceback.print_exc()
        verbose_proxy_logger.warning("Failed to initialise email queue")
        return None


def is_configured() -> bool:
    """Return True if the email queue Redis env vars are set."""
    return bool(os.getenv("EMAIL_REDIS_HOST"))


async def send_invitation_email(
    user_email: str,
    user_name: str,
    inviter_name: str,
    invite_link: str,
    workspace_name: str = "Alchemi Studio Console",
) -> bool:
    """
    Push a WORKSPACE_MEMBER_INVITED email job to the queue.

    Returns True if the job was enqueued successfully.
    """
    queue = await _get_queue()
    if queue is None:
        verbose_proxy_logger.info(
            "Email queue not configured (EMAIL_REDIS_HOST not set). "
            "Skipping invitation email."
        )
        return False

    try:
        job = await queue.add(
            "send-email",
            {
                "type": "event",
                "eventId": "WORKSPACE_MEMBER_INVITED",
                "to": {"email": user_email, "name": user_name},
                "placeholders": {
                    "user_name": user_name,
                    "inviter_name": inviter_name,
                    "workspace_name": workspace_name,
                    "invite_link": invite_link,
                },
            },
        )
        verbose_proxy_logger.info(
            f"Invitation email queued for {user_email} (job {job.id})"
        )
        return True
    except Exception:
        traceback.print_exc()
        verbose_proxy_logger.warning(
            f"Failed to queue invitation email for {user_email}"
        )
        return False


async def send_email(
    user_email: str,
    user_name: str,
    event_id: str,
    placeholders: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Push an arbitrary email job to the queue.

    ``event_id`` must match a row in the worker's
    ``notificationtemplates`` table.
    """
    queue = await _get_queue()
    if queue is None:
        return False

    merged = {"user_name": user_name}
    if placeholders:
        merged.update(placeholders)

    try:
        job = await queue.add(
            "send-email",
            {
                "type": "event",
                "eventId": event_id,
                "to": {"email": user_email, "name": user_name},
                "placeholders": merged,
            },
        )
        verbose_proxy_logger.info(
            f"Email queued for {user_email} event={event_id} (job {job.id})"
        )
        return True
    except Exception:
        traceback.print_exc()
        verbose_proxy_logger.warning(
            f"Failed to queue email for {user_email} event={event_id}"
        )
        return False
