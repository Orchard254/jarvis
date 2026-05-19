# Jarvis Event Bus Integration Plan: Enabling Proactive AI

**Author:** Manus AI  
**Date:** May 19, 2026  

## 1. Introduction

This document outlines a detailed plan for integrating an event bus architecture with context-aware triggers into the Jarvis personal AI agent. The primary goal is to transition Jarvis from a predominantly reactive system to a truly proactive assistant capable of anticipating user needs and initiating actions without explicit commands. This will significantly enhance its efficiency, intelligence, and overall utility.

## 2. Phase 1: Design the Event Bus Core Architecture

An event bus will serve as the central nervous system for Jarvis's proactive capabilities, enabling decoupled communication between various components. It will facilitate the emission, propagation, and consumption of events across the system.

### 2.1 Core Principles

*   **Decoupling:** Event producers (sensors) should not need to know about event consumers (listeners/agents). This promotes modularity and scalability.
*   **Asynchronous Communication:** Events should be processed asynchronously to prevent blocking operations and ensure responsiveness.
*   **Scalability:** The architecture should support a growing number of event types and listeners without significant performance degradation.
*   **Reliability:** Critical events should be handled with mechanisms to ensure delivery and processing.

### 2.2 Key Components of the Event Bus

| Component | Description | Technologies/Considerations |
| :-------- | :---------- | :-------------------------- |
| **Event** | A data structure representing a significant occurrence within the system. It should be immutable and contain relevant data (e.g., `type`, `timestamp`, `payload`). | Python dataclasses or simple dictionaries. Standardized event schemas. |
| **Event Producer (Emitter)** | Any component that detects an occurrence and publishes an event to the bus. | Existing Jarvis modules (e.g., `perception`, `system`, `memory`, `tools`). |
| **Event Bus (Broker)** | The central mechanism responsible for receiving events from producers and dispatching them to registered consumers. | In-process (e.g., Python `queue`, `asyncio` queues, `blinker` library) for simplicity and performance. For future distributed needs, consider message brokers like RabbitMQ or Kafka. |
| **Event Consumer (Listener/Subscriber)** | Any component that registers interest in specific event types and performs actions when those events are received. | Jarvis agents (e.g., a new `ProactiveAgent`), specialized trigger modules. |
| **Event Store (Optional)** | A persistent log of all events, useful for debugging, auditing, and replaying events. | SQLite database (existing Jarvis memory system), or a dedicated log file. |

### 2.3 Event Structure

Each event should adhere to a standardized structure to ensure consistent processing across the system. A proposed structure is as follows:

```json
{
  "event_id": "uuid_v4_string",
  "timestamp": "ISO_8601_datetime_string",
  "event_type": "string_describing_the_event",
  "source": "string_identifying_the_producer_module",
  "payload": {
    "key1": "value1",
    "key2": "value2"
  },
  "context": {
    "user_id": "string",
    "session_id": "string",
    "current_app": "string"
  }
}
```

### 2.4 Implementation Considerations

For the initial implementation, an in-process event bus using Python's `asyncio` queues or a simple observer pattern would be sufficient. This minimizes external dependencies and complexity while providing the necessary decoupling. The `core/orchestrator.py` could host the event bus instance, or a new dedicated `event_bus.py` module could be introduced.

**Example (Conceptual):**

```python
# event_bus.py
import asyncio
import uuid
import datetime

class EventBus:
    def __init__(self):
        self._listeners = {}
        self._queue = asyncio.Queue()

    async def publish(self, event_type: str, payload: dict, source: str, context: dict = None):
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "context": context or {}
        }
        await self._queue.put(event)

    def subscribe(self, event_type: str, listener_func):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener_func)

    async def _process_events(self):
        while True:
            event = await self._queue.get()
            if event["event_type"] in self._listeners:
                for listener in self._listeners[event["event_type"]]:
                    # Run listeners concurrently or sequentially based on requirement
                    asyncio.create_task(listener(event))
            self._queue.task_done()

    def start(self):
        asyncio.create_task(self._process_events())

# Integration point in Jarvis (e.g., orchestrator)
# event_bus = EventBus()
# event_bus.start()
# await event_bus.publish("system_resource_alert", {"cpu_usage": 95}, "ambient_monitor")
```

