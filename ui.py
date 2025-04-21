import gradio as gr
from typing import List, Dict, Any, Optional, Callable
import os
import re
import base64
from urllib.parse import urlparse
import time  # Zaman işlemleri için time modülünü ekledik
import secrets  # Güvenli rastgele değer üretmek için
import hashlib  # Şifreleme için
import signal  # Sinyal işlemleri için
import threading  # Arka planda düzenli kontrol için

# ANSI renkli kodları temizleme fonksiyonu
def strip_ansi_codes(text):
    """ANSI renk kodlarını metinden temizler"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# API anahtarlarını şifrelemek ve şifresini çözmek için fonksiyonlar
def encrypt_api_key(api_key, salt=None):
    """API anahtarını geçici olarak hafızada şifreli saklamak için basit şifreleme"""
    if not salt:
        salt = secrets.token_hex(16)  # 16 baytlık rastgele salt oluştur
    
    # Salt ile birleştirip hash'le
    key_bytes = api_key.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hashed = hashlib.pbkdf2_hmac('sha256', key_bytes, salt_bytes, 100000)
    
    # Base64 ile kodla
    encrypted = base64.b64encode(hashed).decode('utf-8')
    return encrypted, salt

def decrypt_api_key(encrypted_key, original_key, salt):
    """Şifrelenmiş API anahtarının doğruluğunu kontrol etmek için"""
    # Aynı tuz ile orijinal anahtarı şifrele
    test_encrypted, _ = encrypt_api_key(original_key, salt)
    # Eğer şifrelenmiş hali aynıysa doğrudur
    return test_encrypted == encrypted_key

# TeeStdOut sınıfı: Hem yakalamak hem de orijinal stdout'a yazdırmak için
class TeeStdOut:
    def __init__(self, original_stdout, captured_output):
        self.original_stdout = original_stdout
        self.captured_output = captured_output
        
    def write(self, message):
        # Hem orijinal stdout'a hem de yakalanan çıktıya yaz
        self.original_stdout.write(message)
        self.captured_output.write(message)
        
    def flush(self):
        # Her iki çıktıyı da flush et
        self.original_stdout.flush()
        self.captured_output.flush()

class ChatUI:
    def __init__(self, agent_creator_func: Callable, openai_models: Dict[str, str], gemini_models: Dict[str, str], api_expiry_minutes: int = 30):
        """Initialize the chat UI with a function that creates an agent with given API provider, key and model."""
        self.agent_creator_func = agent_creator_func
        self.agent = None  # Her oturum için agent SessionState'te saklanacak
        self.chat_history = []  # Her oturum için sohbet geçmişi SessionState'te saklanacak
        self.openai_models = openai_models
        self.gemini_models = gemini_models
        self.last_file_path = None  # Her oturum için son dosya yolu SessionState'te saklanacak
        
        # API güvenliği için değişkenler ekledik
        self.api_expiry_minutes = api_expiry_minutes  # API anahtarının geçerli olacağı süre (dakika)
        self.api_expiry_time = None  # Her oturum için son kullanım zamanı SessionState'te saklanacak
        self.is_api_expired = True  # Her oturum için süre dolma durumu SessionState'te saklanacak
        
        # API güvenliği için şifreleme değişkenleri
        self.encrypted_api_key = None  # Her oturum için şifrelenmiş anahtar SessionState'te saklanacak
        self.api_salt = None  # Her oturum için tuz değeri SessionState'te saklanacak
        self.api_provider = None  # Her oturum için sağlayıcı bilgisi SessionState'te saklanacak
        
        # Arka plan kontrolü için zamanlayıcı
        self.timer = None
        
        # Hugging Face Spaces için geçici dizin yapılandırması
        self.setup_temp_directory()
        
        # Sinyal yakalayıcıları ayarla
        self._setup_signal_handlers()
        
        # HuggingFace Space için düzenli kontrol mekanizmasını başlat
        if os.environ.get('SPACE_ID'):
            self._start_api_expiry_checker()
    
    def _setup_signal_handlers(self):
        """Uygulama kapatma sinyallerini yakalamak için sinyal işleyicileri ayarla"""
        # Windows için özellikle SIGINT (Ctrl+C) sinyalini yakala
        try:
            signal.signal(signal.SIGINT, self._cleanup_on_exit)
            signal.signal(signal.SIGTERM, self._cleanup_on_exit)
        except (AttributeError, ValueError) as e:
            print(f"Sinyal işleyicileri ayarlanamadı: {e}")
    
    def _start_api_expiry_checker(self):
        """Hugging Face Spaces için API anahtar süresini arka planda düzenli olarak kontrol eden mekanizması"""
        print("Hugging Face Spaces için API süresi kontrol mekanizması başlatılıyor...")
        
        # Bu metod sadece Hugging Face Spaces ortamında çağrılır
        # API anahtarının süresini kontrol etmek için bir iş parçacığı oluştur
        def check_api_expiry():
            while True:
                # 300 saniyede bir kontrol et
                time.sleep(300)
                
                # API anahtarı süresi dolmuşsa, otomatik olarak temizle
                if self.api_expiry_time and time.time() > self.api_expiry_time:
                    print("Arka plan kontrolü: API süresi doldu! Otomatik temizleme yapılıyor...")
                    self.clear_sensitive_data()
        
        # İş parçacığını başlat (daemon=True ile ana program kapandığında otomatik kapanır)
        checker_thread = threading.Thread(target=check_api_expiry, daemon=True)
        checker_thread.start()
    
    def _cleanup_on_exit(self, signum, frame):
        """Uygulama çıkışında tüm hassas verileri temizle"""
        print("Uygulama kapatılıyor, hassas veriler temizleniyor...")
        
        # API anahtarlarını çevre değişkenlerinden temizle
        for key in ["OPENAI_API_KEY", "GEMINI_API_KEY"]:
            if key in os.environ:
                del os.environ[key]
        
        # Normal çıkış işlemini devam ettir
        os._exit(0)
    
    def clear_sensitive_data(self, session_state=None):
        """Hassas verileri manuel olarak temizle"""
        print("API verileri manuel olarak temizleniyor...")
        
        # API anahtarlarını çevre değişkenlerinden temizle
        for key in ["OPENAI_API_KEY", "GEMINI_API_KEY"]:
            if key in os.environ:
                old_val = os.environ[key]
                del os.environ[key]
                print(f"{key} çevre değişkeninden silindi. Değer var mıydı: {'Evet' if old_val else 'Hayır'}")
        
        # Session state varsa, oturum değişkenlerini temizle
        if session_state is not None:
            old_key = session_state.get("encrypted_api_key")
            if "encrypted_api_key" in session_state:
                session_state["encrypted_api_key"] = None
            if "api_salt" in session_state:
                session_state["api_salt"] = None
            if "api_provider" in session_state:
                session_state["api_provider"] = None
            if "api_expiry_time" in session_state:
                session_state["api_expiry_time"] = None
            if "is_api_expired" in session_state:
                session_state["is_api_expired"] = True
            if "agent" in session_state:
                session_state["agent"] = None
            if "api_key" in session_state:
                session_state["api_key"] = None
        else:
            # Session state yoksa instance değişkenlerini temizle
            old_key = self.encrypted_api_key
            self.encrypted_api_key = None
            self.api_salt = None
            self.api_provider = None
            self.api_expiry_time = None
            self.is_api_expired = True
            self.agent = None
        
        print(f"Şifrelenmiş API bilgileri temizlendi. Değer var mıydı: {'Evet' if old_key else 'Hayır'}")
        
        # JavaScript ile API süre sayacını da sıfırla
        api_reset_script = """
        <script>
        window.apiExpiryTime = 0;
        if (window.updateApiExpiryTime) window.updateApiExpiryTime();
        </script>
        <div class="api-expiry-info"><p>⚠️ <strong>API anahtarınız temizlendi.</strong> Lütfen yeniden giriş yapın.</p></div>
        """
        
        # Gradio bildirim metni oluştur
        with gr.Blocks() as notification:
            gr.Markdown(api_reset_script)
            
        return """⚠️ **API verileri güvenlik nedeniyle temizlendi.**

