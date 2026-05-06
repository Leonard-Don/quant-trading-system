"""Auth helpers for API-key, JWT tokens, local users and OAuth providers."""

from __future__ import annotations

from ._crypto import (
    _b64url_decode,
    _b64url_encode,
    _hash_password,
    _hash_token,
    _verify_password,
)

from .constants import (
    ACCESS_TOKEN_TYPE,
    AUTH_OAUTH_PROVIDER_RECORD_TYPE,
    AUTH_OAUTH_STATE_RECORD_TYPE,
    AUTH_POLICY_RECORD_TYPE,
    AUTH_REFRESH_RECORD_TYPE,
    AUTH_USER_RECORD_TYPE,
    DEFAULT_AUTH_SECRET,
    ENV_OAUTH_PROVIDER_MAPPINGS,
    FALSE_ENV_VALUES,
    OAUTH_PROVIDER_PRESETS,
    PRODUCTION_ENVIRONMENTS,
    REFRESH_TOKEN_TYPE,
    TRUE_ENV_VALUES,
)

from .secrets import (
    _auth_secret,
    _env_auth_required,
    _env_bool_value,
    is_production_environment,
    is_auth_secret_production_ready,
    _env_flag,
)

from .policy import (
    _load_policy,
    get_auth_policy,
    update_auth_policy,
)

from .oauth_states import (
    _find_oauth_state_record,
    _persist_oauth_state,
    _mark_oauth_state_used,
    _backend_public_base_url,
    _frontend_public_origin,
    _pkce_challenge,
)

from .oauth_providers import (
    _oauth_provider_preset,
    _env_oauth_provider_specs,
    _find_oauth_provider_record,
    _sanitize_oauth_provider,
    list_oauth_providers,
    sync_env_oauth_providers,
    diagnose_oauth_provider,
    upsert_oauth_provider,
)

from .users import (
    _find_user_record,
    _sanitize_user,
    list_local_users,
    upsert_local_user,
    authenticate_local_user,
    _find_linked_oauth_user,
    _upsert_oauth_user,
)

from .tokens import (
    _default_access_ttl,
    _default_refresh_ttl,
    _normalize_scope_items,
    _find_refresh_session,
    _sanitize_refresh_session,
    list_refresh_sessions,
    create_access_token,
    create_refresh_token,
    verify_access_token,
    refresh_access_token,
    _persist_refresh_session,
    revoke_refresh_session,
    _issue_token_bundle,
)

from .oauth_flow import (
    begin_oauth_authorization,
    _resolve_oauth_user_identity,
    _fetch_oauth_userinfo,
    exchange_oauth_authorization_code,
)

from .runtime import (
    auth_status,
    get_current_user_optional,
    oauth2_scheme_optional,
)

__all__ = [
    "_b64url_decode",
    "_b64url_encode",
    "_hash_password",
    "_hash_token",
    "_verify_password",
    "ACCESS_TOKEN_TYPE",
    "AUTH_OAUTH_PROVIDER_RECORD_TYPE",
    "AUTH_OAUTH_STATE_RECORD_TYPE",
    "AUTH_POLICY_RECORD_TYPE",
    "AUTH_REFRESH_RECORD_TYPE",
    "AUTH_USER_RECORD_TYPE",
    "DEFAULT_AUTH_SECRET",
    "ENV_OAUTH_PROVIDER_MAPPINGS",
    "FALSE_ENV_VALUES",
    "OAUTH_PROVIDER_PRESETS",
    "PRODUCTION_ENVIRONMENTS",
    "REFRESH_TOKEN_TYPE",
    "TRUE_ENV_VALUES",
    "_auth_secret",
    "_env_auth_required",
    "_env_bool_value",
    "is_production_environment",
    "is_auth_secret_production_ready",
    "_env_flag",
    "_load_policy",
    "get_auth_policy",
    "update_auth_policy",
    "_find_oauth_state_record",
    "_persist_oauth_state",
    "_mark_oauth_state_used",
    "_backend_public_base_url",
    "_frontend_public_origin",
    "_pkce_challenge",
    "_oauth_provider_preset",
    "_env_oauth_provider_specs",
    "_find_oauth_provider_record",
    "_sanitize_oauth_provider",
    "list_oauth_providers",
    "sync_env_oauth_providers",
    "diagnose_oauth_provider",
    "upsert_oauth_provider",
    "_find_user_record",
    "_sanitize_user",
    "list_local_users",
    "upsert_local_user",
    "authenticate_local_user",
    "_find_linked_oauth_user",
    "_upsert_oauth_user",
    "_default_access_ttl",
    "_default_refresh_ttl",
    "_normalize_scope_items",
    "_find_refresh_session",
    "_sanitize_refresh_session",
    "list_refresh_sessions",
    "create_access_token",
    "create_refresh_token",
    "verify_access_token",
    "refresh_access_token",
    "_persist_refresh_session",
    "revoke_refresh_session",
    "_issue_token_bundle",
    "begin_oauth_authorization",
    "_resolve_oauth_user_identity",
    "_fetch_oauth_userinfo",
    "exchange_oauth_authorization_code",
    "auth_status",
    "get_current_user_optional",
    "oauth2_scheme_optional",
]
