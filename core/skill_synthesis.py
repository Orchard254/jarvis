"""
Dynamic Skill Synthesis Module for JARVIS Phase 5.
Enables the agent to create new tools/skills on the fly based on task requirements.
Implements skill composition, code generation, and runtime registration.
"""
import logging
import inspect
import types
import importlib.util
import tempfile
import os
import hashlib
import json
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


class SkillType(Enum):
    """Types of dynamically creatable skills."""
    COMPOSED = "composed"  # Combination of existing skills
    GENERATED = "generated"  # Code-generated new skill
    WRAPPED = "wrapped"  # Wrapper around external API/function
    MACRO = "macro"  # Sequence of operations as a single skill


@dataclass
class SkillSignature:
    """Defines the signature of a skill."""
    name: str
    description: str
    parameters: Dict[str, Any]  # {param_name: {type, description, required}}
    return_type: str
    examples: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class SynthesizedSkill:
    """Represents a dynamically created skill."""
    signature: SkillSignature
    skill_type: SkillType
    implementation: Callable
    source_skills: List[str] = field(default_factory=list)  # For composed skills
    generated_code: Optional[str] = None  # For generated skills
    created_at: float = field(default_factory=time.time)
    usage_count: int = 0
    success_rate: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def record_usage(self, success: bool = True):
        """Record a usage of this skill."""
        self.usage_count += 1
        # Exponential moving average for success rate
        alpha = 0.1
        self.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * self.success_rate


class SkillComposer:
    """Composes new skills from existing skills."""
    
    def __init__(self, skill_registry: Dict[str, Callable]):
        """
        Initialize the composer.
        
        Args:
            skill_registry: Dictionary of available skills {name: function}
        """
        self.skill_registry = skill_registry
        self._composition_history: List[Dict] = []
    
    def compose(self, name: str, description: str, 
                skill_sequence: List[Tuple[str, Dict]],
                output_transform: Optional[Callable] = None) -> Callable:
        """
        Compose a new skill from a sequence of existing skills.
        
        Args:
            name: Name for the composed skill
            description: Description of what the composed skill does
            skill_sequence: List of (skill_name, kwargs) tuples to execute in order
            output_transform: Optional function to transform final output
            
        Returns:
            A new callable that executes the skill sequence
        """
        def composed_skill(**kwargs) -> Any:
            """Executes the composed skill sequence."""
            current_output = kwargs
            execution_log = []
            
            for skill_name, static_kwargs in skill_sequence:
                if skill_name not in self.skill_registry:
                    raise ValueError(f"Unknown skill in composition: {skill_name}")
                
                skill_fn = self.skill_registry[skill_name]
                
                # Merge dynamic kwargs with static kwargs
                exec_kwargs = {**static_kwargs}
                for key, value in current_output.items():
                    if key not in exec_kwargs:
                        exec_kwargs[key] = value
                
                try:
                    logger.debug(f"Executing composed skill step: {skill_name}")
                    result = skill_fn(**exec_kwargs)
                    
                    # Handle different return types
                    if isinstance(result, dict):
                        current_output = {**current_output, **result}
                    else:
                        current_output['result'] = result
                    
                    execution_log.append({
                        'skill': skill_name,
                        'success': True,
                        'output_keys': list(result.keys()) if isinstance(result, dict) else ['result']
                    })
                    
                except Exception as e:
                    logger.error(f"Skill composition failed at {skill_name}: {e}")
                    execution_log.append({
                        'skill': skill_name,
                        'success': False,
                        'error': str(e)
                    })
                    raise
            
            # Apply output transformation if provided
            if output_transform:
                current_output = output_transform(current_output)
            
            current_output['_execution_log'] = execution_log
            return current_output
        
        return composed_skill
    
    def analyze_compatibility(self, skill1_name: str, skill2_name: str) -> Dict[str, Any]:
        """Analyze if two skills can be composed together."""
        if skill1_name not in self.skill_registry or skill2_name not in self.skill_registry:
            return {"compatible": False, "reason": "One or both skills not found"}
        
        # Get signatures (would use introspection or registry metadata in production)
        skill1_fn = self.skill_registry[skill1_name]
        skill2_fn = self.skill_registry[skill2_name]
        
        try:
            sig1 = inspect.signature(skill1_fn)
            sig2 = inspect.signature(skill2_fn)
            
            # Check if output of skill1 could match input of skill2
            skill1_params = set(sig1.parameters.keys())
            skill2_params = set(sig2.parameters.keys())
            
            # Simple heuristic: check for overlapping parameter names
            overlap = skill1_params & skill2_params
            
            return {
                "compatible": len(overlap) > 0 or 'result' in skill2_params,
                "overlap": list(overlap),
                "skill1_outputs": list(skill1_params),
                "skill2_inputs": list(skill2_params),
                "suggestion": f"Consider mapping outputs to inputs explicitly" if not overlap else ""
            }
        except Exception as e:
            return {"compatible": False, "reason": str(e)}


