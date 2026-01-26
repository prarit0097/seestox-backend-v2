import logging
import time

from django.conf import settings
from django.db import connection

logger = logging.getLogger("perf.request")


class SlowRequestLoggingMiddleware:
    """Log slow requests with timing and basic context."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(getattr(settings, "REQUEST_SLOW_MS", 800))

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000.0

        if duration_ms >= self.threshold_ms:
            query_count = None
            query_time_ms = None
            try:
                queries = connection.queries
                if queries:
                    query_count = len(queries)
                    query_time_ms = sum(float(q.get("time", 0) or 0) for q in queries) * 1000.0
            except Exception:
                pass

            user_id = getattr(getattr(request, "user", None), "id", None)
            logger.warning(
                "slow_request method=%s path=%s status=%s ms=%.1f user_id=%s queries=%s query_ms=%s",
                request.method,
                request.path,
                getattr(response, "status_code", None),
                duration_ms,
                user_id,
                query_count,
                f"{query_time_ms:.1f}" if query_time_ms is not None else None,
            )

        return response
