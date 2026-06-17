# FEAT-016: Real-Time Multi-User Collaboration

**Status**: Draft  
**Priority**: High  
**Effort**: XL (16 days)  
**Depends on**: ARCH-001, ARCH-002  

---

## Problem Statement

The current sync mechanism uses file-based locking and JSON files, which introduces several limitations for multi-user workflows:

- **No real-time updates** — changes made by one user are not visible to others until manual refresh
- **File locking contention** — when two users attempt to edit simultaneously, one gets a lock error
- **No presence awareness** — users cannot see who else is viewing or editing the same data
- **Manual conflict resolution** — conflicts are resolved by file-last-saved-wins, risking data loss
- **No collaborative editing** — only one user can edit a schedule at a time

---

## Proposed Solution

Implement a WebSocket-based real-time synchronization system with Operational Transform (OT) for conflict-free collaborative editing. The system includes a Python asyncio WebSocket server using the `websockets` library, a client integration layer with auto-connect logic and fallback to file-based sync, and full presence awareness.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Architecture Overview                        │
└─────────────────────────────────────────────────────────────────────┘

┌──────────┐    WebSocket    ┌────────────────┐    WebSocket    ┌──────────┐
│ Client A │ ◄─────────────► │                │ ◄─────────────► │ Client B │
│ (User 1) │                 │  Sync Server   │                 │ (User 2) │
└──────────┘                 │  (asyncio)     │                 └──────────┘
                             │                │
┌──────────┐    WebSocket    │  OT Engine     │    WebSocket    ┌──────────┐
│ Client C │ ◄─────────────► │                │ ◄─────────────► │ Client D │
│ (User 3) │                 │  State Store   │                 │ (User 4) │
└──────────┘                 └────────────────┘                 └──────────┘
                                     │
                                     ▼
                             ┌────────────────┐
                             │  File System   │
                             │  (JSON Store)  │
                             └────────────────┘
```

### Message Protocol

All messages are JSON-encoded with the following structure:

```json
{
  "type": "<MessageType>",
  "sender_id": "<uuid>",
  "session_id": "<uuid>",
  "timestamp": "<ISO-8601>",
  "payload": { }
}
```

#### Message Types

| Type | Direction | Description | Payload |
|------|-----------|-------------|---------|
| `Join` | Client → Server | User enters a session | `{ "username": str, "session": str, "cursor_position": dict }` |
| `Leave` | Client → Server | User exits a session | `{ "reason": str }` |
| `Edit` | ↔ Bidirectional | An operation was applied | `{ "operation": OT_Op, "version": int, "unit_id": str, "field": str }` |
| `Ack` | Server → Client | Server confirms operation | `{ "version": int, "server_timestamp": str }` |
| `Conflict` | Server → Client | Concurrent edit detected | `{ "conflicting_version": int, "server_operation": OT_Op, "resolution": str }` |
| `Merge` | Server → Client | OT merge was applied | `{ "result_version": int, "merged_value": any }` |
| `Presence` | ↔ Bidirectional | User presence update | `{ "user_id": str, "cursor_pos": dict, "typing": bool, "viewing": str }` |

### Operational Transform Engine

The OT engine handles concurrent edits to text fields using a client-server OT model.

```python
# sync/ot_engine.py

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any
from uuid import uuid4


class OperationType(Enum):
    INSERT = auto()
    DELETE = auto()
    RETAIN = auto()


@dataclass
class OT_Op:
    """A single OT operation component."""
    type: OperationType
    position: int
    value: str | None = None
    count: int = 0


@dataclass
class Operation:
    """A full OT operation consisting of sequential components."""
    ops: list[OT_Op]
    
    def apply(self, text: str) -> str:
        """Apply this operation to a text string."""
        result = []
        pos = 0
        for op in self.ops:
            if op.type == OperationType.INSERT:
                result.append(op.value)
            elif op.type == OperationType.RETAIN:
                result.append(text[pos:pos + op.count])
                pos += op.count
            elif op.type == OperationType.DELETE:
                pos += op.count
        result.append(text[pos:])
        return ''.join(result)


