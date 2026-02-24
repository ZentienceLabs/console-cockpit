# INSTRUCTIONS FOR LITELLM

This document provides comprehensive instructions for AI agents working in the LiteLLM repository.

## OVERVIEW

LiteLLM is a unified interface for 100+ LLMs that:
- Translates inputs to provider-specific completion, embedding, and image generation endpoints
- Provides consistent OpenAI-format output across all providers
- Includes retry/fallback logic across multiple deployments (Router)
- Offers a proxy server (LLM Gateway) with budgets, rate limits, and authentication
- Supports advanced features like function calling, streaming, caching, and observability

## REPOSITORY STRUCTURE

### Core Components
- `litellm/` - Main library code
  - `llms/` - Provider-specific implementations (OpenAI, Anthropic, Azure, etc.)
  - `proxy/` - Proxy server implementation (LLM Gateway)
  - `router_utils/` - Load balancing and fallback logic
  - `types/` - Type definitions and schemas
  - `integrations/` - Third-party integrations (observability, caching, etc.)

### Key Directories
- `tests/` - Comprehensive test suites
- `docs/my-website/` - Documentation website
- `ui/litellm-dashboard/` - Admin dashboard UI
- `alchemi/` - Alchemi enterprise extensions (replaces `enterprise/`)
  - `auth/` - Zitadel OIDC, account resolution, super admin
  - `db/` - Tenant-scoped Prisma client + asyncpg copilot DB wrapper
  - `endpoints/` - Account management + copilot feature endpoints
  - `hooks/` - Audit logging, secret detection, cost tracking
  - `middleware/` - Account middleware + tenant context
  - `scripts/` - Data migration scripts

## DEVELOPMENT GUIDELINES

### MAKING CODE CHANGES

1. **Provider Implementations**: When adding/modifying LLM providers:
   - Follow existing patterns in `litellm/llms/{provider}/`
   - Implement proper transformation classes that inherit from `BaseConfig`
   - Support both sync and async operations
   - Handle streaming responses appropriately
   - Include proper error handling with provider-specific exceptions

2. **Type Safety**: 
   - Use proper type hints throughout
   - Update type definitions in `litellm/types/`
   - Ensure compatibility with both Pydantic v1 and v2

3. **Testing**:
   - Add tests in appropriate `tests/` subdirectories
   - Include both unit tests and integration tests
   - Test provider-specific functionality thoroughly
   - Consider adding load tests for performance-critical changes

### MAKING CODE CHANGES FOR THE UI (IGNORE FOR BACKEND)

1. **Tremor is DEPRECATED, do not use Tremor components in new features/changes**
   - The only exception is the Tremor Table component and its required Tremor Table sub components.

2. **Use Common Components as much as possible**:
   - These are usually defined in the `common_components` directory
   - Use these components as much as possible and avoid building new components unless needed

3. **Testing**:
   - The codebase uses **Vitest** and **React Testing Library**
   - **Query Priority Order**: Use query methods in this order: `getByRole`, `getByLabelText`, `getByPlaceholderText`, `getByText`, `getByTestId`
   - **Always use `screen`** instead of destructuring from `render()` (e.g., use `screen.getByText()` not `getByText`)
   - **Wrap user interactions in `act()`**: Always wrap `fireEvent` calls with `act()` to ensure React state updates are properly handled
   - **Use `query` methods for absence checks**: Use `queryBy*` methods (not `getBy*`) when expecting an element to NOT be present
   - **Test names must start with "should"**: All test names should follow the pattern `it("should ...")`
   - **Mock external dependencies**: Check `setupTests.ts` for global mocks and mock child components/networking calls as needed
   - **Structure tests properly**:
     - First test should verify the component renders successfully
     - Subsequent tests should focus on functionality and user interactions
     - Use `waitFor` for async operations that aren't already awaited
   - **Avoid using `querySelector`**: Prefer React Testing Library queries over direct DOM manipulation

### IMPORTANT PATTERNS

1. **Function/Tool Calling**:
   - LiteLLM standardizes tool calling across providers
   - OpenAI format is the standard, with transformations for other providers
   - See `litellm/llms/anthropic/chat/transformation.py` for complex tool handling

2. **Streaming**:
   - All providers should support streaming where possible
   - Use consistent chunk formatting across providers
   - Handle both sync and async streaming

3. **Error Handling**:
   - Use provider-specific exception classes
   - Maintain consistent error formats across providers
   - Include proper retry logic and fallback mechanisms

4. **Configuration**:
   - Support both environment variables and programmatic configuration
   - Use `BaseConfig` classes for provider configurations
   - Allow dynamic parameter passing

## PROXY SERVER (LLM GATEWAY)

The proxy server is a critical component that provides:
- Authentication and authorization
- Rate limiting and budget management
- Load balancing across multiple models/deployments
- Observability and logging
- Admin dashboard UI
- Enterprise features

Key files:
- `litellm/proxy/proxy_server.py` - Main server implementation
- `litellm/proxy/auth/` - Authentication logic
- `litellm/proxy/management_endpoints/` - Admin API endpoints

## COPILOT FEATURE LAYER

The copilot layer provides tenant-scoped management of credit budgets, agents, marketplace, connections, and guardrails. All data lives in the `copilot.*` PostgreSQL schema (separate from Prisma) and is accessed via `CopilotDB` (asyncpg).