class CodeGenerator:
    """Generates code for new skills."""
    
    def __init__(self, llm_client=None, language: str = "python"):
        """
        Initialize the code generator.
        
        Args:
            llm_client: LLM client for code generation
            language: Target programming language
        """
        self.llm_client = llm_client
        self.language = language
        self._generated_code_cache: Dict[str, str] = {}
    
    def generate_skill_code(self, name: str, signature: SkillSignature,
                            requirements: str, examples: List[str] = None) -> str:
        """
        Generate code for a new skill.
        
        Args:
            name: Name of the skill
            signature: The skill's signature
            requirements: Natural language description of requirements
            examples: Example inputs/outputs
            
        Returns:
            Generated code as a string
        """
        cache_key = hashlib.md5(f"{name}{requirements}".encode()).hexdigest()
        if cache_key in self._generated_code_cache:
            return self._generated_code_cache[cache_key]
        
        # Try LLM-based code generation first
        code = None
        try:
            from brain.ollama_client import chat
            prompt = self._build_code_generation_prompt(name, signature, requirements, examples)
            result = chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_retries=1,
            )
            generated = result.get("content", "").strip()
            # Extract code block if wrapped in markdown
            if "```python" in generated:
                generated = generated.split("```python", 1)[1].split("```", 1)[0].strip()
            elif "```" in generated:
                generated = generated.split("```", 1)[1].split("```", 1)[0].strip()
            if generated:
                valid, _ = self.validate_code(generated)
                if valid:
                    code = generated
                    logger.info(f"LLM generated valid code for skill '{name}'")
        except Exception as e:
            logger.debug(f"LLM code generation failed for '{name}': {e}")

        if code is None:
            code = self._generate_template_code(name, signature, requirements)
        
        self._generated_code_cache[cache_key] = code
        return code
    
    def _generate_template_code(self, name: str, signature: SkillSignature,
                                 requirements: str) -> str:
        """Generate a template for the skill code."""
        params_def = ", ".join([
            f"{name}: {p.get('type', 'Any')}" 
            for name, p in signature.parameters.items()
        ])
        
        param_docs = "\n".join([
            f"    {name}: {p.get('description', '')}"
            for name, p in signature.parameters.items()
        ])
        
        code = f'''
"""Auto-generated skill: {name}

{signature.description}

Requirements: {requirements}
"""

def {name}({params_def}) -> {signature.return_type}:
    """
    {signature.description}
    
    Parameters:
{param_docs}
    
    Returns:
        {signature.return_type}
    """
    # Auto-generated template — implement logic per requirements:
    # {requirements}
    result = {{}}
    
    # Process inputs
    # [Implementation goes here]
    
    return result


# Example usage:
if __name__ == "__main__":
    # Test the generated skill
    test_args = {{}}  # Fill with test values
    output = {name}(**test_args)
    print(f"Result: {{output}}")
'''
        return code.strip()
    
    def _build_code_generation_prompt(self, name: str, signature: SkillSignature,
                                       requirements: str, examples: List[str]) -> str:
        """Build prompt for LLM-based code generation."""
        examples_text = "\n\n".join([f"Example {i+1}: {ex}" for i, ex in enumerate(examples or [])])
        
        return f"""Generate a Python function with the following specification:

Function Name: {name}
Description: {signature.description}

Parameters:
{json.dumps(signature.parameters, indent=2)}

Return Type: {signature.return_type}

Requirements:
{requirements}

{examples_text if examples else ""}

Provide only the complete, working Python function with docstring:"""
    
    def validate_code(self, code: str) -> Tuple[bool, str]:
        """Validate generated code for syntax errors."""
        try:
            compile(code, '<string>', 'exec')
            return True, "Code is syntactically valid"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def load_skill_from_code(self, code: str, skill_name: str) -> Optional[Callable]:
        """Load a skill from generated code."""
        try:
            # Create a temporary module
            spec = importlib.util.spec_from_loader(
                skill_name,
                loader=None,
                origin='generated'
            )
            module = importlib.util.module_from_spec(spec)
            
            # Execute the code in the module's namespace with restricted builtins
            restricted_builtins = {
                '__builtins__': {
                    'None': None, 'True': True, 'False': False,
                    'int': int, 'float': float, 'str': str, 'bool': bool,
                    'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                    'len': len, 'range': range, 'enumerate': enumerate, 'zip': zip,
                    'map': map, 'filter': filter, 'sorted': sorted, 'reversed': reversed,
                    'min': min, 'max': max, 'sum': sum, 'abs': abs,
                    'isinstance': isinstance, 'issubclass': issubclass, 'hasattr': hasattr, 'getattr': getattr, 'setattr': setattr,
                    'type': type, 'print': print, 'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
                    'KeyError': KeyError, 'IndexError': IndexError, 'StopIteration': StopIteration,
                    'iter': iter, 'next': next, 'any': any, 'all': all,
                    'open': open, 'super': super, 'property': property, 'staticmethod': staticmethod, 'classmethod': classmethod,
                    '__import__': __import__, # still needed for imports
                }
            }
            exec(code, {**restricted_builtins, **module.__dict__})
            
            # Get the function
            if skill_name not in module.__dict__:
                logger.error(f"Function {skill_name} not found in generated code")
                return None
            
            skill_fn = module.__dict__[skill_name]
            
            if not callable(skill_fn):
                logger.error(f"{skill_name} is not callable")
                return None
            
            return skill_fn
            
        except Exception as e:
            logger.error(f"Failed to load skill from code: {e}")
            return None