class OTEngine:
    """Operational Transform engine for text field merges."""
    
    def __init__(self):
        self._version = 0
        self._pending_ops: list[tuple[int, Operation]] = []
    
    def transform(self, op_a: Operation, op_b: Operation) -> tuple[Operation, Operation]:
        """Transform two concurrent operations so they commute."""
        # Standard OT transform algorithm
        result_a: list[OT_Op] = []
        result_b: list[OT_Op] = []
        i = j = 0
        
        while i < len(op_a.ops) and j < len(op_b.ops):
            op_a_comp = op_a.ops[i]
            op_b_comp = op_b.ops[j]
            
            if op_a_comp.type == OperationType.INSERT:
                result_a.append(op_a_comp)
                result_b.append(OT_Op(OperationType.RETAIN, 
                                      op_a_comp.position, 
                                      count=len(op_a_comp.value or '')))
                i += 1
                
            elif op_b_comp.type == OperationType.INSERT:
                result_b.append(op_b_comp)
                result_a.append(OT_Op(OperationType.RETAIN,
                                      op_b_comp.position,
                                      count=len(op_b_comp.value or '')))
                j += 1
                
            elif op_a_comp.type == OperationType.RETAIN and op_b_comp.type == OperationType.RETAIN:
                common = min(op_a_comp.count, op_b_comp.count)
                result_a.append(OT_Op(OperationType.RETAIN, op_a_comp.position, count=common))
                result_b.append(OT_Op(OperationType.RETAIN, op_b_comp.position, count=common))
                op_a_comp.count -= common
                op_b_comp.count -= common
                if op_a_comp.count == 0: i += 1
                if op_b_comp.count == 0: j += 1
                
            elif op_a_comp.type == OperationType.DELETE and op_b_comp.type == OperationType.DELETE:
                common = min(op_a_comp.count, op_b_comp.count)
                op_a_comp.count -= common
                op_b_comp.count -= common
                if op_a_comp.count == 0: i += 1
                if op_b_comp.count == 0: j += 1
                
            # Additional composition cases omitted for brevity,
            # see references for full OT transform matrix
        
        return (Operation(result_a + op_a.ops[i:]),
                Operation(result_b + op_b.ops[j:]))
    
    def apply_local(self, operation: Operation, current_text: str) -> tuple[str, int]:
        """Apply a local operation, assign version, and return new text."""
        self._version += 1
        new_text = operation.apply(current_text)
        self._pending_ops.append((self._version, operation))
        return new_text, self._version
    
    def apply_remote(self, operation: Operation, 
                     current_text: str, 
                     remote_version: int) -> str:
        """Apply a remote operation, transforming against pending local ops."""
        transformed_op = operation
        for v, local_op in self._pending_ops:
            if v > remote_version:
                _, transformed_op = self.transform(local_op, transformed_op)
        self._version += 1
        new_text = transformed_op.apply(current_text)
        return new_text
```

### WebSocket Server

```python
# sync/ws_server.py

import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets
from websockets.server import WebSocketServerProtocol


logger = logging.getLogger(__name__)


