import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from smolagents.tools import Tool

class TrendyolBaseTool(Tool):
    """Base class for Trendyol tools with temporary file management."""
    
    # Tool sınıfı için gerekli özellikler
    name = "trendyol_base_tool"
    description = "Base tool for Trendyol scraping operations that handles file management."
    inputs = {}  # Base tool olduğu için boş inputs
    output_type = "string"
    
    # Sınıf değişkeni olarak geçici dosyaları izleme
    _temp_files = {}  # dosya_yolu -> silinme_zamani sözlüğü
    _temp_dir = None  # Geçici dosyalar için dizin
    
    @classmethod
    def initialize_temp_directory(cls):
        """Geçici dosyalar için dizin oluştur"""
        if cls._temp_dir is None:
            # Önce Huggingface Spaces için kontrol et
            if os.environ.get('SPACE_ID'):
                # Huggingface Spaces'te /tmp kullan
                cls._temp_dir = Path("/tmp/trendyol_scraper")
            else:
                # Yerel geliştirmede temp dizini kullan
                temp_path = Path(tempfile.gettempdir()) / "trendyol_scraper"
                # Workspace'in içinde temp dizini de oluştur (alternatif olarak)
                workspace_temp = Path(os.getcwd()) / "temp"
                
                # Önce workspace içindeki temp dizinini kullanmayı dene
                if workspace_temp.exists() or workspace_temp.mkdir(exist_ok=True):
                    cls._temp_dir = workspace_temp
                else:
                    # Eğer workspace içinde temp oluşturulamazsa, sistem temp dizinini kullan
                    cls._temp_dir = temp_path
                
            # Dizini oluştur (yoksa)
            os.makedirs(cls._temp_dir, exist_ok=True)
            
            print(f"Geçici dosya dizini oluşturuldu: {cls._temp_dir}")
            
            # Geçici dosyaların otomatik temizlenmesi için zamanlama başlat
            cls._start_cleaner()
    
    @classmethod
    def _start_cleaner(cls):
        """Eski geçici dosyaları temizlemek için bir background thread başlat"""
        # Bu işlevi gerçek bir thread veya asyncio task olarak çalıştırabilirsiniz
        # Basit olması için şimdilik sadece kontrol ediyoruz
        cls._cleanup_old_files()
    
    @classmethod
    def _cleanup_old_files(cls):
        """Eski geçici dosyaları temizle"""
        now = datetime.now()
        files_to_delete = []
        
        for file_path, expiry_time in cls._temp_files.items():
            if now > expiry_time:
                files_to_delete.append(file_path)
        
        # Süresi dolmuş dosyaları sil
        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Geçici dosya silindi: {file_path}")
                del cls._temp_files[file_path]
            except Exception as e:
                print(f"Dosya silinirken hata oluştu: {file_path} - {str(e)}")
    
    @classmethod
    def register_temp_file(cls, file_path, ttl_minutes=60):
        """Geçici dosyayı izleme listesine ekle"""
        expiry_time = datetime.now() + timedelta(minutes=ttl_minutes)
        cls._temp_files[file_path] = expiry_time
        print(f"Geçici dosya kaydedildi: {file_path} - {ttl_minutes} dakika sonra silinecek")
        
        # Her kayıtta eski dosyaları kontrol et ve temizle
        cls._cleanup_old_files()
    
    def __init__(self):
        """Sınıf başlatıldığında geçici dizini ayarla"""
        super().__init__()
        self.initialize_temp_directory()
    
    def get_file_path(self, filename):
        """Dosya yolunu oluştur - Huggingface veya yerel dosya sistemine göre"""
        # Eğer tam yol verilmişse, doğrudan kullan
        if os.path.isabs(filename):
            return filename
            
        # Yoksa, geçici dizin içinde oluştur
        return os.path.join(self._temp_dir, filename)
    
    def get_file_url(self, filename):
        """Dosya URL veya yolunu oluştur (Hugging Face veya yerel için)"""
        file_path = self.get_file_path(filename)
        
        # Hugging Face Spaces'te dosya yolunu döndür (zaten /tmp altında olacak)
        if os.environ.get('SPACE_ID'):
            return file_path
        else:
            # Yerel dosya yolu
            return file_path
            
    def forward(self):
        """Base tool için varsayılan forward metodu - inputs boş olduğunda hiçbir parametre almamalı"""
        return "Bu bir temel araçtır ve doğrudan kullanılmamalıdır."

# Önce TrendyolBaseTool tanımlandıktan sonra diğer modülleri import ediyoruz
from tools.trendyol_scraper import TrendyolScraper
from tools.comment_scraper import TrendyolCommentScraper
from tools.question_scraper import TrendyolQuestionScraper
from tools.keyword_scraper import TrendyolKeywordScraper
from tools.store_scraper import TrendyolStoreScraper

__all__ = [
    'TrendyolScraper',
    'TrendyolCommentScraper',
    'TrendyolQuestionScraper',
    'TrendyolKeywordScraper',
    'TrendyolStoreScraper',
    'TrendyolBaseTool',
] 