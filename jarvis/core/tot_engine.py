"""
Tree of Thoughts (ToT) Implementation for JARVIS
Enables multi-path reasoning, self-evaluation, and backtracking for complex problems.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time

class ThoughtStatus(Enum):
    PENDING = "pending"
    EXPLORED = "explored"
    PROMISING = "promising"
    DEAD_END = "dead_end"
    SOLUTION = "solution"

@dataclass
class ThoughtNode:
    """A single node in the Tree of Thoughts."""
    id: str
    content: str
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    status: ThoughtStatus = ThoughtStatus.PENDING
    value_score: float = 0.0  # 0.0 to 1.0 (confidence/success probability)
    execution_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "parent_id": self.parent_id,
            "children": self.children,
            "status": self.status.value,
            "value_score": self.value_score,
            "execution_result": self.execution_result,
            "metadata": self.metadata
        }

class TreeOfThoughtsEngine:
    """
    Manages the Tree of Thoughts process:
    1. Generate multiple possible next steps (branching)
    2. Evaluate each step heuristically or via LLM
    3. Search (BFS/DFS/Beam) to find the optimal path
    4. Execute and backtrack if necessary
    """
    
    def __init__(self, llm_interface, max_depth: int = 5, beam_width: int = 3, max_branches: int = 4):
        self.llm = llm_interface
        self.max_depth = max_depth
        self.beam_width = beam_width  # Number of top paths to keep at each level
        self.max_branches = max_branches  # Max children per node
        self.nodes: Dict[str, ThoughtNode] = {}
        self.root_id: Optional[str] = None
        self.solution_path: List[str] = []
        
    def initialize_tree(self, problem_statement: str) -> str:
        """Create the root node representing the initial problem."""
        root_id = f"root_{int(time.time())}"
        root = ThoughtNode(
            id=root_id,
            content=f"Problem: {problem_statement}",
            status=ThoughtStatus.PENDING,
            metadata={"type": "root", "depth": 0}
        )
        self.nodes[root_id] = root
        self.root_id = root_id
        return root_id
    
    async def generate_branches(self, node_id: str, context: str) -> List[ThoughtNode]:
        """Generate multiple possible next thoughts/actions from current node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
            
        prompt = f"""
        Current State: {context}
        Current Thought: {node.content}
        
        Generate {self.max_branches} distinct possible next steps or strategies to solve the problem.
        Each step should be a concrete action or logical deduction.
        Format as JSON list: [{{"thought": "description", "action_type": "tool_use|logic|search"}}]
        """
        
        try:
            response = await self.llm.generate_async(prompt, temperature=0.7)
            # Parse JSON response (simplified parsing logic)
            # In production, use robust JSON extraction
            branches_data = self._parse_llm_json(response)
            
            new_nodes = []
            for i, branch in enumerate(branches_data[:self.max_branches]):
                child_id = f"{node_id}_child_{i}"
                child_node = ThoughtNode(
                    id=child_id,
                    content=branch.get("thought", ""),
                    parent_id=node_id,
                    metadata={
                        "action_type": branch.get("action_type", "general"),
                        "depth": node.metadata.get("depth", 0) + 1
                    }
                )
                node.children.append(child_id)
                self.nodes[child_id] = child_node
                new_nodes.append(child_node)
                
            return new_nodes
            
        except Exception as e:
            print(f"Error generating branches: {e}")
            return []
    
    async def evaluate_node(self, node_id: str, context: str) -> float:
        """Evaluate the promise of a specific node (0.0 to 1.0)."""
        node = self.nodes.get(node_id)
        if not node:
            return 0.0
            
        prompt = f"""
        Context: {context}
        Proposed Step: {node.content}
        
        Evaluate this step on a scale of 0.0 to 1.0 based on:
        1. Relevance to the original goal
        2. Feasibility of execution
        3. Likelihood of leading to a solution
        
        Return only a float score.
        """
        
        try:
            response = await self.llm.generate_async(prompt, temperature=0.2)
            score = float(response.strip())
            node.value_score = max(0.0, min(1.0, score))
            return node.value_score
        except Exception as e:
            print(f"Error evaluating node: {e}")
            return 0.5  # Default neutral score
    
    async def execute_node(self, node_id: str, tools_context: Dict[str, Any]) -> Any:
        """Attempt to execute the action described in the node."""
        node = self.nodes.get(node_id)
        if not node:
            return None
            
        # Check if node requires tool execution
        action_type = node.metadata.get("action_type", "")
        
        if action_type == "tool_use":
            # Extract tool call from thought content
            # This would integrate with the existing ToolExecutor
            pass
        
        # Simulate execution result storage
        node.execution_result = "Executed successfully" # Placeholder
        node.status = ThoughtStatus.EXPLORED
        return node.execution_result

    def _parse_llm_json(self, text: str) -> List[Dict]:
        """Robustly extract JSON from LLM response."""
        import re
        try:
            # Try to find JSON array pattern
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return []
        except:
            return []

    async def solve(self, problem: str, tools_context: Dict[str, Any]) -> Optional[str]:
        """Main ToT solving loop using Beam Search."""
        root_id = self.initialize_tree(problem)
        current_level = [root_id]
        
        for depth in range(self.max_depth):
            next_level_candidates = []
            
            # Expand all nodes in current level
            for node_id in current_level:
                context = self._build_context(node_id)
                
                # Generate branches
                children = await self.generate_branches(node_id, context)
                
                # Evaluate each child
                for child in children:
                    score = await self.evaluate_node(child.id, context)
                    if score > 0.3:  # Threshold to prune bad ideas early
                        next_level_candidates.append((child.id, score))
            
            # Sort by score and keep top beam_width (Beam Search)
            next_level_candidates.sort(key=lambda x: x[1], reverse=True)
            current_level = [x[0] for x in next_level_candidates[:self.beam_width]]
            
            # Check for solution condition (simplified)
            for node_id in current_level:
                node = self.nodes[node_id]
                if "solution" in node.content.lower() or node.value_score > 0.9:
                    node.status = ThoughtStatus.SOLUTION
                    self.solution_path = self._reconstruct_path(node_id)
                    return self._format_solution(self.solution_path)
        
        # If no perfect solution found, return best effort path
        if current_level:
            best_node_id = current_level[0]
            self.solution_path = self._reconstruct_path(best_node_id)
            return self._format_solution(self.solution_path)
            
        return None

    def _build_context(self, node_id: str) -> str:
        """Build the full context chain from root to node."""
        path = self._reconstruct_path(node_id)
        context_parts = []
        for nid in path:
            node = self.nodes[nid]
            context_parts.append(node.content)
        return "\n".join(context_parts)

    def _reconstruct_path(self, node_id: str) -> List[str]:
        """Trace back from node to root."""
        path = []
        current = node_id
        while current:
            path.append(current)
            node = self.nodes.get(current)
            if node:
                current = node.parent_id
            else:
                break
        return list(reversed(path))

    def _format_solution(self, path_ids: List[str]) -> str:
        """Format the solution path into executable instructions."""
        steps = []
        for i, nid in enumerate(path_ids):
            node = self.nodes[nid]
            if i == 0: continue # Skip root problem statement
            steps.append(f"Step {i}: {node.content} (Score: {node.value_score:.2f})")
        return "\n".join(steps)
