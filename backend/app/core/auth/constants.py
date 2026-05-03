"""Shared constants for auth helpers."""

from __future__ import annotations

from typing import Any


AUTH_USER_RECORD_TYPE = "auth_user"

AUTH_POLICY_RECORD_TYPE = "auth_policy"

AUTH_REFRESH_RECORD_TYPE = "auth_refresh_session"

AUTH_OAUTH_PROVIDER_RECORD_TYPE = "auth_oauth_provider"

AUTH_OAUTH_STATE_RECORD_TYPE = "auth_oauth_state"

ACCESS_TOKEN_TYPE = "access"

REFRESH_TOKEN_TYPE = "refresh"

DEFAULT_AUTH_SECRET = "dev-only-change-me"

PRODUCTION_ENVIRONMENTS = {"production", "prod"}

TRUE_ENV_VALUES = {"1", "true", "yes", "on", "enabled"}

FALSE_ENV_VALUES = {"0", "false", "no", "off", "disabled"}

OAUTH_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "email_url": "https://api.github.com/user/emails",
        "scopes": ["read:user", "user:email"],
        "subject_field": "login",
        "display_name_field": "name",
        "email_field": "email",
    },
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": ["openid", "email", "profile"],
        "subject_field": "sub",
        "display_name_field": "name",
        "email_field": "email",
    },
}

ENV_OAUTH_PROVIDER_MAPPINGS: dict[str, dict[str, Any]] = {
    "github": {
        "provider_id": "github",
        "provider_type": "github",
        "label": "GitHub",
        "client_id_env": "GITHUB_OAUTH_CLIENT_ID",
        "client_secret_env": "GITHUB_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "GITHUB_OAUTH_REDIRECT_URI",
        "frontend_origin_env": "GITHUB_OAUTH_FRONTEND_ORIGIN",
        "scopes_env": "GITHUB_OAUTH_SCOPES",
        "default_scopes_env": "GITHUB_OAUTH_DEFAULT_SCOPES",
        "default_role_env": "GITHUB_OAUTH_DEFAULT_ROLE",
        "auto_create_user_env": "GITHUB_OAUTH_AUTO_CREATE_USER",
        "enabled_env": "GITHUB_OAUTH_ENABLED",
    },
    "google": {
        "provider_id": "google",
        "provider_type": "google",
        "label": "Google",
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "GOOGLE_OAUTH_REDIRECT_URI",
        "frontend_origin_env": "GOOGLE_OAUTH_FRONTEND_ORIGIN",
        "scopes_env": "GOOGLE_OAUTH_SCOPES",
        "default_scopes_env": "GOOGLE_OAUTH_DEFAULT_SCOPES",
        "default_role_env": "GOOGLE_OAUTH_DEFAULT_ROLE",
        "auto_create_user_env": "GOOGLE_OAUTH_AUTO_CREATE_USER",
        "enabled_env": "GOOGLE_OAUTH_ENABLED",
    },
}
