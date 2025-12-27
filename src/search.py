# src/search.py
from .config import load_config
import requests

def search_official_site(company: str, max_results: int = 3) -> list[dict]:
    cfg = load_config()

    # Build API Call
    base_url = "https://www.googleapis.com/customsearch/v1"
        
    params = {
        "key": cfg['google']['api_key'],
        "cx": cfg['google']['cx'],
        "q": f"{company} official site"
    }
    response = requests.get(base_url, params=params)
    data = response.json()
    
    # Return results from API Call
    if "items" in data:
        results = [{'title':i.get('title'),
                    'link':i.get('link'),
                    'snippet':i.get('snippet')
                    } for i in data['items'][:max_results]]
    else:
        results = None
    
    return results