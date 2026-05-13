"""
Multi-Agent Negotiation Protocol Module for JARVIS Phase 5.
Enables multiple agent instances to collaborate, negotiate, and resolve conflicts
when working on complex tasks that require distributed expertise.
"""
import logging
import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in multi-agent communication."""
    PROPOSAL = "proposal"
    COUNTER_PROPOSAL = "counter_proposal"
    ACCEPTANCE = "acceptance"
    REJECTION = "rejection"
    INFORMATION_REQUEST = "information_request"
    INFORMATION_RESPONSE = "information_response"
    TASK_ANNOUNCEMENT = "task_announcement"
    BID = "bid"
    AWARD = "award"
    STATUS_UPDATE = "status_update"
    NEGOTIATION_COMPLETE = "negotiation_complete"


class AgentRole(Enum):
    """Roles an agent can take in negotiations."""
    INITIATOR = "initiator"
    PARTICIPANT = "participant"
    MEDIATOR = "mediator"
    ARBITER = "arbiter"
    OBSERVER = "observer"


@dataclass
class AgentCapability:
    """Represents a capability of an agent."""
    name: str
    confidence: float  # 0.0 to 1.0
    avg_completion_time: float  # seconds
    success_rate: float  # 0.0 to 1.0
    cost: float = 0.0  # Abstract cost unit
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A message between agents."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    receiver_id: str = ""  # Empty for broadcast
    message_type: MessageType = MessageType.PROPOSAL
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    in_reply_to: Optional[str] = None
    expires_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        """Check if the message has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class NegotiationSession:
    """Tracks a negotiation session between agents."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    initiator_id: str = ""
    participants: Set[str] = field(default_factory=set)
    messages: List[Message] = field(default_factory=list)
    proposals: Dict[str, Dict] = field(default_factory=dict)  # agent_id -> proposal
    votes: Dict[str, str] = field(default_factory=dict)  # agent_id -> voted_proposal_id
    status: str = "active"  # active, completed, failed, timeout
    outcome: Optional[Dict] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class TaskAllocation:
    """Result of task allocation negotiation."""
    task_id: str
    allocated_to: str
    allocation_method: str  # auction, consensus, direct
    bid_details: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


class AgentRegistry:
    """Registry of available agents and their capabilities."""
    
    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._capabilities: Dict[str, List[AgentCapability]] = defaultdict(list)
        self._availability: Dict[str, bool] = {}
        self._load: Dict[str, float] = {}  # Current load 0.0 to 1.0
    
    def register_agent(self, agent_id: str, capabilities: List[AgentCapability],
                       metadata: Optional[Dict] = None):
        """Register an agent with its capabilities."""
        self._agents[agent_id] = {
            'id': agent_id,
            'metadata': metadata or {},
            'registered_at': time.time()
        }
        
        for cap in capabilities:
            self._capabilities[cap.name].append(cap)
        
        self._availability[agent_id] = True
        self._load[agent_id] = 0.0
        
        logger.info(f"Registered agent {agent_id} with {len(capabilities)} capabilities")
    
    def unregister_agent(self, agent_id: str):
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
        
        # Remove from capabilities
        for cap_list in self._capabilities.values():
            self._capabilities[cap_list[0].name] = [
                c for c in cap_list 
                if not any(self._agents.get(agent_id) for _ in [0])
            ]
        
        self._availability.pop(agent_id, None)
        self._load.pop(agent_id, None)
        
        logger.info(f"Unregistered agent {agent_id}")
    
    def find_agents_for_capability(self, capability_name: str, 
                                    min_confidence: float = 0.5) -> List[Tuple[str, AgentCapability]]:
        """Find agents capable of handling a specific capability."""
        candidates = []
        
        for cap in self._capabilities.get(capability_name, []):
            agent_id = None
            # Find which agent this capability belongs to
            for aid in self._agents:
                if aid in [c for c in self._capabilities.get(capability_name, [])]:
                    agent_id = aid
                    break
            
            if agent_id and self._availability.get(agent_id, False):
                if cap.confidence >= min_confidence:
                    candidates.append((agent_id, cap))
        
        # Sort by confidence and load
        candidates.sort(key=lambda x: (x[1].confidence, -self._load.get(x[0], 0)), reverse=True)
        
        return candidates
    
    def update_availability(self, agent_id: str, available: bool):
        """Update agent availability."""
        self._availability[agent_id] = available
    
    def update_load(self, agent_id: str, load: float):
        """Update agent load (0.0 to 1.0)."""
        self._load[agent_id] = max(0.0, min(1.0, load))
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Get information about an agent."""
        if agent_id not in self._agents:
            return None
        
        agent_caps = []
        for cap_name, caps in self._capabilities.items():
            for cap in caps:
                agent_caps.append(cap)
        
        return {
            **self._agents[agent_id],
            'available': self._availability.get(agent_id, False),
            'load': self._load.get(agent_id, 0.0),
            'capabilities': agent_caps
        }


