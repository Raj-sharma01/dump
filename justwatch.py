import requests
import json
from abc import ABC, abstractmethod

class TrendingStrategy(ABC):
    @abstractmethod
    def fetch_trending(self, limit: int = 10) -> list[dict]:
        pass

class JustWatchStrategy(TrendingStrategy):
    def __init__(self, platforms: list[str] = None):
        self.url = "https://apis.justwatch.com/graphql"
        self.headers = {
            "Content-Type": "application/json", 
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        self.platforms = platforms if platforms else ["zee", "nfx", "prv"]
        
        # We must use the EXACT query from your browser's network payload
        self.graphql_query = """
        query GetProviderTop10TitlesFallback($backdropProfile: BackdropProfile, $country: Country!, $first: Int! = 70, $format: ImageFormat, $language: Language!, $platform: Platform! = WEB, $after: String, $popularTitlesFilter: TitleFilter, $popularTitlesSortBy: PopularTitlesSorting! = POPULAR, $profile: PosterProfile, $sortRandomSeed: Int! = 0, $watchNowFilter: WatchNowOfferFilter!, $offset: Int = 0, $creditsRole: CreditRole! = DIRECTOR, $streamingChartsFilter: StreamingChartsFilter, $offerFilter: OfferFilter!) {
          popularTitles(
            country: $country
            filter: $popularTitlesFilter
            first: $first
            sortBy: $popularTitlesSortBy
            sortRandomSeed: $sortRandomSeed
            offset: $offset
            after: $after
          ) {
            edges {
              cursor
              node {
                id
                objectId
                objectType
                streamingCharts(country: $country, filter: $streamingChartsFilter) {
                  edges {
                    streamingChartInfo {
                      rank
                      trend
                      trendDifference
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                content(country: $country, language: $language) {
                  title
                  fullPath
                  scoring {
                    imdbVotes
                    imdbScore
                    tmdbPopularity
                    tmdbScore
                    __typename
                  }
                  posterUrl(profile: $profile, format: $format)
                  ... on MovieOrShowOrSeasonContent {
                    backdrops(profile: $backdropProfile, format: $format) {
                      backdropUrl
                      __typename
                    }
                    __typename
                  }
                  isReleased
                  credits(role: $creditsRole) {
                    name
                    personId
                    __typename
                  }
                  scoring {
                    imdbVotes
                    __typename
                  }
                  runtime
                  originalReleaseYear
                  genres {
                    id
                    translation(language: $language)
                    shortName
                    __typename
                  }
                  __typename
                }
                likelistEntry {
                  createdAt
                  __typename
                }
                dislikelistEntry {
                  createdAt
                  __typename
                }
                watchlistEntryV2 {
                  createdAt
                  __typename
                }
                customlistEntries {
                  createdAt
                  __typename
                }
                watchNowOffer(country: $country, platform: $platform, filter: $watchNowFilter) {
                  ...WatchNowOffer
                  __typename
                }
                offers(country: $country, platform: $platform, filter: $offerFilter) {
                  ...WatchNowOffer
                  __typename
                }
                ... on Movie {
                  seenlistEntry {
                    createdAt
                    __typename
                  }
                  __typename
                }
                ... on Show {
                  tvShowTrackingEntry {
                    createdAt
                    __typename
                  }
                  seenState(country: $country) {
                    seenEpisodeCount
                    progress
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            pageInfo {
              startCursor
              endCursor
              hasPreviousPage
              hasNextPage
              __typename
            }
            totalCount
            __typename
          }
        }

        fragment WatchNowOffer on Offer {
          __typename
          id
          standardWebURL
          preAffiliatedStandardWebURL
          streamUrl
          streamUrlExternalPlayer
          package {
            id
            icon
            packageId
            clearName
            shortName
            technicalName
            iconWide(profile: S160)
            hasRectangularIcon(country: $country, platform: WEB)
            __typename
          }
          retailPrice(language: $language)
          retailPriceValue
          lastChangeRetailPriceValue
          currency
          presentationType
          monetizationType
          availableTo
          dateCreated
          newElementCount
          mediaDealId
        }
        """

    def fetch_trending(self, limit: int = 10) -> list[dict]:
        extracted_data = []
        
        for provider_code in self.platforms:
            for obj_type in ["SHOW", "MOVIE"]:
                
                # We also include every single variable field your network request used
                payload = {
                    "operationName": "GetProviderTop10TitlesFallback",
                    "variables": {
                        "first": limit,
                        "platform": "WEB",
                        "popularTitlesSortBy": "TRENDING",
                        "sortRandomSeed": 0,
                        "offset": 0,
                        "creditsRole": "DIRECTOR",
                        "after": "",
                        "popularTitlesFilter": {
                            "packages": [provider_code],
                            "objectTypes": [obj_type]
                        },
                        "watchNowFilter": {
                            "packages": [provider_code]
                        },
                        "offerFilter": {
                            "packages": [provider_code],
                            "bestOnly": True,
                            "preAffiliate": True
                        },
                        "language": "en",
                        "country": "IN",
                        "streamingChartsFilter": {
                            "category": "WEEKLY_POPULARITY_SAME_CONTENT_TYPE",
                            "objectType": obj_type,
                            "nextTitles": 0,
                            "previousTitles": 0
                        }
                    },
                    "query": self.graphql_query
                }
                
                response = requests.post(self.url, json=payload, headers=self.headers)
                
                # Added robust error logging!
                if response.status_code != 200:
                    print(f"Failed to fetch {obj_type} for {provider_code}")
                    print(f"Server Response: {response.status_code} - {response.text}")
                    continue
                    
                edges = response.json().get("data", {}).get("popularTitles", {}).get("edges", [])
                
                for index, edge in enumerate(edges, 1):
                    node = edge.get("node", {})
                    content = node.get("content", {}) or {}
                    watch_offer = node.get("watchNowOffer", {}) or {}
                    package = watch_offer.get("package", {}) or {}
                    
                    platform_name = package.get("clearName", provider_code.upper())
                    
                    rank = index
                    trend_diff_str = "0"
                    
                    charts_edges = node.get("streamingCharts", {}).get("edges", [])
                    if charts_edges:
                        chart_info = charts_edges[0].get("streamingChartInfo", {})
                        rank = chart_info.get("rank", index) 
                        
                        raw_diff = chart_info.get("trendDifference", 0)
                        if raw_diff > 0:
                            trend_diff_str = f"+{raw_diff}"
                        else:
                            trend_diff_str = str(raw_diff)
                    
                    list_label = "Movies" if obj_type == "MOVIE" else "TV Shows"
                    
                    extracted_data.append({
                        "title": content.get("title"),
                        "content_type": "TV Show" if obj_type == "SHOW" else "Movie",
                        "rank": rank,
                        "trending_direction": trend_diff_str,
                        "platform": platform_name,
                        "list_name": f"TOP 10 {list_label}",
                        "source": "JustWatch",
                        "days_in_top_10": None 
                    })
                    
        return extracted_data

if __name__ == "__main__":
    jw_strategy = JustWatchStrategy(platforms=["nfx", "zee", "prv"])
    print("Fetching platform-specific trending data from JustWatch...")
    results = jw_strategy.fetch_trending(limit=10)
    
    print(f"\nTotal records extracted: {len(results)}")
    print(json.dumps(results[:5], indent=4))
