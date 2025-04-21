import asyncio
import httpx
import json
import time
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from smolagents.tools import Tool
import cloudscraper
import re

class TrendyolKeywordScraper(Tool):
    """A tool for scraping products from Trendyol by keyword search."""
    
    name = "trendyol_keyword_scraper"
    description = "Searches Trendyol for products matching a keyword and exports results to Excel."
    inputs = {
        "keyword": {
            "type": "string",
            "description": "The keyword to search for on Trendyol",
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
    
    async def fetch_page(self, client: httpx.AsyncClient, search_text: str, pi: int, semaphore) -> list:
        """Fetch a single page of product results for the given search term and page number."""
        async with semaphore:
            # Sadece güncel API endpoint'ini kullan
            api_url = os.getenv("trendyolkeyword")
            
            params = {
                'q': search_text,
                'qt': search_text,
                'st': search_text,
                'os': '1',
                'sk': '1',
                'pi': pi,
                'culture': 'tr-TR',
                'pId': '0',
                'isLegalRequirementConfirmed': 'false',
                'searchStrategyType': 'DEFAULT',
                'productStampType': 'TypeA',
                'scoringAlgorithmId': '2',
                'fixSlotProductAdsIncluded': 'true',
                'searchAbDecider': 'CA_B,SuggestionTermActive_B,AZSmartlisting_62,BH2_B,MB_B,FRA_2,MRF_1,ARR_B,BrowsingHistoryCard_B,SP_B,PastSearches_B,SearchWEB_14,SuggestionJFYProducts_B,SDW_24,SuggestionQF_B,BSA_D,BadgeBoost_A,Relevancy_1,FilterRelevancy_1,Smartlisting_65,SuggestionBadges_B,ProductGroupTopPerformer_B,OpenFilterToggle_2,RF_1,CS_1,RR_2,BS_2,SuggestionPopularCTR_B',
                'location': 'null',
                'initialSearchText': search_text,
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
                    print(f"Sayfa {pi}: {len(products)} ürün çekildi.")
                    return products
                else:
                    print(f"Sayfa {pi} boş.")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    print(f"Sayfa {pi} bulunamadı (404). Başka sayfa yok.")
                    return '404'
                print(f"Sayfa {pi} istek hatası: {e}")
            except Exception as e:
                print(f"Sayfa {pi} çekilirken hata: {e}")
            
            return []
            
    async def search_products(self, keyword: str) -> List[Dict]:
        """Search for products matching the given keyword."""
        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(30)
        all_products = []
        pi = 1
        is_last_page = False
        
        print(f"'{keyword}' anahtar kelimesi için ürün araması başlatılıyor...")
        
        # Create client with headers
        async with httpx.AsyncClient(timeout=30) as client:
            while not is_last_page and pi < 100:  # Maksimum 100 sayfa ile sınırla
                # Fetch multiple pages concurrently
                tasks = [self.fetch_page(client, keyword, i, semaphore) for i in range(pi, min(pi + 10, 100))]  # 10 sayfa eşzamanlı
                results = await asyncio.gather(*tasks)

                fetched_any = False
                for idx, products in enumerate(results):
                    if products == '404':
                        is_last_page = True
                        print("Daha fazla sayfa bulunamadı. Veri çekme tamamlandı.")
                        break
                    elif products:
                        all_products.extend(products)
                        fetched_any = True

                if not fetched_any:
                    print("Başka ürün bulunamadı. Veri çekme tamamlandı.")
                    break

                print(f"Toplam {len(all_products)} ürün toplandı. Devam ediliyor...")
                pi += 10
                await asyncio.sleep(0.5)  # Daha güvenli rate limiting
        
        print(f"Arama tamamlandı. Toplam {len(all_products)} ürün bulundu.")
        return all_products
    
    def products_to_excel(self, products: List[Dict], keyword: str) -> Tuple[str, str]:
        """Convert the product data to Excel format and save to temp directory."""
        if not products:
            return "Arama sonucunda ürün bulunamadı.", None
        
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
                    
                    # Kategori hiyerarşisini işle
                    category_hierarchy = product.get('categoryHierarchy', '')
                    if isinstance(category_hierarchy, str):
                        row['Kategori Hiyerarşisi'] = category_hierarchy
                    elif isinstance(category_hierarchy, list):
                        # Liste içindeki kategori nesnelerini işle
                        hierarchy_text = []
                        for cat in category_hierarchy:
                            if isinstance(cat, dict):
                                hierarchy_text.append(cat.get('name', ''))
                            else:
                                hierarchy_text.append(str(cat))
                        row['Kategori Hiyerarşisi'] = ' > '.join(hierarchy_text)
                    
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
                        'Hızlı Teslimat Süresi': product.get('rushDeliveryDuration', 0),
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
            safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword[:30])
            filename = f"arama_{safe_keyword}_{timestamp}.xlsx"
            filepath = os.path.join(self.base_tool._temp_dir, filename)
            
            # Save Excel to temp directory
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            # Geçici dosya olarak kaydet (30 dakika sonra otomatik silinecek)
            self.base_tool.register_temp_file(filepath, ttl_minutes=30)
            
            # JSON yedek olarak da kaydet
            json_filename = f"arama_{safe_keyword}_{timestamp}.json"
            json_filepath = os.path.join(self.base_tool._temp_dir, json_filename)
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=4)
            self.base_tool.register_temp_file(json_filepath, ttl_minutes=30)
            
            return filename, self.base_tool.get_file_url(filename)
            
        except Exception as e:
            print(f"Excel dosyası oluşturulurken hata: {str(e)}")
            return f"Excel dosyası oluşturulurken hata: {str(e)}", None
    
    def forward(self, keyword: Optional[str] = None) -> str:
        """
        Search Trendyol for products matching the given keyword and export results to Excel.
        
        Args:
            keyword: The keyword to search for on Trendyol
        """
        if not keyword or keyword.strip() == "":
            return "Lütfen aramak için bir anahtar kelime girin."
        
        print(f"Trendyol ürün araması başlatılıyor: '{keyword}'")
        
        try:
            # Search for products
            start_time = time.time()
            products = asyncio.run(self.search_products(keyword))
            end_time = time.time()
            
            if not products:
                return f"'{keyword}' için arama sonucunda ürün bulunamadı."
                
            # Convert products to Excel and get the filename
            excel_filename, excel_path = self.products_to_excel(products, keyword)
            
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
                    category_hierarchy = product.get('categoryHierarchy', '')
                    
                    # categoryHierarchy bazen string, bazen de liste olabilir
                    if isinstance(category_hierarchy, str):
                        # Eğer string ise, / veya > ile ayrılmış olabilir
                        if '/' in category_hierarchy:
                            parts = category_hierarchy.split('/')
                        elif '>' in category_hierarchy:
                            parts = category_hierarchy.split('>')
                        else:
                            parts = [category_hierarchy]
                            
                        if parts:
                            main_category = parts[0].strip()
                            if main_category in category_stats:
                                category_stats[main_category] += 1
                            else:
                                category_stats[main_category] = 1
                    elif isinstance(category_hierarchy, list) and category_hierarchy:
                        # Eğer liste ise ve boş değilse
                        main_category_obj = category_hierarchy[0]
                        if isinstance(main_category_obj, dict):
                            main_category = main_category_obj.get('name', 'Belirtilmemiş')
                        else:
                            main_category = str(main_category_obj)
                            
                        if main_category in category_stats:
                            category_stats[main_category] += 1
                        else:
                            category_stats[main_category] = 1
                    
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
            result = f"✅ '{keyword}' araması tamamlandı!\n\n"
            result += f"**Toplam {len(products)} ürün bulundu ve Excel dosyasına kaydedildi.**\n\n"
            result += f"**Arama süresi**: {end_time - start_time:.2f} saniye\n\n"
            
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
            
            result += f"\n**Dosya Adı**: {excel_filename}\n\n"
            
            # Dosya indirme bağlantıları
            if os.environ.get('SPACE_ID'):
                # Huggingface Spaces'te çalışıyorsa
                space_name = os.environ.get('SPACE_ID')
                result += f"**📥 İndirme Linkleri**:\n"
                result += f"- [Excel İndir](/{space_name}/file={excel_path})\n\n"
                result += "**NOT**: Dosyalar 30 dakika sonra otomatik olarak silinecektir. Lütfen bu süre içinde indirin."
            else:
                # Yerel geliştirmede
                result += f"**📥 İndirme Linkleri**:\n"
                result += f"- [Excel İndir]({excel_path})\n\n"
                result += "**NOT**: Dosyalar 30 dakika sonra otomatik olarak silinecektir."
                
            return result
            
        except asyncio.TimeoutError:
            return "Trendyol ile bağlantı zaman aşımına uğradı. Lütfen daha sonra tekrar deneyin."
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            return f"Ürünler çekilirken bir hata oluştu: {str(e)}"
