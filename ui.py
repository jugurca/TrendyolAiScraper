import gradio as gr
from typing import List, Dict, Any, Optional, Callable
import os
import re
import base64
from urllib.parse import urlparse

# ANSI renkli kodları temizleme fonksiyonu
def strip_ansi_codes(text):
    """ANSI renk kodlarını metinden temizler"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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
    def __init__(self, agent_creator_func: Callable, openai_models: Dict[str, str], gemini_models: Dict[str, str]):
        """Initialize the chat UI with a function that creates an agent with given API provider, key and model."""
        self.agent_creator_func = agent_creator_func
        self.agent = None
        self.chat_history = []
        self.openai_models = openai_models
        self.gemini_models = gemini_models
        self.last_file_path = None
        
        # Hugging Face Spaces için geçici dizin yapılandırması
        self.setup_temp_directory()
        
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
        
    def initialize_agent(self, api_provider: str, api_key: str, model_id: str) -> str:
        """Initialize the agent with the provided API provider, key and model."""
        if not api_key or api_key.strip() == "":
            return "API anahtarı girmelisiniz!"
        
        try:
            # API anahtarını ortam değişkeni olarak kaydetme (Hugging Face Spaces'te kalıcı olabiliyor)
            # Bunun yerine sadece agent oluştururken parametreyi kullan
            self.api_provider = api_provider
            self.api_key = api_key
            self.model_id = model_id
            
            # Create the agent using the provided function - ortam değişkenini kullanmadan doğrudan aktarıyoruz
            self.agent = self.agent_creator_func(api_provider, api_key, model_id)
            
            # Initialize chat history with the welcome message
            welcome_message = """👋 Merhaba! Ben Trendyol Scraping Asistanınız. Size nasıl yardımcı olabilirim:

✅ **Trendyol'da keyword araması yapabilir** ve tüm ürün bilgilerini çekebilirim
✅ **Trendyol ürün linkinden** yorumları veya soru-cevap çiftlerini toplayabilirim
✅ **Trendyol mağaza linkinden** mağaza ürün verilerini toplayabilirim
✅ **Tüm çektiğim verileri Excel dosyası olarak** size sunabilirim

Hemen sorularınızı bekliyorum!"""

            # Clear any existing chat history
            self.chat_history = []
            # Add the welcome message as an assistant message
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
        
    def process_message(self, message: str, history) -> tuple:
        """Process a user message and update the chat history."""
        if not self.agent:
            return history, "Lütfen önce API anahtarınızı girin ve AI asistanı başlatın.", "", None
        
        if not message or message.strip() == "":
            return history, "Lütfen bir mesaj girin.", "", None
        
        if history:
            self.chat_history = history
            
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
                result = self.agent.run(message, reset=False)
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
                self.last_file_path = file_path
                
                # Dosyanın büyüklüğünü kontrol et
                file_size_kb = os.path.getsize(file_path) / 1024
                file_size_info = f"({file_size_kb:.1f} KB)" if file_size_kb < 1024 else f"({file_size_kb/1024:.1f} MB)"
                
                # Hugging Face Spaces için dosya yolunu ayarla
                if os.environ.get('SPACE_ID'):
                    # Dosyayı public olarak erişilebilir yap - HF Spaces'te dosyalar zaten public
                    # Excel dosya adını al
                    file_name = os.path.basename(file_path)
                    display_path = file_path  # Hugging Face'te doğrudan dosya yolunu kullan
                else:
                    # Yerel ortamda tam dosya yolunu kullan
                    display_path = file_path
                
                # Mesaja Excel linki ekle (eğer zaten yoksa)
                if "Excel dosyası" not in response_text and "İndirme Linki" not in response_text:
                    response_text += f"\n\n**📥 İndirme Linki**: [Excel Dosyasını İndir]({display_path}) {file_size_info}"
            
            # Update chat history with proper message format
            self.chat_history.append({"role": "user", "content": message})
            self.chat_history.append({"role": "assistant", "content": response_text})
            
            return self.chat_history, "", "", file_path
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Hata ayrıntıları: {error_trace}")
            error_message = f"Hata: {str(e)}"
            return history, error_message, message, None
    
    def extract_stats_from_output(self, output):
        """Terminal çıktısından önemli istatistikleri çıkar"""
        stats = []
        
        # Ürün sayısı
        product_match = re.search(r'Toplam (\d+) ürün bulundu', output)
        if product_match:
            stats.append(f"Toplam ürün: {product_match.group(1)}")
        
        # Yorum sayısı
        comment_match = re.search(r'Toplam (\d+) yorum bulundu', output)
        if comment_match:
            stats.append(f"Toplam yorum: {comment_match.group(1)}")
        
        # Sayfa sayısı
        page_match = re.search(r'(\d+) sayfa işlendi', output)
        if page_match:
            stats.append(f"İşlenen sayfa: {page_match.group(1)}")
        
        # Tamamlanma yüzdesi
        progress_matches = re.findall(r'İşlem: (\d+)%', output)
        if progress_matches:
            stats.append(f"Son işlem durumu: %{progress_matches[-1]}")
        
        return "\n".join(stats) if stats else ""
    
    def launch_ui(self, share=False):
        """Create and launch the Gradio UI with API key input."""
        with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue", secondary_hue="indigo")) as demo:
            gr.Markdown("# AI Trendyol Scraping Asistanı")
            
            # Sayfa yenilendiğinde uyarı mesajı ekle
            gr.Markdown("""
            ⚠️ **Önemli Bilgilendirme**: Sayfayı kapattığınızda veya yenilediğinizde API anahtarınız sıfırlanacaktır. 
            Her oturumda API anahtarınızı yeniden girmeniz gerekecektir.
            """, elem_id="session_warning")
            
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
            
            status_text = gr.Markdown("AI asistanı başlatmak için API sağlayıcınızı, modelinizi ve API anahtarınızı belirtin.")
            
            # Define welcome message for later use
            welcome_message = """👋 Merhaba! Ben Trendyol Scraping Asistanınız. Size nasıl yardımcı olabilirim:

