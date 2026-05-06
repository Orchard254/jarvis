# Toolset Audit Report: Redundancies and Overlaps

## Executive Summary

This audit identifies significant redundancies and overlaps in the JARVIS toolset architecture. The primary issues are:

1. **Duplicate Registry Implementations**: Two nearly identical `ToolRegistry` classes
2. **Multiple Execution Paths**: Three different tool execution mechanisms
3. **Conflicting Result Types**: Multiple `ToolResult` definitions
4. **Redundant Global Functions**: Duplicate helper functions across modules

---

## 1. DUPLICATE REGISTRY IMPLEMENTATIONS ⚠️ CRITICAL

### Files Involved:
- `/workspace/jarvis/tools/registry.py` (487 lines)
- `/workspace/jarvis/tools/registry_refactored.py` (487 lines)

### Issues:

#### 1.1 Identical Class Structure
Both files define a `ToolRegistry` class with:
- Same singleton pattern implementation
- Same methods: `register()`, `get()`, `execute()`, `load_from_module()`, `load_all_tools()`
- Same internal data structures: `_tools`, `_loaded_modules`
- Same global helper functions: `get_registry()`, `execute_tool()`, `tool_exists()`, `get_all_schemas()`

#### 1.2 Differences (Minor)
`registry_refactored.py` adds:
- `TOOL_HINTS` dictionary for keyword-based filtering
- `filter_tools_by_hints()` method
- `get_filtered_schemas()` method
- `_validate_tool_name_format()` method
- `_migrate_tool_name()` method for legacy name conversion

#### 1.3 Usage Analysis
```bash
# registry.py usage (20+ imports found):
- jarvis/core/orchestrator.py
- jarvis/core/brain.py
- jarvis/core/runtime.py
- jarvis/execution/tool_runner.py
- jarvis/monitoring/health_check.py
- Multiple test files

# registry_refactored.py usage (1 import found):
- jarvis/tools/resilient_router.py (only imports TOOL_HINTS)
```

### Recommendation:
**MERGE** the two files into a single `registry.py`:
1. Keep `registry.py` as the primary file
2. Add `TOOL_HINTS`, intent gating, and filtering methods from `registry_refactored.py`
3. Add migration logic for legacy tool names
4. Delete `registry_refactored.py` after migration

---

## 2. MULTIPLE TOOL EXECUTION MECHANISMS ⚠️ HIGH

### Files Involved:
- `/workspace/jarvis/tools/registry.py` → `execute_tool()` function
- `/workspace/jarvis/tools/executor.py` → `ToolExecutor` class + `execute_tool()` function
- `/workspace/jarvis/execution/tool_runner.py` → `ToolRunner` class
- `/workspace/jarvis/tools/executor_vision_patch.py` (unclear purpose)

### Issues:

#### 2.1 Execution Path Confusion

**Path A: Direct Registry Execution**
```python
# In jarvis/tools/registry.py (line 285-287)
def execute_tool(name: str, **kwargs) -> ToolResult:
    return get_registry().execute(name, **kwargs)
```

**Path B: Executor Wrapper**
```python
# In jarvis/tools/executor.py (line 219-225)
def execute_tool(tool_name: str, arguments: Dict[str, Any], verify: bool = True) -> ToolResult:
    return get_executor().execute(tool_name, arguments, verify)
```
This wraps Path A but adds:
- Verification logic
- Execution history tracking
- Different parameter signature (`arguments` dict vs `**kwargs`)

**Path C: Async ToolRunner**
```python
# In jarvis/execution/tool_runner.py (line 122-227)
async def execute(self, tool_name: str, params: dict, timeout_ms: float) -> ToolResult:
    # Has its own registry loading
    # Implements async execution with timeout
    # Different ToolResult definition
```

#### 2.2 Parameter Signature Inconsistency