class ContractNetProtocol:
    """
    Implements the Contract Net Protocol for task allocation.
    
    Based on the classic contract net protocol:
    1. Manager announces task
    2. Contractors submit bids
    3. Manager awards contract to best bidder
    """
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._auctions: Dict[str, Dict] = {}
    
    def announce_task(self, task_id: str, requirements: Dict[str, Any],
                      deadline: Optional[float] = None) -> str:
        """Announce a task for bidding."""
        auction_id = f"auction_{task_id}_{int(time.time())}"
        
        self._auctions[auction_id] = {
            'task_id': task_id,
            'requirements': requirements,
            'deadline': deadline,
            'bids': {},
            'status': 'open',
            'created_at': time.time()
        }
        
        logger.info(f"Announced task {task_id} with auction {auction_id}")
        return auction_id
    
    def submit_bid(self, auction_id: str, agent_id: str, 
                   bid: Dict[str, Any]) -> bool:
        """Submit a bid for an auction."""
        if auction_id not in self._auctions:
            return False
        
        auction = self._auctions[auction_id]
        
        if auction['status'] != 'open':
            return False
        
        # Check if deadline passed
        if auction['deadline'] and time.time() > auction['deadline']:
            auction['status'] = 'closed'
            return False
        
        auction['bids'][agent_id] = {
            'bid': bid,
            'submitted_at': time.time()
        }
        
        logger.debug(f"Received bid from {agent_id} for auction {auction_id}")
        return True
    
    def award_contract(self, auction_id: str, 
                       evaluation_fn: Optional[Callable[[Dict], float]] = None) -> Optional[TaskAllocation]:
        """Award contract to the best bidder."""
        if auction_id not in self._auctions:
            return None
        
        auction = self._auctions[auction_id]
        
        if not auction['bids']:
            auction['status'] = 'no_bids'
            return None
        
        # Evaluate bids
        def default_eval(bid_data: Dict) -> float:
            bid = bid_data['bid']
            # Default: prefer lower cost, higher confidence, faster completion
            cost = bid.get('cost', 1.0)
            confidence = bid.get('confidence', 0.5)
            time_estimate = bid.get('time_estimate', 100)
            
            # Score: higher is better
            score = confidence / (cost * (time_estimate / 100 + 1))
            return score
        
        eval_fn = evaluation_fn or default_eval
        
        scored_bids = [
            (agent_id, eval_fn(bid_data), bid_data)
            for agent_id, bid_data in auction['bids'].items()
        ]
        
        if not scored_bids:
            return None
        
        # Select winner
        winner_id, winner_score, winner_bid = max(scored_bids, key=lambda x: x[1])
        
        auction['status'] = 'awarded'
        auction['winner'] = winner_id
        
        allocation = TaskAllocation(
            task_id=auction['task_id'],
            allocated_to=winner_id,
            allocation_method='auction',
            bid_details=winner_bid['bid'],
            confidence=winner_score
        )
        
        logger.info(f"Awarded auction {auction_id} to {winner_id}")
        return allocation
    
    def close_auction(self, auction_id: str):
        """Close an auction without awarding."""
        if auction_id in self._auctions:
            self._auctions[auction_id]['status'] = 'closed'


