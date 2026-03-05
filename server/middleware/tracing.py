"""Request tracing middleware — adds custom spans for auth, validation, DB, business logic."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log


class TracingMiddleware(BaseHTTPMiddleware):
    """Adds custom spans to every request for deep trace visibility.

    Produces at minimum 3 spans per request (middleware_entry, auth_check, response_finalize).
    Combined with FastAPI auto-instrumentation, route handler spans, DB spans, and
    security spans, each request generates 8+ spans.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        tracer = get_tracer()
        start = time.time()
        client_ip = request.client.host if request.client else "unknown"

        with tracer.start_as_current_span("middleware.entry") as entry_span:
            entry_span.set_attribute("http.client_ip", client_ip)
            entry_span.set_attribute("http.user_agent", request.headers.get("user-agent", ""))
            entry_span.set_attribute("http.url.path", request.url.path)
            entry_span.set_attribute("http.method", request.method)

            # Span 2: Auth context extraction
            with tracer.start_as_current_span("auth.check") as auth_span:
                auth_header = request.headers.get("authorization", "")
                session_cookie = request.cookies.get("session_id", "")
                auth_span.set_attribute("auth.has_token", bool(auth_header))
                auth_span.set_attribute("auth.has_session", bool(session_cookie))
                auth_span.set_attribute("auth.method",
                    "bearer" if auth_header.startswith("Bearer") else
                    "basic" if auth_header.startswith("Basic") else
                    "session" if session_cookie else "none"
                )

            # Span 3: Request validation
            with tracer.start_as_current_span("request.validate") as val_span:
                content_type = request.headers.get("content-type", "")
                content_length = request.headers.get("content-length", "0")
                val_span.set_attribute("request.content_type", content_type)
                val_span.set_attribute("request.content_length", content_length)

            # Call the actual route handler (generates its own spans)
            response = await call_next(request)

            # Span 4: Response finalization
            with tracer.start_as_current_span("response.finalize") as resp_span:
                duration = time.time() - start
                resp_span.set_attribute("http.status_code", response.status_code)
                resp_span.set_attribute("http.response_time_ms", round(duration * 1000, 2))

                # Log slow requests
                if duration > 2.0:
                    push_log("WARNING", "Slow request detected", **{
                        "http.url.path": request.url.path,
                        "http.response_time_ms": round(duration * 1000, 2),
                        "http.client_ip": client_ip,
                        "performance.slow_request": True,
                    })

            return response
