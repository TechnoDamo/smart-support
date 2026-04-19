"""Internal operations logging utilities."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from app.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def log_operation(
    operation: str, context: Optional[Dict[str, Any]] = None, level: str = "info"
):
    """Context manager for logging internal operations with timing."""
    start_time = time.time()
    context = context or {}

    try:
        # Log operation start
        getattr(logger, level)(
            f"Operation started: {operation}",
            extra={
                "operation": operation,
                "operation_phase": "start",
                **context,
            },
        )

        yield

        # Log operation completion
        duration = (time.time() - start_time) * 1000
        getattr(logger, level)(
            f"Operation completed: {operation}",
            extra={
                "operation": operation,
                "operation_phase": "complete",
                "operation_duration_ms": round(duration, 2),
                **context,
            },
        )

    except Exception as exc:
        # Log operation failure
        duration = (time.time() - start_time) * 1000
        logger.error(
            f"Operation failed: {operation}",
            extra={
                "operation": operation,
                "operation_phase": "error",
                "operation_duration_ms": round(duration, 2),
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc),
                **context,
            },
            exc_info=True,
        )
        raise


def log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
    **kwargs,
):
    """Log LLM API call."""
    logger.info(
        "LLM API call",
        extra={
            "llm_model": model,
            "llm_prompt_tokens": prompt_tokens,
            "llm_completion_tokens": completion_tokens,
            "llm_total_tokens": total_tokens,
            "llm_duration_ms": round(duration_ms, 2),
            **kwargs,
        },
    )


def log_embedding_call(model: str, input_tokens: int, duration_ms: float, **kwargs):
    """Log embedding API call."""
    logger.info(
        "Embedding API call",
        extra={
            "embedding_model": model,
            "embedding_input_tokens": input_tokens,
            "embedding_duration_ms": round(duration_ms, 2),
            **kwargs,
        },
    )


def log_rag_retrieval(
    query: str,
    document_count: int,
    chunk_count: int,
    avg_score: Optional[float],
    duration_ms: float,
    **kwargs,
):
    """Log RAG retrieval operation."""
    logger.info(
        "RAG retrieval",
        extra={
            "rag_query_length": len(query),
            "rag_document_count": document_count,
            "rag_chunk_count": chunk_count,
            "rag_avg_score": avg_score,
            "rag_duration_ms": round(duration_ms, 2),
            **kwargs,
        },
    )


def log_ticket_event(
    ticket_id: str,
    event_type: str,
    from_status: Optional[str],
    to_status: str,
    user_id: Optional[str],
    **kwargs,
):
    """Log ticket status change event."""
    logger.info(
        f"Ticket {event_type}",
        extra={
            "ticket_id": ticket_id,
            "ticket_event_type": event_type,
            "ticket_from_status": from_status,
            "ticket_to_status": to_status,
            "ticket_user_id": user_id,
            **kwargs,
        },
    )


def log_chat_event(
    chat_id: str,
    event_type: str,
    mode_from: Optional[str],
    mode_to: str,
    user_id: Optional[str],
    **kwargs,
):
    """Log chat mode change event."""
    logger.info(
        f"Chat {event_type}",
        extra={
            "chat_id": chat_id,
            "chat_event_type": event_type,
            "chat_mode_from": mode_from,
            "chat_mode_to": mode_to,
            "chat_user_id": user_id,
            **kwargs,
        },
    )


def log_message_event(
    chat_id: str,
    ticket_id: str,
    message_id: str,
    entity: str,
    message_length: int,
    **kwargs,
):
    """Log message sent event."""
    logger.info(
        "Message sent",
        extra={
            "message_chat_id": chat_id,
            "message_ticket_id": ticket_id,
            "message_id": message_id,
            "message_entity": entity,
            "message_length": message_length,
            **kwargs,
        },
    )


def log_file_upload(
    filename: str,
    file_size: int,
    file_type: str,
    upload_type: str,
    user_id: Optional[str],
    **kwargs,
):
    """Log file upload event."""
    logger.info(
        "File uploaded",
        extra={
            "file_name": filename,
            "file_size": file_size,
            "file_type": file_type,
            "upload_type": upload_type,
            "upload_user_id": user_id,
            **kwargs,
        },
    )


def log_scheduler_job(
    job_id: str, job_type: str, result: str, duration_ms: float, **kwargs
):
    """Log scheduler job execution."""
    logger.info(
        "Scheduler job executed",
        extra={
            "scheduler_job_id": job_id,
            "scheduler_job_type": job_type,
            "scheduler_result": result,
            "scheduler_duration_ms": round(duration_ms, 2),
            **kwargs,
        },
    )
