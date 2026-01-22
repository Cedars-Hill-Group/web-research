#!/usr/bin/env python3
"""Test script to verify metadata appending behavior for focus, firm_type, etc."""

import tempfile
from pathlib import Path
import yaml
from src.store import (
    write_markdown, 
    update_metadata_in_files, 
    append_to_list_field,
    normalize_list_field
)


def test_append_to_list_field():
    """Test the append_to_list_field function."""
    print("Testing append_to_list_field()...")
    
    # Test 1: Append to None
    result = append_to_list_field(None, "Value1")
    assert result == "Value1", f"Expected 'Value1', got {result}"
    print("  ✓ Append to None returns single value")
    
    # Test 2: Append to single value
    result = append_to_list_field("Existing", "New")
    assert result == ["Existing", "New"], f"Expected ['Existing', 'New'], got {result}"
    print("  ✓ Append to single value creates list")
    
    # Test 3: Append to list
    result = append_to_list_field(["Existing"], "New")
    assert result == ["Existing", "New"], f"Expected ['Existing', 'New'], got {result}"
    print("  ✓ Append to list works")
    
    # Test 4: Append duplicate (case-insensitive)
    result = append_to_list_field(["Existing"], "existing")
    assert result == "Existing", f"Expected 'Existing', got {result}"
    print("  ✓ Duplicate detection works (case-insensitive)")
    
    # Test 5: Append multiple values
    result = append_to_list_field("Existing", "New1, New2")
    assert result == ["Existing", "New1", "New2"], f"Expected ['Existing', 'New1', 'New2'], got {result}"
    print("  ✓ Append multiple comma-separated values")


def test_update_metadata_in_files():
    """Test the update_metadata_in_files function."""
    print("\nTesting update_metadata_in_files()...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        # Create a test markdown file with existing focus
        meta = {
            "website": "https://example.com/",
            "date": "2025-01-10T10:00:00Z",
            "focus": "Commercial Real Estate",
            "firm_type": None,
        }
        content = "Test content"
        
        test_file = md_dir / "test.md"
        fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        test_file.write_text(f"---\n{fm}---\n\n{content}", encoding="utf-8")
        
        print("  Initial file focus:", meta["focus"])
        
        # Update with new focus values
        updates = {
            "focus": "Healthcare",
            "firm_type": "Venture Capital"
        }
        count = update_metadata_in_files(md_dir, updates)
        assert count == 1, f"Expected 1 file updated, got {count}"
        print("  ✓ update_metadata_in_files() updated 1 file")
        
        # Read back and check
        updated_text = test_file.read_text(encoding="utf-8")
        parts = updated_text.split("---", 2)
        updated_meta = yaml.safe_load(parts[1])
        
        # Focus should be appended
        assert isinstance(updated_meta["focus"], list), f"Expected list for focus, got {type(updated_meta['focus'])}"
        assert "Commercial Real Estate" in updated_meta["focus"], "Original focus value missing"
        assert "Healthcare" in updated_meta["focus"], "New focus value missing"
        print("  ✓ Focus was appended:", updated_meta["focus"])
        
        # Firm_type should be added (was None)
        assert updated_meta["firm_type"] == "Venture Capital", f"Expected 'Venture Capital', got {updated_meta['firm_type']}"
        print("  ✓ Firm_type was added:", updated_meta["firm_type"])
        
        # Date should be preserved
        assert updated_meta["date"] == "2025-01-10T10:00:00Z", "Date was modified"
        print("  ✓ Date was preserved:", updated_meta["date"])
        
        # Test updating again with duplicate
        updates2 = {
            "focus": "Commercial Real Estate",  # This is already there
            "firm_type": "Private Equity"  # This should be added
        }
        count = update_metadata_in_files(md_dir, updates2)
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        updated_text = test_file.read_text(encoding="utf-8")
        parts = updated_text.split("---", 2)
        updated_meta = yaml.safe_load(parts[1])
        
        # Focus should not have duplicates
        assert updated_meta["focus"].count("Commercial Real Estate") == 1, "Duplicate in focus list"
        assert "Healthcare" in updated_meta["focus"], "Healthcare focus missing after second update"
        print("  ✓ Duplicate focus value not added")
        
        # Firm_type should be appended
        assert isinstance(updated_meta["firm_type"], list), f"Expected list for firm_type, got {type(updated_meta['firm_type'])}"
        assert "Venture Capital" in updated_meta["firm_type"], "First firm_type value missing"
        assert "Private Equity" in updated_meta["firm_type"], "Second firm_type value missing"
        print("  ✓ Firm_type was appended:", updated_meta["firm_type"])


def test_merge_scenario():
    """Test a realistic merge scenario."""
    print("\nTesting merge scenario...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        # Simulate first batch processing: focus = "Healthcare"
        meta1 = {
            "website": "https://example.com/",
            "date": "2025-01-10T10:00:00Z",
            "focus": "Healthcare",
            "firm_type": "Consulting",
        }
        test_file = md_dir / "page1.md"
        fm = yaml.safe_dump(meta1, sort_keys=False, allow_unicode=True)
        test_file.write_text(f"---\n{fm}---\n\nFirst page content", encoding="utf-8")
        
        # Simulate second batch processing: user enters focus = "Commercial Real Estate, Technology"
        updates = {
            "focus": "Commercial Real Estate, Technology",
            "firm_type": "Investment Banking",
        }
        count = update_metadata_in_files(md_dir, updates)
        assert count == 1, f"Expected 1 file updated, got {count}"
        
        # Verify
        updated_text = test_file.read_text(encoding="utf-8")
        parts = updated_text.split("---", 2)
        updated_meta = yaml.safe_load(parts[1])
        
        print("  Updated focus:", updated_meta["focus"])
        print("  Updated firm_type:", updated_meta["firm_type"])
        
        assert isinstance(updated_meta["focus"], list), f"Expected list, got {type(updated_meta['focus'])}"
        assert len(updated_meta["focus"]) == 3, f"Expected 3 focus values, got {len(updated_meta['focus'])}"
        assert "Healthcare" in updated_meta["focus"], "Healthcare missing"
        assert "Commercial Real Estate" in updated_meta["focus"], "Commercial Real Estate missing"
        assert "Technology" in updated_meta["focus"], "Technology missing"
        
        assert isinstance(updated_meta["firm_type"], list), f"Expected list, got {type(updated_meta['firm_type'])}"
        assert len(updated_meta["firm_type"]) == 2, f"Expected 2 firm_type values, got {len(updated_meta['firm_type'])}"
        assert "Consulting" in updated_meta["firm_type"], "Consulting missing"
        assert "Investment Banking" in updated_meta["firm_type"], "Investment Banking missing"
        
        print("  ✓ Realistic merge scenario works correctly")


if __name__ == "__main__":
    test_append_to_list_field()
    test_update_metadata_in_files()
    test_merge_scenario()
    print("\n✅ All tests passed!")
