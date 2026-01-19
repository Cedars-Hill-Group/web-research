#!/usr/bin/env python3
"""
Demo showing how metadata is added to existing files without overwriting.
New fields are added only if they don't already exist or are None/null.
"""

import tempfile
import yaml
from pathlib import Path
from src.store import update_metadata_in_files, write_markdown, default_metadata


def demo_metadata_add_without_overwrite():
    """Demonstrate the metadata add-only workflow."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir) / "company-markdown"
        md_dir.mkdir()
        
        print("=" * 70)
        print("METADATA ADD-ONLY DEMO (NO OVERWRITING)")
        print("=" * 70)
        
        # Step 1: Create initial company file with default metadata
        print("\n[STEP 1] Creating initial company file...")
        meta = default_metadata("https://example-company.com")
        print(f"Initial metadata:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        md_file = md_dir / "page1.md"
        write_markdown(md_dir, "page1", "# Example Company\n\nInitial company information.", meta)
        
        print(f"✓ File created: {md_file.name}")
        
        # Step 2: First metadata update - add firm type and source
        print("\n[STEP 2] First update: Adding firm_type and source...")
        count = update_metadata_in_files(
            md_dir,
            {"firm_type": "Commercial Real Estate Firm", "source": "web_research"}
        )
        print(f"✓ Updated {count} file(s)")
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        current_meta = yaml.safe_load(parts[1])
        print(f"Updated metadata:\n{yaml.safe_dump(current_meta, default_flow_style=False)}")
        
        # Step 3: Second metadata update - add property type and loan type
        print("\n[STEP 3] Second update: Adding property and loan types...")
        count = update_metadata_in_files(
            md_dir,
            {"prop_type": "Office, Multi-Family", "loan_type": "Construction, Bridge"}
        )
        print(f"✓ Updated {count} file(s)")
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        current_meta = yaml.safe_load(parts[1])
        print(f"Updated metadata:\n{yaml.safe_dump(current_meta, default_flow_style=False)}")
        
        # Step 4: Try to update existing focus (should NOT overwrite)
        print("\n[STEP 4] Third update: Attempting to change firm_type (should be ignored)...")
        print("Sending update: firm_type='THIS SHOULD NOT APPEAR'")
        count = update_metadata_in_files(
            md_dir,
            {"firm_type": "THIS SHOULD NOT APPEAR", "focus": "Acquisition"}
        )
        print(f"✓ Updated {count} file(s)")
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        current_meta = yaml.safe_load(parts[1])
        print(f"Updated metadata:\n{yaml.safe_dump(current_meta, default_flow_style=False)}")
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        print("\n✓ Final metadata state:")
        for key, value in sorted(current_meta.items()):
            print(f"  - {key}: {value}")
        
        print("\n✓ Key observations:")
        print(f"  - firm_type kept original value: '{current_meta.get('firm_type')}'")
        print(f"  - focus was added (was None): '{current_meta.get('focus')}'")
        print(f"  - date preserved from initial creation: '{current_meta.get('date')}'")
        print(f"  - All new fields were added successfully")
        
        print("\n" + "=" * 70)
        print("✅ Demo complete - metadata added without overwriting existing values!")
        print("=" * 70)


if __name__ == "__main__":
    demo_metadata_add_without_overwrite()