This foundational design establishes the mechanism for event flow, which is crucial for building proactive capabilities. The next phase will focus on identifying and integrating various event sources (sensors) into this bus. [1] [2]

## 3. Phase 2: Define Event Sources and Listeners (Sensors)

To enable proactive behavior, Jarvis needs to perceive its environment through various "sensors" that emit events onto the event bus. These sensors will replace or augment existing polling mechanisms, providing real-time updates about system state, user activity, and external conditions.

### 3.1 Categories of Event Sources

Event sources can be broadly categorized based on their origin:

*   **System Events:** Changes in the operating system or hardware state.
*   **Application Events:** Interactions within specific applications.
*   **User Activity Events:** Direct user input or patterns of behavior.
*   **External Service Events:** Updates from integrated third-party services (e.g., email, calendar).
*   **Internal Agent Events:** Events generated by Jarvis's own sub-agents (e.g., task completion, error states).

### 3.2 Detailed Event Sources and Their Integration

| Event Source Category | Specific Event Source | Event Type (Example) | Payload (Example) | Integration Method |
| :-------------------- | :-------------------- | :------------------- | :------------------ | :----------------- |
| **System Events**     | System Resource Monitor (CPU, RAM, Disk, Battery) | `system_resource_alert` | `{"resource": "cpu", "usage": 95, "threshold": 90}` | Modify `autonomous/ambient_monitor.py` to publish events instead of direct notifications. |
|                       | Active Window Change | `window_focus_changed` | `{"window_title": "Google Chrome", "process_name": "chrome.exe"}` | Hook into OS-level APIs (e.g., `pygetwindow` or Windows API) within a dedicated `system_monitor` module. |
|                       | Application Launch/Close | `application_status_changed` | `{"app_name": "Microsoft Word", "status": "launched"}` | Similar to active window, monitor process creation/termination. |
| **Application Events** | Email Client (New Email) | `email_received` | `{"sender": "john.doe@example.com", "subject": "Meeting Reminder"}` | Integrate with email client APIs (e.g., Outlook, Gmail) or monitor local email client files. |
|                       | Calendar (Upcoming Event) | `calendar_event_upcoming` | `{"event_title": "Team Sync", "time_until": "15m"}` | Integrate with calendar APIs (e.g., Google Calendar, Outlook Calendar). |
|                       | File System Changes | `file_system_modified` | `{"path": "/docs/report.docx", "change_type": "created"}` | Use OS-level file system watchers (e.g., `watchdog` library). |
| **User Activity Events** | Keyboard/Mouse Input | `user_idle_start` / `user_active` | `{"idle_duration": "5m"}` | Monitor input device activity; publish events for idle/active states. |
|                       | Clipboard Change | `clipboard_content_changed` | `{"content_type": "text", "preview": "Hello World..."}` | Hook into OS clipboard events. |
| **Internal Agent Events** | Task Completion/Failure | `agent_task_completed` / `agent_task_failed` | `{"agent": "research", "task_id": "abc123", "success": true}` | Modify `agents/execution.py` and sub-agents to publish events upon task outcome. |
|                       | Memory Update | `memory_updated` | `{"memory_type": "semantic", "key": "user_preference", "value": "dark_mode"}` | Modify `memory/memory_manager.py` to publish events on significant memory changes. |

### 3.3 Listener Integration

Each event source will be responsible for detecting its specific condition and publishing a standardized event to the central event bus. The existing `autonomous/ambient_monitor.py` is a prime candidate for refactoring into an event producer. Instead of directly calling `_notify_user`, it would publish `system_resource_alert` events. Similarly, other modules will be adapted to emit relevant events.

**Example: Refactoring `ambient_monitor.py` to use the Event Bus**