Tüm API anahtarları ve hassas veriler sistemden silindi. 
Asistanı tekrar kullanmak için lütfen yeniden API anahtarınızı girin."""
    
    def setup_temp_directory(self):
        """Hugging Face Spaces veya yerel ortam için geçici dizini yapılandırır"""
        # Hugging Face Spaces ortamını kontrol et
        if os.environ.get('SPACE_ID'):
            # Hugging Face Spaces'te /tmp kullan (kalıcı olmayan)
            self.temp_dir = "/tmp/trendyol_scraper"
        else:
            # Yerel geliştirmede çalışma dizini içinde bir temp klasörü kullan
            self.temp_dir = os.path.join(os.getcwd(), "temp")
            
        # Geçici dizini oluştur (yoksa)
        os.makedirs(self.temp_dir, exist_ok=True)
        print(f"Geçici dosya dizini: {self.temp_dir}")
        
    def initialize_agent(self, api_provider: str, api_key: str, model_id: str, session_state=None) -> str:
        """Initialize the agent with the provided API provider, key and model."""
        if not api_key or api_key.strip() == "":
            return "API anahtarı girmelisiniz!"
        
        try:
            # API anahtarının şifrelenmiş halini ve tuz değerini sakla
            encrypted_api_key, api_salt = encrypt_api_key(api_key)
            
            # Session state varsa, bu değerleri oturumda sakla
            if session_state is not None:
                session_state["encrypted_api_key"] = encrypted_api_key
                session_state["api_salt"] = api_salt
                session_state["api_provider"] = api_provider
                session_state["api_key"] = api_key
            else:
                # Session state yoksa instance değişkenlerinde sakla
                self.encrypted_api_key = encrypted_api_key
                self.api_salt = api_salt
                self.api_provider = api_provider
            
            if api_provider == "openai":
                os.environ["OPENAI_API_KEY"] = api_key
            elif api_provider == "gemini":
                os.environ["GEMINI_API_KEY"] = api_key
            
            agent = self.agent_creator_func(api_provider, api_key, model_id)
            
            # Session state varsa, agent'i oturumda sakla
            if session_state is not None:
                session_state["agent"] = agent
            else:
                self.agent = agent
            
            # API son kullanım süresini ayarla
            api_expiry_time = time.time() + (self.api_expiry_minutes * 60)
            
            # Session state varsa, son kullanım zamanını oturumda sakla
            if session_state is not None:
                session_state["api_expiry_time"] = api_expiry_time
                session_state["is_api_expired"] = False
            else:
                self.api_expiry_time = api_expiry_time
                self.is_api_expired = False
            
            welcome_message = """👋 Merhaba! Ben Trendyol Scraping Asistanınız. Size nasıl yardımcı olabilirim:

