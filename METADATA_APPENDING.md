# Metadata Add-Only Implementation

## Overview
Modified the database file update mechanism to **add new metadata fields without overwriting existing ones**. This ensures that existing metadata values are never lost when new information is added.

## Changes Made

### 1. **Updated `src/store.py`**
   - Modified `update_metadata_in_files()` function to only add metadata that doesn't already exist
   - Existing metadata fields are **never overwritten** (except when their value is `None`/null)
   - No timestamps or metadata_updates lists - just clean, direct metadata

### 2. **Fixed Python 3.8+ Compatibility**
   - Added `from __future__ import annotations` for type hint compatibility
   - Replaced `UTC` (Python 3.11+) with `timezone.utc` in:
     - `src/store.py`
     - `src/main.py`
     - `src/ui_tui.py`

## How It Works

### Add-Only Behavior (Never Overwrites)

When metadata is updated using `update_metadata_in_files()`:

**Initial File:**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: null
firm_type: null
---
```

**After First Update (firm_type, source added):**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: null
firm_type: Commercial Real Estate
source: web
---
```

**After Second Update (trying to change firm_type, adding loan_type):**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: null
firm_type: Commercial Real Estate    # NOT CHANGED (original value preserved)
loan_type: construction               # ADDED (new field)
source: web
---
```

### Key Features

✅ **Never Overwrites**: Existing metadata values are always preserved
✅ **Add Only**: New fields are added only if they don't exist or are None/null
✅ **Date Protection**: Original date is always preserved
✅ **Multiple Values Support**: All metadata fields (focus, firm_type, source, prop_type, loan_type) support comma-separated values that become YAML lists
✅ **Simple & Clean**: No timestamps, no history lists, just straightforward metadata
✅ **Predictable**: If a field has a value, it will never change

## Multiple Values Support

All metadata fields can accept **comma-separated values** which are automatically converted to YAML lists:

```python
# Single value - stored as string
updates = {"focus": "commercial real estate"}
# Result: focus: commercial real estate

# Multiple values - stored as list
updates = {"focus": "commercial real estate, residential, industrial"}
# Result:
# focus:
#   - commercial real estate
#   - residential
#   - industrial

# Works for all fields
updates = {
    "focus": "acquisition, development",
    "firm_type": "LLC, Partnership",
    "source": "web, linkedin, direct research",
    "prop_type": "Office, Retail, Industrial",
    "loan_type": "Construction, Bridge, Permanent"
}
```

## Function Signature

```python
def update_metadata_in_files(md_dir: Path, updates: dict) -> int:
    """Update metadata fields in existing markdown files.
    
    Only adds new metadata fields that don't already exist or have None/null values.
    Never overwrites existing metadata values (except date which is preserved separately).
    
    Args:
        md_dir: Path to directory containing markdown files
        updates: Dict of metadata fields to add
    
    Returns:
        Number of files updated
    """
```

## Usage Example

```python
from pathlib import Path
from src.store import update_metadata_in_files

md_dir = Path("data/companies/example-company/markdown")
updates = {
    "firm_type": "LLC",
    "source": "web"
}

# New metadata fields will be added, existing ones preserved
count = update_metadata_in_files(md_dir, updates)
print(f"Updated {count} files")
```

## Behavior Rules

1. **New Field**: If metadata field doesn't exist → ADD IT
2. **Existing Field with Value**: If metadata field exists and has a value → KEEP ORIGINAL
3. **Existing Field with None/null**: If metadata field is None/null → REPLACE WITH NEW VALUE
4. **Date Field**: Always preserve existing date, never overwrite

## Benefits

1. **No Data Loss**: Existing metadata is never accidentally overwritten
2. **Safe Updates**: Can run updates repeatedly without fear of losing data
3. **Clean Metadata**: No history tracking complexity, just current values
4. **Simple to Understand**: Straightforward "add if missing" logic
5. **Idempotent**: Running the same update multiple times has no effect

## Testing

A comprehensive test suite (`test_metadata_append.py`) validates:
- ✓ New metadata fields are added correctly
- ✓ Existing metadata fields are never overwritten
- ✓ None/null values are replaced with new values
- ✓ Date is always preserved
- ✓ Multiple updates work correctly

**Run tests:**
```bash
python test_metadata_append.py
```

**Run demo:**
```bash
python demo_metadata_append.py
```

## Files Modified

- [src/store.py](src/store.py) - Core implementation
- [src/main.py](src/main.py) - Python 3.8 compatibility fix
- [src/ui_tui.py](src/ui_tui.py) - Python 3.8 compatibility fix
- [test_metadata_append.py](test_metadata_append.py) - Test suite
- [demo_metadata_append.py](demo_metadata_append.py) - Interactive demo