```python
# autonomous/ambient_monitor.py (conceptual change)
# ... existing imports and setup ...

# Assume event_bus is globally accessible or passed in
from core.event_bus import event_bus # New module

def _alert(event_key: str, message: str, urgency: str):
    now = time.time()
    if now - _last_alert.get(event_key, 0) < _COOLDOWN:
        return
    
    # Publish event instead of direct notification
    event_payload = {"message": message, "urgency": urgency, "event_key": event_key}
    asyncio.create_task(event_bus.publish("system_alert", event_payload, "ambient_monitor"))
    
    _last_alert[event_key] = now
    logger.info(f"ambient_monitor: alert [{urgency}] — {message}")

# ... rest of the monitoring functions remain similar, calling _alert ...
```

This approach ensures that all relevant system activities are captured as events, providing a rich stream of information for the context-aware trigger logic in the subsequent phases. [3] [4]

## 4. Phase 3: Design the Context-Aware Trigger Logic (The Brain)

This phase focuses on how Jarvis will process the incoming events, integrate them with its understanding of user context and preferences, and decide whether to initiate a proactive action. This logic will primarily reside within the LLM, potentially orchestrated by a new `ProactiveAgent` or integrated into the main `Jarvis` agent.

### 4.1 The Proactive Agent's Role

A dedicated `ProactiveAgent` will subscribe to all relevant events on the event bus. Its core function will be to:

1.  **Filter and Aggregate Events:** Discard irrelevant noise and aggregate related events over a short time window to form a coherent understanding of a situation.
2.  **Contextualize:** Combine event data with current user context (e.g., active application, calendar schedule, semantic memory preferences, recent interactions).
3.  **Reason with LLM:** Utilize the LLM's reasoning capabilities to evaluate the situation and determine if a proactive action is warranted.
4.  **Plan Action:** If an action is needed, the LLM will formulate a `BATCH_TOOL_PLAN` or delegate to another sub-agent (e.g., `InteractionAgent` to type text, `SystemAgent` to open an app, `MemoryAgent` to record a new insight).
5.  **Execute Action:** The plan is then passed to the `Execution` agent for safe execution.

### 4.2 Contextual Information for Proactivity

For effective proactivity, the LLM needs access to a rich set of contextual information. This will be provided as part of the system prompt or through specific tool calls.

| Contextual Data Source | Description | Integration Method |
| :--------------------- | :---------- | :----------------- |
| **User Preferences**   | Stored semantic memories about user habits, preferred tools, working hours, notification preferences. | `MemoryAgent` calls to retrieve preferences. |
| **Current Activity**   | Active window, running applications, current task (if known from previous interactions). | `PerceptionAgent` and `SystemAgent` calls. |
| **Calendar/Schedule**  | Upcoming meetings, deadlines, free blocks. | `tools/comm/time_calendar.py` integration. |
| **Communication State** | Unread emails, unresponded messages. | `email_received` events, `messaging` tool status. |
| **System State**       | CPU/RAM usage, battery level, network connectivity. | `system_resource_alert` events. |

### 4.3 LLM Reasoning for Proactive Decisions

The LLM will be prompted to act as a proactive assistant, considering the following factors when deciding on an action:

*   **Relevance:** Is the event relevant to the user's current goals or known preferences?
*   **Urgency:** Does the event require immediate attention?
*   **Impact:** What is the potential positive or negative impact of taking an action?
*   **User State:** Is the user currently busy, idle, or in a meeting? (e.g., avoid interrupting during presentations).
*   **Historical Success:** Has a similar proactive action been successful in the past for this user?

**Example LLM Prompt Snippet (Conceptual for `ProactiveAgent`):**

```
You are a proactive AI assistant. An event has occurred: {{event_details}}.

Here is the current user context:
{{current_user_context}}

Based on this information, should you take any proactive action? If so, what is the most appropriate action to assist the user without being intrusive? Consider user preferences, current activity, and the potential impact. If no action is needed, state 'NO_ACTION'.

If an action is needed, output a BATCH_TOOL_PLAN to achieve it.
```

### 4.4 Avoiding Alert Fatigue and Intrusiveness

To ensure Jarvis remains helpful and not annoying, several mechanisms will be implemented:

