import asyncio
import httpx
import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import time
import re
import os
from smolagents.tools import Tool

class TrendyolQuestionScraper(Tool):
    """A tool for scraping product questions and answers from Trendyol."""
    
    name = "trendyol_question_scraper"
    description = "Scrapes questions and answers from a Trendyol product page URL and exports them to Excel."
    inputs = {
        "url": {
            "type": "string",
            "description": "The Trendyol product page URL to scrape questions from",
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
    
    # Function to fetch product questions for a given page
    async def fetch_questions_page(self, client: httpx.AsyncClient, content_id: str, page: int, semaphore) -> List[Dict]:
        async with semaphore:
            params = {
                "tag": "tümü",
                "size": 50,
                "storefrontId": 1,
                "culture": "tr-TR",
                "contentId": content_id,
                "fulfilmentType": "MP,ST,FT",
                "orderBy": "CreatedDate",
                "order": "DESC",
                "channelId": 1,
                "page": page
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8',
                'Origin': 'https://www.trendyol.com',
                'Referer': 'https://www.trendyol.com/'
            }
            
            base_url = os.getenv("trendyolquestion")
            
            try:
                response = await client.get(base_url, params=params, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    # Veri yapısı değişimi: result içinde doğrudan soru listesi geliyor olabilir
                    content = data.get('result', [])
                    if isinstance(content, dict):
                        content = content.get('content', [])
                    return content
                else:
                    return []
            except Exception as e:
                print(f"Hata oluştu: {e}")
                return []
    
    async def scrape_questions(self, url: str):
        # Extract content ID from URL
        content_id = self.extract_content_id(url)
        if content_id is None:
            return "Ürün ID'si URL'den çıkarılamadı. Lütfen geçerli bir Trendyol ürün URL'si girin."
            
        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(30)
        all_questions = []
        page = 0
        error_count = 0  # Hata sayacı ekledik
        
        # Default headers for requests
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8',
            'Origin': 'https://www.trendyol.com',
            'Referer': 'https://www.trendyol.com/'
        }
        
        # Create client with headers
        async with httpx.AsyncClient(headers=headers) as client:
            while True:
                try:
                    # Fetch multiple pages concurrently
                    tasks = [self.fetch_questions_page(client, content_id, p, semaphore) for p in range(page, page + 30)]
                    results = await asyncio.gather(*tasks)

                    # Flatten the results
                    new_data = [item for sublist in results if sublist for item in sublist]

                    if not new_data:
                        print(f"Page {page}-{page+30}: No more questions")
                        break  # Stop if no new data is fetched

                    all_questions.extend(new_data)
                    print(f"Pages {page}-{page+29}: Collected {len(new_data)} questions. Total: {len(all_questions)}")
                    
                    if len(new_data) < 30 * 50:  # If we got less than the expected maximum
                        break
                        
                    page += 30
                    await asyncio.sleep(0.3)  # Rate limiting to avoid being blocked
                except Exception as e:
                    print(f"Pages {page}-{page+29}: Error fetching data: {str(e)}")
                    error_count += 1
                    if error_count >= 3:  # 3 ardışık hata sonrası durdur
                        print("Çok fazla hata, işlem durduruluyor. Çekilen sorular kaydedilecek.")
                        break
                    # Bir sonraki sayfa grubuna geç
                    page += 30
                    await asyncio.sleep(1)  # Hata durumunda biraz daha bekle
        
        print(f"Toplam {len(all_questions)} soru toplandı.")
        return all_questions
    
    def questions_to_excel(self, questions: List[Dict], url: str, content_id: str) -> Tuple[str, str]:
        if not questions:
            return "Ürün için soru bulunamadı.", None
            
        print(f"Excel dosyası oluşturuluyor ({len(questions)} soru)...")
        
        try:
            # Create a dataframe from the questions
            df_data = []
            for question in questions:
                try:
                    # Yeni veri yapısına göre düzenlenen sorular
                    row = {
                        'Soru ID': question.get('id', ''),
                        'Soru': question.get('text', ''),
                        'Soru Tarihi': question.get('creationDate', ''),
                        'Soru Sahibi': question.get('userName', ''),
                        'Cevaplanma Süresi': question.get('answeredDateMessage', ''),
                        'Güvenilir': question.get('trusted', False),
                    }
                    
                    # Satıcı bilgisi 
                    row['Satıcı'] = question.get('merchantName', '')
                    row['Satıcı ID'] = question.get('merchantId', '')
                    
                    # Cevap bilgisi
                    try:
                        answer = question.get('answer', {})
                        if answer and isinstance(answer, dict):
                            row['Cevap'] = answer.get('text', '')
                            row['Cevap Tarihi'] = answer.get('creationDate', '')
                        else:
                            row['Cevap'] = ''
                            row['Cevap Tarihi'] = ''
                    except (AttributeError, TypeError) as e:
                        print(f"Cevap bilgisi işlenirken hata: {str(e)}")
                        row['Cevap'] = ''
                        row['Cevap Tarihi'] = ''
                        
                    df_data.append(row)
                except Exception as e:
                    print(f"Soru işlenirken hata: {str(e)}. Bu soru atlanıyor.")
                    continue
                
            df = pd.DataFrame(df_data)
            
            # Format dates if available
            for date_col in ['Soru Tarihi', 'Cevap Tarihi']:
                if date_col in df.columns:
                    try:
                        # Try to parse the date string or timestamp
                        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                        # Format all dates to a consistent format
                        df[date_col] = df[date_col].dt.strftime('%Y-%m-%d %H:%M')
                    except Exception as e:
                        # If there's any error in date formatting, keep as is
                        print(f"{date_col} tarih dönüştürme hatası: {str(e)}")
                        pass
            
            # Excel dosyasını geçici dizine kaydet
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sorular_{content_id}_{timestamp}.xlsx"
            filepath = os.path.join(self.base_tool._temp_dir, filename)
            
            # Save Excel to temp directory
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            # Geçici dosya olarak kaydet (30 dakika sonra otomatik silinecek)
            self.base_tool.register_temp_file(filepath, ttl_minutes=30)
            
            # JSON yedek olarak da kaydet
            json_filename = f"sorular_{content_id}_{timestamp}.json"
            json_filepath = os.path.join(self.base_tool._temp_dir, json_filename)
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(questions, f, ensure_ascii=False, indent=4)
            self.base_tool.register_temp_file(json_filepath, ttl_minutes=30)
            
            return filename, self.base_tool.get_file_url(filename)
            
        except Exception as e:
            print(f"Excel dosyası oluşturulurken hata: {str(e)}")
            return f"Excel dosyası oluşturulurken hata: {str(e)}", None
    
    def forward(self, url: Optional[str] = None) -> str:
        """
        Scrape questions and answers from a Trendyol product page URL and export them to Excel.
        
        Args:
            url: The Trendyol product page URL to scrape questions from
        """
        if not url or url.strip() == "":
            return "Lütfen Trendyol ürün URLsini girin."
        
        print(f"Trendyol soru-cevap taraması başlatılıyor: {url}")
        
        # Extract content ID from URL
        content_id = self.extract_content_id(url)
        if not content_id:
            return "URLden ürün ID çıkarılamadı. Geçerli bir Trendyol ürün URL'si girin."
        
        try:
            # Fetch questions
            start_time = time.time()
            questions = asyncio.run(self.scrape_questions(url))
            end_time = time.time()
            
            if isinstance(questions, str):  # Check if we got an error message
                return questions
                
            if not questions:
                return f"Bu ürün için soru bulunamadı: {url}"
                
            # Convert to Excel and get the filename
            excel_filename, excel_path = self.questions_to_excel(questions, url, content_id)
            
            if not excel_path:
                return excel_filename  # Hata mesajı dönmüş olacak
            
            # İstatistikler
            answered_questions = len([q for q in questions if q.get('answer') not in [None, {}]])
            unanswered_questions = len(questions) - answered_questions
            
            # Satıcı bazlı istatistikler
            merchant_stats = {}
            for q in questions:
                merchant = q.get('merchantName', 'Belirsiz Satıcı')
                if merchant in merchant_stats:
                    merchant_stats[merchant] += 1
                else:
                    merchant_stats[merchant] = 1
            
            # Sonuç mesajı oluştur
            result = f"✅ Soru-cevap taraması tamamlandı!\n\n"
            result += f"**Toplam {len(questions)} soru toplandı ve Excel dosyasına kaydedildi.**\n\n"
            result += f"**Tarama süresi**: {end_time - start_time:.2f} saniye\n\n"
            
            # İstatistikler
            result += "📊 **Soru-Cevap İstatistikleri**\n\n"
            result += f"Cevaplanmış Sorular: {answered_questions} ({answered_questions/len(questions)*100:.1f}%)\n"
            result += f"Cevaplanmamış Sorular: {unanswered_questions} ({unanswered_questions/len(questions)*100:.1f}%)\n\n"
            
            # En aktif satıcılar
            result += "**En Fazla Soru Cevaplayan Satıcılar**:\n"
            top_merchants = sorted(merchant_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            for i, (merchant, count) in enumerate(top_merchants, 1):
                result += f"{i}. {merchant}: {count} soru\n"
            
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
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            return f"Sorular çekilirken bir hata oluştu: {str(e)}" 
