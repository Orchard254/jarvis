import asyncio
import uuid
import datetime
import logging

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self._listeners = {}
        self._queue = asyncio.Queue()
        self._running = False

    async def publish(self, event_type: str, payload: dict, source: str, context: dict = None):
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "context": context or {}
        }
        logger.debug(f"EventBus: Publishing event {event_type} from {source}")
        await self._queue.put(event)

    def subscribe(self, event_type: str, listener_func):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener_func)
        logger.debug(f"EventBus: Listener subscribed to {event_type}")

    async def _process_events(self):
        while self._running:
            try:
                event = await self._queue.get()
                logger.debug(f"EventBus: Processing event {event['event_type']}")
                if event["event_type"] in self._listeners:
                    for listener in self._listeners[event["event_type"]]:
                        try:
                            # Run listeners concurrently as tasks
                            asyncio.create_task(listener(event))
                        except Exception as e:
                            logger.error(f"EventBus: Error in listener for {event['event_type']}: {e}")
                self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("EventBus: Event processing cancelled.")
                break
            except Exception as e:
                logger.error(f"EventBus: Error processing event: {e}")

    def start(self):
        if not self._running:
            self._running = True
            asyncio.create_task(self._process_events())
            logger.info("EventBus: Started event processing.")

    async def stop(self):
        if self._running:
            self._running = False
            await self._queue.join() # Wait for all pending events to be processed
            logger.info("EventBus: Stopped event processing.")

# Global instance for easy access, or pass explicitly via dependency injection
event_bus = EventBus()