class DynamicSkillSynthesizer:
    """
    Main orchestrator for dynamic skill synthesis.
    
    Coordinates composition, code generation, and runtime registration.
    """
    
    def __init__(self, base_skill_registry: Dict[str, Callable] = None,
                 llm_client=None, auto_register: bool = True):
        """
        Initialize the synthesizer.
        
        Args:
            base_skill_registry: Initial registry of available skills
            llm_client: LLM client for advanced synthesis
            auto_register: Whether to auto-register synthesized skills
        """
        self.base_registry = base_skill_registry or {}
        self.synthesized_skills: Dict[str, SynthesizedSkill] = {}
        self.llm_client = llm_client
        self.auto_register = auto_register
        
        self.composer = SkillComposer(self.base_registry)
        self.code_generator = CodeGenerator(llm_client)
        
        self._synthesis_history: List[Dict] = []
        
        logger.info("DynamicSkillSynthesizer initialized")
    
    def add_base_skill(self, name: str, fn: Callable, signature: Optional[SkillSignature] = None):
        """Add a skill to the base registry."""
        self.base_registry[name] = fn
        self.composer.skill_registry[name] = fn
        logger.debug(f"Added base skill: {name}")
    
    def synthesize_by_composition(self, name: str, description: str,
                                   skill_sequence: List[Tuple[str, Dict]],
                                   tags: List[str] = None) -> SynthesizedSkill:
        """
        Synthesize a new skill by composing existing skills.
        
        Args:
            name: Name for the new skill
            description: Description of the skill
            skill_sequence: Sequence of (skill_name, kwargs) to compose
            tags: Tags for categorization
            
        Returns:
            The synthesized skill
        """
        logger.info(f"Synthesizing composed skill: {name}")
        
        # Validate all skills exist
        for skill_name, _ in skill_sequence:
            if skill_name not in self.base_registry:
                raise ValueError(f"Required skill not found: {skill_name}")
        
        # Create the composed function
        composed_fn = self.composer.compose(name, description, skill_sequence)
        
        # Infer signature from composition
        signature = SkillSignature(
            name=name,
            description=description,
            parameters={"**kwargs": {"type": "Any", "description": "Dynamic parameters"}},
            return_type="Dict[str, Any]",
            tags=tags or [SkillType.COMPOSED.value]
        )
        
        skill = SynthesizedSkill(
            signature=signature,
            skill_type=SkillType.COMPOSED,
            implementation=composed_fn,
            source_skills=[s[0] for s in skill_sequence]
        )
        
        self._register_synthesized_skill(skill)
        self._record_synthesis("composition", name, skill_sequence)
        
        return skill
    
    def synthesize_by_generation(self, name: str, description: str,
                                  parameters: Dict[str, Any],
                                  return_type: str,
                                  requirements: str,
                                  examples: List[str] = None) -> Optional[SynthesizedSkill]:
        """
        Synthesize a new skill by generating code.
        
        Args:
            name: Name for the new skill
            description: Description
            parameters: Parameter definitions
            return_type: Expected return type
            requirements: Natural language requirements
            examples: Example inputs/outputs
            
        Returns:
            The synthesized skill, or None if generation failed
        """
        logger.info(f"Synthesizing generated skill: {name}")
        
        signature = SkillSignature(
            name=name,
            description=description,
            parameters=parameters,
            return_type=return_type,
            examples=examples or [],
            tags=["generated"]
        )
        
        # Generate code
        code = self.code_generator.generate_skill_code(name, signature, requirements, examples)
        
        # Validate code
        is_valid, msg = self.code_generator.validate_code(code)
        if not is_valid:
            logger.error(f"Generated code validation failed: {msg}")
            return None
        
        # Load the function
        skill_fn = self.code_generator.load_skill_from_code(code, name)
        if not skill_fn:
            return None
        
        skill = SynthesizedSkill(
            signature=signature,
            skill_type=SkillType.GENERATED,
            implementation=skill_fn,
            generated_code=code
        )
        
        self._register_synthesized_skill(skill)
        self._record_synthesis("generation", name, {"requirements": requirements})
        
        return skill
    
    def create_macro(self, name: str, description: str,
                     operations: List[Dict[str, Any]]) -> SynthesizedSkill:
        """
        Create a macro skill that executes multiple operations.
        
        Args:
            name: Name for the macro
            description: Description
            operations: List of operation definitions
            
        Returns:
            The macro skill
        """
        def macro_impl(**kwargs) -> Dict[str, Any]:
            results = []
            context = kwargs.copy()
            
            for op in operations:
                op_type = op.get('type')
                op_name = op.get('skill')
                op_args = op.get('args', {})
                
                if op_type == 'skill' and op_name in self.base_registry:
                    # Execute skill
                    skill_fn = self.base_registry[op_name]
                    result = skill_fn(**context, **op_args)
                    if isinstance(result, dict):
                        context.update(result)
                    results.append({'skill': op_name, 'result': result})
                    
                elif op_type == 'transform':
                    # Apply transformation
                    transform_fn = op.get('function')
                    if callable(transform_fn):
                        context = transform_fn(context)
                    results.append({'transform': op_name, 'applied': True})
                    
                elif op_type == 'condition':
                    # Conditional execution
                    condition = op.get('condition')
                    if_eval = op.get('if_true', [])
                    else_eval = op.get('if_false', [])
                    
                    # Evaluate condition against current context
                    condition_met = bool(context.get(condition)) if condition else True
                    sub_ops = if_eval if condition_met else else_eval
                    
                    for sub_op in sub_ops:
                        # Recursively handle sub-operations
                        pass
            
            return {'results': results, 'final_context': context}
        
        signature = SkillSignature(
            name=name,
            description=description,
            parameters={"**kwargs": {"type": "Any", "description": "Input context"}},
            return_type="Dict[str, Any]",
            tags=[SkillType.MACRO.value]
        )
        
        skill = SynthesizedSkill(
            signature=signature,
            skill_type=SkillType.MACRO,
            implementation=macro_impl,
            metadata={"operations": operations}
        )
        
        self._register_synthesized_skill(skill)
        self._record_synthesis("macro", name, {"operation_count": len(operations)})
        
        return skill
    
    def _register_synthesized_skill(self, skill: SynthesizedSkill):
        """Register a synthesized skill."""
        self.synthesized_skills[skill.signature.name] = skill
        
        if self.auto_register:
            self.base_registry[skill.signature.name] = skill.implementation
            self.composer.skill_registry[skill.signature.name] = skill.implementation
        
        logger.info(f"Registered synthesized skill: {skill.signature.name} (type: {skill.skill_type.value})")
    
    def _record_synthesis(self, method: str, name: str, details: Dict):
        """Record a synthesis operation."""
        self._synthesis_history.append({
            'timestamp': time.time(),
            'method': method,
            'name': name,
            'details': details
        })
    
    def get_skill(self, name: str) -> Optional[SynthesizedSkill]:
        """Get a synthesized skill by name."""
        return self.synthesized_skills.get(name)
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """List all synthesized skills."""
        return [
            {
                'name': skill.signature.name,
                'type': skill.skill_type.value,
                'description': skill.signature.description,
                'usage_count': skill.usage_count,
                'success_rate': skill.success_rate,
                'source_skills': skill.source_skills
            }
            for skill in self.synthesized_skills.values()
        ]
    
    def get_synthesis_stats(self) -> Dict[str, Any]:
        """Get statistics about skill synthesis."""
        if not self._synthesis_history:
            return {"total_syntheses": 0}
        
        by_type = {}
        for record in self._synthesis_history:
            method = record['method']
            by_type[method] = by_type.get(method, 0) + 1
        
        avg_success_rate = (
            sum(s.success_rate for s in self.synthesized_skills.values()) / 
            len(self.synthesized_skills)
        ) if self.synthesized_skills else 0
        
        return {
            "total_syntheses": len(self._synthesis_history),
            "by_method": by_type,
            "active_skills": len(self.synthesized_skills),
            "average_success_rate": avg_success_rate,
            "total_usages": sum(s.usage_count for s in self.synthesized_skills.values())
        }


# Singleton instance
skill_synthesizer = DynamicSkillSynthesizer()


def synthesize_composed_skill(name: str, description: str,
                               skill_sequence: List[Tuple[str, Dict]]) -> SynthesizedSkill:
    """Convenience function to synthesize a composed skill."""
    return skill_synthesizer.synthesize_by_composition(name, description, skill_sequence)


def synthesize_generated_skill(name: str, description: str,
                                parameters: Dict, return_type: str,
                                requirements: str) -> Optional[SynthesizedSkill]:
    """Convenience function to synthesize a generated skill."""
    return skill_synthesizer.synthesize_by_generation(
        name, description, parameters, return_type, requirements
    )
