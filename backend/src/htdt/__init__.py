"""Home Theater Digital Twin backend."""

__version__ = "0.1.0.dev0"

from .migration_guard import install_migration_guard

install_migration_guard()
