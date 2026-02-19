"""PostgreSQL DB 매니저."""

from __future__ import annotations

import os
from typing import Any, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


class DBManager:
    """간단한 PostgreSQL DB 매니저."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = (dsn or os.environ.get("DATABASE_URL", "")).strip()
        if not self.dsn:
            raise RuntimeError("DATABASE_URL이 설정되지 않았습니다")

    def execute_query(self, query: str, params: Optional[tuple[Any, ...]] = None) -> List[dict]:
        """SELECT 쿼리를 실행하고 dict 리스트를 반환합니다."""
        with psycopg2.connect(self.dsn, connect_timeout=5) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        """INSERT/UPDATE/DELETE 쿼리를 실행합니다."""
        with psycopg2.connect(self.dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