### Copilot Endpoints (all under `/copilot/`)
| Prefix | File | Key Operations |
|--------|------|----------------|
| `/copilot/budgets` | `alchemi/endpoints/copilot_budget_endpoints.py` | CRUD, `/summary`, `/alerts`, `/record-usage`, `/plans` |
| `/copilot/agents` | `alchemi/endpoints/copilot_agent_endpoints.py` | CRUD, `/groups`, `/groups/{id}/members` |
| `/copilot/marketplace` | `alchemi/endpoints/copilot_marketplace_endpoints.py` | CRUD, `/featured`, `/{id}/install` |
| `/copilot/connections` | `alchemi/endpoints/copilot_connection_endpoints.py` | CRUD, `/{id}/test` |
| `/copilot/guardrails` | `alchemi/endpoints/copilot_guardrails_endpoints.py` | `/config`, `/config/{type}/toggle`, `/patterns`, `/audit` |
| `/copilot/entitlements` | `alchemi/endpoints/copilot_entitlements_endpoints.py` | `GET/PUT /{account_id}` (super admin only) |

### Copilot Database (`alchemi/db/copilot_db.py`)
- `CopilotDB` class with `find_many`, `find_by_id`, `create`, `update`, `delete`, `count`, `atomic_increment`
- Auto-injects `WHERE account_id = ?` using tenant context (super admins bypass)
- Pre-built table accessors: `credit_budgets`, `budget_plans`, `agents_def`, `agent_groups`, `agent_group_members`, `marketplace_items`, `account_connections`, `guardrails_config`, `guardrails_custom_patterns`, `guardrails_audit_log`
- Pool initialized in `proxy_server.py` startup, closed on shutdown

### Integration Clients
- **alchemi-web**: `/workspaces/alchemi-web/src/lib/console_api/client.ts` -- TypeScript HTTP client (server-only, ~50 exported functions)
- **alchemi-ai**: `/workspaces/alchemi-ai/gen_ui_backend/utils/console_client.py` -- Python async httpx client (budget check, usage recording, guardrails, connections)

### Copilot UI Pages
- 4 dashboard pages under COPILOT nav group: Credit Budgets, Agents & Marketplace, Connections & Tools, Enhanced Guardrails
- React Query hooks in `ui/litellm-dashboard/src/app/(dashboard)/hooks/copilot/`
- Super admin tabs in tenant-admin: Billing Overview, Model Registry, Account Entitlements

## MCP (MODEL CONTEXT PROTOCOL) SUPPORT

LiteLLM supports MCP for agent workflows:
- MCP server integration for tool calling
- Transformation between OpenAI and MCP tool formats
- Support for external MCP servers (Zapier, Jira, Linear, etc.)
- See `litellm/experimental_mcp_client/` and `litellm/proxy/_experimental/mcp_server/`

## RUNNING SCRIPTS

Use `poetry run python script.py` to run Python scripts in the project environment (for non-test files).

## GITHUB TEMPLATES

When opening issues or pull requests, follow these templates:

### Bug Reports (`.github/ISSUE_TEMPLATE/bug_report.yml`)
- Describe what happened vs. expected behavior
- Include relevant log output
- Specify LiteLLM version
- Indicate if you're part of an ML Ops team (helps with prioritization)

### Feature Requests (`.github/ISSUE_TEMPLATE/feature_request.yml`)
- Clearly describe the feature
- Explain motivation and use case with concrete examples

### Pull Requests (`.github/pull_request_template.md`)
- Add at least 1 test in `tests/litellm/`
- Ensure `make test-unit` passes


## TESTING CONSIDERATIONS

1. **Provider Tests**: Test against real provider APIs when possible
2. **Proxy Tests**: Include authentication, rate limiting, and routing tests
3. **Performance Tests**: Load testing for high-throughput scenarios
4. **Integration Tests**: End-to-end workflows including tool calling

## DOCUMENTATION

- Keep documentation in sync with code changes
- Update provider documentation when adding new providers
- Include code examples for new features
- Update changelog and release notes

## SECURITY CONSIDERATIONS

- Handle API keys securely
- Validate all inputs, especially for proxy endpoints
- Consider rate limiting and abuse prevention
- Follow security best practices for authentication

## ENTERPRISE FEATURES

- Enterprise features live in `alchemi/` (the `enterprise/` directory has been removed)
- All enterprise features are always enabled (`premium_user = True`)
- Maintain compatibility between open-source LiteLLM base and Alchemi extensions

## COMMON PITFALLS TO AVOID

1. **Breaking Changes**: LiteLLM has many users - avoid breaking existing APIs
2. **Provider Specifics**: Each provider has unique quirks - handle them properly
3. **Rate Limits**: Respect provider rate limits in tests
4. **Memory Usage**: Be mindful of memory usage in streaming scenarios
5. **Dependencies**: Keep dependencies minimal and well-justified

## HELPFUL RESOURCES

- Main documentation: https://docs.litellm.ai/
- Provider-specific docs in `docs/my-website/docs/providers/`
- Admin UI for testing proxy features

## WHEN IN DOUBT

- Follow existing patterns in the codebase
- Check similar provider implementations
- Ensure comprehensive test coverage
- Update documentation appropriately
- Consider backward compatibility impact 