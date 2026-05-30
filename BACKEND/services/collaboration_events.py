# -*- coding: utf-8 -*-
"""
AERIS Multi-Agent Collaboration Event Bus
Enables real-time event streaming for cooperative task orchestration.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Set

logger = logging.getLogger(__name__)

class CollaborationEventBus:
    """Asyncio-based event bus for tracking multi-agent collaboration in real-time."""

    def __init__(self):
        # Maps task_id -> set of asyncio.Queue subscriptions
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    async def emit(self, task_id: str, event_type: str, data: dict):
        """Emit a collaboration event to all subscribers of a task.
        
        Args:
            task_id: The unique identifier of the task/operation.
            event_type: e.g., 'agent_start', 'agent_progress', 'agent_complete', 'info'.
            data: Arbitrary dictionary containing payload details (agent_id, progress, status, text, etc.).
        """
        payload = {
            "type": event_type,
            "task_id": task_id,
            "data": data
        }
        logger.debug(f"Emitting collaboration event for task {task_id}: {event_type}")

        if task_id in self._subscribers:
            # Create a list of queues to prevent mutation during iteration
            queues = list(self._subscribers[task_id])
            for queue in queues:
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drain one item if full to avoid blocking
                    try:
                        queue.get_nowait()
                        queue.put_nowait(payload)
                    except Exception:
                        pass

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to events for a specific task.
        
        Returns an asyncio.Queue from which events can be read.
        """
        queue = asyncio.Queue(maxsize=100)
        if task_id not in self._subscribers:
            self._subscribers[task_id] = set()
        self._subscribers[task_id].add(queue)
        logger.info(f"New subscription added for task: {task_id}")
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """Unsubscribe a specific queue from a task's events."""
        if task_id in self._subscribers:
            self._subscribers[task_id].discard(queue)
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]
            logger.info(f"Subscription removed for task: {task_id}")

    async def stream(self, task_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events for a task."""
        queue = self.subscribe(task_id)
        try:
            # Yield initial keep-alive or connection acknowledgement
            yield f"data: {json.dumps({'type': 'connected', 'task_id': task_id})}\n\n"
            
            while True:
                # Wait for next event in the queue
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Event stream for task {task_id} cancelled.")
        finally:
            self.unsubscribe(task_id, queue)

# Singleton event bus instance
collaboration_bus = CollaborationEventBus()
