#!/usr/bin/env python3
"""Test that metadata fields are added without overwriting existing values."""

import tempfile
import yaml
from pathlib import Path
from datetime import datetime, timezone
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.store import update_metadata_in_files


def test_metadata_add_without_overwrite():
    """Test that metadata fields are added only if they don't already exist."""
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
        
        # First update - add new fields
        print("=== First Update: Adding new fields ===")
        count = update_metadata_in_files(md_dir, {"firm_type": "LLC", "source": "web"})
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after first update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        # New fields should be added
        assert meta.get("firm_type") == "LLC", f"Expected firm_type='LLC', got {meta.get('firm_type')}"
        assert meta.get("source") == "web", f"Expected source='web', got {meta.get('source')}"
        
        # Original metadata should be preserved
        assert meta.get("website") == "https://example.com/", "website should be preserved"
        assert meta.get("date") == "2025-01-10T10:00:00Z", "date should be preserved"
        assert meta.get("focus") == "real estate", "focus should be preserved"
        
        print("✓ New fields added, existing fields preserved")
        
        # Second update - try to overwrite existing field (should NOT overwrite)
        print("\n=== Second Update: Attempt to overwrite existing field ===")
        count = update_metadata_in_files(md_dir, {"focus": "THIS SHOULD NOT APPEAR", "loan_type": "construction"})
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after second update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        # Existing focus should NOT be overwritten
        assert meta.get("focus") == "real estate", f"focus should NOT be overwritten, got {meta.get('focus')}"
        
        # New loan_type should be added
        assert meta.get("loan_type") == "construction", f"Expected loan_type='construction', got {meta.get('loan_type')}"
        
        # All previous fields should still be there
        assert meta.get("firm_type") == "LLC", "firm_type should still be present"
        assert meta.get("source") == "web", "source should still be present"
        assert meta.get("website") == "https://example.com/", "website should be preserved"
        assert meta.get("date") == "2025-01-10T10:00:00Z", "date should be preserved"
        
        print("✓ Existing field NOT overwritten, new field added")
        
        print("\n=== Test Summary ===")
        print("✓ New metadata fields are added")
        print("✓ Existing metadata fields are never overwritten")
        print("✓ Original metadata preserved")


def test_metadata_with_none_values():
    """Test that None values in existing metadata are replaced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        # Create a markdown file with None/null values
        md_file = md_dir / "test_company2.md"
        initial_meta = {
            "website": "https://example.com/",
            "date": "2025-01-10T10:00:00Z",
            "focus": None,
            "firm_type": None,
        }
        fm = yaml.safe_dump(initial_meta, sort_keys=False, allow_unicode=True)
        content = f"---\n{fm}---\n\n# Test Company\n\nSome content here."
        md_file.write_text(content, encoding="utf-8")
        
        print("=== Test: Replace None/null values ===")
        
        # Update with values for None fields
        count = update_metadata_in_files(md_dir, {"focus": "commercial", "firm_type": "Partnership"})
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Read and verify
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        
        print(f"Metadata after update:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        # None values should be replaced
        assert meta.get("focus") == "commercial", f"None focus should be replaced, got {meta.get('focus')}"
        assert meta.get("firm_type") == "Partnership", f"None firm_type should be replaced, got {meta.get('firm_type')}"
        
        # Original values preserved
        assert meta.get("website") == "https://example.com/", "website should be preserved"
        assert meta.get("date") == "2025-01-10T10:00:00Z", "date should be preserved"
        
        print("✓ None/null values replaced correctly")


if __name__ == "__main__":
    print("Testing metadata add without overwrite functionality...\n")
    test_metadata_add_without_overwrite()
    print("\n" + "="*50 + "\n")
    test_metadata_with_none_values()
    print("\n" + "="*50)
    print("\n✅ All tests passed!")
