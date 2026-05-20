import sys, json, asyncio, logging, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("proactive_shell")

from agents.sub_agents.proactive_agent import ProactiveAgent
from agents.base_agent import SubAgentTask


def _notify(title: str, message: str):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=5)
    except ImportError:
        print(f"\n[ProactiveAgent] {title}: {message}", flush=True)


def _local_execute(tool_name: str, args: dict) -> dict:
    if tool_name == "notify":
        _notify(args.get("title", "ProactiveAgent"), args.get("message", ""))
        return {"success": True, "message": "Notification sent", "data": {}, "timestamp": ""}
    logger.warning(f"Tool '{tool_name}' not available in subprocess")
    return {"success": False, "message": f"Unavailable: {tool_name}", "data": {}, "timestamp": ""}


async def main():
    agent = ProactiveAgent(event_source="stdin")
    agent._execute = _local_execute
    agent._verify = lambda *a, **kw: {"success": True}
    await agent.run(SubAgentTask(goal="Start proactive monitoring", context={}))
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