class NegotiationManager:
    """
    Manages multi-agent negotiations using various protocols.
    
    Supports:
    - Contract Net Protocol for task allocation
    - Consensus-based decision making
    - Mediated negotiations for conflict resolution
    """
    
    def __init__(self, agent_id: str, registry: AgentRegistry,
                 role: AgentRole = AgentRole.PARTICIPANT):
        """
        Initialize the negotiation manager.
        
        Args:
            agent_id: This agent's identifier
            registry: Shared agent registry
            role: This agent's role in negotiations
        """
        self.agent_id = agent_id
        self.registry = registry
        self.role = role
        
        self._sessions: Dict[str, NegotiationSession] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._handlers: Dict[MessageType, Callable] = {}
        self._contract_net = ContractNetProtocol(registry)
        
        self._setup_default_handlers()
        
        logger.info(f"NegotiationManager initialized for {agent_id} as {role.value}")
    
    def _setup_default_handlers(self):
        """Set up default message handlers."""
        self._handlers = {
            MessageType.TASK_ANNOUNCEMENT: self._handle_task_announcement,
            MessageType.PROPOSAL: self._handle_proposal,
            MessageType.COUNTER_PROPOSAL: self._handle_counter_proposal,
            MessageType.ACCEPTANCE: self._handle_acceptance,
            MessageType.REJECTION: self._handle_rejection,
            MessageType.INFORMATION_REQUEST: self._handle_info_request,
            MessageType.BID: self._handle_bid,
            MessageType.AWARD: self._handle_award,
        }
    
    def create_session(self, task_id: str, participants: List[str]) -> NegotiationSession:
        """Create a new negotiation session."""
        session = NegotiationSession(
            task_id=task_id,
            initiator_id=self.agent_id,
            participants=set(participants)
        )
        session.participants.add(self.agent_id)
        
        self._sessions[session.id] = session
        
        logger.info(f"Created negotiation session {session.id} for task {task_id}")
        return session
    
    async def send_message(self, message: Message):
        """Send a message to another agent (or broadcast)."""
        # In production, this would use actual network communication
        # For now, just log and add to queue simulation
        logger.debug(f"Sending {message.message_type.value} from {message.sender_id} "
                    f"to {message.receiver_id or 'all'}")
        
        # Simulate delivery
        await self._message_queue.put(message)
    
    async def broadcast(self, session_id: str, message_type: MessageType,
                        content: Dict[str, Any], expires_in: Optional[float] = None):
        """Broadcast a message to all session participants."""
        if session_id not in self._sessions:
            raise ValueError(f"Unknown session: {session_id}")
        
        session = self._sessions[session_id]
        
        message = Message(
            sender_id=self.agent_id,
            message_type=message_type,
            content=content,
            expires_at=time.time() + expires_in if expires_in else None
        )
        
        for participant in session.participants:
            if participant != self.agent_id:
                msg_copy = Message(
                    **{k: v for k, v in message.__dict__.items() if k != 'id'},
                    receiver_id=participant
                )
                await self.send_message(msg_copy)
    
    def receive_message(self, message: Message):
        """Receive and process a message."""
        if message.is_expired():
            logger.debug(f"Ignoring expired message {message.id}")
            return
        
        handler = self._handlers.get(message.message_type)
        if handler:
            asyncio.create_task(handler(message))
        else:
            logger.warning(f"No handler for message type: {message.message_type}")
    
    async def _handle_task_announcement(self, message: Message):
        """Handle incoming task announcement."""
        task_id = message.content.get('task_id')
        requirements = message.content.get('requirements')
        deadline = message.content.get('deadline')
        
        logger.info(f"Received task announcement for {task_id}")
        
        # Check if we can handle this task
        required_caps = requirements.get('required_capabilities', [])
        can_handle = True
        bid_details = {'cost': 1.0, 'confidence': 0.8, 'time_estimate': 60}
        
        for cap in required_caps:
            agents = self.registry.find_agents_for_capability(cap)
            if not any(a[0] == self.agent_id for a in agents):
                can_handle = False
                break
        
        if can_handle:
            # Submit bid
            bid_message = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                message_type=MessageType.BID,
                content={
                    'task_id': task_id,
                    'auction_id': message.content.get('auction_id'),
                    'bid': bid_details
                },
                in_reply_to=message.id
            )
            await self.send_message(bid_message)
    
    async def _handle_proposal(self, message: Message):
        """Handle incoming proposal."""
        session_id = message.content.get('session_id')
        proposal = message.content.get('proposal')
        
        logger.info(f"Received proposal for session {session_id}")
        
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.proposals[message.sender_id] = proposal
            session.messages.append(message)
            
            # Evaluate and respond
            acceptance = self._evaluate_proposal(proposal)
            
            response_type = MessageType.ACCEPTANCE if acceptance else MessageType.REJECTION
            response = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                message_type=response_type,
                content={'session_id': session_id},
                in_reply_to=message.id
            )
            await self.send_message(response)
    
    async def _handle_counter_proposal(self, message: Message):
        """Handle counter-proposal."""
        logger.info(f"Received counter-proposal from {message.sender_id}")
        # Implementation for counter-proposal handling
    
    async def _handle_acceptance(self, message: Message):
        """Handle acceptance message."""
        logger.info(f"Proposal accepted by {message.sender_id}")
    
    async def _handle_rejection(self, message: Message):
        """Handle rejection message."""
        logger.info(f"Proposal rejected by {message.sender_id}")
    
    async def _handle_info_request(self, message: Message):
        """Handle information request."""
        query = message.content.get('query')
        
        # Provide information based on query
        response_content = {'query': query, 'data': {}}
        
        if query == 'capabilities':
            response_content['data'] = [
                {'name': c.name, 'confidence': c.confidence}
                for c in self.registry._capabilities.values()
                for c in c
            ][:10]  # Limit response size
        
        response = Message(
            sender_id=self.agent_id,
            receiver_id=message.sender_id,
            message_type=MessageType.INFORMATION_RESPONSE,
            content=response_content,
            in_reply_to=message.id
        )
        await self.send_message(response)
    
    async def _handle_bid(self, message: Message):
        """Handle incoming bid (for auction manager)."""
        auction_id = message.content.get('auction_id')
        agent_id = message.sender_id
        bid = message.content.get('bid')
        
        logger.info(f"Received bid from {agent_id} for auction {auction_id}")
        
        self._contract_net.submit_bid(auction_id, agent_id, bid)
    
    async def _handle_award(self, message: Message):
        """Handle contract award."""
        task_id = message.content.get('task_id')
        awarded_to = message.content.get('awarded_to')
        
        if awarded_to == self.agent_id:
            logger.info(f"Won contract for task {task_id}")
        else:
            logger.info(f"Contract for {task_id} awarded to {awarded_to}")
    
    def _evaluate_proposal(self, proposal: Dict) -> bool:
        """Evaluate whether to accept a proposal."""
        # Simple heuristic: accept if confidence is high enough
        confidence = proposal.get('confidence', 0.5)
        return confidence > 0.7
    
    def get_session(self, session_id: str) -> Optional[NegotiationSession]:
        """Get a negotiation session by ID."""
        return self._sessions.get(session_id)
    
    def get_active_sessions(self) -> List[NegotiationSession]:
        """Get all active sessions."""
        return [s for s in self._sessions.values() if s.status == 'active']