class SyncServer:
    """Asyncio WebSocket server for real-time collaboration."""
    
    def __init__(self, host: str = 'localhost', port: int = 8765):
        self._host = host
        self._port = port
        self._sessions: dict[str, set[WebSocketServerProtocol]] = {}
        self._user_map: dict[WebSocketServerProtocol, dict] = {}
        self._ot_engines: dict[str, 'OTEngine'] = {}
    
    async def start(self):
        """Start the WebSocket server."""
        async with websockets.serve(self._handle_connection, 
                                     self._host, self._port):
            logger.info(f"Sync server started on ws://{self._host}:{self._port}")
            await asyncio.Future()  # run forever
    
    async def _handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle a new WebSocket connection."""
        try:
            async for raw_message in websocket:
                message = json.loads(raw_message)
                handler = self._get_handler(message['type'])
                if handler:
                    await handler(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            await self._handle_disconnect(websocket)
    
    async def _handle_join(self, websocket: WebSocketServerProtocol, 
                           message: dict):
        """Handle a Join message."""
        session = message['payload']['session']
        if session not in self._sessions:
            self._sessions[session] = set()
            self._ot_engines[session] = OTEngine()
        
        self._sessions[session].add(websocket)
        self._user_map[websocket] = {
            'user_id': message['sender_id'],
            'username': message['payload']['username'],
            'session': session,
        }
        
        # Broadcast presence to all in session
        await self._broadcast(session, {
            'type': 'Presence',
            'payload': {
                'users': self._get_session_users(session),
                'joined': message['payload']['username'],
            }
        })
    
    async def _handle_edit(self, websocket: WebSocketServerProtocol, 
                           message: dict):
        """Handle an Edit message with OT transformation."""
        session = self._user_map.get(websocket, {}).get('session')
        if not session:
            return
        
        operation = Operation.deserialize(message['payload']['operation'])
        unit_id = message['payload']['unit_id']
        version = message['payload']['version']
        
        engine = self._ot_engines.get(session)
        if not engine:
            return
        
        # Transform and apply
        # (OT logic integrated with session state)
        ack = {
            'type': 'Ack',
            'sender_id': 'server',
            'session_id': session,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': {
                'version': engine.version,
                'server_timestamp': datetime.now(timezone.utc).isoformat(),
            }
        }
        await websocket.send(json.dumps(ack))
        
        # Broadcast transformed operation to other clients
        await self._broadcast(session, message, exclude=websocket)
    
    async def _broadcast(self, session: str, message: dict, 
                         exclude: WebSocketServerProtocol | None = None):
        """Send a message to all clients in a session."""
        if session not in self._sessions:
            return
        dead = set()
        for client in self._sessions[session]:
            if client == exclude:
                continue
            try:
                await client.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                dead.add(client)
        self._sessions[session] -= dead
    
    def _get_session_users(self, session: str) -> list[dict]:
        """Get list of active users in a session."""
        users = []
        for ws, info in self._user_map.items():
            if info.get('session') == session:
                users.append({
                    'user_id': info['user_id'],
                    'username': info['username'],
                })
        return users
    
    async def _handle_disconnect(self, websocket: WebSocketServerProtocol):
        """Clean up on disconnect."""
        info = self._user_map.pop(websocket, None)
        if info:
            session = info['session']
            if session in self._sessions:
                self._sessions[session].discard(websocket)
                await self._broadcast(session, {
                    'type': 'Leave',
                    'sender_id': info['user_id'],
                    'session_id': session,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'payload': {'reason': 'disconnected'},
                })
    
    def _get_handler(self, msg_type: str):
        handlers = {
            'Join': self._handle_join,
            'Leave': self._handle_disconnect,
            'Edit': self._handle_edit,
        }
        return handlers.get(msg_type)
```

### Client Integration

```python
# sync/client.py

import asyncio
import json
import logging
from typing import Callable

import websockets


logger = logging.getLogger(__name__)


class SyncClient:
    """Client-side sync manager with auto-connect and fallback."""
    
    def __init__(self, server_url: str = 'ws://localhost:8765',
                 auto_connect: bool = True,
                 fallback_to_file_sync: bool = True):
        self._server_url = server_url
        self._websocket: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._fallback_to_file_sync = fallback_to_file_sync
        self._listeners: dict[str, list[Callable]] = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._session_id: str | None = None
        self._user_id: str | None = None
        
        if auto_connect:
            asyncio.create_task(self._connect())
    
    async def _connect(self):
        """Connect to the sync server."""
        try:
            self._websocket = await websockets.connect(self._server_url)
            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to sync server at {self._server_url}")
            asyncio.create_task(self._listen())
            # Send Join message
            await self._send({
                'type': 'Join',
                'payload': {
                    'username': self._user_id or 'anonymous',
                    'session': self._session_id or 'default',
                    'cursor_position': {},
                }
            })
        except (ConnectionRefusedError, OSError) as e:
            logger.warning(f"Failed to connect to sync server: {e}")
            if self._fallback_to_file_sync:
                logger.info("Falling back to file-based sync")
            self._schedule_reconnect()
    
    async def _reconnect(self):
        """Attempt to reconnect to the server."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnect attempts reached, staying in fallback mode")
            return
        self._reconnect_attempts += 1
        await asyncio.sleep(min(2 ** self._reconnect_attempts, 30))
        await self._connect()
    
    def _schedule_reconnect(self):
        """Schedule a reconnect attempt."""
        asyncio.create_task(self._reconnect())
    
    async def _listen(self):
        """Listen for incoming messages from the server."""
        try:
            async for raw_message in self._websocket:
                message = json.loads(raw_message)
                msg_type = message['type']
                if msg_type in self._listeners:
                    for callback in self._listeners[msg_type]:
                        await callback(message)
                # Fire wildcard listener
                for callback in self._listeners.get('*', []):
                    await callback(message)
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            logger.warning("Connection to sync server closed")
            self._schedule_reconnect()
    
    async def _send(self, message: dict):
        """Send a message to the server."""
        if not self._connected or not self._websocket:
            logger.warning("Cannot send message: not connected")
            return
        message['sender_id'] = self._user_id
        message['session_id'] = self._session_id
        message['timestamp'] = __import__('datetime').datetime.now(
            __import__('datetime').timezone.utc
        ).isoformat()
        await self._websocket.send(json.dumps(message))
    
    def on(self, msg_type: str, callback: Callable):
        """Register a listener for a message type."""
        if msg_type not in self._listeners:
            self._listeners[msg_type] = []
        self._listeners[msg_type].append(callback)
    
    async def send_edit(self, operation: dict, unit_id: str, version: int):
        """Send an edit operation."""
        await self._send({
            'type': 'Edit',
            'payload': {
                'operation': operation,
                'unit_id': unit_id,
                'version': version,
            }
        })
    
    async def send_presence(self, cursor_pos: dict | None = None,
                             typing: bool = False,
                             viewing: str | None = None):
        """Send a presence update."""
        await self._send({
            'type': 'Presence',
            'payload': {
                'cursor_pos': cursor_pos or {},
                'typing': typing,
                'viewing': viewing or '',
            }
        })
    
    async def disconnect(self):
        """Disconnect from the server."""
        if self._websocket:
            await self._send({'type': 'Leave', 'payload': {'reason': 'user_disconnect'}})
            await self._websocket.close()
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
```

### Presence Awareness

```
┌─────────────────────────────────────────────────────┐
│              Presence Awareness System              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐     ┌──────────────┐              │
│  │  User: Alice  │     │  User: Bob   │             │
│  │  ─────────── │     │  ─────────── │              │
│  │  📝 Typing... │     │  👁 Viewing: │              │
│  │  Cursor: L42 │     │  Unit COM-  │              │
│  │              │     │  14230       │              │
│  └──────────────┘     └──────────────┘              │
│                                                     │
│  ┌──────────────┐     ┌──────────────┐              │
│  │  User: Carol  │     │  User: Dave  │              │
│  │  ─────────── │     │  ─────────── │              │
│  │  ✏️ Editing    │     │  📖 Browsing │              │
│  │  Field: Notes │     │  View: List  │              │
│  └──────────────┘     └──────────────┘              │
└─────────────────────────────────────────────────────┘
```

### Conflict Resolution UI

When a conflict is detected, the UI shows both versions and offers resolution options:

```python
# gui/conflict_resolver.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QTextEdit, QPushButton, QLabel, QSplitter)


