"""
Shared Pydantic models and enums for copilot endpoints.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class BudgetScopeType(str, Enum):
    ACCOUNT = "account"
    GROUP = "group"
    TEAM = "team"
    USER = "user"


class BudgetAllocationStrategy(str, Enum):
    MANUAL = "manual"
    EQUAL_DISTRIBUTION = "equal_distribution"
    OVERRIDE = "override"


class ConnectionType(str, Enum):
    MCP = "mcp"
    OPENAPI = "openapi"
    INTEGRATION = "integration"


class GuardType(str, Enum):
    PII = "pii"
    TOXIC = "toxic"
    JAILBREAK = "jailbreak"


class ActionOnFail(str, Enum):
    BLOCK = "block"
    FLAG = "flag"
    LOG_ONLY = "log_only"


class PatternType(str, Enum):
    DETECT = "detect"
    BLOCK = "block"
    ALLOW = "allow"


class PatternAction(str, Enum):
    MASK = "mask"
    REDACT = "redact"
    HASH = "hash"
    BLOCK = "block"


class MarketplaceEntityType(str, Enum):
    AGENT = "agent"
    MCP_SERVER = "mcp_server"
    OPENAPI_SPEC = "openapi_spec"
    INTEGRATION = "integration"
    WORKFLOW = "workflow"
    PROMPT_TEMPLATE = "prompt_template"


class MarketplaceStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"


class PricingModel(str, Enum):
    FREE = "free"
    PAID = "paid"
    FREEMIUM = "freemium"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CopilotMembershipRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class CopilotInviteStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NotificationTemplateType(str, Enum):
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    SMS = "SMS"
    IN_APP = "IN_APP"


class SupportTicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SupportTicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    URGENT = "URGENT"
    IMPORTANT = "IMPORTANT"


# ============================================
# Credit Budget Models
# ============================================

class CreditBudgetCreate(BaseModel):
    scope_type: BudgetScopeType
    scope_id: str
    allocated: int = 0
    limit_amount: int = 0
    overflow_cap: Optional[int] = None
    cycle_start: datetime
    cycle_end: datetime
    budget_plan_id: Optional[str] = None
    parent_budget_id: Optional[str] = None
    allocation_strategy: BudgetAllocationStrategy = BudgetAllocationStrategy.MANUAL


class CreditBudgetUpdate(BaseModel):
    allocated: Optional[int] = None
    limit_amount: Optional[int] = None
    overflow_cap: Optional[int] = None
    parent_budget_id: Optional[str] = None
    allocation_strategy: Optional[BudgetAllocationStrategy] = None


class BudgetUsageRecord(BaseModel):
    budget_id: Optional[str] = None
    scope_type: Optional[BudgetScopeType] = None
    scope_id: Optional[str] = None
    amount: int
    description: Optional[str] = None


class BudgetAllocateRequest(BaseModel):
    target_scope_type: BudgetScopeType
    target_scope_id: str
    allocated: int
    limit_amount: Optional[int] = None
    overflow_cap: Optional[int] = None
    allocation_strategy: BudgetAllocationStrategy = BudgetAllocationStrategy.MANUAL


class BudgetDistributeEqualRequest(BaseModel):
    target_scope_type: BudgetScopeType = BudgetScopeType.USER
    include_override_users: bool = False


class BudgetPlanCreate(BaseModel):
    name: str = "Default Plan"
    is_active: bool = True
    distribution: Dict[str, Any] = {"groups": [], "teams": [], "users": []}


class BudgetPlanUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    distribution: Optional[Dict[str, Any]] = None


# ============================================
# Agent Models
# ============================================

class AgentDefCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    page: Optional[str] = None
    categories: Dict[str, Any] = {}
    tags: List[str] = []
    builtin_tools: List[str] = []
    tools_mcp_ids: List[str] = []
    tools_openapi_ids: List[str] = []
    links: Dict[str, Any] = {
        "knowledge": {"file_ids": [], "mcp_ids": [], "openapi_ids": []},
        "guardrails": {"file_ids": [], "mcp_ids": [], "openapi_ids": []},
        "actions": {"file_ids": [], "mcp_ids": [], "openapi_ids": []},
    }
    is_singleton: bool = False
    is_non_conversational: bool = False
    status: str = "active"
    availability: List[str] = ["platform"]
    provider: str = "PLATFORM"


class AgentDefUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    page: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    builtin_tools: Optional[List[str]] = None
    tools_mcp_ids: Optional[List[str]] = None
    tools_openapi_ids: Optional[List[str]] = None
    links: Optional[Dict[str, Any]] = None
    is_singleton: Optional[bool] = None
    is_non_conversational: Optional[bool] = None
    status: Optional[str] = None
    availability: Optional[List[str]] = None
    provider: Optional[str] = None


class AgentGroupCreate(BaseModel):
    group_code: str
    name: str
    description: Optional[str] = None
    group_type: str = "custom"
    metadata: Dict[str, Any] = {}


class AgentGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    group_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class AgentGroupMemberAdd(BaseModel):
    agent_id: str
    display_order: int = 0
    metadata: Dict[str, Any] = {}


# ============================================
# Marketplace Models
# ============================================

class MarketplaceItemCreate(BaseModel):
    entity_id: str
    entity_type: MarketplaceEntityType = MarketplaceEntityType.AGENT
    connection_id: Optional[str] = None
    provider: str = "PLATFORM"
    metadata: Dict[str, Any] = {}
    title: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None
    screenshots: List[str] = []
    demo_video_url: Optional[str] = None
    author: Optional[str] = None
    author_url: Optional[str] = None
    version: str = "1.0.0"
    changelog: List[Dict[str, str]] = []
    pricing_model: PricingModel = PricingModel.FREE
    price: Optional[float] = None
    capabilities: List[Dict[str, str]] = []
    requirements: List[Dict[str, Any]] = []


class MarketplaceItemUpdate(BaseModel):
    title: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None
    screenshots: Optional[List[str]] = None
    demo_video_url: Optional[str] = None
    author: Optional[str] = None
    author_url: Optional[str] = None
    version: Optional[str] = None
    changelog: Optional[List[Dict[str, str]]] = None
    pricing_model: Optional[PricingModel] = None
    price: Optional[float] = None
    marketplace_status: Optional[MarketplaceStatus] = None
    is_featured: Optional[bool] = None
    is_verified: Optional[bool] = None
    capabilities: Optional[List[Dict[str, str]]] = None
    requirements: Optional[List[Dict[str, Any]]] = None


class MarketplaceAssignment(BaseModel):
    scope_type: Literal["account", "group", "team", "user"]
    scope_id: str


class MarketplaceInstallRequest(BaseModel):
    assignments: Optional[List[MarketplaceAssignment]] = None


# ============================================
# Connection Models
# ============================================

class ConnectionCreate(BaseModel):
    connection_type: ConnectionType
    name: str
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    connection_data: Dict[str, Any] = {}
    is_active: bool = True
    is_default: bool = False
    metadata: Dict[str, Any] = {}


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    connection_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================
# Guardrails Models
# ============================================

class GuardrailsConfigUpsert(BaseModel):
    enabled: Optional[bool] = None
    execution_order: Optional[int] = None
    action_on_fail: Optional[ActionOnFail] = None
    config: Optional[Dict[str, Any]] = None


class GuardrailsPatternCreate(BaseModel):
    guard_type: GuardType
    pattern_name: str
    pattern_regex: str
    pattern_type: PatternType = PatternType.DETECT
    action: PatternAction = PatternAction.MASK
    enabled: bool = True
    category: Optional[str] = None
    description: Optional[str] = None
    severity: Severity = Severity.MEDIUM


class GuardrailsPatternUpdate(BaseModel):
    pattern_name: Optional[str] = None
    pattern_regex: Optional[str] = None
    pattern_type: Optional[PatternType] = None
    action: Optional[PatternAction] = None
    enabled: Optional[bool] = None
    category: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None


# ============================================
# Copilot Users / Memberships / Groups / Teams
# ============================================

class CopilotUserCreate(BaseModel):
    email: str
    name: str
    profile_image: Optional[str] = None
    app_role: CopilotMembershipRole = CopilotMembershipRole.USER


class CopilotUserUpdate(BaseModel):
    name: Optional[str] = None
    profile_image: Optional[str] = None
    is_active: Optional[bool] = None


class CopilotMembershipUpdate(BaseModel):
    app_role: Optional[CopilotMembershipRole] = None
    is_active: Optional[bool] = None
    team_id: Optional[str] = None


class CopilotGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None


class CopilotGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None


class CopilotTeamCreate(BaseModel):
    group_id: str
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None


class CopilotTeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None


class CopilotTeamMemberAssign(BaseModel):
    user_id: str


class CopilotInviteCreate(BaseModel):
    email: str
    role: CopilotMembershipRole = CopilotMembershipRole.USER
    role_id: Optional[str] = None
    workspace_id: Optional[str] = None
    expires_in_days: int = 7
    invitation_data: Dict[str, Any] = {}


# ============================================
# Notification Templates
# ============================================

class NotificationTemplateCreate(BaseModel):
    template_id: Optional[str] = None
    title_line: str
    template_content: str
    event_id: Optional[str] = None
    type: NotificationTemplateType = NotificationTemplateType.EMAIL
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class NotificationTemplateUpdate(BaseModel):
    template_id: Optional[str] = None
    title_line: Optional[str] = None
    template_content: Optional[str] = None
    event_id: Optional[str] = None
    type: Optional[NotificationTemplateType] = None
    updated_by: Optional[str] = None


# ============================================
# Support Tickets
# ============================================

class SupportTicketCreate(BaseModel):
    user_profile_id: Optional[str] = None
    subject: str
    description: str
    status: SupportTicketStatus = SupportTicketStatus.OPEN
    priority: SupportTicketPriority = SupportTicketPriority.MEDIUM
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class SupportTicketUpdate(BaseModel):
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[SupportTicketStatus] = None
    priority: Optional[SupportTicketPriority] = None
    assigned_to: Optional[str] = None
    updated_by: Optional[str] = None


class SupportTicketBulkUpdate(BaseModel):
    ticket_ids: List[str]
    status: Optional[SupportTicketStatus] = None
    priority: Optional[SupportTicketPriority] = None
    assigned_to: Optional[str] = None
    account_id: Optional[str] = None
