"""Database operation logging."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger

logger = get_logger(__name__)


class DBQueryLogger:
    """Logs database queries with timing and context."""

    def __init__(self):
        self.query_count = 0
        self.total_time = 0.0

    def setup(self, engine: Engine):
        """Setup SQLAlchemy event listeners."""
        # Sync engine events
        event.listen(engine, "before_cursor_execute", self._before_cursor_execute)
        event.listen(engine, "after_cursor_execute", self._after_cursor_execute)

        # Connection events
        event.listen(engine, "connect", self._on_connect)
        event.listen(engine, "close", self._on_close)

    def _before_cursor_execute(
        self, conn, cursor, statement, parameters, context, executemany
    ):
        """Called before SQL execution."""
        conn.info.setdefault("query_start_time", []).append(time.time())

    def _after_cursor_execute(
        self, conn, cursor, statement, parameters, context, executemany
    ):
        """Called after SQL execution."""
        try:
            start_time = conn.info["query_start_time"].pop()
            duration = (time.time() - start_time) * 1000  # Convert to ms

            self.query_count += 1
            self.total_time += duration

            # Extract table name from statement (simplified)
            table_name = self._extract_table_name(statement)
            operation = self._extract_operation(statement)

            # Log slow queries
            if duration > 100:  # 100ms threshold
                logger.warning(
                    f"Slow DB query: {operation} on {table_name or 'unknown'}",
                    extra={
                        "db_operation": operation,
                        "db_table": table_name,
                        "db_duration_ms": round(duration, 2),
                        "db_statement": self._sanitize_statement(statement),
                        "db_parameters": self._sanitize_parameters(parameters),
                        "db_rowcount": cursor.rowcount
                        if hasattr(cursor, "rowcount")
                        else None,
                    },
                )
            elif duration > 10:  # 10ms threshold for info logging
                logger.info(
                    f"DB query: {operation} on {table_name or 'unknown'}",
                    extra={
                        "db_operation": operation,
                        "db_table": table_name,
                        "db_duration_ms": round(duration, 2),
                    },
                )
            else:
                logger.debug(
                    f"DB query: {operation} on {table_name or 'unknown'}",
                    extra={
                        "db_operation": operation,
                        "db_table": table_name,
                        "db_duration_ms": round(duration, 2),
                    },
                )

        except Exception as e:
            logger.debug(f"Failed to log query: {e}")

    def _on_connect(self, dbapi_connection, connection_record):
        """Called when a connection is created."""
        logger.debug("DB connection established")

    def _on_close(self, dbapi_connection, connection_record):
        """Called when a connection is closed."""
        logger.debug("DB connection closed")

    def _extract_table_name(self, statement: str) -> Optional[str]:
        """Extract table name from SQL statement (simplified)."""
        statement_lower = statement.lower().strip()

        # Common patterns
        if " from " in statement_lower:
            # SELECT ... FROM table
            parts = statement_lower.split(" from ", 1)
            if len(parts) > 1:
                table_part = parts[1].split()[0]
                # Remove schema prefix if present
                return table_part.split(".")[-1].strip('"`[]')

        elif "insert into " in statement_lower:
            # INSERT INTO table
            parts = statement_lower.split("insert into ", 1)
            if len(parts) > 1:
                table_part = parts[1].split()[0]
                return table_part.split(".")[-1].strip('"`[]')

        elif "update " in statement_lower:
            # UPDATE table
            parts = statement_lower.split("update ", 1)
            if len(parts) > 1:
                table_part = parts[1].split()[0]
                return table_part.split(".")[-1].strip('"`[]')

        elif "delete from " in statement_lower:
            # DELETE FROM table
            parts = statement_lower.split("delete from ", 1)
            if len(parts) > 1:
                table_part = parts[1].split()[0]
                return table_part.split(".")[-1].strip('"`[]')

        return None

    def _extract_operation(self, statement: str) -> str:
        """Extract operation type from SQL statement."""
        statement_lower = statement.lower().strip()

        if statement_lower.startswith("select"):
            return "SELECT"
        elif statement_lower.startswith("insert"):
            return "INSERT"
        elif statement_lower.startswith("update"):
            return "UPDATE"
        elif statement_lower.startswith("delete"):
            return "DELETE"
        elif statement_lower.startswith("create"):
            return "CREATE"
        elif statement_lower.startswith("alter"):
            return "ALTER"
        elif statement_lower.startswith("drop"):
            return "DROP"
        elif statement_lower.startswith("begin") or statement_lower.startswith(
            "start transaction"
        ):
            return "BEGIN"
        elif statement_lower.startswith("commit"):
            return "COMMIT"
        elif statement_lower.startswith("rollback"):
            return "ROLLBACK"
        else:
            return "OTHER"

    def _sanitize_statement(self, statement: str) -> str:
        """Sanitize SQL statement for logging."""
        # Truncate very long statements
        if len(statement) > 1000:
            return statement[:1000] + "..."
        return statement

    def _sanitize_parameters(self, parameters) -> Any:
        """Sanitize SQL parameters for logging."""
        if parameters is None:
            return None

        if isinstance(parameters, (list, tuple)):
            # Mask potential sensitive data in parameters
            sanitized = []
            for param in parameters:
                if isinstance(param, str) and any(
                    sensitive in param.lower()
                    for sensitive in ["password", "token", "secret", "key"]
                ):
                    sanitized.append("***MASKED***")
                elif isinstance(param, (dict, list)):
                    # Don't log complex structures
                    sanitized.append("<complex>")
                else:
                    sanitized.append(str(param)[:100])  # Truncate long values
            return sanitized

        elif isinstance(parameters, dict):
            sanitized = {}
            for key, value in parameters.items():
                key_lower = str(key).lower()
                if any(
                    sensitive in key_lower
                    for sensitive in ["password", "token", "secret", "key"]
                ):
                    sanitized[key] = "***MASKED***"
                elif isinstance(value, (dict, list)):
                    sanitized[key] = "<complex>"
                else:
                    sanitized[key] = str(value)[:100]
            return sanitized

        else:
            return str(parameters)[:100]


# Global instance
db_logger = DBQueryLogger()


@contextmanager
def session_logging_context(
    session: AsyncSession, operation: str, context: Optional[Dict[str, Any]] = None
):
    """Context manager for logging session operations."""
    start_time = time.time()

    try:
        yield session

        duration = (time.time() - start_time) * 1000

        logger.info(
            f"DB session operation: {operation}",
            extra={
                "db_operation": operation,
                "db_duration_ms": round(duration, 2),
                "db_context": context or {},
            },
        )

    except Exception as exc:
        duration = (time.time() - start_time) * 1000

        logger.error(
            f"DB session operation failed: {operation}",
            extra={
                "db_operation": operation,
                "db_duration_ms": round(duration, 2),
                "db_context": context or {},
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc),
            },
            exc_info=True,
        )
        raise
