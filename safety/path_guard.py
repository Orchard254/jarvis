"""
Single source of truth for sensitive path fragments and blocked-path checking.

All tools that read/write files should import from here instead of defining
their own copy of the fragment list.
"""

from pathlib import Path

SENSITIVE_PATH_FRAGMENTS = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".gpg",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
    "known_hosts",
    ".netrc",
    ".pgpass",
    "credentials",
    ".kube/config",
    "kubeconfig",
)


def contains_sensitive_path(p: Path) -> bool:
    """Return True if *p* matches any sensitive path fragment."""
    normalized = p.as_posix().lower()
    return any(frag in normalized for frag in SENSITIVE_PATH_FRAGMENTS)
