# Metadata Appending Implementation

## Overview
Modified the database file update mechanism to **append metadata changes** instead of overwriting them. This ensures that all metadata updates are preserved with timestamps for audit and history tracking.

## Changes Made

### 1. **Updated `src/store.py`**
   - Modified `update_metadata_in_files()` function to support two modes:
     - **Append Mode (default)**: Metadata updates are stored in a `metadata_updates` list with timestamps
     - **Overwrite Mode**: Original behavior for backward compatibility

### 2. **Fixed Python 3.8 Compatibility**
   - Replaced `UTC` (Python 3.11+) with `timezone.utc` in:
     - `src/store.py`
     - `src/main.py`
     - `src/ui_tui.py`

## How It Works

### Append Mode (New Default Behavior)

When metadata is updated using `update_metadata_in_files()`:

**Before (Original metadata):**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: real estate
---
```

**After First Update (firm_type, source added):**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: real estate
metadata_updates:
  - firm_type: LLC
    source: web
    updated_at: '2026-01-16T18:42:01Z'
---
```

**After Second Update (focus and loan_type updated):**
```yaml
---
website: https://example.com/
date: '2025-01-10T10:00:00Z'
focus: real estate
metadata_updates:
  - firm_type: LLC
    source: web
    updated_at: '2026-01-16T18:42:01Z'
  - focus: commercial real estate
    loan_type: construction
    updated_at: '2026-01-16T18:42:01Z'
---
```

### Key Features

✅ **Append All Updates**: Each metadata update is preserved as a separate entry
✅ **Timestamped**: Each update includes `updated_at` field for audit trail
✅ **Original Data Preserved**: Initial metadata (website, date, focus) remains unchanged
✅ **Backward Compatible**: Overwrite mode available if needed
✅ **Ordered History**: Updates are stored in chronological order

## Function Signature

```python
def update_metadata_in_files(md_dir: Path, updates: dict, append_mode: bool = True) -> int:
    """Update metadata fields in existing markdown files.
    
    Args:
        md_dir: Path to directory containing markdown files
        updates: Dict of metadata fields to update
        append_mode: If True (default), append metadata to metadata_updates list.
                     If False, use original overwrite behavior.
    
    Returns:
        Number of files updated
    """
```

## Usage Examples

### Using Append Mode (Default)
```python
from pathlib import Path
from src.store import update_metadata_in_files

md_dir = Path("data/companies/example-company/markdown")
updates = {
    "firm_type": "LLC",
    "source": "web"
}

# Metadata updates will be appended
count = update_metadata_in_files(md_dir, updates)
print(f"Updated {count} files")
```

### Using Overwrite Mode (Legacy)
```python
# Only use if backward compatibility is needed
count = update_metadata_in_files(md_dir, updates, append_mode=False)
```

## Benefits

1. **Complete Audit Trail**: All metadata modifications are recorded with timestamps
2. **Data Preservation**: No information is lost - all updates are kept
3. **History Tracking**: Can track how metadata evolved over time
4. **Debugging**: Easier to identify when and what metadata was changed
5. **Compliance**: Supports requirements for data change documentation

## Testing

A comprehensive test suite (`test_metadata_append.py`) validates:
- ✓ Metadata updates are appended correctly
- ✓ Each update includes a timestamp
- ✓ Original metadata is preserved
- ✓ Multiple updates are tracked in order
- ✓ Overwrite mode still works for backward compatibility

**Run tests:**
```bash
python test_metadata_append.py
```

## Migration Notes

- The change is **automatically applied** when `update_metadata_in_files()` is called
- Existing metadata files without `metadata_updates` will have the field created on first update
- No manual migration needed
- Old metadata remains untouched

## Files Modified

- [src/store.py](src/store.py) - Core implementation
- [src/main.py](src/main.py) - Python 3.8 compatibility fix
- [src/ui_tui.py](src/ui_tui.py) - Python 3.8 compatibility fix
- [test_metadata_append.py](test_metadata_append.py) - New test suite
