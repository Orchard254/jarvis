"""
Phase 3: Skill Versioning & A/B Testing Framework

Enables deploying multiple versions of skills, routing traffic between them,
and comparing performance to identify the best implementation.
"""
import time
import json
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import os
import random

logger = logging.getLogger(__name__)

class DeploymentStatus(Enum):
    DRAFT = "draft"
    CANARY = "canary"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

@dataclass
class SkillVersion:
    skill_name: str
    version: str  # e.g., "v1.0.0", "v2.0.0-beta"
    implementation_hash: str
    created_at: float = field(default_factory=time.time)
    status: DeploymentStatus = DeploymentStatus.DRAFT
    traffic_percentage: float = 0.0  # 0.0 to 100.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['status'] = self.status.value
        return d

@dataclass
class ABTestResult:
    test_id: str
    skill_name: str
    version_a: str
    version_b: str
    start_time: float
    end_time: Optional[float] = None
    metrics_a: Dict[str, float] = field(default_factory=dict)
    metrics_b: Dict[str, float] = field(default_factory=dict)
    winner: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> dict:
        d = asdict(self)
        if self.end_time is None:
            d['end_time'] = None
        return d

class VersionRegistry:
    """Manages skill versions and traffic routing."""
    
    def __init__(self, storage_path: str = "output/skill_versions.json"):
        self.storage_path = storage_path
        self.versions: Dict[str, List[SkillVersion]] = {}  # skill_name -> [versions]
        self.active_tests: Dict[str, ABTestResult] = {}
        self._ensure_storage_dir()
        self._load_existing()
        
    def _ensure_storage_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
    def _load_existing(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for skill_name, versions_data in data.get('versions', {}).items():
                        self.versions[skill_name] = []
                        for v_data in versions_data:
                            v_data['status'] = DeploymentStatus(v_data['status'])
                            self.versions[skill_name].append(SkillVersion(**v_data))
                    
                    for test_id, test_data in data.get('tests', {}).items():
                        self.active_tests[test_id] = ABTestResult(**test_data)
                        
                logger.info(f"Loaded {len(self.versions)} skills with versions")
            except Exception as e:
                logger.error(f"Failed to load version registry: {e}")

    def _persist(self):
        try:
            data = {
                'versions': {k: [v.to_dict() for v in v_list] for k, v_list in self.versions.items()},
                'tests': {k: v.to_dict() for k, v in self.active_tests.items()}
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist version registry: {e}")

    def register_version(self, skill_name: str, version: str, implementation_func: Callable, 
                         status: DeploymentStatus = DeploymentStatus.DRAFT,
                         metadata: Optional[Dict[str, Any]] = None) -> SkillVersion:
        """Register a new version of a skill."""
        # Create hash of implementation
        impl_hash = hashlib.sha256(implementation_func.__code__.co_code).hexdigest()[:12]
        
        skill_version = SkillVersion(
            skill_name=skill_name,
            version=version,
            implementation_hash=impl_hash,
            status=status,
            metadata=metadata or {}
        )
        
        if skill_name not in self.versions:
            self.versions[skill_name] = []
            
        self.versions[skill_name].append(skill_version)
        self._persist()
        
        logger.info(f"Registered {skill_name} {version} (hash: {impl_hash})")
        return skill_version

    def get_active_versions(self, skill_name: str) -> List[SkillVersion]:
        """Get all active/canary versions for traffic routing."""
        if skill_name not in self.versions:
            return []
        return [
            v for v in self.versions[skill_name]
            if v.status in (DeploymentStatus.ACTIVE, DeploymentStatus.CANARY)
        ]

    def select_version(self, skill_name: str) -> Optional[SkillVersion]:
        """Select a version based on traffic percentages."""
        active_versions = self.get_active_versions(skill_name)
        if not active_versions:
            return None
            
        if len(active_versions) == 1:
            return active_versions[0]
            
        # Weighted random selection based on traffic percentage
        total_traffic = sum(v.traffic_percentage for v in active_versions)
        if total_traffic == 0:
            # Equal distribution if no percentages set
            return random.choice(active_versions)
            
        rand_val = random.uniform(0, total_traffic)
        cumulative = 0
        for version in active_versions:
            cumulative += version.traffic_percentage
            if rand_val <= cumulative:
                return version
                
        return active_versions[-1]

    def create_ab_test(self, skill_name: str, version_a: str, version_b: str,
                       test_duration_hours: float = 24.0) -> ABTestResult:
        """Create an A/B test between two versions."""
        test_id = f"{skill_name}_{version_a}_vs_{version_b}_{int(time.time())}"
        
        test_result = ABTestResult(
            test_id=test_id,
            skill_name=skill_name,
            version_a=version_a,
            version_b=version_b,
            start_time=time.time()
        )
        
        self.active_tests[test_id] = test_result
        self._persist()
        
        logger.info(f"Created A/B test {test_id}")
        return test_result

    def record_metric(self, test_id: str, version: str, metric_name: str, value: float):
        """Record a metric for an A/B test."""
        if test_id not in self.active_tests:
            logger.warning(f"Test {test_id} not found")
            return
            
        test = self.active_tests[test_id]
        if version == test.version_a:
            if metric_name not in test.metrics_a:
                test.metrics_a[metric_name] = 0
            test.metrics_a[metric_name] += value
        elif version == test.version_b:
            if metric_name not in test.metrics_b:
                test.metrics_b[metric_name] = 0
            test.metrics_b[metric_name] += value
            
        self._persist()

    def conclude_test(self, test_id: str, winner: str, confidence: float):
        """Conclude an A/B test with a winner."""
        if test_id not in self.active_tests:
            return
            
        test = self.active_tests[test_id]
        test.end_time = time.time()
        test.winner = winner
        test.confidence = confidence
        
        self._persist()
        logger.info(f"Concluded A/B test {test_id}: {winner} wins ({confidence:.2%} confidence)")

# Global instance
version_registry = VersionRegistry()

def get_registry() -> VersionRegistry:
    return version_registry
