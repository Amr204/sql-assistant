"""Knowledge layer: profile models, loader, and validators.

Phase 2 deliverable. Generation of profiles from a SQL schema (and the
related ``schema_extractor`` / ``profile_generator`` modules) is planned
for a later phase and is intentionally not exposed here yet.
"""

from vai_agent.knowledge.profile_loader import (
    ProfileError,
    ProfileFileError,
    ProfileLoader,
    ProfileNotFoundError,
)
from vai_agent.knowledge.profile_models import Profile
from vai_agent.knowledge.validators import (
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_profile,
)

__all__ = [
    "Profile",
    "ProfileError",
    "ProfileFileError",
    "ProfileLoader",
    "ProfileNotFoundError",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "validate_profile",
]
