"""HTTP request/response logging middleware."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging import RequestContext, get_logger, mask_sensitive_data

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""

    def __init__(self, app: ASGIApp, exclude_paths: Optional[list[str]] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/favicon.ico"]

    async def dispatch(self, request: Request, call_next):
        # Skip logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Extract user ID from headers or auth (simplified)
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # In real app, decode JWT to get user ID
            pass

        # Start timing
        start_time = time.time()

        # Create request context
        with RequestContext(
            request_id=request_id,
            user_id=user_id,
            endpoint=f"{request.method} {request.url.path}",
        ):
            # Log request
            await self._log_request(request, request_id)

            # Process request
            try:
                response = await call_next(request)
                duration_ms = (time.time() - start_time) * 1000

                # Log response
                await self._log_response(request, response, duration_ms, request_id)

                # Add request ID to response headers
                response.headers["X-Request-ID"] = request_id

                return response

            except Exception as exc:
                duration_ms = (time.time() - start_time) * 1000
                await self._log_exception(request, exc, duration_ms, request_id)
                raise

    async def _log_request(self, request: Request, request_id: str):
        """Log incoming HTTP request."""
        try:
            # Read request body if available
            body = None
            if request.headers.get("content-type") == "application/json":
                try:
                    body_bytes = await request.body()
                    if body_bytes:
                        body = json.loads(body_bytes)
                        body = mask_sensitive_data(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body = "<binary or invalid json>"

            # Extract headers (mask sensitive ones)
            headers = dict(request.headers)
            sensitive_headers = {"authorization", "cookie", "set-cookie", "x-api-key"}
            for header in sensitive_headers:
                if header in headers:
                    headers[header] = "***MASKED***"
                if header.title() in headers:
                    headers[header.title()] = "***MASKED***"

            log_data = {
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": headers,
                "client_host": request.client.host if request.client else None,
                "client_port": request.client.port if request.client else None,
            }

            if body is not None:
                log_data["body"] = body

            logger.info(
                f"HTTP Request: {request.method} {request.url.path}", extra=log_data
            )

        except Exception as e:
            logger.warning(f"Failed to log request: {e}")

    async def _log_response(
        self, request: Request, response: Response, duration_ms: float, request_id: str
    ):
        """Log HTTP response."""
        try:
            # Extract response body if available
            body = None
            if hasattr(response, "body"):
                try:
                    # For streaming responses, we can't read the body easily
                    if hasattr(response, "body_iterator"):
                        body = "<streaming response>"
                    else:
                        body_str = (
                            response.body.decode("utf-8") if response.body else None
                        )
                        if body_str and response.headers.get(
                            "content-type", ""
                        ).startswith("application/json"):
                            body = json.loads(body_str)
                            body = mask_sensitive_data(body)
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    body = "<binary or invalid json>"

            log_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "response_size": response.headers.get("content-length"),
                "response_headers": {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"authorization", "cookie", "set-cookie"}
                },
            }

            if body is not None:
                log_data["response_body"] = body

            # Log at appropriate level
            if response.status_code >= 500:
                logger.error(
                    f"HTTP Response {response.status_code}: {request.method} {request.url.path}",
                    extra=log_data,
                )
            elif response.status_code >= 400:
                logger.warning(
                    f"HTTP Response {response.status_code}: {request.method} {request.url.path}",
                    extra=log_data,
                )
            else:
                logger.info(
                    f"HTTP Response {response.status_code}: {request.method} {request.url.path}",
                    extra=log_data,
                )

        except Exception as e:
            logger.warning(f"Failed to log response: {e}")

    async def _log_exception(
        self, request: Request, exc: Exception, duration_ms: float, request_id: str
    ):
        """Log exception during request processing."""
        logger.error(
            f"HTTP Exception: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc),
            },
            exc_info=True,
        )
