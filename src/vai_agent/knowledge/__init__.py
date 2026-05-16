"""Knowledge layer: profile models, loader, and validators.

``profile_generator`` (Phase 3) is intentionally **not** re-exported
here because it imports from :mod:`vai_agent.db.schema_extractor`,
which itself depends on :mod:`vai_agent.knowledge.profile_models`.
Re-exporting would create a circular import via this ``__init__``.
Consumers must import the generator's public helpers from the
submodule directly::

    from vai_agent.knowledge.profile_generator import (
        generate_profile, read_schema_file, write_profile_to_disk,
    )
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
