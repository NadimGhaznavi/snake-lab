"""Application-independent MariaDB connections, CRUD operations and transactions."""

from contextlib import contextmanager
from enum import Enum
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Mapping, Sequence

import pymysql
from pymysql.constants import CR


class DatabaseError(RuntimeError):
    """Database operation failed; the driver error is available as __cause__."""


class SqlValue(Enum):
    CURRENT_TIMESTAMP = "CURRENT_TIMESTAMP(6)"


class DbMgr:
    """Own a connection and all of its cursors; serialize transactions."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._lock = RLock()
        self._in_transaction = False
        self._closed = False

    @classmethod
    def connect(cls, *, credentials_file: str | Path, host: str, port: int,
                user: str, database: str, connect_timeout: int = 3,
                read_timeout: int = 3, write_timeout: int = 3) -> "DbMgr":
        credentials = json.loads(Path(credentials_file).read_text(encoding="utf-8"))
        password = credentials.get("password")
        if not isinstance(password, str) or not password:
            raise ValueError(f"Database password is missing from {credentials_file}")
        try:
            connection = pymysql.connect(
                host=host, port=port, user=credentials.get("user", user),
                password=password, database=credentials.get("database", database),
                charset="utf8mb4", autocommit=False,
                init_command="SET time_zone = '+00:00'",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=connect_timeout, read_timeout=read_timeout,
                write_timeout=write_timeout,
            )
        except pymysql.Error as error:
            raise DatabaseError("Could not connect to MariaDB") from error
        return cls(connection)

    @staticmethod
    def _identifier(name: str) -> str:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid SQL identifier: {name!r}")
        return f"`{name}`"

    @classmethod
    def _where(cls, conditions: Mapping[str, Any]) -> tuple[str, list[Any]]:
        clauses, parameters = [], []
        for name, value in conditions.items():
            column = cls._identifier(name)
            if value is None:
                clauses.append(f"{column} IS NULL")
            elif isinstance(value, (tuple, list)):
                if not value:
                    raise ValueError("IN conditions must contain at least one value")
                clauses.append(f"{column} IN ({', '.join(['%s'] * len(value))})")
                parameters.extend(value)
            else:
                clauses.append(f"{column} = %s")
                parameters.append(value)
        return " AND ".join(clauses), parameters

    @staticmethod
    def _value(value: Any, parameters: list[Any]) -> str:
        if isinstance(value, SqlValue):
            return value.value
        parameters.append(value)
        return "%s"

    def _begin_transaction(self, read_only: bool) -> None:
        if read_only:
            with self._connection.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
        else:
            self._connection.begin()

    @contextmanager
    def transaction(self, *, read_only: bool = False):
        """Commit one unit of work, or roll back errors propagated by its caller."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Database manager is closed")
            if self._in_transaction:
                raise RuntimeError("Nested transactions are not supported")
            self._in_transaction = True
            try:
                try:
                    self._begin_transaction(read_only)
                except (pymysql.OperationalError, pymysql.InterfaceError) as error:
                    if error.args[0] not in (0, CR.CR_SERVER_GONE_ERROR, CR.CR_SERVER_LOST):
                        raise
                    # BEGIN has not run any application statements. Reopen an
                    # expired connection once, restoring the driver's settings.
                    self._connection.connect()
                    self._begin_transaction(read_only)
                yield self
                self._connection.commit()
            except BaseException as error:
                try:
                    self._connection.rollback()
                except pymysql.Error:
                    pass  # Preserve the original failure, even if the connection died.
                if isinstance(error, pymysql.Error):
                    raise DatabaseError("MariaDB transaction failed") from error
                raise
            finally:
                self._in_transaction = False

    @contextmanager
    def _operation(self):
        with self._lock:
            if self._in_transaction:
                yield
            else:
                with self.transaction():
                    yield

    def select(self, table: str, columns: Sequence[str], *,
               where: Mapping[str, Any] | None = None, one: bool = False,
               for_update: bool = False):
        if not columns or isinstance(columns, str):
            raise ValueError("Select requires a sequence of column names")
        sql = f"SELECT {', '.join(self._identifier(c) for c in columns)} FROM {self._identifier(table)}"
        clause, parameters = self._where(where or {})
        if clause:
            sql += f" WHERE {clause}"
        if one:
            sql += " LIMIT 1"
        if for_update:
            sql += " FOR UPDATE"
        with self._lock:
            if for_update and not self._in_transaction:
                raise RuntimeError("Row locking requires an explicit transaction")
            with self._operation():
                with self._connection.cursor() as cursor:
                    cursor.execute(sql, tuple(parameters))
                    return cursor.fetchone() if one else list(cursor.fetchall())

    def sum(self, table: str, column: str, *, where: Mapping[str, Any]):
        """Return a column sum, or zero when no rows match."""
        clause, parameters = self._where(where)
        sql = (f"SELECT COALESCE(SUM({self._identifier(column)}), 0) AS total "
               f"FROM {self._identifier(table)}")
        if clause:
            sql += f" WHERE {clause}"
        with self._operation():
            with self._connection.cursor() as cursor:
                cursor.execute(sql, tuple(parameters))
                return cursor.fetchone()["total"]

    def insert(self, table: str, values: Mapping[str, Any]) -> int:
        """Insert a row and return the generated ID (zero if none)."""
        if not values:
            raise ValueError("Insert requires values")
        parameters: list[Any] = []
        columns = ', '.join(self._identifier(c) for c in values)
        placeholders = ', '.join(self._value(v, parameters) for v in values.values())
        sql = f"INSERT INTO {self._identifier(table)} ({columns}) VALUES ({placeholders})"
        with self._operation():
            with self._connection.cursor() as cursor:
                cursor.execute(sql, tuple(parameters))
                return cursor.lastrowid

    def update(self, table: str, values: Mapping[str, Any], *, where: Mapping[str, Any]) -> int:
        if not values or not where:
            raise ValueError("Update requires values and conditions")
        parameters: list[Any] = []
        assignments = ', '.join(f"{self._identifier(c)} = {self._value(v, parameters)}" for c, v in values.items())
        clause, conditions = self._where(where)
        with self._operation():
            with self._connection.cursor() as cursor:
                cursor.execute(f"UPDATE {self._identifier(table)} SET {assignments} WHERE {clause}",
                               tuple(parameters + conditions))
                return cursor.rowcount

    def delete(self, table: str, *, where: Mapping[str, Any]) -> int:
        if not where:
            raise ValueError("Delete requires conditions")
        clause, parameters = self._where(where)
        with self._operation():
            with self._connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {self._identifier(table)} WHERE {clause}", tuple(parameters))
                return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            if self._in_transaction:
                raise RuntimeError("Cannot close an active transaction")
            if not self._closed:
                try:
                    self._connection.close()
                except pymysql.Error as error:
                    raise DatabaseError("Could not close MariaDB connection") from error
                finally:
                    self._closed = True
