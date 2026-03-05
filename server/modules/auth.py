"""Authentication module — OWASP A07: Identification and Authentication Failures.

Vulnerabilities:
- Weak password hashing (intentionally uses md5 fallback)
- No rate limiting on login endpoint
- JWT with weak secret
- Session fixation via cookie
- Username enumeration through different error messages
"""

import hashlib
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
tracer_fn = get_tracer

# In-memory session store (intentionally insecure — no server-side validation)
_sessions: dict[str, dict] = {}
_login_attempts: dict[str, list[float]] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Login endpoint — vulnerable to brute force (no rate limiting)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.username", req.username)
        span.set_attribute("auth.client_ip", client_ip)

        # Track attempts (but don't enforce — intentional vuln)
        _login_attempts.setdefault(client_ip, []).append(time.time())

        if len(_login_attempts.get(client_ip, [])) > cfg.max_login_attempts:
            with security_span("broken_auth", severity="high",
                             payload=f"brute force: {len(_login_attempts[client_ip])} attempts",
                             source_ip=client_ip, username=req.username):
                log_security_event("broken_auth", "high",
                    f"Brute force detected from {client_ip}: {len(_login_attempts[client_ip])} attempts",
                    source_ip=client_ip, username=req.username)

        async with get_db() as db:
            # VULN: Username enumeration — different error messages
            with tracer.start_as_current_span("db.user_lookup") as db_span:
                result = await db.execute(
                    text("SELECT id, username, password_hash, role FROM users WHERE username = :u"),
                    {"u": req.username}
                )
                user = result.fetchone()

            if user is None:
                span.set_attribute("auth.result", "user_not_found")
                return {"error": "User not found", "status": "failed"}  # VULN: enumeration

            # VULN: Weak password check (md5 fallback)
            with tracer.start_as_current_span("auth.password_verify") as pw_span:
                md5_hash = hashlib.md5(req.password.encode()).hexdigest()
                if user.password_hash != md5_hash and not _check_bcrypt(req.password, user.password_hash):
                    span.set_attribute("auth.result", "invalid_password")
                    return {"error": "Invalid password", "status": "failed"}  # VULN: enumeration

            # Create session — VULN: predictable session ID
            session_id = hashlib.md5(f"{user.username}{time.time()}".encode()).hexdigest()
            _sessions[session_id] = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "created_at": time.time(),
            }

            # VULN: Session fixation — sets cookie without regeneration
            response.set_cookie("session_id", session_id, httponly=False, samesite="none")

            push_log("INFO", f"User {req.username} logged in", **{
                "auth.username": req.username,
                "auth.role": user.role,
                "http.client_ip": client_ip,
            })

            return {
                "status": "success",
                "session_id": session_id,  # VULN: exposing session ID in response body
                "user": {"id": user.id, "username": user.username, "role": user.role}
            }


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    """Register — vulnerable to mass assignment (role field accepted from request)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("auth.register") as span:
        body = await request.json()

        # VULN: Mass assignment — accepts 'role' from user input
        role = body.get("role", "user")
        if role == "admin":
            with security_span("mass_assignment", severity="critical",
                             payload=f"role escalation attempt: {role}",
                             source_ip=client_ip, username=req.username):
                log_security_event("mass_assignment", "critical",
                    f"Admin role assignment attempt by {req.username}",
                    source_ip=client_ip, username=req.username)

        # VULN: Weak password hashing (md5)
        password_hash = hashlib.md5(req.password.encode()).hexdigest()

        async with get_db() as db:
            with tracer.start_as_current_span("db.user_create"):
                await db.execute(
                    text("INSERT INTO users (username, email, password_hash, role) VALUES (:u, :e, :p, :r)"),
                    {"u": req.username, "e": req.email, "p": password_hash, "r": role}
                )

        return {"status": "created", "username": req.username, "role": role}


@router.get("/session")
async def get_session(request: Request):
    """Return session info — VULN: no server-side session validation."""
    session_id = request.cookies.get("session_id") or request.query_params.get("session_id", "")
    session = _sessions.get(session_id)
    if not session:
        return {"authenticated": False}
    return {"authenticated": True, **session}


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id", "")
    _sessions.pop(session_id, None)
    response.delete_cookie("session_id")
    return {"status": "logged_out"}


def get_current_user(request: Request) -> dict | None:
    """Helper to extract current user from session."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id", "")
    return _sessions.get(session_id)


def _check_bcrypt(password: str, hash_str: str) -> bool:
    try:
        from passlib.hash import bcrypt
        return bcrypt.verify(password, hash_str)
    except Exception:
        return False
