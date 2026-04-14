"""Infrastructure endpoints for persistence, tasks, auth and notifications."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.app.core.auth import (
    authenticate_local_user,
    auth_status,
    begin_oauth_authorization,
    create_access_token,
    diagnose_oauth_provider,
    exchange_oauth_authorization_code,
    get_auth_policy,
    get_current_user_optional,
    list_local_users,
    list_oauth_providers,
    list_refresh_sessions,
    refresh_access_token,
    revoke_refresh_session,
    sync_env_oauth_providers,
    update_auth_policy,
    upsert_oauth_provider,
    upsert_local_user,
)
from backend.app.core.persistence import persistence_manager
from backend.app.core.rate_limit_state import rate_limiter
from backend.app.core.task_queue import task_queue_manager
from backend.app.services.notification_service import notification_service

router = APIRouter()


class TokenRequest(BaseModel):
    subject: str = "researcher"
    role: str = "researcher"
    expires_in_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)
    refresh_expires_in_seconds: int = Field(default=60 * 60 * 24 * 30, ge=3600, le=60 * 60 * 24 * 180)


class LoginRequest(BaseModel):
    subject: str
    password: str
    expires_in_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)
    refresh_expires_in_seconds: int = Field(default=60 * 60 * 24 * 30, ge=3600, le=60 * 60 * 24 * 180)


class RefreshRequest(BaseModel):
    refresh_token: str
    expires_in_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)
    refresh_expires_in_seconds: int = Field(default=60 * 60 * 24 * 30, ge=3600, le=60 * 60 * 24 * 180)


class AuthUserRequest(BaseModel):
    subject: str
    password: Optional[str] = None
    role: str = "researcher"
    display_name: str = ""
    enabled: bool = True
    scopes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuthPolicyRequest(BaseModel):
    required: bool = False


class OAuthProviderRequest(BaseModel):
    provider_id: str
    label: str = ""
    provider_type: str = "generic"
    enabled: bool = True
    client_id: str
    client_secret: Optional[str] = None
    auth_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    redirect_uri: str = ""
    frontend_origin: str = ""
    scopes: List[str] = Field(default_factory=list)
    auto_create_user: bool = True
    default_role: str = "researcher"
    default_scopes: List[str] = Field(default_factory=list)
    subject_field: str = ""
    display_name_field: str = ""
    email_field: str = ""
    extra_params: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OAuthAuthorizationRequest(BaseModel):
    frontend_origin: str = ""
    redirect_uri: str = ""


class OAuthExchangeRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str = ""
    expires_in_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)
    refresh_expires_in_seconds: int = Field(default=60 * 60 * 24 * 30, ge=3600, le=60 * 60 * 24 * 180)


class TaskRequest(BaseModel):
    name: str = "manual_task"
    payload: Dict[str, Any] = Field(default_factory=dict)
    execution_backend: str = "auto"


class RecordRequest(BaseModel):
    record_type: str = "research"
    record_key: str = "default"
    payload: Dict[str, Any] = Field(default_factory=dict)
    record_id: Optional[str] = None


class TimeSeriesRequest(BaseModel):
    series_name: str
    symbol: str
    timestamp: str
    value: Optional[float] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class PersistenceBootstrapRequest(BaseModel):
    enable_timescale_schema: bool = True


class PersistenceMigrationRequest(BaseModel):
    sqlite_path: Optional[str] = None
    dry_run: bool = True
    include_records: bool = True
    include_timeseries: bool = True
    dedupe_timeseries: bool = True
    record_limit: Optional[int] = Field(default=None, ge=1, le=100_000)
    timeseries_limit: Optional[int] = Field(default=None, ge=1, le=100_000)


class NotificationRequest(BaseModel):
    channel: str = "dry_run"
    payload: Dict[str, Any] = Field(default_factory=dict)


class NotificationChannelRequest(BaseModel):
    id: str
    type: str = "webhook"
    label: str = ""
    enabled: bool = True
    settings: Dict[str, Any] = Field(default_factory=dict)


class ConfigVersionRequest(BaseModel):
    config_type: str
    config_key: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    owner_id: str = "default"


class ConfigRestoreRequest(BaseModel):
    config_type: str
    config_key: str
    version: int = Field(..., ge=1)
    owner_id: str = "default"


class RateLimitRuleRequest(BaseModel):
    id: Optional[str] = None
    pattern: str
    requests_per_minute: int = Field(..., ge=1, le=10_000)
    burst_size: int = Field(..., ge=1, le=10_000)
    enabled: bool = True


class RateLimitUpdateRequest(BaseModel):
    default_requests_per_minute: int = Field(..., ge=1, le=10_000)
    default_burst_size: int = Field(..., ge=1, le=10_000)
    rules: List[RateLimitRuleRequest] = Field(default_factory=list)


def _config_record_type(owner_id: str, config_type: str, config_key: str) -> str:
    return f"config:{owner_id}:{config_type}:{config_key}"


def _list_config_records(owner_id: str, config_type: str, config_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    return persistence_manager.list_records(
        record_type=_config_record_type(owner_id, config_type, config_key),
        limit=limit,
    )


def _find_config_record(owner_id: str, config_type: str, config_key: str, version: int) -> Optional[Dict[str, Any]]:
    for record in _list_config_records(owner_id, config_type, config_key, limit=200):
        payload = record.get("payload") or {}
        if int(payload.get("version") or 0) == int(version):
            return record
    return None


def _diff_payloads(left: Any, right: Any, path: str = "") -> List[Dict[str, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        changes: List[Dict[str, Any]] = []
        keys = sorted(set(left.keys()) | set(right.keys()))
        for key in keys:
            child_path = f"{path}.{key}" if path else str(key)
            if key not in left:
                changes.append({"path": child_path, "change": "added", "before": None, "after": right.get(key)})
            elif key not in right:
                changes.append({"path": child_path, "change": "removed", "before": left.get(key), "after": None})
            else:
                changes.extend(_diff_payloads(left.get(key), right.get(key), child_path))
        return changes

    if isinstance(left, list) and isinstance(right, list):
        if left == right:
            return []
        return [{
            "path": path or "$",
            "change": "modified",
            "before": left,
            "after": right,
            "before_length": len(left),
            "after_length": len(right),
        }]

    if left == right:
        return []
    return [{"path": path or "$", "change": "modified", "before": left, "after": right}]


def _require_admin_or_bootstrap(user: Dict[str, Any]) -> None:
    current_auth = auth_status()
    if current_auth.get("bootstrap_required"):
        return
    if str(user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/status", summary="基础设施状态")
async def get_infrastructure_status(user: Dict[str, Any] = Depends(get_current_user_optional)):
    return {
        "user": user,
        "auth": auth_status(),
        "persistence": persistence_manager.health(),
        "task_queue": task_queue_manager.health(),
        "notifications": notification_service.status(),
        "rate_limits": rate_limiter.status(),
    }


@router.post("/auth/token", summary="签发本地研究令牌")
async def create_auth_token(request: TokenRequest):
    token = create_access_token(
        subject=request.subject,
        role=request.role,
        expires_in_seconds=request.expires_in_seconds,
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in_seconds": request.expires_in_seconds,
    }


@router.post("/auth/login", summary="本地用户密码登录")
async def login_auth_user(request: LoginRequest):
    return authenticate_local_user(
        subject=request.subject,
        password=request.password,
        expires_in_seconds=request.expires_in_seconds,
        refresh_expires_in_seconds=request.refresh_expires_in_seconds,
    )


@router.post("/auth/refresh", summary="使用 refresh token 刷新访问令牌")
async def refresh_auth_user(request: RefreshRequest):
    return refresh_access_token(
        refresh_token=request.refresh_token,
        expires_in_seconds=request.expires_in_seconds,
        refresh_expires_in_seconds=request.refresh_expires_in_seconds,
    )


@router.post("/oauth/token", summary="OAuth2 Password / Refresh Token 交换")
async def issue_oauth_token(
    grant_type: str = Form(default="password"),
    username: Optional[str] = Form(default=None),
    password: Optional[str] = Form(default=None),
    refresh_token: Optional[str] = Form(default=None),
    scope: str = Form(default=""),
):
    normalized_grant = str(grant_type or "password").strip().lower()
    if normalized_grant == "password":
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required for password grant")
        return authenticate_local_user(
            subject=username,
            password=password,
            expires_in_seconds=86400,
        )
    if normalized_grant == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token is required for refresh_token grant")
        return refresh_access_token(refresh_token=refresh_token, expires_in_seconds=86400)
    raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")


@router.get("/auth/users", summary="查看本地用户目录")
async def get_auth_users():
    return {
        "users": list_local_users(),
        "sessions": list_refresh_sessions(limit=100),
        "policy": get_auth_policy(),
        "providers": list_oauth_providers(),
    }


@router.get("/auth/oauth/providers", summary="查看 OAuth Provider 配置")
async def get_oauth_providers():
    return {
        "providers": list_oauth_providers(),
        "status": auth_status(),
    }


@router.post("/auth/oauth/providers", summary="创建或更新 OAuth Provider")
async def save_oauth_provider(request: OAuthProviderRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    _require_admin_or_bootstrap(user)
    try:
        provider = upsert_oauth_provider(
            provider_id=request.provider_id,
            label=request.label,
            provider_type=request.provider_type,
            enabled=request.enabled,
            client_id=request.client_id,
            client_secret=request.client_secret,
            auth_url=request.auth_url,
            token_url=request.token_url,
            userinfo_url=request.userinfo_url,
            redirect_uri=request.redirect_uri,
            frontend_origin=request.frontend_origin,
            scopes=request.scopes,
            auto_create_user=request.auto_create_user,
            default_role=request.default_role,
            default_scopes=request.default_scopes,
            subject_field=request.subject_field,
            display_name_field=request.display_name_field,
            email_field=request.email_field,
            extra_params=request.extra_params,
            metadata=request.metadata,
            updated_by=user.get("sub"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "saved_by": user.get("sub"),
        "provider": provider,
        "providers": list_oauth_providers(),
    }


@router.post("/auth/oauth/providers/sync-env", summary="从环境变量同步 OAuth Provider")
async def sync_oauth_providers_from_env(user: Dict[str, Any] = Depends(get_current_user_optional)):
    _require_admin_or_bootstrap(user)
    providers = sync_env_oauth_providers(updated_by=user.get("sub") or "env_sync")
    return {
        "synced_count": len(providers),
        "providers": providers,
        "status": auth_status(),
    }


@router.get("/auth/oauth/providers/{provider_id}/diagnostics", summary="诊断 OAuth Provider 配置")
async def get_oauth_provider_diagnostics(provider_id: str):
    return diagnose_oauth_provider(provider_id)


@router.post("/auth/oauth/providers/{provider_id}/authorize", summary="生成 OAuth 授权链接")
async def authorize_oauth_provider(provider_id: str, request: OAuthAuthorizationRequest, http_request: Request):
    callback_base = str(http_request.base_url).rstrip("/")
    callback_uri = request.redirect_uri or f"{callback_base}/infrastructure/auth/oauth/providers/{provider_id}/callback"
    authorization = begin_oauth_authorization(
        provider_id,
        redirect_uri=callback_uri,
        frontend_origin=request.frontend_origin or http_request.headers.get("origin") or "",
    )
    return authorization


@router.post("/auth/oauth/providers/{provider_id}/exchange", summary="交换 OAuth 授权码")
async def exchange_oauth_provider_code(provider_id: str, request: OAuthExchangeRequest, http_request: Request):
    callback_base = str(http_request.base_url).rstrip("/")
    callback_uri = request.redirect_uri or f"{callback_base}/infrastructure/auth/oauth/providers/{provider_id}/callback"
    return exchange_oauth_authorization_code(
        provider_id,
        code=request.code,
        state=request.state,
        redirect_uri=callback_uri,
        expires_in_seconds=request.expires_in_seconds,
        refresh_expires_in_seconds=request.refresh_expires_in_seconds,
    )


@router.get("/auth/oauth/providers/{provider_id}/callback", response_class=HTMLResponse, summary="OAuth 登录回调")
async def oauth_provider_callback(
    provider_id: str,
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    callback_base = str(request.base_url).rstrip("/")
    callback_uri = f"{callback_base}/infrastructure/auth/oauth/providers/{provider_id}/callback"
    target_origin = request.headers.get("origin") or "*"
    payload: Dict[str, Any]
    if error:
        payload = {"success": False, "provider_id": provider_id, "error": error}
    elif not code or not state:
        payload = {"success": False, "provider_id": provider_id, "error": "missing code/state"}
    else:
        try:
            exchanged = exchange_oauth_authorization_code(
                provider_id,
                code=code,
                state=state,
                redirect_uri=callback_uri,
            )
            target_origin = exchanged.get("frontend_origin") or target_origin
            payload = {"success": True, "provider_id": provider_id, "payload": exchanged}
        except HTTPException as exc:
            payload = {"success": False, "provider_id": provider_id, "error": exc.detail}
        except Exception as exc:
            payload = {"success": False, "provider_id": provider_id, "error": str(exc)}
    script_payload = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    script_target_origin = json.dumps(target_origin or "*", ensure_ascii=False)
    return HTMLResponse(
        content=f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><title>OAuth Callback</title></head>
  <body style="font-family: sans-serif; padding: 24px;">
    <h3>Quant Lab OAuth 回调</h3>
    <p id="status">正在把登录结果回传到主窗口…</p>
    <script>
      (function() {{
        const payload = {script_payload};
        const targetOrigin = {script_target_origin};
        try {{
          if (window.opener && typeof window.opener.postMessage === 'function') {{
            window.opener.postMessage({{ type: 'quant-oauth-callback', ...payload }}, targetOrigin || '*');
          }}
          document.getElementById('status').textContent = payload.success ? '登录完成，窗口将自动关闭。' : ('登录失败: ' + (payload.error || 'unknown error'));
        }} catch (error) {{
          document.getElementById('status').textContent = '回传结果失败: ' + String(error);
        }}
        setTimeout(function() {{ window.close(); }}, payload.success ? 800 : 2000);
      }})();
    </script>
  </body>
</html>""",
    )


