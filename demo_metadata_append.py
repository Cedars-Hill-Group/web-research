#!/usr/bin/env python3
"""
Integration test demonstrating the append metadata feature in a realistic scenario.
Shows how metadata updates accumulate over time with timestamps.
"""

import tempfile
import yaml
from pathlib import Path
from src.store import update_metadata_in_files, write_markdown, default_metadata


def demo_metadata_appending():
    """Demonstrate the metadata appending workflow."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        md_dir = Path(tmpdir) / "company-markdown"
        md_dir.mkdir()
        
        print("=" * 70)
        print("METADATA APPENDING DEMO")
        print("=" * 70)
        
        # Step 1: Create initial company file with default metadata
        print("\n[STEP 1] Creating initial company file...")
        meta = default_metadata("https://example-company.com")
        print(f"Initial metadata:\n{yaml.safe_dump(meta, default_flow_style=False)}")
        
        md_file = md_dir / "page1.md"
        write_markdown(md_dir, "page1", "# Example Company\n\nInitial company information.", meta)
        
        print(f"✓ File created: {md_file.name}")
        
        # Step 2: First metadata update - add firm type and source
        print("\n[STEP 2] First metadata update: Adding firm_type and source...")
        count = update_metadata_in_files(
            md_dir,
            {"firm_type": "Commercial Real Estate Firm", "source": "web_research"},
            append_mode=True
        )
        print(f"✓ Updated {count} file(s)")
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        current_meta = yaml.safe_load(parts[1])
        print(f"Updated metadata:\n{yaml.safe_dump(current_meta, default_flow_style=False)}")
        
        # Step 3: Second metadata update - add property type and loan type
        print("\n[STEP 3] Second metadata update: Adding property and loan types...")
        count = update_metadata_in_files(
            md_dir,
            {"prop_type": "Office, Multi-Family", "loan_type": "Construction, Bridge"},
            append_mode=True
        )
        print(f"✓ Updated {count} file(s)")
        
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        current_meta = yaml.safe_load(parts[1])
        print(f"Updated metadata:\n{yaml.safe_dump(current_meta, default_flow_style=False)}")
        
        # Step 4: Third metadata update - update focus
        print("\n[STEP 4] Third metadata update: Updating focus...")
        count = update_metadata_in_files(
            md_dir,
            {"focus": "Acquisition and Development"},
            append_mode=True
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
        
        updates = current_meta.get("metadata_updates", [])
        print(f"\nTotal metadata updates recorded: {len(updates)}")
        print("\nUpdate History:")
        for i, update in enumerate(updates, 1):
            print(f"\n  Update {i} (at {update.get('updated_at', 'unknown')}):")
            for key, value in sorted(update.items()):
                if key != 'updated_at':
                    print(f"    - {key}: {value}")
        
        print("\n✓ Original metadata preserved:")
        for key in ["website", "date"]:
            if key in current_meta:
                print(f"    - {key}: {current_meta[key]}")
        
        print("\n✓ Current active metadata values:")
        for key in ["focus", "firm_type"]:
            if key in current_meta:
                print(f"    - {key}: {current_meta[key]}")
        
        print("\n" + "=" * 70)
        print("✅ Demo complete - metadata was appended with timestamps!")
        print("=" * 70)


if __name__ == "__main__":
    demo_metadata_appending()
