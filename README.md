# AI Trendyol Scraping Asistanı

[![Hugging Face Spaces](https://img.shields.io/badge/Hugging%20Face-Spaces-yellow)](https://huggingface.co/spaces/jugurca/TrendyolAiScraper)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-View%20Profile-blue?logo=linkedin)](https://www.linkedin.com/in/ibrahim-u%C4%9Furca-83232927b/)

Trendyol veri çekme işlemlerini otomatize etmek için geliştirilmiş bir yapay zeka asistanıdır. Kullanıcıların doğal dil ile iletişim kurarak Trendyol'dan ürün bilgilerini, yorumları, soruları ve mağaza verilerini çekmesine yardımcı olur.

## Özellikler

- **Doğal Dil Arayüzü**: Karmaşık komutlar yerine normal Türkçe ile iletişim kurabilirsiniz
- **Anahtar Kelime Araması**: Trendyol'da anahtar kelime araması yaparak ürünlerin detaylarını çeker
- **Ürün Yorumları**: Bir ürünün tüm yorumlarını Excel dosyasına aktarır
- **Soru-Cevap**: Ürün soru-cevaplarını toplar
- **Mağaza Ürünleri**: Trendyol mağazasındaki tüm ürünleri çeker
- **Excel Export**: Tüm veriler otomatik olarak Excel dosyasına kaydedilir

## Kullanım

1. AI sağlayıcınızı seçin (OpenAI veya Gemini)
2. API anahtarınızı girin ve asistanı başlatın
3. Doğal dil ile isteklerinizi belirtin, örneğin:
   - "ruj araması yap"
   - "https://www.trendyol.com/xxx/xxx-p-123456 ürününün yorumlarını çek"
   - "şu mağazadaki ürünleri listele: https://www.trendyol.com/magaza/xxx-m-123456"

## Teknik Bilgiler

- **Yapay Zeka**: OpenAI (GPT-4, GPT-4o) veya Google Gemini modellerini kullanır
- **Framework**: Gradio ile oluşturulmuş kullanıcı arayüzü
- **Veri İşleme**: Trendyol'dan veri çekmek için özel araçlar ve web scraping
- **Excel Entegrasyonu**: Veriler otomatik olarak Excel formatında kaydedilir ve indirilebilir

## Hugging Face Spaces Kullanımı

Bu uygulamayı Hugging Face Spaces üzerinde kullanırken dikkat edilmesi gerekenler:

1. API anahtarınızı güvenli bir şekilde girin (başkalarıyla paylaşmayın)
2. İndirilen Excel dosyaları geçici olarak saklanır, önemli verileri kendi cihazınıza kaydedin
3. Hugging Face Spaces'in kaynak kısıtlamaları nedeniyle büyük veri çekme işlemleri sınırlı olabilir

## Başlangıç

OpenAI API anahtarınızı veya Google Gemini API anahtarınızı hazırlayın ve hemen kullanmaya başlayın!

## Örnek Mesajlar

- "ruj keywordunu ara"
- "Trendyolda akıllı saat araması yap"
- "https://www.trendyol.com/x/x-p-32041644 buradaki tüm yorumları çek"
- "https://www.trendyol.com/x/x-p-32041644 buradaki tüm soru cevapları çek"
- "https://www.trendyol.com/magaza/bershka-m-104961?sst=0 ürünleri çek" 