@router.post("/auth/sessions/{session_id}/revoke", summary="撤销 refresh session")
async def revoke_auth_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user_optional)):
    _require_admin_or_bootstrap(user)
    session = revoke_refresh_session(session_id, revoked_by=user.get("sub") or "system")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "revoked_by": user.get("sub"),
        "session": session,
    }


@router.post("/auth/users", summary="创建或更新本地用户")
async def save_auth_user(request: AuthUserRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    _require_admin_or_bootstrap(user)
    try:
        saved = upsert_local_user(
            subject=request.subject,
            password=request.password,
            role=request.role,
            display_name=request.display_name,
            enabled=request.enabled,
            scopes=request.scopes,
            metadata=request.metadata,
            updated_by=user.get("sub"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "saved_by": user.get("sub"),
        "user": saved,
        "policy": get_auth_policy(),
    }


@router.post("/auth/policy", summary="更新认证策略")
async def save_auth_policy(request: AuthPolicyRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    _require_admin_or_bootstrap(user)
    current_auth = auth_status()
    if request.required and current_auth.get("enabled_users", 0) <= 0:
        raise HTTPException(status_code=400, detail="Enable at least one local user before requiring authentication")
    policy = update_auth_policy(required=request.required, updated_by=user.get("sub"))
    return {
        "updated_by": user.get("sub"),
        "policy": policy,
        "status": auth_status(),
    }


@router.post("/tasks", summary="提交异步任务")
async def create_task(request: TaskRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    payload = {**request.payload, "submitted_by": user.get("sub")}
    return task_queue_manager.submit(
        name=request.name,
        payload=payload,
        backend=request.execution_backend,
    )


@router.get("/tasks", summary="查看任务队列")
async def list_tasks(limit: int = Query(default=50, ge=1, le=200)):
    return {"tasks": task_queue_manager.list_tasks(limit=limit)}


@router.get("/tasks/{task_id}", summary="查看任务状态")
async def get_task(task_id: str):
    task = task_queue_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/cancel", summary="取消异步任务")
async def cancel_task(task_id: str, user: Dict[str, Any] = Depends(get_current_user_optional)):
    task = task_queue_manager.cancel(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "cancelled_by": user.get("sub"),
        "task": task,
    }


@router.post("/rate-limits", summary="更新按用户 / 按端点限流规则")
async def update_rate_limits(
    request: RateLimitUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user_optional),
):
    rate_limiter.configure_defaults(
        requests_per_minute=request.default_requests_per_minute,
        burst_size=request.default_burst_size,
    )
    configured = rate_limiter.configure_endpoint_rules([item.model_dump() for item in request.rules])
    return {
        "updated_by": user.get("sub"),
        "default_rule": {
            "requests_per_minute": request.default_requests_per_minute,
            "burst_size": request.default_burst_size,
        },
        "rules": configured,
        "status": rate_limiter.status(),
    }


@router.post("/persistence/records", summary="写入持久化记录")
async def put_record(request: RecordRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    payload = {**request.payload, "_meta": {**(request.payload.get("_meta") or {}), "updated_by": user.get("sub")}}
    return persistence_manager.put_record(
        record_type=request.record_type,
        record_key=request.record_key,
        payload=payload,
        record_id=request.record_id,
    )


@router.get("/persistence/records", summary="读取持久化记录")
async def list_records(
    record_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return {"records": persistence_manager.list_records(record_type=record_type, limit=limit)}


@router.get("/persistence/diagnostics", summary="查看数据库 / TimescaleDB 接入诊断")
async def get_persistence_diagnostics():
    return persistence_manager.persistence_diagnostics()


@router.post("/persistence/bootstrap", summary="初始化 PostgreSQL / TimescaleDB 持久化结构")
async def bootstrap_persistence(
    request: PersistenceBootstrapRequest,
    user: Dict[str, Any] = Depends(get_current_user_optional),
):
    _require_admin_or_bootstrap(user)
    try:
        result = persistence_manager.bootstrap_postgres(enable_timescale_schema=request.enable_timescale_schema)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "bootstrapped_by": user.get("sub"),
        **result,
    }


@router.get("/persistence/migration/preview", summary="预览 SQLite fallback -> PostgreSQL 迁移")
async def preview_persistence_migration(sqlite_path: Optional[str] = Query(default=None)):
    return persistence_manager.preview_sqlite_fallback_migration(sqlite_path=sqlite_path)


@router.post("/persistence/migration/run", summary="执行 SQLite fallback -> PostgreSQL 迁移")
async def run_persistence_migration(
    request: PersistenceMigrationRequest,
    user: Dict[str, Any] = Depends(get_current_user_optional),
):
    _require_admin_or_bootstrap(user)
    if not request.include_records and not request.include_timeseries:
        raise HTTPException(status_code=400, detail="At least one of include_records or include_timeseries must be true")
    result = persistence_manager.migrate_sqlite_fallback_to_postgres(
        sqlite_path=request.sqlite_path,
        dry_run=request.dry_run,
        include_records=request.include_records,
        include_timeseries=request.include_timeseries,
        dedupe_timeseries=request.dedupe_timeseries,
        record_limit=request.record_limit,
        timeseries_limit=request.timeseries_limit,
    )
    return {
        "triggered_by": user.get("sub"),
        **result,
    }


@router.post("/persistence/timeseries", summary="写入时序记录")
async def put_timeseries(request: TimeSeriesRequest):
    return persistence_manager.put_timeseries(
        series_name=request.series_name,
        symbol=request.symbol,
        timestamp=request.timestamp,
        value=request.value,
        payload=request.payload,
    )


@router.get("/persistence/timeseries", summary="读取时序记录")
async def list_timeseries(
    series_name: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return {
        "timeseries": persistence_manager.list_timeseries(
            series_name=series_name,
            symbol=symbol,
            limit=limit,
        )
    }


@router.post("/config-versions", summary="保存配置版本")
async def save_config_version(request: ConfigVersionRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    existing = _list_config_records(request.owner_id, request.config_type, request.config_key, limit=200)
    next_version = len(existing) + 1
    record_type = _config_record_type(request.owner_id, request.config_type, request.config_key)
    record_id = f"{record_type}:v{next_version}"
    return persistence_manager.put_record(
        record_type=record_type,
        record_key=f"v{next_version}",
        record_id=record_id,
        payload={
            "owner_id": request.owner_id,
            "config_type": request.config_type,
            "config_key": request.config_key,
            "version": next_version,
            "payload": request.payload,
            "created_by": user.get("sub"),
        },
    )


@router.get("/config-versions", summary="读取配置版本")
async def list_config_versions(
    config_type: str = Query(...),
    config_key: str = Query(...),
    owner_id: str = Query(default="default"),
    limit: int = Query(default=20, ge=1, le=200),
):
    record_type = _config_record_type(owner_id, config_type, config_key)
    return {"versions": persistence_manager.list_records(record_type=record_type, limit=limit)}


@router.get("/config-versions/diff", summary="对比配置版本")
async def diff_config_versions(
    config_type: str = Query(...),
    config_key: str = Query(...),
    from_version: int = Query(..., ge=1),
    to_version: int = Query(..., ge=1),
    owner_id: str = Query(default="default"),
):
    left = _find_config_record(owner_id, config_type, config_key, from_version)
    right = _find_config_record(owner_id, config_type, config_key, to_version)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Config version not found")

    left_payload = (left.get("payload") or {}).get("payload") or {}
    right_payload = (right.get("payload") or {}).get("payload") or {}
    changes = _diff_payloads(left_payload, right_payload)
    return {
        "config_type": config_type,
        "config_key": config_key,
        "owner_id": owner_id,
        "from_version": from_version,
        "to_version": to_version,
        "change_count": len(changes),
        "changes": changes,
    }


@router.post("/config-versions/restore", summary="从历史配置恢复为新版本")
async def restore_config_version(request: ConfigRestoreRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    source_record = _find_config_record(
        request.owner_id,
        request.config_type,
        request.config_key,
        request.version,
    )
    if not source_record:
        raise HTTPException(status_code=404, detail="Config version not found")

    existing = _list_config_records(request.owner_id, request.config_type, request.config_key, limit=200)
    next_version = len(existing) + 1
    record_type = _config_record_type(request.owner_id, request.config_type, request.config_key)
    record_id = f"{record_type}:v{next_version}"
    source_payload = source_record.get("payload") or {}
    return persistence_manager.put_record(
        record_type=record_type,
        record_key=f"v{next_version}",
        record_id=record_id,
        payload={
            "owner_id": request.owner_id,
            "config_type": request.config_type,
            "config_key": request.config_key,
            "version": next_version,
            "payload": source_payload.get("payload") or {},
            "created_by": user.get("sub"),
            "restored_from": request.version,
        },
    )


@router.post("/notifications/test", summary="测试通知通道")
async def test_notification(request: NotificationRequest, user: Dict[str, Any] = Depends(get_current_user_optional)):
    payload = {
        "source": "infrastructure_test",
        "title": request.payload.get("title") or "Quant notification test",
        "message": request.payload.get("message") or f"Triggered by {user.get('sub')}",
        **request.payload,
    }
    return notification_service.send(request.channel, payload)


@router.post("/notifications/channels", summary="保存通知渠道")
async def save_notification_channel(request: NotificationChannelRequest):
    try:
        return notification_service.save_channel(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/notifications/channels/{channel_id}", summary="删除通知渠道")
async def delete_notification_channel(channel_id: str):
    return notification_service.delete_channel(channel_id)
