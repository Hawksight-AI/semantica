"""
Provenance Storage Backends

This module provides storage backends for provenance tracking, including
in-memory and persistent SQLite storage with W3C PROV-O compliance.

Storage Backends:
    - InMemoryStorage: Fast in-memory storage for development/testing
    - SQLiteStorage: Persistent SQLite storage for production use

Features:
    - W3C PROV-O compliant schema
    - Lineage tracing with BFS traversal
    - Efficient entity retrieval
    - Type-based filtering
    - Integrity verification support

Author: Semantica Contributors
License: MIT
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import sqlite3
import json
from collections import deque
from contextlib import contextmanager

from .schemas import ProvenanceEntry
from ..utils.logging import get_logger


class ProvenanceStorage(ABC):
    """
    Abstract storage interface for provenance tracking.
    
    All storage backends must implement these methods to ensure
    consistent provenance tracking across different storage types.
    """
    
    @abstractmethod
    def store(self, entry: ProvenanceEntry) -> None:
        """
        Store a provenance entry.
        
        Args:
            entry: ProvenanceEntry to store
        """
        pass
    
    @abstractmethod
    def retrieve(self, entity_id: str) -> Optional[ProvenanceEntry]:
        """
        Retrieve a provenance entry by entity ID.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            ProvenanceEntry if found, None otherwise
        """
        pass
    
    @abstractmethod
    def retrieve_all(self, entity_type: Optional[str] = None) -> List[ProvenanceEntry]:
        """
        Retrieve all provenance entries, optionally filtered by type.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of ProvenanceEntry objects
        """
        pass
    
    @abstractmethod
    def trace_lineage(self, entity_id: str, max_depth: Optional[int] = None) -> List[ProvenanceEntry]:
        """
        Trace complete lineage for an entity.
        
        Note:
            Custom storage backends implementing only trace_lineage(self, entity_id)
            remain backward compatible; ProvenanceManager automatically preserves
            one-argument invocations when max_depth is omitted or unsupported.
        
        Args:
            entity_id: Entity identifier
            max_depth: Optional maximum BFS depth (default: None)
            
        Returns:
            List of ProvenanceEntry objects in lineage chain
        """
        pass
    
    @abstractmethod
    def clear(self) -> int:
        """
        Clear all provenance data.
        
        Returns:
            Number of entries cleared
        """
        pass
    
    @contextmanager
    def transaction(self):
        """Default transaction context manager for storage backends."""
        yield None

    def _store_with_conn(self, conn: Any, entry: ProvenanceEntry) -> None:
        """Internal store method using an active connection/transaction."""
        self.store(entry)

    def _retrieve_with_conn(self, conn: Any, entity_id: str) -> Optional[ProvenanceEntry]:
        """Internal retrieve method using an active connection/transaction."""
        return self.retrieve(entity_id)


class InMemoryStorage(ProvenanceStorage):
    """
    Fast in-memory storage for provenance tracking.
    
    Suitable for:
        - Development and testing
        - Short-lived processes
        - Small to medium datasets
        - When persistence is not required
    
    Features:
        - O(1) entity retrieval
        - BFS lineage tracing
        - Type-based filtering
        - No external dependencies
    
    Example:
        >>> storage = InMemoryStorage()
        >>> storage.store(entry)
        >>> lineage = storage.trace_lineage("entity_123")
    """
    
    def __init__(self):
        """Initialize in-memory storage."""
        self._entries: Dict[str, ProvenanceEntry] = {}
    
    def store(self, entry: ProvenanceEntry) -> None:
        """
        Store a provenance entry in memory.
        
        Args:
            entry: ProvenanceEntry to store
        """
        self._entries[entry.entity_id] = entry
    
    def retrieve(self, entity_id: str) -> Optional[ProvenanceEntry]:
        """
        Retrieve a provenance entry by entity ID.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            ProvenanceEntry if found, None otherwise
        """
        return self._entries.get(entity_id)
    
    def retrieve_all(self, entity_type: Optional[str] = None) -> List[ProvenanceEntry]:
        """
        Retrieve all provenance entries, optionally filtered by type.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of ProvenanceEntry objects
        """
        if entity_type:
            return [
                entry for entry in self._entries.values()
                if entry.entity_type == entity_type
            ]
        return list(self._entries.values())
    
    def trace_lineage(self, entity_id: str, max_depth: Optional[int] = None) -> List[ProvenanceEntry]:
        """
        Trace complete lineage using BFS traversal.
        
        Traces both parent entities (wasDerivedFrom) and used entities
        to build complete provenance chain.
        
        Args:
            entity_id: Entity identifier
            max_depth: Optional maximum BFS depth
            
        Returns:
            List of ProvenanceEntry objects in lineage chain
        """
        lineage = []
        visited = set()
        queue = deque([(entity_id, 0)])
        
        while queue:
            current_id, depth = queue.popleft()
            
            if current_id in visited or (max_depth is not None and depth >= max_depth):
                continue
            
            visited.add(current_id)
            entry = self.retrieve(current_id)
            
            if entry:
                lineage.append(entry)
                
                # Add parent entity to queue
                if entry.parent_entity_id:
                    queue.append((entry.parent_entity_id, depth + 1))
                
                # Add used entities to queue
                for used_id in entry.used_entities:
                    if used_id not in visited:
                        queue.append((used_id, depth + 1))
        
        return lineage
    
    def clear(self) -> int:
        """
        Clear all provenance data.
        
        Returns:
            Number of entries cleared
        """
        count = len(self._entries)
        self._entries.clear()
        return count

    @contextmanager
    def transaction(self):
        """In-memory transaction context manager."""
        yield None

    def _store_with_conn(self, conn: Any, entry: ProvenanceEntry) -> None:
        """Internal store method using an active connection/transaction."""
        self.store(entry)

    def _retrieve_with_conn(self, conn: Any, entity_id: str) -> Optional[ProvenanceEntry]:
        """Internal retrieve method using an active connection/transaction."""
        return self.retrieve(entity_id)


class SQLiteStorage(ProvenanceStorage):
    """
    Persistent SQLite storage for provenance tracking.
    
    Suitable for:
        - Production use
        - Long-term provenance tracking
        - Large datasets
        - Audit trail requirements
        - Regulatory compliance
    
    Features:
        - W3C PROV-O compliant schema
        - Persistent storage
        - Efficient indexing
        - Transaction support
        - Integrity verification
    
    Example:
        >>> storage = SQLiteStorage("provenance.db")
        >>> storage.store(entry)
        >>> lineage = storage.trace_lineage("entity_123")
    """
    
    def __init__(self, db_path: str = "provenance.db"):
        """
        Initialize SQLite storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.logger = get_logger("sqlite_storage")
        self._init_db()

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """
        Configure SQLite connection PRAGMAs.
        
        Architectural Decision (#807):
        We do NOT hold a persistent self._conn across calls like SQLiteVecStore does.
        Holding an open file handle across public method calls breaks Windows tests
        that call os.unlink(db_path) immediately after their last SQLiteStorage or
        ProvenanceManager call without calling .close() first (confirmed: none of
        them call .close() today). Instead: we scope one connection to the full
        duration of each PUBLIC method call (not per internal SQL statement), so
        multiple internal operations within one public call share a transaction,
        but the connection always closes before that public method returns —
        preserving exact current Windows-unlink safety while still fixing atomicity
        and connection churn within each call.
        
        PRAGMA busy_timeout is set to 5000ms (5 seconds) to prevent 'database is
        locked' OperationalErrors during concurrent process/thread access by
        instructing SQLite's default busy handler to retry for up to 5 seconds.
        """
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as e:
            self.logger.warning(
                f"WAL journal mode not supported ({e}), falling back to DELETE journal mode."
            )
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
            except Exception:
                pass

        try:
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.OperationalError as e:
            self.logger.warning(f"busy_timeout PRAGMA not supported ({e})")

        try:
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError as e:
            self.logger.warning(f"synchronous PRAGMA not supported ({e})")

    @contextmanager
    def transaction(self):
        """
        Context manager providing an active SQLite connection within a transaction.
        
        Starts an IMMEDIATE write transaction (BEGIN IMMEDIATE) so read-modify-write
        sequences are serialized across concurrent connections.
        Commits on normal exit, rolls back on exception, and always closes the connection.
        Configures PRAGMAs (WAL, busy_timeout=5000, synchronous=NORMAL).
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._configure_connection(conn)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _read_connection(self):
        """
        Context manager providing a configured SQLite connection for read-only
        operations, without taking SQLite's writer lock.

        `transaction()` uses BEGIN IMMEDIATE, which acquires the single RESERVED
        (writer) lock so read-modify-write sequences serialize correctly. That
        lock is unnecessary for plain reads (retrieve, trace_lineage) and, if
        used there, would serialize every read behind every other read/write —
        defeating WAL's readers-don't-block-writers concurrency. Reads use a
        connection with no explicit BEGIN instead.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._configure_connection(conn)
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables with W3C PROV-O compliant schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            self._configure_connection(conn)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS provenance (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    activity_id TEXT NOT NULL,
                    agent_id TEXT DEFAULT 'semantica',
                    source_document TEXT,
                    source_location TEXT,
                    source_quote TEXT,
                    timestamp TEXT NOT NULL,
                    first_seen TEXT,
                    last_updated TEXT,
                    confidence REAL DEFAULT 1.0,
                    checksum TEXT,
                    parent_entity_id TEXT,
                    used_entities TEXT,
                    start_index INTEGER,
                    end_index INTEGER,
                    credibility REAL,
                    metadata TEXT,
                    version TEXT DEFAULT '1.0'
                )
            """)
            
            # Create indexes for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_type 
                ON provenance(entity_type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_document 
                ON provenance(source_document)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_parent_entity 
                ON provenance(parent_entity_id)
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def store(self, entry: ProvenanceEntry) -> None:
        """
        Store a provenance entry in SQLite database.
        
        Args:
            entry: ProvenanceEntry to store
        """
        with self.transaction() as conn:
            self._store_with_conn(conn, entry)

    def _store_with_conn(self, conn: sqlite3.Connection, entry: ProvenanceEntry) -> None:
        """Internal store method using an active connection/transaction."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO provenance VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            entry.entity_id,
            entry.entity_type,
            entry.activity_id,
            entry.agent_id,
            entry.source_document,
            entry.source_location,
            entry.source_quote,
            entry.timestamp,
            entry.first_seen,
            entry.last_updated,
            entry.confidence,
            entry.checksum,
            entry.parent_entity_id,
            json.dumps(entry.used_entities),
            entry.start_index,
            entry.end_index,
            entry.credibility,
            json.dumps(entry.metadata),
            entry.version
        ))
    
    def retrieve(self, entity_id: str) -> Optional[ProvenanceEntry]:
        """
        Retrieve a provenance entry by entity ID.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            ProvenanceEntry if found, None otherwise
        """
        with self._read_connection() as conn:
            return self._retrieve_with_conn(conn, entity_id)

    def _retrieve_with_conn(self, conn: sqlite3.Connection, entity_id: str) -> Optional[ProvenanceEntry]:
        """Internal retrieve method using an active connection/transaction."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM provenance WHERE entity_id = ?
        """, (entity_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return self._row_to_entry(row)
    
    def retrieve_all(self, entity_type: Optional[str] = None) -> List[ProvenanceEntry]:
        """
        Retrieve all provenance entries, optionally filtered by type.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of ProvenanceEntry objects
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._configure_connection(conn)
            cursor = conn.cursor()
            if entity_type:
                cursor.execute("""
                    SELECT * FROM provenance WHERE entity_type = ?
                """, (entity_type,))
            else:
                cursor.execute("SELECT * FROM provenance")
            
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        finally:
            conn.close()
    
    def trace_lineage(self, entity_id: str, max_depth: Optional[int] = None) -> List[ProvenanceEntry]:
        """
        Trace complete lineage using batched BFS traversal (#807).
        
        Fetches frontiers in batched IN (...) queries chunked by 999 variables
        to stay safely within SQLite limits, while preserving exact BFS order,
        visited tracking, and optional max_depth semantics.
        
        Args:
            entity_id: Entity identifier
            max_depth: Optional maximum BFS depth
            
        Returns:
            List of ProvenanceEntry objects in lineage chain
        """
        lineage = []
        visited = set()
        frontier = [entity_id]
        depth = 0
        
        with self._read_connection() as conn:
            cursor = conn.cursor()
            while frontier and (max_depth is None or depth < max_depth):
                # Remove duplicates while preserving order, and filter out already visited IDs
                current_frontier = [id_ for id_ in dict.fromkeys(frontier) if id_ not in visited]
                if not current_frontier:
                    break
                
                visited.update(current_frontier)
                
                # Fetch all entries in current frontier using batched IN queries chunked by 999
                entries_map = {}
                for i in range(0, len(current_frontier), 999):
                    chunk = current_frontier[i : i + 999]
                    placeholders = ",".join("?" * len(chunk))
                    cursor.execute(f"""
                        SELECT * FROM provenance WHERE entity_id IN ({placeholders})
                    """, chunk)
                    for row in cursor.fetchall():
                        entry = self._row_to_entry(row)
                        entries_map[entry.entity_id] = entry
                
                # Append entries in exact BFS order and build next frontier
                next_frontier = []
                for current_id in current_frontier:
                    entry = entries_map.get(current_id)
                    if not entry:
                        continue
                    lineage.append(entry)
                    
                    if entry.parent_entity_id and entry.parent_entity_id not in visited:
                        next_frontier.append(entry.parent_entity_id)
                    for used_id in entry.used_entities:
                        if used_id not in visited:
                            next_frontier.append(used_id)
                
                frontier = next_frontier
                depth += 1
                
        return lineage
    
    def clear(self) -> int:
        """
        Clear all provenance data.
        
        Returns:
            Number of entries cleared
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._configure_connection(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM provenance")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM provenance")
            conn.commit()
            
            return count
        finally:
            conn.close()
    
    def _row_to_entry(self, row: tuple) -> ProvenanceEntry:
        """
        Convert database row to ProvenanceEntry.
        
        Args:
            row: Database row tuple
            
        Returns:
            ProvenanceEntry object
        """
        return ProvenanceEntry(
            entity_id=row[0],
            entity_type=row[1],
            activity_id=row[2],
            agent_id=row[3],
            source_document=row[4] or "",
            source_location=row[5],
            source_quote=row[6],
            timestamp=row[7],
            first_seen=row[8],
            last_updated=row[9],
            confidence=row[10],
            checksum=row[11],
            parent_entity_id=row[12],
            used_entities=json.loads(row[13]) if row[13] else [],
            start_index=row[14],
            end_index=row[15],
            credibility=row[16],
            metadata=json.loads(row[17]) if row[17] else {},
            version=row[18]
        )
