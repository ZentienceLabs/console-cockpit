"""
Hooks that are triggered when a litellm user event occurs
"""

import asyncio
from litellm._uuid import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

import litellm
from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import (
    AUDIT_ACTIONS,
    CommonProxyErrors,
    LiteLLM_AuditLogs,
    Litellm_EntityType,
    LiteLLM_UserTable,
    LitellmTableNames,
    NewUserRequest,
    NewUserResponse,
    UserAPIKeyAuth,
    WebhookEvent,
)
from litellm.proxy.management_helpers.audit_logs import create_audit_log_for_update


class UserManagementEventHooks:
    @staticmethod
    async def async_user_created_hook(
        data: NewUserRequest,
        response: NewUserResponse,
        user_api_key_dict: UserAPIKeyAuth,
    ):
        """
        This hook is called when a new user is created on litellm

        Handles:
        - Creating an audit log for the user creation
        - Sending a user invitation email to the user
        """
        from litellm.proxy.proxy_server import litellm_proxy_admin_name, prisma_client

        #########################################################
        ########## Send User Invitation Email ################
        #########################################################
        await UserManagementEventHooks.async_send_user_invitation_email(
            data=data,
            response=response,
            user_api_key_dict=user_api_key_dict,
        )

        #########################################################
        ########## CREATE AUDIT LOG ################
        #########################################################
        try:
            if prisma_client is None:
                raise Exception(CommonProxyErrors.db_not_connected_error.value)
            user_row: BaseModel = await prisma_client.db.litellm_usertable.find_first(
                where={"user_id": response.user_id}
            )

            user_row_litellm_typed = LiteLLM_UserTable(
                **user_row.model_dump(exclude_none=True)
            )
            asyncio.create_task(
                UserManagementEventHooks.create_internal_user_audit_log(
                    user_id=user_row_litellm_typed.user_id,
                    action="created",
                    litellm_changed_by=user_api_key_dict.user_id,
                    user_api_key_dict=user_api_key_dict,
                    litellm_proxy_admin_name=litellm_proxy_admin_name,
                    before_value=None,
                    after_value=user_row_litellm_typed.model_dump_json(
                        exclude_none=True
                    ),
                )
            )
        except Exception as e:
            verbose_proxy_logger.warning(
                "Unable to create audit log for user on `/user/new` - {}".format(str(e))
            )
        pass

    @staticmethod
    async def async_send_user_invitation_email(
        data: NewUserRequest,
        response: NewUserResponse,
        user_api_key_dict: UserAPIKeyAuth,
    ):
        """
        Send a user invitation email to the user.

        When EMAIL_MODE=tenant_first, tries the tenant's own SMTP config
        first.  Then falls back to the central alchemi-worker email queue
        (BullMQ → Azure Communication Services).  Finally falls back to
        enterprise V2 / legacy V1 paths.
        """
        if data.send_invite_email is not True:
            return

        # -----------------------------------------------------------
        # Helper: build invitation URL (shared across paths)
        # -----------------------------------------------------------
        import os

        async def _build_invite_url() -> str:
            try:
                from litellm.proxy._types import InvitationNew
                from litellm.proxy.management_helpers.user_invitation import (
                    create_invitation_for_user,
                )
                invitation = await create_invitation_for_user(
                    data=InvitationNew(user_id=response.user_id),
                    user_api_key_dict=user_api_key_dict,
                )
                base_url = os.getenv("PROXY_BASE_URL", "")
                return f"{base_url}/ui?invitation_id={invitation.id}"
            except Exception as inv_err:
                verbose_proxy_logger.warning(
                    f"Failed to create invitation link: {inv_err}"
                )
                base_url = os.getenv("PROXY_BASE_URL", "")
                return f"{base_url}/ui" if base_url else ""

        # -----------------------------------------------------------
        # Tenant SMTP path (only when EMAIL_MODE=tenant_first)
        # -----------------------------------------------------------
        try:
            from alchemi.integrations.tenant_email import (
                get_email_mode,
                send_tenant_invitation_email,
            )

            if get_email_mode() == "tenant_first" and response.user_email:
                from alchemi.middleware.tenant_context import get_current_account_id

                account_id = get_current_account_id()
                if account_id:
                    invite_url = await _build_invite_url()
                    user_name = response.user_email.split("@")[0]
                    inviter = user_api_key_dict.user_email or "Admin"

                    sent = await send_tenant_invitation_email(
                        account_id=account_id,
                        user_email=response.user_email,
                        user_name=user_name,
                        inviter_name=inviter,
                        invite_link=invite_url,
                    )
                    if sent:
                        return  # success — skip central + legacy paths
        except Exception as e:
            verbose_proxy_logger.warning(
                f"Tenant SMTP send failed, falling back to central: {e}"
            )

        # -----------------------------------------------------------
        # Central email queue (preferred central path)
        # -----------------------------------------------------------
        try:
            from alchemi.integrations.email_queue import (
                is_configured as eq_configured,
                send_invitation_email as eq_send,
            )

            if eq_configured() and response.user_email:
                invite_url = await _build_invite_url()

                user_name = response.user_email.split("@")[0]
                inviter = user_api_key_dict.user_email or "Admin"

                sent = await eq_send(
                    user_email=response.user_email,
                    user_name=user_name,
                    inviter_name=inviter,
                    invite_link=invite_url,
                )
                if sent:
                    return  # success — skip legacy paths
        except Exception as e:
            verbose_proxy_logger.warning(
                f"Email queue send failed, falling back: {e}"
            )

        # -----------------------------------------------------------
        # Fallback: enterprise V2 + legacy V1 paths
        # -----------------------------------------------------------
        event = WebhookEvent(
            event="internal_user_created",
            event_group=Litellm_EntityType.USER,
            event_message="Welcome to LiteLLM Proxy",
            token=response.token,
            spend=response.spend or 0.0,
            max_budget=response.max_budget,
            user_id=response.user_id,
            user_email=response.user_email,
            team_id=response.team_id,
            key_alias=response.key_alias,
        )

        try:
            from alchemi.enterprise_features.email_notifications import (
                BaseEmailLogger,
            )

            initialized_email_loggers = litellm.logging_callback_manager.get_custom_loggers_for_type(
                callback_type=BaseEmailLogger  # type: ignore
            )
            if len(initialized_email_loggers) > 0:
                for email_logger in initialized_email_loggers:
                    if isinstance(email_logger, BaseEmailLogger):  # type: ignore
                        await email_logger.send_user_invitation_email(  # type: ignore
                            event=event,
                        )
        except ImportError:
            pass

        await UserManagementEventHooks.send_legacy_v1_user_invitation_email(
            data=data,
            response=response,
            user_api_key_dict=user_api_key_dict,
            event=event,
        )

    @staticmethod
    async def send_legacy_v1_user_invitation_email(
        data: NewUserRequest,
        response: NewUserResponse,
        user_api_key_dict: UserAPIKeyAuth,
        event: WebhookEvent,
    ):
        """
        Send a user invitation email to the user
        """
        from litellm.proxy.proxy_server import general_settings, proxy_logging_obj

        # check if user has setup email alerting
        if "email" not in general_settings.get("alerting", []):
            raise ValueError(
                "Email alerting not setup on config.yaml. Please set `alerting=['email']. \nDocs: https://docs.litellm.ai/docs/proxy/email`"
            )

        # If user configured email alerting - send an Email letting their end-user know the key was created
        asyncio.create_task(
            proxy_logging_obj.slack_alerting_instance.send_key_created_or_user_invited_email(
                webhook_event=event,
            )
        )

    @staticmethod
    async def create_internal_user_audit_log(
        user_id: str,
        action: AUDIT_ACTIONS,
        litellm_changed_by: Optional[str],
        user_api_key_dict: UserAPIKeyAuth,
        litellm_proxy_admin_name: Optional[str],
        before_value: Optional[str] = None,
        after_value: Optional[str] = None,
    ):
        """
        Create an audit log for an internal user.

        Parameters:
        - user_id: str - The id of the user to create the audit log for.
        - action: AUDIT_ACTIONS - The action to create the audit log for.
        - user_row: LiteLLM_UserTable - The user row to create the audit log for.
        - litellm_changed_by: Optional[str] - The user id of the user who is changing the user.
        - user_api_key_dict: UserAPIKeyAuth - The user api key dictionary.
        - litellm_proxy_admin_name: Optional[str] - The name of the proxy admin.
        """
        if not litellm.store_audit_logs:
            return

        await create_audit_log_for_update(
            request_data=LiteLLM_AuditLogs(
                id=str(uuid.uuid4()),
                updated_at=datetime.now(timezone.utc),
                changed_by=litellm_changed_by
                or user_api_key_dict.user_id
                or litellm_proxy_admin_name,
                changed_by_api_key=user_api_key_dict.api_key,
                table_name=LitellmTableNames.USER_TABLE_NAME,
                object_id=user_id,
                action=action,
                updated_values=after_value,
                before_value=before_value,
            )
        )
