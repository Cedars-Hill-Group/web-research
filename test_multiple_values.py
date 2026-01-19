#!/usr/bin/env python3
"""Test that source, focus, and firm_type support multiple comma-separated values."""

import tempfile
import yaml
from pathlib import Path
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.store import update_metadata_in_files, default_metadata, write_markdown


def test_multiple_values_in_metadata():
    """Test that focus, firm_type, and source accept multiple comma-separated values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir)
        
        print("=" * 70)
        print("Testing Multiple Values for focus, firm_type, and source")
        print("=" * 70)
        
        # Test 1: default_metadata with comma-separated values
        print("\n[TEST 1] Creating metadata with comma-separated values...")
        meta = default_metadata(
            "https://example.com/",
            focus="commercial real estate, residential, industrial",
            firm_type="LLC, Partnership",
            source="web, linkedin, company website"
        )
        
        print("Generated metadata:")
        print(yaml.safe_dump(meta, default_flow_style=False))
        
        assert isinstance(meta["focus"], list), f"focus should be a list, got {type(meta['focus'])}"
        assert len(meta["focus"]) == 3, f"focus should have 3 items, got {len(meta['focus'])}"
        assert meta["focus"] == ["commercial real estate", "residential", "industrial"]
        
        assert isinstance(meta["firm_type"], list), f"firm_type should be a list, got {type(meta['firm_type'])}"
        assert len(meta["firm_type"]) == 2, f"firm_type should have 2 items, got {len(meta['firm_type'])}"
        assert meta["firm_type"] == ["LLC", "Partnership"]
        
        assert isinstance(meta["source"], list), f"source should be a list, got {type(meta['source'])}"
        assert len(meta["source"]) == 3, f"source should have 3 items, got {len(meta['source'])}"
        assert meta["source"] == ["web", "linkedin", "company website"]
        
        print("✓ All fields correctly converted to lists")
        
        # Test 2: update_metadata_in_files with comma-separated values
        print("\n[TEST 2] Updating file with comma-separated values...")
        
        md_file = md_dir / "test.md"
        initial_meta = {
            "website": "https://test.com/",
            "date": "2025-01-10T10:00:00Z",
        }
        fm = yaml.safe_dump(initial_meta, sort_keys=False, allow_unicode=True)
        content = f"---\n{fm}---\n\n# Test"
        md_file.write_text(content, encoding="utf-8")
        
        # Update with comma-separated values
        count = update_metadata_in_files(md_dir, {
            "focus": "acquisition, development, asset management",
            "firm_type": "Private Equity, Real Estate Investment Trust",
            "source": "direct research, third party, public filings"
        })
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        updated_meta = yaml.safe_load(parts[1])
        
        print("Updated metadata:")
        print(yaml.safe_dump(updated_meta, default_flow_style=False))
        
        assert isinstance(updated_meta["focus"], list), f"focus should be a list, got {type(updated_meta['focus'])}"
        assert len(updated_meta["focus"]) == 3
        assert updated_meta["focus"] == ["acquisition", "development", "asset management"]
        
        assert isinstance(updated_meta["firm_type"], list), f"firm_type should be a list"
        assert len(updated_meta["firm_type"]) == 2
        assert updated_meta["firm_type"] == ["Private Equity", "Real Estate Investment Trust"]
        
        assert isinstance(updated_meta["source"], list), f"source should be a list"
        assert len(updated_meta["source"]) == 3
        assert updated_meta["source"] == ["direct research", "third party", "public filings"]
        
        print("✓ All fields correctly updated as lists")
        
        # Test 3: Single values (no commas) should remain as strings
        print("\n[TEST 3] Testing single values remain as strings...")
        
        md_file2 = md_dir / "test2.md"
        single_meta = default_metadata(
            "https://single.com/",
            focus="commercial real estate",
            firm_type="LLC",
            source="web"
        )
        
        print("Single value metadata:")
        print(yaml.safe_dump(single_meta, default_flow_style=False))
        
        assert isinstance(single_meta["focus"], str), f"Single focus should be string, got {type(single_meta['focus'])}"
        assert single_meta["focus"] == "commercial real estate"
        
        assert isinstance(single_meta["firm_type"], str), f"Single firm_type should be string"
        assert single_meta["firm_type"] == "LLC"
        
        assert isinstance(single_meta["source"], str), f"Single source should be string"
        assert single_meta["source"] == "web"
        
        print("✓ Single values correctly remain as strings")
        
        print("\n" + "=" * 70)
        print("✅ All tests passed!")
        print("=" * 70)


if __name__ == "__main__":
    test_multiple_values_in_metadata()
