import sys
import importlib.metadata

try:
    print(f"importlib.metadata has packages_distributions: {hasattr(importlib.metadata, 'packages_distributions')}")
    importlib.metadata.packages_distributions()
except AttributeError as e:
    print(f"Caught expected error: {e}")

try:
    import importlib_metadata
    print("importlib_metadata is installed")
    print(f"importlib_metadata has packages_distributions: {hasattr(importlib_metadata, 'packages_distributions')}")
except ImportError:
    print("importlib_metadata is NOT installed")