*   **User Preferences:** Allow users to configure notification levels, preferred communication channels for proactive alerts, and even disable certain types of proactivity.
*   **Contextual Filtering:** The LLM will use the current context to determine the best time and method for intervention. For example, a low battery warning might be a desktop notification during normal work hours but a subtle visual cue if the user is presenting.
*   **Cooldown Periods:** Implement cooldown timers for specific proactive actions to prevent repeated notifications for the same issue.
*   **Feedback Loop:** Allow users to provide feedback on proactive actions (e.g., "helpful," "not helpful") to refine the LLM's decision-making over time, integrating with the `memory/episodic.py` system. [5] [6]

## 5. Phase 4: Outline Implementation Steps and Integration Strategy

This phase details the practical steps required to implement the event bus architecture and integrate it into the existing Jarvis framework. It covers development, testing, and deployment considerations.

### 5.1 Implementation Steps

1.  **Develop Core Event Bus Module (`core/event_bus.py`):**
    *   Implement the `EventBus` class with `publish`, `subscribe`, and `_process_events` methods as outlined in Phase 2.
    *   Ensure thread-safety and asynchronous operation using `asyncio`.
    *   Define a standardized `Event` dataclass or dictionary structure.

2.  **Integrate Event Bus into Orchestrator:**
    *   Instantiate the `EventBus` in `core/orchestrator.py` or a central `main` function.
    *   Ensure the event bus starts with Jarvis and runs as a background task.

3.  **Refactor Existing Proactive Modules (e.g., `ambient_monitor.py`):**
    *   Modify `autonomous/ambient_monitor.py` to publish `system_resource_alert` events to the new event bus instead of directly calling `_notify_user`.
    *   Remove direct notification logic from these modules.

4.  **Develop New Event Producers (Sensors):**
    *   **System Monitors:** Create new modules (e.g., `system_monitor.py`) to detect active window changes, application launches/closures, and clipboard events. These modules will use OS-specific APIs (e.g., `pygetwindow`, `psutil`, Windows API hooks) and publish corresponding events.
    *   **External Service Integrations:** Develop connectors for email (e.g., `outlook_connector.py`, `gmail_connector.py`) and calendar services (e.g., `google_calendar_connector.py`) to publish `email_received` and `calendar_event_upcoming` events.
    *   **File System Watcher:** Implement a file system monitoring module (e.g., `file_watcher.py` using `watchdog`) to publish `file_system_modified` events.

5.  **Develop `ProactiveAgent` (`agents/sub_agents/proactive_agent.py`):**
    *   Create a new sub-agent that subscribes to all relevant event types from the event bus.
    *   Implement the logic for event filtering, aggregation, and contextualization.
    *   Integrate LLM calls for proactive decision-making, leveraging existing `brain/ollama_client.py`.
    *   Define the prompting strategy for the LLM to evaluate events and user context.
    *   Implement logic to formulate `BATCH_TOOL_PLAN`s or delegate to other sub-agents based on LLM output.

6.  **Enhance Memory Integration:**
    *   Modify `memory/semantic.py` and `memory/episodic.py` to allow the `ProactiveAgent` to query and update user preferences and historical feedback on proactive actions.
    *   Implement a feedback mechanism for users to rate proactive actions, which feeds into the episodic memory for future LLM training/fine-tuning.

7.  **Update `Jarvis` Agent and `prompts/jarvis.yaml`:**
    *   Adjust the main `Jarvis` agent's system prompt to acknowledge the `ProactiveAgent`'s role and capabilities.
    *   Ensure the `ProactiveAgent` can be delegated to for specific proactive tasks if needed, although its primary function is autonomous.

### 5.2 Integration Strategy

*   **Phased Rollout:** Implement the event bus and core event producers first. Then, gradually introduce the `ProactiveAgent` and new event sources, testing each component thoroughly.
*   **Modularity:** Maintain strict modularity, ensuring each event producer and consumer is self-contained and communicates only via the event bus interface.
*   **Configuration:** Expose configuration options for event thresholds, notification preferences, and proactivity levels in `settings.py` to allow users to customize behavior.
*   **Logging and Monitoring:** Implement comprehensive logging for event flow, LLM decisions, and proactive actions to facilitate debugging and performance analysis.
*   **Testing:** Develop unit tests for the event bus, event producers, and the `ProactiveAgent`'s decision logic. Integration tests will verify end-to-end proactive scenarios.