| Mechanism | Parameters | Return Type |
|-----------|-----------|-------------|
| `registry.execute_tool()` | `name, **kwargs` | `ToolResult` (from base.py) |
| `executor.execute_tool()` | `tool_name, arguments: Dict, verify: bool` | `ToolResult` (from base.py) |
| `tool_runner.execute()` | `tool_name, params: Dict, timeout_ms` | `ToolResult` (local definition) |

#### 2.3 Code Duplication in Execution Logic

Both `executor.py` and `tool_runner.py` implement:
- Tool existence checking
- Parameter validation
- Error handling
- Result formatting
- Execution logging

### Recommendation:
**CONSOLIDATE** to a single execution path:
1. Keep `registry.execute()` as the core synchronous execution
2. Make `ToolRunner` use `registry.execute()` internally instead of duplicating logic
3. Remove `executor.py` or make it a thin wrapper around registry
4. Standardize on one `ToolResult` type (use `base.ToolResult`)

---

## 3. CONFLICTING ToolResult DEFINITIONS ⚠️ HIGH

### Files Involved:
- `/workspace/jarvis/tools/base.py` → `class ToolResult`
- `/workspace/jarvis/execution/tool_runner.py` → `class ToolResult` (duplicate!)

### Issues:

#### 3.1 Definition in base.py (lines vary)
```python
@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    exit_code: int = 0
    verified: bool = False
    verify_msg: str = ""
    rollback_actions: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # Runtime-only fields (not serialized)
    tool_name: str = ""
    parameters: dict = field(default_factory=dict)
```

