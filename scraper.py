from abc import ABC, abstractmethod
import requests
from bs4 import BeautifulSoup
import json

# ==========================================
# 1. ABSTRACT BASE STRATEGY (INTERFACE)
# ==========================================
class TrendingStrategy(ABC):
    @abstractmethod
    def fetch_trending(self, limit: int = 40) -> list[dict]:
        """Fetch tracking data and normalize to a common shape."""
        pass


# ==========================================
# 2. CONCRETE STRATEGY: FLIXPATROL
# ==========================================
class FlixPatrolStrategy(TrendingStrategy):
    def __init__(self, url: str = "https://flixpatrol.com/top10/streaming/india/"):
        self.url = url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_trending(self, limit: int = 40) -> list[dict]:
        response = requests.get(self.url, headers=self.headers)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Discover platforms from the navigation menu dynamically
        dropdown_menu = soup.find('div', role='menu')
        discovered_platforms = []
        if dropdown_menu:
            menu_items = dropdown_menu.find_all('a', role='menuitem')
            discovered_platforms = [item.get_text(strip=True) for item in menu_items if item.get_text(strip=True)]
        
        if not discovered_platforms:
            discovered_platforms = ["Netflix", "Amazon Prime", "Apple TV", "Google", "Hotstar", "JioHotstar", "ZEE5"]

        extracted_data = []
        list_cards = soup.find_all('div', class_='card')
        
        for card in list_cards:
            h3_header = card.find('h3')
            if not h3_header:
                continue
            list_name = h3_header.get_text(strip=True)
            
            # Identify parent platform
            section_header = card.find_previous('h2')
            section_text = section_header.get_text(strip=True) if section_header else ""
            
            platform = "Unknown/Overall"
            for p in discovered_platforms:
                if p.lower() in section_text.lower():
                    platform = p
                    break
            
            # Parse layout rows
            rows = card.find_all('tr', class_='table-group')
            for row in rows:
                if len(extracted_data) >= limit:
                    break
                    
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue
                    
                rank_raw = cols[0].get_text(strip=True).replace('.', '')
                trend_div = cols[1].find('div')
                trend = trend_div.get_text(strip=True) if trend_div else "0"
                if trend == "–":
                    trend = "0"
                
                title_tag = cols[2].find('a')
                title = title_tag.get_text(strip=True) if title_tag else cols[2].get_text(strip=True)
                
                # Contextual inference for Content Type based on list naming schema
                content_type = "Movie" if "movie" in list_name.lower() else "TV Show"
                
                days_text = cols[3].get_text(strip=True)
                days_in_top_10 = days_text.replace('d', '').replace('\xa0', '').strip()
                
                extracted_data.append({
                    "title": title,
                    "content_type": content_type,
                    "rank": int(rank_raw) if rank_raw.isdigit() else rank_raw,
                    "trending_direction": trend,
                    "platform": platform,
                    "list_name": list_name,
                    "source": "FlixPatrol",
                    "days_in_top_10": int(days_in_top_10) if days_in_top_10.isdigit() else None
                })
                
        return extracted_data[:limit]


# ==========================================
# 3. CONCRETE STRATEGY: JUSTWATCH
# ==========================================
class JustWatchStrategy(TrendingStrategy):
    def __init__(self, url: str = "https://apis.justwatch.com/graphql"):
        self.url = url
        self.headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        self.graphql_query = """
        query GetPopularTitles($country: Country!, $first: Int! = 70, $language: Language!, $watchNowFilter: WatchNowOfferFilter!) {
          popularTitles(country: $country, filter: {}, first: $first, sortBy: POPULAR) {
            edges {
              node {
                objectType
                content(country: $country, language: $language) { title }
                watchNowOffer(country: $country, platform: WEB, filter: $watchNowFilter) {
                  package { clearName }
                }
              }
            }
          }
        }
        """

    def fetch_trending(self, limit: int = 40) -> list[dict]:
        payload = {
            "operationName": "GetPopularTitles",
            "query": self.graphql_query,
            "variables": {
                "country": "IN",
                "first": limit,
                "language": "en",
                "watchNowFilter": {"packages": [], "monetizationTypes": []}
            }
        }
        
        response = requests.post(self.url, json=payload, headers=self.headers)
        if response.status_code != 200:
            return []
            
        edges = response.json().get("data", {}).get("popularTitles", {}).get("edges", [])
        extracted_data = []
        
        for index, edge in enumerate(edges, 1):
            node = edge.get("node", {})
            content = node.get("content", {}) or {}
            watch_offer = node.get("watchNowOffer", {}) or {}
            package = watch_offer.get("package", {}) or {}
            
            platform = package.get("clearName", "Not Specified / Rent / Buy")
            content_type = "TV Show" if node.get("objectType") == "SHOW" else "Movie"
            
            extracted_data.append({
                "title": content.get("title"),
                "content_type": content_type,
                "rank": index,
                "trending_direction": "0",  # JustWatch is a snapshot; it doesn't serve a delta direction vector
                "platform": platform,
                "list_name": "Popular Titles",
                "source": "JustWatch",
                "days_in_top_10": None      # Metric not tracked on JustWatch popular listings
            })
            
        return extracted_data


# ==========================================
# 4. THE STRATEGY CONTEXT
# ==========================================
class TrendingTracker:
    def __init__(self, strategy: TrendingStrategy):
        self._strategy = strategy

    @property
    def strategy(self) -> TrendingStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, strategy: TrendingStrategy):
        self._strategy = strategy

    def get_trending_data(self, limit: int = 40) -> list[dict]:
        return self._strategy.fetch_trending(limit)


# ==========================================
# 5. EXECUTION PIPELINE
# ==========================================
if __name__ == "__main__":
    # Initialize the engine context with FlixPatrol
    tracker = TrendingTracker(FlixPatrolStrategy())
    
    print("--- Executing FlixPatrol Strategy ---")
    flixpatrol_results = tracker.get_trending_data(limit=5)
    print(json.dumps(flixpatrol_results, indent=4))
    
    # Dynamically pivot strategies on the fly 
    print("\n--- Switching Engines to JustWatch Strategy ---")
    tracker.strategy = JustWatchStrategy()
    
    justwatch_results = tracker.get_trending_data(limit=5)
    print(json.dumps(justwatch_results, indent=4))
