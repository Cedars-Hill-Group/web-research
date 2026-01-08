# New Search Features

## Overview
This update adds the ability to review additional search results and skip/delete companies during batch processing.

## Features Added

### 1. View More Search Results
Users can now request additional search results beyond the initial top 3 results. The system will fetch results in batches of 3, up to the Google Custom Search API limit of 100 results.

#### How to Use:
- When prompted with search results, choose option `(m)ore results`
- The system will fetch the next 3 results and display them
- You can continue fetching more results until the API limit is reached

### 2. Skip and Delete Company from Batch
In batch mode, users can now skip a company entirely and have it automatically removed from the companies.csv file.

#### How to Use:
- When prompted with search results in batch mode, choose option `(x)skip company and delete from batch`
- The company will be skipped for processing
- It will be marked as processed and removed from companies.csv when cleanup runs

## Updated Command Options

### Batch Mode
When processing companies from companies.csv, you'll see these options:
- **(y)es to continue**: Proceed with scraping using the current search results
- **(m)ore results**: Fetch the next 3 search results
- **(x)skip company and delete from batch**: Skip this company and mark for removal from CSV
- **(s)kip scraping but add manually**: Skip scraping but manually enter company data
- **(q)uit batch**: Exit batch processing early

### Single Mode
When processing a single company, you'll see these options:
- **(y)es to continue**: Proceed with scraping using the current search results
- **(m)ore results**: Fetch the next 3 search results
- **(s)kip scraping but add manually**: Skip scraping but manually enter company data
- **(n)ew search**: Start over with a new company search
- **(q)uit**: Exit the program

## Implementation Details

### Changes to `src/search.py`
- Added `start_index` parameter to `search_official_site()` function
- Supports pagination through Google Custom Search API
- Default `start_index=1` maintains backward compatibility

### Changes to `src/main.py`
- Implemented search results loop in both batch and single modes
- Added logic to fetch and display additional results on demand
- Added option to skip and delete companies from batch file
- Results are fetched in batches of 3 and accumulated
- Maximum 100 results can be retrieved (Google API limit)

## Example Workflow

### Batch Mode with More Results:
```
Processing: Acme Corporation

  Search results:
  1. Acme Corp Official - https://acme.com
     Official website of Acme Corporation...

  2. Acme Corp LinkedIn - https://linkedin.com/company/acme
     Company profile on LinkedIn...

  3. Acme Corp Wikipedia - https://wikipedia.org/wiki/Acme
     Wikipedia article about Acme...

  Options: (y)es to continue, (m)ore results, (x)skip company and delete from batch, (s)kip scraping but add manually, (q)uit batch: m

  Fetching more results...

  Search results:
  4. Acme Corp News - https://news.com/acme
     Latest news about Acme...

  5. Acme Corp Careers - https://acme.com/careers
     Join our team at Acme...

  6. Acme Corp Blog - https://acme.com/blog
     Acme's official blog...

  Options: (y)es to continue, (m)ore results, (x)skip company and delete from batch, (s)kip scraping but add manually, (q)uit batch: y
```

### Skipping a Company:
```
Processing: Bad Company Inc

  Search results:
  1. Some unrelated result...
  2. Another unrelated result...
  3. Still not the right company...

  Options: (y)es to continue, (m)ore results, (x)skip company and delete from batch, (s)kip scraping but add manually, (q)uit batch: x

  Skipping Bad Company Inc and will remove from companies.csv.
```

The company will then be removed from companies.csv during the cleanup phase at the end of batch processing.
