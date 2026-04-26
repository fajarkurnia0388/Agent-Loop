"""Debug script to check logging handlers"""
import sys
from pathlib import Path
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import senior_tools

print("=" * 80)
print("Debugging logging handlers...")
print("=" * 80)

# Get root logger
root_logger = logging.getLogger()
print(f"\nRoot logger: {root_logger}")
print(f"Root logger handlers: {len(root_logger.handlers)}")

for i, handler in enumerate(root_logger.handlers):
    print(f"\nHandler {i}: {handler}")
    print(f"  Type: {type(handler).__name__}")
    if hasattr(handler, 'baseFilename'):
        print(f"  File: {handler.baseFilename}")
    if hasattr(handler, 'stream'):
        print(f"  Stream: {handler.stream}")

# Get senior_tools logger
st_logger = logging.getLogger('senior_tools')
print(f"\nsenior_tools logger: {st_logger}")
print(f"senior_tools logger handlers: {len(st_logger.handlers)}")

for i, handler in enumerate(st_logger.handlers):
    print(f"\nHandler {i}: {handler}")
    print(f"  Type: {type(handler).__name__}")
    if hasattr(handler, 'baseFilename'):
        print(f"  File: {handler.baseFilename}")

# Get __main__ logger
main_logger = logging.getLogger('__main__')
print(f"\n__main__ logger: {main_logger}")
print(f"__main__ logger handlers: {len(main_logger.handlers)}")

print("\n" + "=" * 80)

