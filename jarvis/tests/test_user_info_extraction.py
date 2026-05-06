"""Test script to verify user info extraction and profile persistence."""
import sys
sys.path.insert(0, '/workspace')

from jarvis.profile.user_profile import get_profile_manager, reset_profile_manager

# Reset to start fresh
reset_profile_manager()

# Get profile manager
profile_mgr = get_profile_manager()

print("Initial profile:")
print(f"  User name: {profile_mgr.current_profile.context.name}")
print(f"  Location: {profile_mgr.current_profile.context.location}")

# Simulate extracting name from chat
profile_mgr.update_context(name="Orchard")
print("\nAfter updating name to 'Orchard':")
print(f"  User name: {profile_mgr.current_profile.context.name}")

# Verify it persists
reset_profile_manager()
profile_mgr2 = get_profile_manager()
print("\nAfter reset (should persist):")
print(f"  User name: {profile_mgr2.current_profile.context.name}")

print("\n✓ Test complete!")