### 5.3 Potential Challenges and Mitigation

| Challenge | Mitigation Strategy |
| :-------- | :------------------ |
| **Event Overload** | Implement rate limiting for event producers, intelligent event aggregation, and prioritization mechanisms within the `ProactiveAgent`. |
| **LLM Latency** | Optimize LLM calls for proactive decisions (e.g., smaller models for quick checks, caching common responses). Allow for asynchronous LLM processing. |
| **False Positives (Annoyance)** | Rigorous testing with user feedback, fine-tuning LLM prompts, implementing cooldowns, and providing granular user control over proactivity settings. |
| **Security/Privacy** | Ensure sensitive data is not exposed via events. Implement strict access controls for event producers and consumers. All LLM interactions must respect user privacy settings. |

This structured approach will ensure a robust and scalable integration of the event bus architecture, paving the way for a truly proactive Jarvis. [7] [8]

## 6. Conclusion

Integrating an event bus architecture with context-aware triggers represents a significant leap forward for Jarvis, transforming it into a truly proactive and intelligent personal AI assistant. By decoupling event producers from consumers, enabling real-time environmental perception, and leveraging the LLM's reasoning capabilities for nuanced decision-making, Jarvis will be able to anticipate user needs, offer timely assistance, and automate tasks with unprecedented efficiency. This plan provides a clear roadmap for this transformation, emphasizing modularity, scalability, and user-centric design to ensure a robust and helpful system.

## 7. References

[1] Lyzr.ai. *Proactive AI Agents*. Available at: [https://www.lyzr.ai/glossaries/proactive-ai-agents/](https://www.lyzr.ai/glossaries/proactive-ai-agents/)
[2] Poberezhnyi, O. (n.d.). *From passive AI agent to proactive personal assistant*. Medium. Available at: [https://medium.com/@oleksandr.poberezhnyi/from-passive-ai-agent-to-proactive-personal-assistant-5ac2b9ce26e7](https://medium.com/@oleksandr.poberezhnyi/from-passive-ai-agent-to-proactive-personal-assistant-5ac2b9ce26e7)
[3] Baby, A. (n.d.). *UI Automation Agents*. Available at: [https://www.arunbaby.com/ai-agents/0023-ui-automation-agents/](https://www.arunbaby.com/ai-agents/0023-ui-automation-agents/)
[4] TechRxiv. *A Survey on Benchmarks of LLM-based GUI Agents*. Available at: [https://www.techrxiv.org/doi/full/10.36227/techrxiv.176591818.87526814](https://www.techrxiv.org/doi/full/10.36227/techrxiv.176591818.87526814)
[5] arXiv. *Llm-powered gui agents in phone automation: Surveying progress and prospects*. Available at: [https://arxiv.org/abs/2504.19838](https://arxiv.org/abs/2504.19838)
[6] OpenAI API. *Computer use*. Available at: [https://developers.openai.com/api/docs/guides/tools-computer-use](https://developers.openai.com/api/docs/guides/tools-computer-use)
[7] Vardi, Y. (2024, February 16). *Designing Proactive AI Requires Event-Driven Architecture*. LinkedIn. Available at: [https://www.linkedin.com/posts/yvardi_proactive-ai-requires-a-different-type-of-activity-7429353645495828480-k6xZ](https://www.linkedin.com/posts/yvardi_proactive-ai-requires-a-different-type-of-activity-7429353645495828480-k6xZ)
[8] Kamal, S. (2025, June 5). *Event-Driven Architecture for Proactive Bots: The Future of Conversational AI*. Medium. Available at: [https://medium.com/@isachinkamal/event-driven-architecture-for-proactive-bots-the-future-of-conversational-ai-21d5ced09ae0](https://medium.com/@isachinkamal/event-driven-architecture-for-proactive-bots-the-future-of-conversational-ai-21d5ced09ae0)