class ConflictResolverDialog(QDialog):
    """Dialog for resolving edit conflicts."""
    
    def __init__(self, unit_id: str, field: str,
                 local_version: str, remote_version: str,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Conflict: {unit_id} — {field}")
        self.setMinimumSize(600, 400)
        
        self._resolution = None  # 'local', 'remote', 'merged'
        self._merged_text = None
        
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel(
            f"<b>Conflict detected</b> in <code>{unit_id}</code>, "
            f"field <code>{field}</code>. "
            f"Choose which version to keep or merge manually."
        )
        header.setWordWrap(True)
        layout.addWidget(header)
        
        # Split view
        splitter = QSplitter()
        
        local_widget = QTextEdit()
        local_widget.setPlainText(local_version)
        local_widget.setStyleSheet("background-color: #f0fff0;")
        splitter.addWidget(local_widget)
        
        merged_widget = QTextEdit()
        merged_widget.setPlainText("")
        splitter.addWidget(merged_widget)
        
        remote_widget = QTextEdit()
        remote_widget.setPlainText(remote_version)
        remote_widget.setStyleSheet("background-color: #fff0f0;")
        splitter.addWidget(remote_widget)
        
        layout.addWidget(splitter)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        keep_local = QPushButton("Keep Local Version")
        keep_local.clicked.connect(lambda: self._resolve('local'))
        btn_layout.addWidget(keep_local)
        
        auto_merge = QPushButton("Auto-Merge")
        auto_merge.clicked.connect(lambda: self._resolve('auto_merge'))
        btn_layout.addWidget(auto_merge)
        
        keep_remote = QPushButton("Keep Remote Version")
        keep_remote.clicked.connect(lambda: self._resolve('remote'))
        btn_layout.addWidget(keep_remote)
        
        layout.addLayout(btn_layout)
    
    def _resolve(self, resolution: str):
        self._resolution = resolution
        self.accept()
    
    def get_result(self) -> dict:
        return {
            'resolution': self._resolution,
            'merged_text': self._merged_text,
        }
```

---

## Implementation Phases

### Phase 1: WebSocket Server (5 days)
1. Implement `SyncServer` with asyncio + websockets library
2. Implement message protocol: Join, Leave, Edit, Ack, Conflict, Merge, Presence
3. Implement session management with user tracking
4. Implement basic broadcasting and message routing
5. **Tests**: Test server with 10 concurrent clients, verify message delivery

### Phase 2: OT Engine (4 days)
1. Implement `OTEngine` with core transform algorithm
2. Implement operation composition and decomposition for text fields
3. Implement version tracking and pending operation buffer
4. Wire OT engine into the sync server for Edit handling
5. **Tests**: Property-based tests for OT invariants (convergence, commutativity)

### Phase 3: Client Integration (4 days)
1. Implement `SyncClient` with auto-connect and reconnection logic
2. Implement presence awareness (typing indicators, cursor position)
3. Implement ConflictResolverDialog UI
4. Wire SyncClient into existing data editing workflows
5. Implement fallback to file-based sync when server is unavailable
6. **Tests**: Integration tests simulating network disconnection/reconnection

### Phase 4: Production Hardening (3 days)
1. Add authentication and session authorization
2. Add rate limiting and message size limits
3. Add server health monitoring and metrics
4. Add persistent state store (Redis or SQLite-backed sessions)
5. Document deployment guide for production environments
6. **Tests**: Load test with 100+ concurrent clients

---

## Success Criteria

1. Two users editing the same field simultaneously both see their changes merged correctly
2. OT convergence: all clients converge to the same state after any sequence of operations
3. Presence indicators update within 500ms of user action
4. Conflict resolver appears with both versions visible when auto-merge cannot resolve
5. Client gracefully falls back to file-based sync when server is unreachable
6. Server handles 50+ concurrent clients without significant latency (>200ms)
7. Reconnection automatically restores session state within 30 seconds

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| OT algorithm complexity leads to edge cases | Medium | Use property-based testing; reference established OT implementations |
| Network latency causes poor UX | Medium | Optimistic local updates with background sync; show sync status indicator |
| Server becomes single point of failure | Medium | Client fallback to file-based sync; server health monitoring |
| Security: unauthorized session access | Low | Add authentication tokens on Join message |
| Data race on initial sync | Low | Server-authoritative version numbering; reject stale operations |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: WebSocket Server | 5 |
| Phase 2: OT Engine | 4 |
| Phase 3: Client Integration | 4 |
| Phase 4: Production Hardening | 3 |
| **Total** | **16** |
