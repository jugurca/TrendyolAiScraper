from typing import Dict, Any, Optional
from smolagents.tools import Tool
import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime

# Sadece test icin eklendi

class TrendyolScraper(Tool):
    """A tool for scraping product information from Trendyol."""
    
    name = "trendyol_scraper"
    description = "Scrapes product information from a Trendyol product page URL."
    inputs = {
        "url": {
            "type": "string",
            "description": "The Trendyol product page URL to scrape",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        from tools import TrendyolBaseTool
        self.base_tool = TrendyolBaseTool()
    
    def extract_content_id(self, url: str) -> Optional[str]:
        """Extract the content ID from the URL."""
        match = re.search(r'p-(\d+)', url)
        if match:
            return match.group(1)
        else:
            return None
    
    def forward(self, url: Optional[str] = None) -> str:
        """Scrape product information from the given Trendyol URL."""
        if url is None:
            return "Lütfen bir Trendyol ürün URL'si girin."
            
        if not url.startswith("https://www.trendyol.com"):
            return "Lütfen geçerli bir Trendyol ürün URL'si girin. URL 'https://www.trendyol.com' ile başlamalıdır."
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            product_info = {}
            
            product_name_elem = soup.select_one("h1.pr-new-br")
            if product_name_elem:
                product_info["name"] = product_name_elem.text.strip()
            else:
                product_name_elem = soup.select_one("h1.product-name")
                if product_name_elem:
                    product_info["name"] = product_name_elem.text.strip()
            
            price_elem = soup.select_one("span.prc-dsc")
            if price_elem:
                product_info["price"] = price_elem.text.strip()
            
            seller_elem = soup.select_one("span.seller-name")
            if seller_elem:
                product_info["seller"] = seller_elem.text.strip()
            
            rating_elem = soup.select_one("div.pr-rnr-cn")
            if rating_elem:
                rating_text = rating_elem.text.strip()
                # Try to extract the rating value using regex
                rating_match = re.search(r'(\d+,\d+)\s+\(\d+\s+Değerlendirme\)', rating_text)
                if rating_match:
                    product_info["rating"] = rating_match.group(1)
                else:
                    product_info["rating_text"] = rating_text
            
            content_id = self.extract_content_id(url)
            if content_id:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"urun_{content_id}_{timestamp}.json"
                
                filepath = self.base_tool.get_file_path(filename)
                
                product_info["url"] = url
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(product_info, f, ensure_ascii=False, indent=4)
                
                self.base_tool.register_temp_file(filepath, ttl_minutes=30)
            
            if not product_info:
                return "Ürün bilgileri çekilemedi. URL doğru formatta olduğundan ve ürünün mevcut olduğundan emin olun."
            
            results = "**Trendyol Ürün Bilgileri:**\n\n"
            
            if "name" in product_info:
                results += f"**Ürün Adı:** {product_info['name']}\n\n"
            
            if "price" in product_info:
                results += f"**Fiyat:** {product_info['price']}\n\n"
            
            if "seller" in product_info:
                results += f"**Satıcı:** {product_info['seller']}\n\n"
            
            if "rating" in product_info:
                results += f"**Değerlendirme:** {product_info['rating']}\n\n"
            elif "rating_text" in product_info:
                results += f"**Değerlendirme:** {product_info['rating_text']}\n\n"
            
            results += f"**URL:** {url}\n"
            
            if content_id:
                # Dosya URL'sini base_tool üzerinden al
                file_url = self.base_tool.get_file_url(filename)
                
                if os.environ.get('SPACE_ID'):
                    # Huggingface Spaces'te çalışıyorsa
                    space_name = os.environ.get('SPACE_ID')
                    results += f"\n**📥 JSON Verisi**: [JSON İndir]({file_url})\n"
                    results += "**NOT**: Dosya 30 dakika sonra otomatik olarak silinecektir."
                else:
                    # Yerel geliştirmede
                    results += f"\n**📥 JSON Verisi**: [JSON İndir]({file_url})\n"
                    results += "**NOT**: Dosya 30 dakika sonra otomatik olarak silinecektir."
            
            return results
            
        except Exception as e:
            return f"Ürün bilgileri çekilirken bir hata oluştu: {str(e)}" 
