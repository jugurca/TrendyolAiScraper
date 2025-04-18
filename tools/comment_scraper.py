import cloudscraper
import json
import time
import re
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from smolagents.tools import Tool

class TrendyolCommentScraper(Tool):
    """A tool for scraping product comments/reviews from Trendyol."""
    
    name = "trendyol_comment_scraper"
    description = "Scrapes customer reviews from a Trendyol product page URL and exports them to Excel."
    inputs = {
        "url": {
            "type": "string",
            "description": "The Trendyol product page URL to scrape reviews from",
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
    
    # Function to extract content ID from the URL
    def extract_content_id(self, url: str) -> Optional[str]:
        match = re.search(r'p-(\d+)', url)
        if match:
            return match.group(1)
        else:
            return None
    
    # Function to fetch product reviews
    def fetch_reviews(self, content_id: str, max_pages: int = 300):
        # Cloudscraper oluştur
        scraper = cloudscraper.create_scraper()
        
        # Header'lar
        headers = {
            "user-agent": "Mozilla/5.0",
            "accept": "application/json, text/plain, */*",
            "referer": f"https://www.trendyol.com/",
            "origin": "https://www.trendyol.com"
        }
        
        all_reviews = []
        error_count = 0  # Hata sayısını takip etmek için

        for page in range(max_pages):
            try:
                params = {
                    "contentId": content_id,
                    "pageSize": 50,
                    "page": page,
                    "order": "DESC",
                    "orderBy": "LastModifiedDate",
                    "channelId": 1
                }

                response = scraper.get(
                    "https://apigw.trendyol.com/discovery-web-websfxsocialreviewrating-santral/product-reviews-detailed",
                    headers=headers,
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("result", {}).get("productReviews", {}).get("content", [])
                    if not content:
                        print(f"Page {page}: No more reviews.")
                        break

                    all_reviews.extend(content)
                    print(f"Page {page}: Collected {len(content)} reviews. Total: {len(all_reviews)}")
                    time.sleep(0.3)
                else:
                    print(f"Page {page}: Error {response.status_code}")
                    error_count += 1
                    if error_count >= 3:  # 3 ardışık hata sonrası durdur
                        print("Çok fazla hata, işlem durduruluyor.")
                        break
                    continue
            except Exception as e:
                print(f"Page {page}: Exception occurred: {str(e)}")
                error_count += 1
                if error_count >= 3:  # 3 ardışık hata sonrası durdur
                    print("Çok fazla hata, işlem durduruluyor.")
                    break
                continue

        print(f"Toplam {len(all_reviews)} yorum toplandı.")
        return all_reviews
    
    def reviews_to_excel(self, reviews: List[Dict], url: str, content_id: str) -> Tuple[str, str]:
        if not reviews:
            return "Ürün için yorum bulunamadı.", None
        
        print(f"Excel dosyası oluşturuluyor ({len(reviews)} yorum)...")
            
        try:
            # Create a dataframe from the reviews
            df_data = []
            for review in reviews:
                try:
                    # Temel yorum bilgileri
                    row = {
                        'Yorum ID': review.get('id', ''),
                        'Başlık': review.get('commentTitle', ''),
                        'Yorum': review.get('comment', ''),
                        'Puan': review.get('rate', 0),
                        'Tarih': review.get('lastModifiedDate', ''),
                        'Kullanıcı': review.get('userFullName', ''),
                        'Güvenilir': review.get('trusted', False),
                        'Beğeni Sayısı': review.get('reviewLikeCount', 0),
                    }
                    
                    # Satıcı bilgisi
                    if 'sellerName' in review:
                        row['Satıcı'] = review.get('sellerName', '')
                    
                    # Elite veya Influencer kullanıcı mı?
                    row['Elite Kullanıcı'] = review.get('isElite', False)
                    row['Influencer Kullanıcı'] = review.get('isInfluencer', False)
                    
                    # Medya dosyaları var mı?
                    if 'mediaFiles' in review and review['mediaFiles']:
                        try:
                            media_urls = [media.get('url', '') for media in review['mediaFiles'] if media.get('url')]
                            row['Medya URL'] = '; '.join(media_urls)
                            row['Medya Sayısı'] = len(media_urls)
                        except (AttributeError, TypeError) as e:
                            print(f"Medya dosyaları işlenirken hata: {str(e)}")
                            row['Medya URL'] = ''
                            row['Medya Sayısı'] = 0
                        
                    # Ürün özellikleri
                    if 'productAttributes' in review and review['productAttributes']:
                        try:
                            attr_text = []
                            if isinstance(review['productAttributes'], dict):
                                for key, value in review['productAttributes'].items():
                                    attr_text.append(f"{key}: {value}")
                            row['Ürün Özellikleri'] = '; '.join(attr_text)
                        except (AttributeError, TypeError) as e:
                            print(f"Ürün özellikleri işlenirken hata: {str(e)}")
                            row['Ürün Özellikleri'] = ''
                        
                    df_data.append(row)
                except Exception as e:
                    print(f"Yorum işlenirken hata: {str(e)}. Bu yorum atlanıyor.")
                    continue
                
            df = pd.DataFrame(df_data)
            
            # Format dates if available
            if 'Tarih' in df.columns:
                try:
                    # Önce Türkçe tarih formatlarını kontrol et (örn: "19 Şubat 2025")
                    turkish_months = {
                        'Ocak': '01', 'Şubat': '02', 'Mart': '03', 'Nisan': '04', 
                        'Mayıs': '05', 'Haziran': '06', 'Temmuz': '07', 'Ağustos': '08',
                        'Eylül': '09', 'Ekim': '10', 'Kasım': '11', 'Aralık': '12'
                    }
                    
                    # Tarih sütununu işle
                    parsed_dates = []
                    for date_str in df['Tarih']:
                        try:
                            # Eğer bu bir Türkçe tarih formatı ise (19 Şubat 2025)
                            if isinstance(date_str, str) and any(month in date_str for month in turkish_months):
                                for month_name, month_num in turkish_months.items():
                                    if month_name in date_str:
                                        # "19 Şubat 2025" -> "19-02-2025"
                                        date_str = date_str.replace(month_name, month_num)
                                        day, month, year = date_str.split()
                                        parsed_date = f"{year}-{month}-{day.zfill(2)}"
                                        parsed_dates.append(parsed_date)
                                        break
                            else:
                                # Timestamp olabilir
                                if pd.notna(date_str) and not isinstance(date_str, str):
                                    try:
                                        # Unix timestamp'i milisaniye olarak kabul et
                                        dt = pd.to_datetime(date_str, unit='ms')
                                        parsed_dates.append(dt.strftime('%Y-%m-%d %H:%M'))
                                    except:
                                        parsed_dates.append(None)
                                else:
                                    parsed_dates.append(None)
                        except:
                            parsed_dates.append(None)
                    
                    # Dönüştürülmüş tarihleri ata
                    df['Tarih'] = parsed_dates
                    
                    # Herhangi bir eksik değer için yeniden deneme yap
                    mask = df['Tarih'].isna()
                    if mask.any():
                        # Tarih formatını belirterek dönüştürmeyi dene
                        df.loc[mask, 'Tarih'] = pd.to_datetime(
                            df.loc[mask, 'Tarih'], 
                            format='%Y-%m-%d', 
                            errors='coerce'
                        ).dt.strftime('%Y-%m-%d')
                except Exception as e:
                    print(f"Tarih dönüşümünde hata: {str(e)}")
            
            # Excel dosyasını geçici dizine kaydet
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"yorumlar_{content_id}_{timestamp}.xlsx"
            filepath = os.path.join(self.base_tool._temp_dir, filename)
            
            # Save to Excel
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            # Geçici dosya olarak kaydet (30 dakika sonra otomatik silinecek)
            self.base_tool.register_temp_file(filepath, ttl_minutes=30)
            
            # JSON yedek olarak da kaydet
            json_filename = f"yorumlar_{content_id}_{timestamp}.json"
            json_filepath = os.path.join(self.base_tool._temp_dir, json_filename)
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(reviews, f, ensure_ascii=False, indent=4)
            self.base_tool.register_temp_file(json_filepath, ttl_minutes=30)
            
            return filename, self.base_tool.get_file_url(filename)
            
        except Exception as e:
            print(f"Excel dosyası oluşturulurken hata: {str(e)}")
            return f"Excel dosyası oluşturulurken hata: {str(e)}", None
    
    def forward(self, url: Optional[str] = None) -> str:
        """
        Scrape customer reviews from a Trendyol product page URL and export them to Excel.
        
        Args:
            url: The Trendyol product page URL to scrape reviews from
        """
        if not url or url.strip() == "":
            return "Lütfen Trendyol ürün URLsini girin."
        
        print(f"Trendyol yorum taraması başlatılıyor: {url}")
        
        # Extract content ID from URL
        content_id = self.extract_content_id(url)
        if not content_id:
            return "URLden ürün ID çıkarılamadı. Geçerli bir Trendyol ürün URL'si girin."
        
        try:
            # Fetch reviews
            start_time = time.time()
            reviews = self.fetch_reviews(content_id)
            end_time = time.time()
            
            if not reviews:
                return f"Bu ürün için yorum bulunamadı: {url}"
                
            # Convert to Excel and get the filename
            excel_filename, excel_path = self.reviews_to_excel(reviews, url, content_id)
            
            if not excel_path:
                return excel_filename  # Hata mesajı dönmüş olacak
            
            # İstatistikler
            ratings = [review.get('rate', 0) for review in reviews if 'rate' in review]
            rating_counts = {i: ratings.count(i) for i in range(1, 6)}
            
            # Kullanıcı bilgileri
            elite_users = len([r for r in reviews if r.get('isElite', False)])
            influencer_users = len([r for r in reviews if r.get('isInfluencer', False)])
            trusted_users = len([r for r in reviews if r.get('trusted', False)])
            
            # Yorum uzunluğu ve içeriği analizi
            comment_lengths = [len(review.get('comment', '')) for review in reviews if 'comment' in review]
            avg_comment_length = sum(comment_lengths) / len(comment_lengths) if comment_lengths else 0
            
            # Sonuç mesajı oluştur
            result = f"✅ Yorum taraması tamamlandı!\n\n"
            result += f"**Toplam {len(reviews)} yorum toplandı ve Excel dosyasına kaydedildi.**\n\n"
            result += f"**Tarama süresi**: {end_time - start_time:.2f} saniye\n\n"
            
            # İstatistikler
            result += "📊 **Değerlendirme İstatistikleri**\n\n"
            
            # Yıldız dağılımı
            result += "**Yıldız Dağılımı**:\n"
            total_ratings = sum(rating_counts.values())
            for star in range(5, 0, -1):
                count = rating_counts.get(star, 0)
                percentage = (count / total_ratings) * 100 if total_ratings > 0 else 0
                result += f"{star} ⭐: {count} yorum ({percentage:.1f}%)\n"
            
            # Ortalama değerlendirme puanı
            avg_rating = sum(star * count for star, count in rating_counts.items()) / total_ratings if total_ratings > 0 else 0
            result += f"\n**Ortalama Değerlendirme**: {avg_rating:.1f} / 5\n"
            
            # Kullanıcı bilgileri
            result += f"\n**Kullanıcı İstatistikleri**:\n"
            result += f"Elite Kullanıcılar: {elite_users} yorum ({elite_users/len(reviews)*100:.1f}%)\n"
            result += f"Influencer Kullanıcılar: {influencer_users} yorum ({influencer_users/len(reviews)*100:.1f}%)\n"
            result += f"Güvenilir Kullanıcılar: {trusted_users} yorum ({trusted_users/len(reviews)*100:.1f}%)\n"
            
            # Yorum uzunluğu
            result += f"\n**Yorum Uzunluğu**: Ortalama {avg_comment_length:.0f} karakter\n\n"
            
            result += f"**Dosya Adı**: {excel_filename}\n\n"
            
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
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            return f"Yorumlar çekilirken bir hata oluştu: {str(e)}"
