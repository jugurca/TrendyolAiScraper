import asyncio
import httpx
import json
import time
import pandas as pd
import os
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from smolagents.tools import Tool

class TrendyolStoreScraper(Tool):
    """A tool for scraping products from a Trendyol store/seller."""
    
    name = "trendyol_store_scraper"
    description = "Scrapes products from a Trendyol store URL and exports them to Excel."
    inputs = {
        "url": {
            "type": "string",
            "description": "The Trendyol store page URL to scrape products from",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        # TrendyolBaseTool sınıfının fonksiyonlarını kullanmak için
        # tools modülünden bu sınıfı lazy import ile alıyoruz
        from tools import TrendyolBaseTool
        self.base_tool = TrendyolBaseTool()
    
    def extract_merchant_id(self, url: str) -> Optional[str]:
        """Extract the merchant ID from a Trendyol store URL."""
        match = re.search(r'(?:mid=|m-)(\d+)', str(url))
        return match.group(1) if match else None
    
    async def fetch_page(self, client: httpx.AsyncClient, merchant_id: str, page: int, semaphore) -> List[Dict]:
        """Fetch a single page of products for the given merchant and page number."""
        async with semaphore:
            # API endpoint for store products
            api_url = os.getenv("trendyolstore")
            
            params = {
                'mid': merchant_id,
                'os': '1',
                'pi': page,
                'culture': 'tr-TR',
                'pId': '0',
                'isLegalRequirementConfirmed': 'false',
                'searchStrategyType': 'DEFAULT',
                'productStampType': 'TypeA',
                'scoringAlgorithmId': '2',
                'fixSlotProductAdsIncluded': 'false',
                'searchAbDecider': 'CA_B,SuggestionTermActive_B,AZSmartlisting_62,BH2_B,MB_B,FRA_2,MRF_1,ARR_B,BrowsingHistoryCard_B,SP_B,PastSearches_B,SearchWEB_14,SuggestionJFYProducts_B,SDW_24,SuggestionQF_B,BSA_D,BadgeBoost_A,Relevancy_1,FilterRelevancy_1,Smartlisting_65,SuggestionBadges_B,ProductGroupTopPerformer_B,OpenFilterToggle_2,RF_1,CS_1,RR_2,BS_2,SuggestionPopularCTR_B',
                'location': 'null',
                'channelId': '1',
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://www.trendyol.com',
                'Referer': 'https://www.trendyol.com',
            }

            try:
                response = await client.get(api_url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                products = data.get('result', {}).get('products', [])

                if products:
                    print(f"Sayfa {page}: {len(products)} ürün çekildi.")
                    return products
                else:
                    print(f"Sayfa {page} boş.")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    print(f"Sayfa {page} bulunamadı (404). Başka sayfa yok.")
                    return '404'
                print(f"Sayfa {page} istek hatası: {e}")
            except Exception as e:
                print(f"Sayfa {page} çekilirken hata: {e}")
            
            return []
    
    async def scrape_store_products(self, merchant_id: str) -> List[Dict]:
        """Scrape all products from a store with given merchant ID."""
        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(30)
        all_products = []
        page = 1
        
        print(f"Mağaza ID {merchant_id} için ürün taraması başlatılıyor...")
        
        # Create client
        async with httpx.AsyncClient(timeout=30) as client:
            while page < 100:  # Maksimum 100 sayfa ile sınırla
                # Fetch multiple pages concurrently
                tasks = [self.fetch_page(client, merchant_id, p, semaphore) for p in range(page, page + 30)]
                results = await asyncio.gather(*tasks)

                # Process results
                new_data = []
                for products in results:
                    if products == '404':
                        print("Daha fazla sayfa bulunamadı. Veri çekme tamamlandı.")
                        break
                    elif products:
                        new_data.extend(products)
                
                if not new_data:
                    print("Başka ürün bulunamadı. Veri çekme tamamlandı.")
                    break
                
                all_products.extend(new_data)
                print(f"Toplam {len(all_products)} ürün toplandı. Devam ediliyor...")
                
                page += 30
                await asyncio.sleep(0.3)  # Rate limiting için
        
        print(f"Mağaza taraması tamamlandı. Toplam {len(all_products)} ürün bulundu.")
        return all_products
    
    def products_to_excel(self, products: List[Dict], merchant_id: str) -> Tuple[str, str]:
        """Convert the product data to Excel format and save to temp directory."""
        if not products:
            return "Mağaza ürünleri bulunamadı.", None
        
        print(f"Excel dosyası oluşturuluyor ({len(products)} ürün)...")
        
        try:
            # Create a dataframe from the products
            df_data = []
            for product in products:
                try:
                    # Ana ürün bilgileri
                    row = {
                        'Ürün ID': product.get('id', ''),
                        'Ürün Adı': product.get('name', ''),
                        'Marka': product.get('brand', {}).get('name', ''),
                        'Kategori ID': product.get('categoryId', ''),
                        'Kategori Adı': product.get('categoryName', ''),
                    }
                    
                    # Kategori hiyerarşisi
                    category_hierarchy = product.get('categoryHierarchy', '')
                    if isinstance(category_hierarchy, str):
                        row['Kategori Hiyerarşisi'] = category_hierarchy
                    
                    # Fiyat bilgileri
                    price_data = product.get('price', {})
                    row.update({
                        'Fiyat': price_data.get('discountedPrice', 0),
                        'Orijinal Fiyat': price_data.get('originalPrice', 0),
                        'İndirim Oranı': price_data.get('discountRatio', 0),
                        'Para Birimi': price_data.get('currency', 'TL'),
                    })
                    
                    # Ürün puanı ve değerlendirme
                    rating_data = product.get('ratingScore', {})
                    row.update({
                        'Puan': rating_data.get('averageRating', 0),
                        'Değerlendirme Sayısı': rating_data.get('totalCount', 0),
                    })
                    
                    # Satıcı ve kampanya bilgileri
                    row.update({
                        'Satıcı ID': product.get('merchantId', ''),
                        'Kampanya ID': product.get('campaignId', ''),
                        'Kampanya Adı': product.get('campaignName', ''),
                        'Kargo Bedava': product.get('freeCargo', False),
                        'Aynı Gün Kargo': product.get('sameDayShipping', False),
                    })
                    
                    # Ürün URL ve resim URL'leri
                    if 'url' in product:
                        row['Ürün URL'] = f"https://www.trendyol.com{product['url']}"
                    
                    if 'images' in product and len(product['images']) > 0:
                        row['Resim URL'] = f"https://cdn.dsmcdn.com{product['images'][0]}"
                        
                        # İlave resimler
                        additional_images = []
                        for img in product['images'][1:]:
                            additional_images.append(f"https://cdn.dsmcdn.com{img}")
                        row['Diğer Resimler'] = ', '.join(additional_images[:3])  # İlk 3 ilave resmi al
                    
                    # Sosyal kanıt
                    social_proof = product.get('socialProof', {})
                    if social_proof:
                        # Sipariş sayısı
                        order_count = social_proof.get('orderCount', {})
                        if order_count:
                            row['Sipariş Sayısı'] = order_count.get('count', '')
                        
                        # Favori sayısı
                        favorite_count = social_proof.get('favoriteCount', {})
                        if favorite_count:
                            row['Favori Sayısı'] = favorite_count.get('count', '')
                    
                    df_data.append(row)
                except Exception as e:
                    print(f"Ürün işlenirken hata: {str(e)}")
                    continue
            
            # Create DataFrame
            df = pd.DataFrame(df_data)
            
            # Create Excel file in temp directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"magaza_{merchant_id}_{timestamp}.xlsx"
            filepath = os.path.join(self.base_tool._temp_dir, filename)
            
            # Save Excel to temp directory
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            # Geçici dosya olarak kaydet (30 dakika sonra otomatik silinecek)
            self.base_tool.register_temp_file(filepath, ttl_minutes=30)
            
            # Dosya URL'sini oluştur
            file_url = self.base_tool.get_file_url(filename)
            
            return filename, file_url
            
        except Exception as e:
            print(f"Excel dosyası oluşturulurken hata: {str(e)}")
            return f"Excel dosyası oluşturulurken hata: {str(e)}", None
    
    def save_json_backup(self, products: List[Dict], merchant_id: str) -> Tuple[str, str]:
        """JSON yedek dosyasını kaydet"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"magaza_{merchant_id}_{timestamp}.json"
        filepath = os.path.join(self.base_tool._temp_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=4)
        
        # Geçici dosya olarak kaydet (30 dakika sonra otomatik silinecek)
        self.base_tool.register_temp_file(filepath, ttl_minutes=30)
        
        # Dosya URL'sini oluştur
        file_url = self.base_tool.get_file_url(filename)
            
        return filename, file_url
    
    def forward(self, url: Optional[str] = None) -> str:
        """
        Scrape all products from a Trendyol store and export results to Excel.
        
        Args:
            url: The Trendyol store URL to scrape products from
        """
        if not url or url.strip() == "":
            return "Lütfen Trendyol mağaza URL'sini girin."
        
        merchant_id = self.extract_merchant_id(url)
        if not merchant_id:
            return "Geçerli bir Trendyol mağaza URL'si girin. Mağaza ID'si bulunamadı."
            
        print(f"Trendyol mağaza taraması başlatılıyor: Mağaza ID {merchant_id}")
        
        try:
            # Scrape products
            start_time = time.time()
            products = asyncio.run(self.scrape_store_products(merchant_id))
            end_time = time.time()
            
            if not products:
                return f"Mağaza ID {merchant_id} için ürün bulunamadı."
                
            # Save to JSON file for backup
            json_filename, json_path = self.save_json_backup(products, merchant_id)
                
            # Convert products to Excel and get the filename
            excel_filename, excel_path = self.products_to_excel(products, merchant_id)
            
            if not excel_path:
                return excel_filename  # Hata mesajı dönmüş olacak
            
            # Kategori bazlı istatistikler
            category_stats = {}
            brand_stats = {}
            price_ranges = {
                "0-50 TL": 0,
                "51-100 TL": 0,
                "101-250 TL": 0,
                "251-500 TL": 0,
                "501-1000 TL": 0,
                "1000+ TL": 0
            }
            
            for product in products:
                try:
                    # Marka istatistikleri
                    brand = product.get('brand', {}).get('name', 'Belirtilmemiş')
                    if brand in brand_stats:
                        brand_stats[brand] += 1
                    else:
                        brand_stats[brand] = 1
                    
                    # Kategori istatistikleri
                    category = product.get('categoryName', 'Belirtilmemiş')
                    if category in category_stats:
                        category_stats[category] += 1
                    else:
                        category_stats[category] = 1
                    
                    # Fiyat aralıkları
                    price = product.get('price', {}).get('discountedPrice', 0)
                    if price <= 50:
                        price_ranges["0-50 TL"] += 1
                    elif price <= 100:
                        price_ranges["51-100 TL"] += 1
                    elif price <= 250:
                        price_ranges["101-250 TL"] += 1
                    elif price <= 500:
                        price_ranges["251-500 TL"] += 1
                    elif price <= 1000:
                        price_ranges["501-1000 TL"] += 1
                    else:
                        price_ranges["1000+ TL"] += 1
                        
                except Exception as e:
                    print(f"Ürün istatistikleri işlenirken hata: {str(e)}")
                    continue
            
            # En popüler 5 marka ve kategoriyi al
            top_brands = sorted(brand_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            top_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # İstatistik sonuçlarını oluştur
            result = f"✅ Mağaza ID {merchant_id} taraması tamamlandı!\n\n"
            result += f"**Toplam {len(products)} ürün bulundu ve Excel dosyasına kaydedildi.**\n\n"
            result += f"**Tarama süresi**: {end_time - start_time:.2f} saniye\n\n"
            
            # İstatistikler
            result += "📊 **İstatistikler**\n\n"
            
            # En popüler markalar
            result += "**En Popüler Markalar**:\n"
            for i, (brand, count) in enumerate(top_brands, 1):
                result += f"{i}. {brand}: {count} ürün\n"
            
            result += "\n**En Popüler Kategoriler**:\n"
            for i, (category, count) in enumerate(top_categories, 1):
                result += f"{i}. {category}: {count} ürün\n"
            
            result += "\n**Fiyat Dağılımı**:\n"
            for price_range, count in price_ranges.items():
                if count > 0:
                    percentage = (count / len(products)) * 100
                    result += f"{price_range}: {count} ürün ({percentage:.1f}%)\n"
            
            result += f"\n**Dosya Adı**: {excel_filename}\n"
            result += f"**JSON Yedek**: {json_filename}\n\n"
            
            # Dosya indirme bağlantıları
            if os.environ.get('SPACE_ID'):
                # Huggingface Spaces'te çalışıyorsa
                space_name = os.environ.get('SPACE_ID')
                result += f"**📥 İndirme Linkleri**:\n"
                result += f"- [Excel İndir](/{space_name}/file={excel_path})\n"
                result += f"- [JSON İndir](/{space_name}/file={json_path})\n\n"
                result += "**NOT**: Dosyalar 30 dakika sonra otomatik olarak silinecektir. Lütfen bu süre içinde indirin."
            else:
                # Yerel geliştirmede
                result += f"**📥 İndirme Linkleri**:\n"
                result += f"- [Excel İndir]({excel_path})\n"
                result += f"- [JSON İndir]({json_path})\n\n"
                result += "**NOT**: Dosyalar 30 dakika sonra otomatik olarak silinecektir."
                
            return result
            
        except asyncio.TimeoutError:
            return "Trendyol ile bağlantı zaman aşımına uğradı. Lütfen daha sonra tekrar deneyin."
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            return f"Mağaza ürünleri çekilirken bir hata oluştu: {str(e)}"
