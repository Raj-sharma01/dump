import requests
from bs4 import BeautifulSoup
import json

def scrape_flixpatrol_dynamic(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Dynamically discover platforms from the navigation menu
    dropdown_menu = soup.find('div', role='menu')
    discovered_platforms = []
    
    if dropdown_menu:
        menu_items = dropdown_menu.find_all('a', role='menuitem')
        for item in menu_items:
            platform_name = item.get_text(strip=True)
            if platform_name:
                discovered_platforms.append(platform_name)
                
    if not discovered_platforms:
        discovered_platforms = ["Netflix", "Amazon Prime", "Apple TV", "Google", "Hotstar", "JioHotstar", "ZEE5"]

    # 2. Extract trending data cards
    extracted_data = []
    list_cards = soup.find_all('div', class_='card')
    
    for card in list_cards:
        # Get the sub-list title inside the card (e.g., "TOP 10 Movies")
        h3_header = card.find('h3')
        if not h3_header:
            continue
        list_name = h3_header.get_text(strip=True)
        
        # --- FIX: Look backward up the HTML document to find the platform section header ---
        section_header = card.find_previous('h2')
        section_text = section_header.get_text(strip=True) if section_header else ""
        
        # Match the section text against our platform list
        platform = "Unknown/Overall"
        for p in discovered_platforms:
            if p.lower() in section_text.lower():
                platform = p
                break
                
        # Parse table rows
        rows = card.find_all('tr', class_='table-group')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue
                
            rank = cols[0].get_text(strip=True).replace('.', '')
            trend_div = cols[1].find('div')
            trend = trend_div.get_text(strip=True) if trend_div else "–"
            
            # Clean up the trend representation if desired
            if trend == "–":
                trend = "0"
            
            title_tag = cols[2].find('a')
            title = title_tag.get_text(strip=True) if title_tag else cols[2].get_text(strip=True)
            
            days_text = cols[3].get_text(strip=True)
            days_in_top_10 = days_text.replace('d', '').replace('\xa0', '').strip()
            
            extracted_data.append({
                "Platform": platform,
                "source": "FlixPatrol",
                "List Name": list_name,
                "Rank": int(rank) if rank.isdigit() else rank,
                "Title": title,
                "Trending Direction": trend,
                "Days in Top 10": int(days_in_top_10) if days_in_top_10.isdigit() else days_in_top_10
            })
            
    return extracted_data

if __name__ == "__main__":
    target_url = "https://flixpatrol.com/top10/streaming/india/"
    results = scrape_flixpatrol_dynamic(target_url)
    
    print(f"Scraped {len(results)} total items.")
    # Show a slice of items to verify platform names match correctly now
    print(json.dumps(results[:5], indent=4, ensure_ascii=False))