✅ **Trendyol'da keyword araması yapabilir** ve tüm ürün bilgilerini çekebilirim
✅ **Trendyol ürün linkinden** yorumları veya soru-cevap çiftlerini toplayabilirim
✅ **Trendyol mağaza linkinden** mağaza ürün verilerini toplayabilirim
✅ **Tüm çektiğim verileri Excel dosyası olarak** size sunabilirim

Hemen sorularınızı bekliyorum!"""
            
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
            def api_key_callback(provider, api_key, openai_model_val, gemini_model_val):
                model_id = openai_model_val if provider == "openai" else gemini_model_val
                result = self.initialize_agent(provider, api_key, model_id)
                # Return both the status message and the chatbot with welcome message
                return result, self.chat_history
            
            api_key_button.click(
                api_key_callback,
                [api_provider, api_key_input, openai_model, gemini_model],
                [status_text, chatbot]
            )
            
            # Define callback for message submission
            def chat_callback(message, chat_history):
                chat_result, error, msg_clear, file_path = self.process_message(message, chat_history)
                
                # Excel dosyası var mı kontrol et
                download_visible = file_path is not None and os.path.exists(file_path)
                
                # Dosya yolu varsa, dosya bileşenini güncelle
                file_component = None
                file_info_text = ""
                
                if download_visible:
                    file_component = file_path
                    file_name = os.path.basename(file_path)
                    file_size_kb = os.path.getsize(file_path) / 1024
                    file_size_text = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb/1024:.1f} MB"
                    file_info_text = f"**📊 Excel Dosyası**: {file_name} ({file_size_text})"
                
                return chat_result, error, msg_clear, gr.update(visible=download_visible), file_component, file_info_text
            
            # Dosya indirme butonu için callback
            def download_file():
                if self.last_file_path and os.path.exists(self.last_file_path):
                    return self.last_file_path
                return None
            
            # Her iki gönderme yöntemi için aynı fonksiyonu kullan
            submit_action = lambda message, chat_history: chat_callback(message, chat_history)
            
            # Mesaj gönderme (enter tuşu)
            msg.submit(
                submit_action,
                [msg, chatbot],
                [chatbot, error_box, msg, download_row, file_output, file_info]
            )
            
            # Mesaj gönderme (buton)
            submit_btn.click(
                submit_action,
                [msg, chatbot],
                [chatbot, error_box, msg, download_row, file_output, file_info]
            )
            
            # Dosya indirme butonu
            download_button.click(
                download_file,
                [],
                [file_output]
            )
            
            # Sample questions for easy testing
            with gr.Accordion("Örnek Sorular", open=True):
                sample_questions = [
                    "ruj keywordundeki ürünleri çek",
                    "Trendyolda akıllı saat araması yap ve tüm ürünleri çek",
                    "https://www.trendyol.com/x/x-p-32041644 buradaki tüm yorumları çek",
                    "https://www.trendyol.com/x/x-p-32041644 buradaki tüm soru cevapları çek",
                    "https://www.trendyol.com/magaza/bershka-m-104961?sst=0 ürünleri çek",
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
            </style>
            """)
            
            # JavaScript - sayfa yüklendiğinde API anahtarı durumunu temizle
            gr.HTML("""
            <script>
                // Sayfa yüklendiğinde çalışacak kod
                document.addEventListener('DOMContentLoaded', function() {
                    // Gradio otomatik API anahtarı doldurmasını engelle
                    setTimeout(function() {
                        // API anahtarı input alanını bul ve içeriğini temizle
                        const apiKeyInputs = document.querySelectorAll('input[type="password"]');
                        apiKeyInputs.forEach(input => {
                            input.value = '';
                            // Input değerini değiştirdiğimizi Gradio'ya bildir
                            const event = new Event('input', { bubbles: true });
                            input.dispatchEvent(event);
                        });
                        
                        console.log("Sayfa yüklendi, API anahtarı formu temizlendi.");
                    }, 500);
                });
                
                // Sayfa kapatıldığında veya yenilendiğinde API durumunu sıfırla
                window.addEventListener('beforeunload', function() {
                    // Sessionda kalabilen API anahtarı varsa temizle
                    sessionStorage.removeItem('api_key_state');
                    console.log("Sayfa kapatılıyor, API durumu sıfırlandı.");
                });
                
                // Sayfa her yüklendiğinde otomatik olarak API durumunu kontrol et
                (function checkApiKeyState() {
                    // Sayfa açıldığında durum mesajını kontrol et ve taze sayfa olduğuna emin ol
                    setTimeout(function() {
                        const statusElements = document.querySelectorAll('.prose p, .prose');
                        statusElements.forEach(el => {
                            // Eğer API zaten yüklenmiş görünüyorsa, sayfayı tazele
                            if (el.textContent && el.textContent.includes("AI asistan başarıyla başlatıldı")) {
                                console.log("Yüklü API durumu tespit edildi, sayfa yenileniyor.");
                                window.location.reload();
                            }
                        });
                    }, 1000);
                })();
            </script>
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