class MultiAgentCoordinator:
    """
    High-level coordinator for multi-agent collaboration.
    
    Orchestrates task decomposition, agent selection, and result aggregation.
    """
    
    def __init__(self, registry: AgentRegistry):
        """Initialize the coordinator."""
        self.registry = registry
        self._allocations: Dict[str, TaskAllocation] = {}
        self._collaboration_history: List[Dict] = []
    
    async def coordinate_task(self, task_id: str, task_description: str,
                               requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate a task across multiple agents.
        
        Args:
            task_id: Unique task identifier
            task_description: Description of the task
            requirements: Required capabilities and constraints
            
        Returns:
            Task execution results
        """
        logger.info(f"Coordinating task {task_id}: {task_description}")
        
        # Step 1: Decompose task if needed
        subtasks = self._decompose_task(task_id, task_description, requirements)
        
        # Step 2: Allocate subtasks via auction
        allocations = []
        for subtask in subtasks:
            allocation = self._allocate_subtask(subtask)
            if allocation:
                allocations.append(allocation)
                self._allocations[subtask['id']] = allocation
        
        # Step 3: Monitor execution
        results = await self._monitor_execution(allocations)
        
        # Step 4: Aggregate results
        final_result = self._aggregate_results(results)
        
        self._record_collaboration(task_id, subtasks, allocations, final_result)
        
        return final_result
    
    def _decompose_task(self, task_id: str, description: str,
                        requirements: Dict) -> List[Dict]:
        """Decompose a task into subtasks. Uses LLM when available, else splits by capability."""
        # Try LLM-based decomposition
        llm_subtasks = self._llm_decompose(task_id, description, requirements)
        if llm_subtasks:
            return llm_subtasks

        # Fallback: split by required capabilities
        required_caps = requirements.get('required_capabilities', ['general'])
        
        subtasks = []
        for i, cap in enumerate(required_caps):
            subtasks.append({
                'id': f"{task_id}_sub_{i}",
                'description': f"Handle {cap} aspect of: {description}",
                'required_capability': cap,
                'parent_task': task_id
            })
        
        if not subtasks:
            subtasks.append({
                'id': f"{task_id}_sub_0",
                'description': description,
                'required_capability': 'general',
                'parent_task': task_id
            })
        
        logger.info(f"Decomposed task {task_id} into {len(subtasks)} subtasks")
        return subtasks
    
    def _llm_decompose(self, task_id: str, description: str,
                       requirements: Dict) -> Optional[List[Dict]]:
        """Use LLM to intelligently decompose a task into subtasks."""
        try:
            from brain.ollama_client import chat
            import json as _json
        except ImportError:
            return None

        caps = requirements.get('required_capabilities', [])
        prompt = (
            f"Decompose this task into subtasks:\n"
            f"Task: {description}\n"
            f"Available capabilities: {', '.join(caps) if caps else 'general'}\n\n"
            f"Respond with ONLY a JSON array of subtasks:\n"
            '[{"description": "...", "required_capability": "..."}]'
        )
        try:
            result = chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_retries=1,
            )
            text = result.get("content", "")
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                return None
            parsed = _json.loads(text[start:end])
            subtasks = []
            for i, item in enumerate(parsed):
                subtasks.append({
                    'id': f"{task_id}_sub_{i}",
                    'description': item.get('description', ''),
                    'required_capability': item.get('required_capability', 'general'),
                    'parent_task': task_id,
                })
            return subtasks if subtasks else None
        except Exception as e:
            logger.debug(f"LLM task decomposition failed: {e}")
            return None

    def _allocate_subtask(self, subtask: Dict) -> Optional[TaskAllocation]:
        """Allocate a subtask to an agent via auction."""
        required_cap = subtask.get('required_capability', 'general')
        
        # Find capable agents
        capable_agents = self.registry.find_agents_for_capability(required_cap)
        
        if not capable_agents:
            logger.warning(f"No agents found for capability: {required_cap}")
            return None
        
        # Create auction
        auction_id = self._contract_net.announce_task(
            subtask['id'],
            {'required_capabilities': [required_cap]},
            deadline=time.time() + 30  # 30 second bidding window
        )
        
        # Simulate bids from capable agents
        for agent_id, capability in capable_agents[:3]:  # Top 3 bidders
            self._contract_net.submit_bid(auction_id, agent_id, {
                'cost': capability.cost or 1.0,
                'confidence': capability.confidence,
                'time_estimate': capability.avg_completion_time
            })
        
        # Award contract
        allocation = self._contract_net.award_contract(auction_id)
        
        return allocation
    
    async def _monitor_execution(self, allocations: List[TaskAllocation]) -> List[Dict]:
        """Monitor execution of allocated tasks."""
        results = []
        
        for allocation in allocations:
            # Simulate execution result
            result = {
                'task_id': allocation.task_id,
                'agent_id': allocation.allocated_to,
                'success': True,
                'output': f"Result from {allocation.allocated_to}",
                'execution_time': 10.0
            }
            results.append(result)
        
        return results
    
    def _aggregate_results(self, results: List[Dict]) -> Dict[str, Any]:
        """Aggregate results from multiple agents."""
        return {
            'success': all(r.get('success', False) for r in results),
            'partial_results': results,
            'aggregated_output': " | ".join(r.get('output', '') for r in results),
            'total_agents': len(results)
        }
    
    def _record_collaboration(self, task_id: str, subtasks: List[Dict],
                               allocations: List[TaskAllocation], result: Dict):
        """Record collaboration for analytics."""
        self._collaboration_history.append({
            'task_id': task_id,
            'timestamp': time.time(),
            'subtask_count': len(subtasks),
            'allocation_count': len(allocations),
            'success': result.get('success', False)
        })
    
    @property
    def _contract_net(self) -> ContractNetProtocol:
        """Get contract net protocol instance."""
        return ContractNetProtocol(self.registry)
    
    def get_collaboration_stats(self) -> Dict[str, Any]:
        """Get statistics about multi-agent collaborations."""
        if not self._collaboration_history:
            return {"total_collaborations": 0}
        
        total = len(self._collaboration_history)
        successful = sum(1 for c in self._collaboration_history if c['success'])
        
        return {
            "total_collaborations": total,
            "success_rate": successful / total,
            "avg_subtasks": sum(c['subtask_count'] for c in self._collaboration_history) / total,
            "avg_agents": sum(c['allocation_count'] for c in self._collaboration_history) / total
        }


# Singleton instances
agent_registry = AgentRegistry()


def create_negotiation_manager(agent_id: str, 
                                capabilities: List[AgentCapability],
                                role: AgentRole = AgentRole.PARTICIPANT) -> NegotiationManager:
    """Create a negotiation manager for an agent."""
    agent_registry.register_agent(agent_id, capabilities)
    return NegotiationManager(agent_id, agent_registry, role)


def create_coordinator() -> MultiAgentCoordinator:
    """Create a multi-agent coordinator."""
    return MultiAgentCoordinator(agent_registry)