✅ **Trendyol'da keyword araması yapabilir** ve tüm ürün bilgilerini çekebilirim
✅ **Trendyol ürün linkinden** yorumları veya soru-cevap çiftlerini toplayabilirim
✅ **Trendyol mağaza linkinden** mağaza ürün verilerini toplayabilirim
✅ **Tüm çektiğim verileri Excel dosyası olarak** size sunabilirim

Hemen sorularınızı bekliyorum!

⚠️ **Güvenlik Bilgisi**: API anahtarınız güvenlik amacıyla yalnızca {} dakika aktif kalacaktır. Süre dolduğunda tekrar girmeniz gerekecektir.""".format(self.api_expiry_minutes)

            if session_state is not None:
                session_state["chat_history"] = []
                session_state["chat_history"].append({"role": "assistant", "content": welcome_message})
            else:
                self.chat_history = []
                self.chat_history.append({"role": "assistant", "content": welcome_message})
            
            return f"AI asistan başarıyla başlatıldı! ({api_provider.upper()} - {model_id}) Şimdi sohbet edebilirsiniz."
        except Exception as e:
            return f"Asistan başlatılırken hata oluştu: {str(e)}"
    
    def extract_download_link(self, text):
        """
        Mesaj içindeki indirme linkini ve Excel dosya yolunu çıkarır
        """
        # Excel dosya yolunu bulmak için farklı desenleri kontrol et
        patterns = [
            r'\[Excel Dosyasını İndir\]\((.*?\.xlsx)\)',  # Markdown link
            r'\|Excel Dosyasını İndir\]\((.*?\.xlsx)\)',  # Hatalı Markdown link
            r'(trendyol_.*?\.xlsx)',  # Doğrudan dosya adı
            r'(\w+_\d+_\d+\.xlsx)'  # Genel Excel dosya deseni
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
                
        return None
    
    def process_message(self, message: str, history, session_state=None) -> tuple:
        """Process a user message and update the chat history."""
        # Session state varsa, ondan değerleri al, yoksa instance değişkenlerini kullan
        agent = session_state.get("agent", self.agent) if session_state is not None else self.agent
        api_expiry_time = session_state.get("api_expiry_time", self.api_expiry_time) if session_state is not None else self.api_expiry_time
        is_api_expired = session_state.get("is_api_expired", self.is_api_expired) if session_state is not None else self.is_api_expired
        chat_history = session_state.get("chat_history", self.chat_history) if session_state is not None else self.chat_history
        
        if not agent:
            return history, "Lütfen önce API anahtarınızı girin ve AI asistanı başlatın.", "", None
        
        # API süresini kontrol et - Her istek işlenmeden önce kontrol ediliyor
        if api_expiry_time and time.time() > api_expiry_time:
            # Session state varsa, sürenin dolduğunu oturumda işaretle
            if session_state is not None:
                session_state["is_api_expired"] = True
                is_api_expired = True
            else:
                # Session state yoksa instance değişkeninde işaretle (eski davranış)
                self.is_api_expired = True
                is_api_expired = True
                
            print(f"API süresi doldu! Süre: {api_expiry_time}, Şu anki zaman: {time.time()}")
            
            # API anahtarlarını çevre değişkenlerinden temizle
            for key in ["OPENAI_API_KEY", "GEMINI_API_KEY"]:
                if key in os.environ:
                    old_val = os.environ[key]
                    del os.environ[key]
                    print(f"{key} çevre değişkeninden silindi. Değer var mıydı: {'Evet' if old_val else 'Hayır'}")
            
            # Şifrelenmiş API bilgilerini temizle
            if session_state is not None:
                old_key = session_state.get("encrypted_api_key")
                session_state["encrypted_api_key"] = None
                session_state["api_salt"] = None
                session_state["api_provider"] = None
                session_state["api_expiry_time"] = None
                session_state["agent"] = None
            else:
                # Session state yoksa instance değişkenlerini temizle (eski davranış)
                old_key = self.encrypted_api_key
                self.encrypted_api_key = None
                self.api_salt = None
                self.api_provider = None
                self.api_expiry_time = None
                self.agent = None
            
            print(f"Şifrelenmiş API bilgileri temizlendi. Değer var mıydı: {'Evet' if old_key else 'Hayır'}")
            
            # Süresinin dolduğunu belirten mesajla geri dön
            return history, "Güvenlik nedeniyle API anahtarınızın süresi doldu. Lütfen tekrar API anahtarınızı girin.", "", None
        
        # API süresi halen geçerliyse kalan süreyi log'a yaz
        if api_expiry_time:
            kalan_sure = api_expiry_time - time.time()
            print(f"API süre durumu: {kalan_sure:.1f} saniye kaldı.")
        
        if not message or message.strip() == "":
            return history, "Lütfen bir mesaj girin.", "", None
        
        if history:
            # Session state varsa, sohbet geçmişini oturumda sakla
            if session_state is not None:
                session_state["chat_history"] = history
                chat_history = history
            else:
                # Session state yoksa instance değişkeninde sakla (eski davranış)
                self.chat_history = history
                chat_history = history
            
        # Run the agent
        try:
            # Konsol çıktısını yakalamak için 
            import io
            import sys
            import os
            from contextlib import redirect_stdout, redirect_stderr
            
            # Standart çıktıyı ve hata çıktısını geçici olarak yakalayacak
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            captured_output = io.StringIO()
            
            # Ajanın standart çıktısını yakalayarak çalıştır
            # Hem yakalıyoruz hem de ekrana yazdırmaya devam ediyoruz
            sys.stdout = TeeStdOut(original_stdout, captured_output)
            sys.stderr = TeeStdOut(original_stderr, captured_output)
            
            try:
                result = agent.run(message, reset=False)
            finally:
                # Her durumda orijinal çıktıları geri yükle
                sys.stdout = original_stdout
                sys.stderr = original_stderr
            
            # Yakalanan standart çıktı - ANSI kodlarını temizle
            terminal_output = strip_ansi_codes(captured_output.getvalue())
            
            # Extract response text from the result
            response_text = ""
            if hasattr(result, "response"):
                response_text = result.response
            elif hasattr(result, "output"):
                response_text = result.output
            elif hasattr(result, "content"):
                response_text = result.content
            else:
                # As a fallback, convert the result to string
                response_text = str(result)
            
            # Terminal çıktısından önemli istatistikleri çıkar
            stats_text = ""
            full_terminal_output = ""
            if terminal_output:
                import re
                
                # Orijinal terminal çıktısını debug için yazdır
                print("\nYakalanan Terminal Çıktısı:", terminal_output[:500])  # İlk 500 karakteri göster
                
                # Terminal çıktısını satırlara böl
                lines = terminal_output.strip().split('\n')
                important_lines = []
                full_lines = []
                
                for line in lines:
                    line = line.strip()
                    # Önemli satırları seç (istatistikler için)
                    if line and not line.startswith("UserWarning") and not "debug" in line.lower() and not line.startswith("Yakalanan Terminal"):
                        # Önemli bilgileri içeren satırları ayrıca ekleyelim
                        if ("Toplam" in line or "En Popüler" in line or "✅" in line or 
                           "Excel dosyası" in line or "trendyol_" in line or ".xlsx" in line or
                           "İstatistik" in line or "istatistik" in line or
                           "En Popüler Markalar" in line or "En Popüler Kategoriler" in line):
                            important_lines.append(line)
                        
                        # Anlamlı tüm çıktıları da ekleyelim
                        if "trendyol" in line.lower() or "ürün" in line or "yorum" in line or \
                           "%" in line or "bulundu" in line or "işlendi" in line or \
                           "başarıyla" in line or "hata" in line or \
                           "İstatistik" in line or "istatistik" in line or \
                           "En Popüler Markalar" in line or "En Popüler Kategoriler" in line or \
                           "markalar" in line.lower() or "kategoriler" in line.lower():
                            full_lines.append(line)
                
                if important_lines:
                    stats_text = "\n".join(important_lines)
                
                if full_lines:
                    full_terminal_output = "\n".join(full_lines)
            
            # Excel dosya yolunu çıkar
            file_path = self.extract_download_link(response_text)
            
            # Dosya yolunu Hugging Face Spaces veya yerel ortam için uygun şekilde işle
            if file_path:
                # Eğer mutlak yol değilse ve doğrudan bulunamıyorsa
                if not os.path.isabs(file_path) and not os.path.exists(file_path):
                    # Olası yerleri kontrol et
                    possible_paths = [
                        file_path,  # Doğrudan dosya
                        os.path.join(os.getcwd(), file_path),  # Çalışma dizini
                        os.path.join(self.temp_dir, file_path),  # Geçici dizin
                        os.path.join("/tmp", file_path)  # HF Spaces için /tmp
                    ]
                    
                    for path in possible_paths:
                        if os.path.exists(path):
                            file_path = path
                            break
                    
                    # Hala bulunamadıysa, basit dosya adı olarak kullan (geçici dizinde olmalı)
                    if not os.path.exists(file_path):
                        # Dosya adını al ve temp_dir ile birleştir
                        file_name = os.path.basename(file_path)
                        file_path = os.path.join(self.temp_dir, file_name)
            
            # Terminal çıktısını yanıta ekle
            if full_terminal_output:
                # Tüm anlamlı terminal çıktısını markdown olarak ekle
                terminal_section = f"**📋 Terminal Çıktısı:**\n```\n{strip_ansi_codes(full_terminal_output)}\n```"
                
                # Her zaman terminal çıktısını yanıtın başına ekle
                response_text = terminal_section + "\n\n" + response_text
                print("\nTerminal çıktısı eklenecek:", strip_ansi_codes(full_terminal_output[:200]))
            elif stats_text:
                # Sadece istatistik varsa ekle
                response_text = strip_ansi_codes(stats_text) + "\n\n" + response_text
                print("\nTerminal çıktısı eklenecek:", strip_ansi_codes(stats_text))
            
            # Dosya yolunu sakla ve yanıta ekle
            if file_path and os.path.exists(file_path):
                # Session state varsa, dosya yolunu oturumda sakla
                if session_state is not None:
                    session_state["last_file_path"] = file_path
                else:
                    # Session state yoksa instance değişkeninde sakla (eski davranış)
                    self.last_file_path = file_path
                
                # Dosyanın büyüklüğünü kontrol et
                file_size_kb = os.path.getsize(file_path) / 1024
                file_size_info = f"({file_size_kb:.1f} KB)" if file_size_kb < 1024 else f"({file_size_kb/1024:.1f} MB)"
                
                # Hugging Face Spaces için dosya yolunu ayarla
                if os.environ.get('SPACE_ID'):
                    # HF Spaces'te dosya yolunu oluştur
                    space_id = os.environ.get('SPACE_ID')
                    space_name = os.environ.get('SPACE_NAME', 'TrendyolAiScraper')
                    file_name = os.path.basename(file_path)
                    
                    # Tüm yolu sabit formatta yap
                    space_parts = space_id.split("/")
                    username = space_parts[0] if "/" in space_id else space_id
                    display_path = f"/file={file_path}"
                    
                    # Mesaja Excel linki ekle (eğer zaten yoksa)
                    if "Excel dosyası" not in response_text and "İndirme Linki" not in response_text:
                        response_text += f"\n\n**📥 İndirme Linki**: [Excel Dosyasını İndir]({display_path}) {file_size_info}"
                else:
                    # Yerel ortamda tam dosya yolunu kullan
                    display_path = file_path
                    
                    # Mesaja Excel linki ekle (eğer zaten yoksa)
                    if "Excel dosyası" not in response_text and "İndirme Linki" not in response_text:
                        response_text += f"\n\n**📥 İndirme Linki**: [Excel Dosyasını İndir]({display_path}) {file_size_info}"
            
            # Update chat history with proper message format
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": response_text})
            
            # Session state varsa, güncellenen sohbet geçmişini oturumda sakla
            if session_state is not None:
                session_state["chat_history"] = chat_history
            
            return chat_history, "", "", file_path
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            error_message = f"Hata: {str(e)}"
            return history, error_message, message, None
    
    def extract_stats_from_output(self, output):
        """
        Çıktı içindeki önemli istatistikleri çıkarır
        """
        stats = []
        
        # Toplam ürün sayısı
        product_count_match = re.search(r'Toplam (\d+) ürün', output)
        if product_count_match:
            stats.append(f"Ürün sayısı: {product_count_match.group(1)}")
        
        # Yorum sayısı
        comment_count_match = re.search(r'Toplam (\d+) yorum', output)
        if comment_count_match:
            stats.append(f"Yorum sayısı: {comment_count_match.group(1)}")
        
        # Soru sayısı
        question_count_match = re.search(r'Toplam (\d+) soru', output)
        if question_count_match:
            stats.append(f"Soru sayısı: {question_count_match.group(1)}")
        
        # Tamamlanma yüzdesi
        progress_matches = re.findall(r'İşlem: (\d+)%', output)
        if progress_matches:
            stats.append(f"Son işlem durumu: %{progress_matches[-1]}")
        
        return "\n".join(stats) if stats else ""
    
    def launch_ui(self, share=False):
        """Create and launch the Gradio UI with API key input."""
        with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue", secondary_hue="indigo")) as demo:
            # Session durumu
            session_state = gr.State({
                "encrypted_api_key": None,
                "api_salt": None,
                "api_provider": None,
                "api_key": None,
                "api_expiry_time": None,
                "is_api_expired": True,
                "agent": None,
                "chat_history": [],
                "last_file_path": None
            })
            
            # API geri sayım zamanlayıcısı için state
            timer_state = gr.State({"timer_active": False, "expiry_time": 0})
            
            gr.Markdown("# Trendyol Scraping Assistant Demo v1")
            
            with gr.Row():
                with gr.Column(scale=2):
                    api_provider = gr.Radio(
                        choices=["openai", "gemini"],
                        value="openai",
                        label="AI Sağlayıcısı",
                        info="Kullanmak istediğiniz AI sağlayıcısını seçin"
                    )
                    
                    with gr.Row():
                        with gr.Column():
                            openai_model = gr.Dropdown(
                                choices=list(self.openai_models.keys()),
                                value="gpt-4o-mini",
                                label="OpenAI Model",
                                visible=True,
                                interactive=True
                            )
                        
                        with gr.Column():
                            gemini_model = gr.Dropdown(
                                choices=list(self.gemini_models.keys()),
                                value="gemini/gemini-2.0-flash",
                                label="Gemini Model",
                                visible=False,
                                interactive=True
                            )
                    
                    api_key_input = gr.Textbox(
                        placeholder="API anahtarınızı buraya girin",
                        label="API Anahtarı",
                        type="password"
                    )
                    
                    api_key_button = gr.Button("AI Asistanı Başlat", variant="primary")
                    
                    # Temizleme butonu ekle
                    clear_data_button = gr.Button("API Verilerini Temizle", variant="secondary")
            
            status_text = gr.Markdown("AI asistanı başlatmak için API sağlayıcınızı, modelinizi ve API anahtarınızı belirtin.")
            
            # API süre bilgisi için HTML element yerine Gradio bileşeni kullanıyoruz
            api_expiry_info = gr.Markdown("", visible=False)
            
            # Zamanlayıcı fonksiyonu - her saniye çalışacak
            def timer_tick(timer_data, session_data):
                if not timer_data["timer_active"]:
                    return None
                
                expiry_time = timer_data["expiry_time"]
                if not expiry_time:
                    return None
                
                # Kalan süreyi hesapla
                now = time.time()
                remaining_secs = max(0, int(expiry_time - now))
                
                if remaining_secs <= 0:
                    # Süre doldu mesajı - artık kullanıcıya gösterilmiyor
                    return None
                else:
                    # Geri sayım mesajı - artık kullanıcıya gösterilmiyor
                    return None
            
            chatbot = gr.Chatbot(
                height=600,
                show_label=False,
                layout="bubble",
                type="messages",
                render_markdown=True
            )
            
            with gr.Row():
                msg = gr.Textbox(
                    placeholder="Bir mesaj yazın...",
                    show_label=False,
                    container=True,
                    scale=8
                )
                submit_btn = gr.Button("Gönder", variant="primary", scale=1)
            
            # Excel dosyası indirme bölümü
            with gr.Row(visible=False) as download_row:
                with gr.Column(scale=3):
                    file_info = gr.Markdown("")
                with gr.Column(scale=1):
                    download_button = gr.Button("📥 Excel Dosyasını İndir", variant="primary")
            
            # Doğrudan indirilebilir dosya bileşeni
            file_output = gr.File(label="Excel Dosyası", visible=True)
            
            error_box = gr.Markdown("")
            
            # API provider değiştiğinde model seçim alanlarını güncelle
            def update_model_visibility(provider):
                if provider == "openai":
                    return gr.update(visible=True), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True)
            
            api_provider.change(
                update_model_visibility,
                [api_provider],
                [openai_model, gemini_model]
            )
            
            # Define callback for API key button
            def api_key_callback(provider, api_key, openai_model_val, gemini_model_val, state, timer_data):
                # API anahtarını ve modeli ayarla
                model_id = openai_model_val if provider == "openai" else gemini_model_val
                result = self.initialize_agent(provider, api_key, model_id, state)
                
                # Session state'ten sohbet geçmişini al
                chat_history = state.get("chat_history", self.chat_history)
                
                # API süre bilgisini güncelle ve zamanlayıcıyı başlat
                api_expiry_time = state.get("api_expiry_time", self.api_expiry_time)
                
                # Timer verisini güncelle
                timer_data["timer_active"] = True
                timer_data["expiry_time"] = api_expiry_time
                
                # API süresini konsola yazdır (debug amaçlı)
                print(f"API expiry time set to: {api_expiry_time}")
                
                # API başlangıç mesajını göster
                api_info_message = f"""<script>
                // Global API süre değişkenlerini ayarla
                window.apiExpiryTime = {api_expiry_time};
                window.apiTimerActive = true;
                console.log("API timer variables set:", window.apiExpiryTime);
                </script>
                """
                
                # Return both the status message and the chatbot with welcome message
                return result, chat_history, api_info_message, timer_data
            
            api_key_button.click(
                api_key_callback,
                [api_provider, api_key_input, openai_model, gemini_model, session_state, timer_state],
                [status_text, chatbot, api_expiry_info, timer_state]
            )
            
            # Temizleme butonu işlevi
            def clear_callback(state, timer_data):
                # API verilerini temizle
                result = self.clear_sensitive_data(state)
                
                # Zamanlayıcıyı durdur
                timer_data["timer_active"] = False
                timer_data["expiry_time"] = 0
                
                return result, timer_data, """<script>
                // Timer'ı durdur
                window.apiExpiryTime = 0;
                window.apiTimerActive = false;
                console.log("API timer stopped");
                </script>
                <div class="api-expiry-info warning">
                    <p>⚠️ <strong>API verileriniz temizlendi.</strong> Lütfen yeniden giriş yapın.</p>
                </div>"""
            
            clear_data_button.click(
                clear_callback,
                [session_state, timer_state],
                [status_text, timer_state, api_expiry_info]
            )
            
            # Define callback for message submission
            def chat_callback(message, chat_history, state):
                # Mesajı işle
                chat_result, error, msg_clear, file_path = self.process_message(message, chat_history, state)
                
                # Excel dosyası var mı kontrol et
                last_file_path = state.get("last_file_path", self.last_file_path) if state else self.last_file_path
                download_visible = file_path is not None and os.path.exists(file_path)
                
                # Dosya yolu varsa, dosya bileşenini güncelle
                file_component = None
                file_info_text = ""
                
                if download_visible:
                    # Dosyayı doğrudan Gradio file_output bileşenine yükle
                    file_component = file_path
                    file_name = os.path.basename(file_path)
                    file_size_kb = os.path.getsize(file_path) / 1024
                    file_size_text = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb/1024:.1f} MB"
                    file_info_text = f"**📊 Excel Dosyası**: {file_name} ({file_size_text})\n\n"
                    
                    # Hugging Face'teyse ekstra uyarı ekle
                    if os.environ.get('SPACE_ID'):
                        file_info_text += "**⬇️ Aşağıdaki 'Download' butonuna tıklayarak Excel dosyasını indirebilirsiniz.**"
                
                return chat_result, error, msg_clear, gr.update(visible=download_visible), file_component, file_info_text
            
            # Dosya indirme butonu için callback
            def download_file(state):
                # Session state'ten son dosya yolunu al
                last_file_path = state.get("last_file_path", self.last_file_path) if state else self.last_file_path
                if last_file_path and os.path.exists(last_file_path):
                    return last_file_path
                return None
            
            # Her iki gönderme yöntemi için aynı fonksiyonu kullan
            submit_action = lambda message, chat_history, state: chat_callback(message, chat_history, state)
            
            # Mesaj gönderme (enter tuşu)
            msg.submit(
                submit_action,
                [msg, chatbot, session_state],
                [chatbot, error_box, msg, download_row, file_output, file_info]
            )
            
            # Mesaj gönderme (buton)
            submit_btn.click(
                submit_action,
                [msg, chatbot, session_state],
                [chatbot, error_box, msg, download_row, file_output, file_info]
            )
            
            # Dosya indirme butonu
            download_button.click(
                download_file,
                [session_state],
                [file_output]
            )
            
            # JavaScript ile API zamanlayıcısı için kod ekle - sadece API süresini takip etmek için
            timer_js = """
            <script>
            // Sayfa yüklendiğinde çalışacak fonksiyon
            (function() {
                console.log("Document loaded, setting up background API expiry timer");
                
                // Zamanlayıcı kontrolü - sadece arka planda çalışır, görsel element göstermez
                function checkApiExpiry() {
                    // Session bilgilerinden API süresini al (global olarak paylaşılıyor)
                    var expiryTime = window.apiExpiryTime || 0;
                    var isActive = window.apiTimerActive || false;
                    
                    if (!isActive || !expiryTime) {
                        console.log("Timer not active or no expiry time set");
                        return;
                    }
                    
                    // Kalan süreyi hesapla
                    var now = Math.floor(Date.now() / 1000);
                    var remainingSecs = Math.max(0, Math.floor(expiryTime - now));
                    
                    // Süre dolmuşsa - konsola log
                    if (remainingSecs <= 0) {
                        console.log("API key expired");
                    }
                }
                
                // Zamanlayıcıyı başlat - sadece arka plan kontrolü
                window.apiTimerInterval = setInterval(checkApiExpiry, 5000);
            })();
            </script>
            """
            
            gr.HTML(timer_js)
            
            # Sample questions for easy testing
            with gr.Accordion("Örnek Mesajlar", open=True):
                sample_questions = [
                    "makyaj kategorisindeki ürünleri çeker misin",
                    "Trendyolda akıllı saat araması yap ve tüm ürünleri çek",
                    "https://www.trendyol.com/x/x-p-32041644 buradaki tüm yorumları çeker misin",
                    "https://www.trendyol.com/x/x-p-32041644 ürün sorularını çeker misin",
                    "https://www.trendyol.com/magaza/bershka-m-104961?sst=0 bu mağazadaki ürün bilgileri lazım",
                ]
                
                for question in sample_questions:
                    gr.Button(question).click(
                        lambda q: q,
                        [gr.Textbox(value=question, visible=False)],
                        [msg],
                        queue=False
                    )
            
            # Hugging Face Spaces bilgi kutusu
            if os.environ.get('SPACE_ID'):
                gr.Markdown("""
                ### 📢 Hugging Face Spaces Bilgilendirmesi
                Bu uygulama Hugging Face Spaces üzerinde çalışıyor. Excel dosyalarını indirmek için dosya linki üzerine tıklayabilirsiniz.
                
                ⚠️ **Bilgilendirme:** Tüm excel dosyaları geçici olarak saklanır ve Hugging Face Spaces'in sınırları dahilinde çalışır.
                
                [Ucretsiz Gemini API Key](https://aistudio.google.com/apikey).
                """)
            
            # CSS styles
            gr.HTML("""
            <style>
                button.gr-button {
                    margin: 3px;
                    font-size: 0.9em !important;
                }
                .message-wrap .user-message {
                    background-color: #2e7fd6 !important;
                }
                button[value="📥 Excel Dosyasını İndir"] {
                    background-color: #4CAF50 !important;
                    color: white !important;
                    padding: 10px 15px !important;
                    border: none !important;
                    border-radius: 4px !important;
                    cursor: pointer !important;
                    font-weight: bold !important;
                    transition: background-color 0.3s !important;
                }
                button[value="📥 Excel Dosyasını İndir"]:hover {
                    background-color: #45a049 !important;
                }
                .download-row {
                    margin-top: 20px !important;
                    margin-bottom: 10px !important;
                    background-color: #f9f9f9 !important;
                    padding: 10px !important;
                    border-radius: 8px !important;
                    border: 1px solid #ddd !important;
                }
                /* Gradio footer'ı gizle */
                footer {
                    display: none !important;
                }
                /* Özel footer ekle */
                .custom-footer {
                    text-align: center;
                    padding: 10px;
                    margin-top: 30px;
                    border-top: 1px solid #eee;
                    color: #666;
                }
                
                .api-expiry-info {
                    background-color: #e8f4ff;
                    padding: 12px;
                    border-radius: 5px;
                    margin-bottom: 15px;
                    margin-top: 15px;
                    border-left: 5px solid #4c8bf5;
                    font-weight: bold;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                
                .api-expiry-info.warning {
                    background-color: #fff8e8;
                    border-left-color: #ff9800;
                }
                
                .api-expiry-info p {
                    margin: 0;
                    color: #333;
                    font-size: 15px;
                    line-height: 1.5;
                }
                
                .api-expiry-box {
                    margin-top: 10px;
                    margin-bottom: 10px;
                    min-height: 60px;
                }
            </style>
            """)
            
            # Özel footer ekle
            gr.HTML("""
            <div class="custom-footer">
                <p>© 2025 İbrahim Uğurca - Trendyol Scraping Assistant</p>
                <p><a href="https://tr.linkedin.com/in/ibrahim-u%C4%9Furca-83232927b/" target="_blank">LinkedIn</a></p>
            </div>
            """)
        
        # Hugging Face Spaces için debug mesajı
        if os.environ.get('SPACE_ID'):
            print("🚀 Uygulama Hugging Face Spaces üzerinde çalışıyor!")
            print(f"Geçici dosya dizini: {self.temp_dir}")
        
        # Demo'yu başlat - footer parametresi kaldırıldı çünkü mevcut Gradio sürümüyle uyumlu değil
        demo.launch(share=share, debug=False, show_api=False, show_error=True)
        return demo 