#### 3.2 Definition in tool_runner.py (lines 16-24)
```python
@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    rollback_actions: list = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### 3.3 Inconsistencies
| Field | base.py | tool_runner.py |
|-------|---------|----------------|
| `success` | ✓ | ✓ |
| `output` | ✓ | ✓ |
| `error` | ✓ | ✓ |
| `exit_code` | ✓ | ✗ |
| `verified` | ✓ | ✗ |
| `verify_msg` | ✓ | ✗ |
| `duration_ms` | ✗ | ✓ |
| `rollback_actions` | ✓ | ✓ |
| `metadata` | ✓ | ✓ |
| `tool_name` | ✓ | ✗ |
| `parameters` | ✓ | ✗ |

### Recommendation:
**UNIFY** ToolResult definitions:
1. Keep single definition in `base.py`
2. Add `duration_ms` field to `base.ToolResult`
3. Remove duplicate definition from `tool_runner.py`
4. Import from `base.py` everywhere

---

## 4. REDUNDANT GLOBAL HELPER FUNCTIONS ⚠️ MEDIUM

### Issue:
Both `registry.py` and `registry_refactored.py` define identical global functions:

```python
# In BOTH files:
def get_registry() -> ToolRegistry: ...
def register_tool(tool: BaseTool) -> None: ...
def get_tool(name: str) -> Optional[BaseTool]: ...
def execute_tool(name: str, **kwargs) -> ToolResult: ...
def tool_exists(name: str) -> bool: ...
def get_all_schemas() -> List[dict]: ...
```

Plus `registry_refactored.py` adds:
```python
def filter_tools(user_input: str, max_tools: int = 5) -> Dict[str, BaseTool]: ...
def get_filtered_schemas(user_input: str, max_tools: int = 5) -> List[dict]: ...
```

### Impact:
- Import confusion: Which module should be imported?
- Potential for inconsistent behavior if files diverge
- Increased maintenance burden

### Recommendation:
**REMOVE** duplicate functions after merging registries.

---

## 5. SKILLS REGISTRY OVERLAP ⚠️ MEDIUM

### File: `/workspace/jarvis/skills/registry.py`

### Issue:
The `SkillsRegistry` class mirrors the structure of `ToolRegistry`:
- Same singleton pattern
- Same discovery mechanism (`discover_builtin_skills()`, `discover_learned_skills()`)
- Same registration pattern

However, this may be **intentional separation** since:
- Skills are higher-level abstractions (multi-step workflows)
- Tools are atomic operations
- Skills can use tools internally

### Recommendation:
**REFACTOR** to share common infrastructure:
1. Extract common registry logic into a base `Registry[T]` class
2. Have both `ToolRegistry` and `SkillsRegistry` inherit from it
3. Keep separate discovery logic (different directories/patterns)

---

## 6. UNUSED OR UNCLEAR FILES ⚠️ LOW

### Files to Review:

1. **`/workspace/jarvis/tools/executor_vision_patch.py`**
   - Purpose unclear from name
   - May be temporary patch that's no longer needed
   - **Action**: Review and delete if obsolete

2. **`/workspace/jarvis/tools/validator.py`**
   - Unknown functionality without inspection
   - May overlap with validation in `registry.py` and `executor.py`
   - **Action**: Review for redundancy

3. **`/workspace/jarvis/tools/resilient_router.py`**
   - Only file using `registry_refactored.py`
   - Imports only `TOOL_HINTS` constant
   - **Action**: After merge, update import to use `registry.py`

---

## 7. NAMING INCONSISTENCIES ⚠️ LOW

### Tool Naming Convention Conflict

From `registry_refactored.py`:
- Advocates for `<domain>.<verb>_<object>` format (e.g., `app.open`, `file.read`)
- Includes migration logic for legacy names

Current State:
- Mixed naming in codebase:
  - Legacy: `lock_pc`, `open_app`, `read_file`
  - New: `system.lock_pc`, `app.open`, `file.read`

### Recommendation:
**COMPLETE MIGRATION**:
1. Run migration script to rename all tools
2. Update `TOOL_HINTS` with new names
3. Remove legacy name support after transition period

---

## ACTION PLAN

### Phase 1: Critical (Week 1)
1. [ ] Merge `registry.py` and `registry_refactored.py`
2. [ ] Remove duplicate `ToolResult` from `tool_runner.py`
3. [ ] Update `resilient_router.py` import to use merged registry

### Phase 2: High Priority (Week 2)
4. [ ] Consolidate execution paths (choose one primary mechanism)
5. [ ] Remove or refactor `executor.py`
6. [ ] Standardize parameter signatures across execution methods

### Phase 3: Medium Priority (Week 3)
7. [ ] Extract common registry base class
8. [ ] Refactor `SkillsRegistry` to use base class
9. [ ] Review and clean up unused files

### Phase 4: Cleanup (Week 4)
10. [ ] Complete tool naming migration
11. [ ] Update all documentation
12. [ ] Add integration tests for unified execution path

---

## METRICS

| Category | Count | Severity |
|----------|-------|----------|
| Duplicate Classes | 2 (ToolRegistry) | CRITICAL |
| Duplicate Functions | 8+ global helpers | HIGH |
| Duplicate Data Types | 2 (ToolResult) | HIGH |
| Execution Paths | 3 different mechanisms | HIGH |
| Unclear/Unused Files | 2-3 | LOW |

**Estimated Effort to Resolve**: 40-60 hours
**Risk if Unaddressed**: 
- Maintenance nightmare
- Bug-prone (fixes in one place, not others)
- Developer confusion
- Performance overhead from duplicate loading

---

## APPENDIX: File Dependency Map

```
jarvis/tools/
├── registry.py ← PRIMARY (keep & enhance)
├── registry_refactored.py ← DELETE after merge
├── base.py ← Source of truth for ToolResult
├── executor.py ← CANDIDATE FOR REMOVAL
├── executor_vision_patch.py ← REVIEW for deletion
├── validator.py ← REVIEW for redundancy
└── resilient_router.py ← Update import after merge

jarvis/execution/
└── tool_runner.py ← Remove duplicate ToolResult, use registry.execute()

jarvis/skills/
└── registry.py ← Refactor to share base registry class
```

