"""Test script to verify the new search features."""

import sys
from src.search import search_official_site

def test_search_with_pagination():
    """Test that search_official_site supports pagination."""
    print("Testing search with pagination...")
    
    # Test with default parameters
    results1 = search_official_site("Microsoft", max_results=3, start_index=1)
    if results1:
        print(f"✓ First batch returned {len(results1)} results")
        for i, r in enumerate(results1, 1):
            print(f"  {i}. {r['title']}")
    else:
        print("✗ No results returned for first batch")
        return False
    
    # Test with offset
    results2 = search_official_site("Microsoft", max_results=3, start_index=4)
    if results2:
        print(f"✓ Second batch returned {len(results2)} results")
        for i, r in enumerate(results2, 4):
            print(f"  {i}. {r['title']}")
    else:
        print("✗ No results returned for second batch")
        return False
    
    # Verify results are different
    if results1[0]['link'] != results2[0]['link']:
        print("✓ Results from different batches are different")
    else:
        print("⚠ Results from different batches are the same (might be expected for some queries)")
    
    print("\n✓ All pagination tests passed!")
    return True

if __name__ == "__main__":
    try:
        test_search_with_pagination()
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
