#!/usr/bin/env python3
"""Test the metadata appending functionality in update_metadata_in_files."""

import tempfile
import yaml
from pathlib import Path
from datetime import datetime, timezone
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.store import update_metadata_in_files


def test_metadata_append_mode():
    """Test that metadata updates are appended instead of overwritten."""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        # Create a markdown file with initial metadata
        md_file = md_dir / "test_company.md"
        initial_meta = {
            "website": "https://example.com/",
            "date": "2025-01-10T10:00:00Z",
            "focus": "real estate",
        }
        fm = yaml.safe_dump(initial_meta, sort_keys=False, allow_unicode=True)
        content = f"---\n{fm}---\n\n# Test Company\n\nSome content here."
        md_file.write_text(content, encoding="utf-8")
        
        # First update
        print("=== First Update ===")
        count = update_metadata_in_files(md_dir, {"firm_type": "LLC", "source": "web"}, append_mode=True)
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify first update was appended
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after first update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        assert "metadata_updates" in meta, "metadata_updates list should be created"
        assert isinstance(meta["metadata_updates"], list), "metadata_updates should be a list"
        assert len(meta["metadata_updates"]) == 1, f"Expected 1 update entry, got {len(meta['metadata_updates'])}"
        
        first_update = meta["metadata_updates"][0]
        assert first_update.get("firm_type") == "LLC", f"Expected firm_type='LLC', got {first_update.get('firm_type')}"
        assert first_update.get("source") == "web", f"Expected source='web', got {first_update.get('source')}"
        assert "updated_at" in first_update, "updated_at timestamp should be present"
        
        # Verify original metadata is preserved
        assert meta.get("website") == "https://example.com/", "website should be preserved"
        assert meta.get("date") == "2025-01-10T10:00:00Z", "date should be preserved"
        assert meta.get("focus") == "real estate", "focus should be preserved"
        
        print("✓ First update appended correctly with timestamp")
        
        # Second update
        print("\n=== Second Update ===")
        count = update_metadata_in_files(md_dir, {"focus": "commercial real estate", "loan_type": "construction"}, append_mode=True)
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify second update was also appended
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after second update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        assert len(meta["metadata_updates"]) == 2, f"Expected 2 update entries, got {len(meta['metadata_updates'])}"
        
        second_update = meta["metadata_updates"][1]
        # Note: "commercial real estate" is a single string without commas, so it stays as string
        assert second_update.get("focus") == "commercial real estate", f"Expected focus string, got {second_update.get('focus')}"
        assert second_update.get("loan_type") == "construction", f"Expected loan_type='construction', got {second_update.get('loan_type')}"
        assert "updated_at" in second_update, "updated_at timestamp should be present"
        
        print("✓ Second update appended correctly")
        
        # Verify first update is still there and unchanged
        assert meta["metadata_updates"][0].get("firm_type") == "LLC", "First update should be unchanged"
        
        print("\n=== Test Summary ===")
        print("✓ All metadata updates appended successfully")
        print("✓ Each update has a timestamp")
        print("✓ Original metadata preserved")
        print("✓ Multiple updates tracked in order")


def test_metadata_overwrite_mode():
    """Test that overwrite mode still works for backward compatibility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        # Create a markdown file with initial metadata
        md_file = md_dir / "test_company2.md"
        initial_meta = {
            "website": "https://example.com/",
            "date": "2025-01-10T10:00:00Z",
            "focus": "real estate",
            "firm_type": "old_value",
        }
        fm = yaml.safe_dump(initial_meta, sort_keys=False, allow_unicode=True)
        content = f"---\n{fm}---\n\n# Test Company\n\nSome content here."
        md_file.write_text(content, encoding="utf-8")
        
        # Update with overwrite mode
        print("=== Overwrite Mode Test ===")
        count = update_metadata_in_files(md_dir, {"firm_type": "new_value", "source": "web"}, append_mode=False)
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after overwrite update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        # In overwrite mode, metadata should be directly updated (old behavior)
        assert meta.get("firm_type") == "new_value", f"Expected firm_type to be overwritten to 'new_value', got {meta.get('firm_type')}"
        assert meta.get("source") == "web", f"Expected source='web', got {meta.get('source')}"
        # metadata_updates should NOT be created in overwrite mode
        assert "metadata_updates" not in meta or len(meta.get("metadata_updates", [])) == 0, "metadata_updates should not be used in overwrite mode"
        
        print("✓ Overwrite mode works correctly (backward compatible)")


if __name__ == "__main__":
    print("Testing metadata appending functionality...\n")
    test_metadata_append_mode()
    print("\n" + "="*50 + "\n")
    test_metadata_overwrite_mode()
    print("\n" + "="*50)
    print("\n✅ All tests passed!")
