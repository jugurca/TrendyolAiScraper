import os
from smolagents import ToolCallingAgent
from smolagents.models import OpenAIServerModel
from smolagents.default_tools import DuckDuckGoSearchTool, PythonInterpreterTool
from tools import TrendyolScraper, TrendyolCommentScraper, TrendyolQuestionScraper, TrendyolKeywordScraper, TrendyolStoreScraper
from ui import ChatUI
import gradio as gr

# Google Gemini model sınıfı ekleyeceğiz
try:
    from smolagents.models import LiteLLMModel
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("Google Gemini modeli yüklenemedi.")

# Mevcut OpenAI modelleri
OPENAI_MODELS = {
    "gpt-4": "GPT-4",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-3.5-turbo": "gpt-3.5-turbo"
}

# Gemini modelleri
GEMINI_MODELS = {
    "gemini/gemini-2.0-flash": "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-flash": "gemini/gemini-1.5-flash",
    "gemini/gemini-1.5-pro": "gemini/gemini-1.5-pro"
}

def create_agent(api_provider: str, api_key: str, model_id: str):
    """Create and return a ToolCallingAgent with the given API key and model."""
    # Define all tools (tüm araçları tanımla)
    tools = [
        DuckDuckGoSearchTool(),
        PythonInterpreterTool(),
        TrendyolScraper(),
        TrendyolCommentScraper(),
        TrendyolQuestionScraper(),
        TrendyolKeywordScraper(),
        TrendyolStoreScraper(),
    ]
    
    # Özelleştirilmiş sistem promptu
    custom_system_prompt = """
    You are a Turkish assistant specialized in Trendyol data scraping. Always respond in Turkish.
    
    Follow these rules when answering user questions:
    
    1. If information is missing from the user, ask for it first. For example:
       - If the user says "can you get the reviews", first ask "Which product reviews would you like me to get? Please share the Trendyol URL of the product."
       - If the user says "can you give me information about the product", first ask "Which product would you like information about? Please share the Trendyol URL of the product."
    
    2. Progress step by step when using tools:
       - TrendyolScraper - Retrieves product details when given a product URL
       - TrendyolCommentScraper - Exports product reviews to Excel when given a product URL
       - TrendyolQuestionScraper - Exports product questions and answers to Excel when given a product URL
       - TrendyolKeywordScraper - Exports products to Excel when given a keyword
       - TrendyolStoreScraper - Exports store products to Excel when given a store URL
    
    3. Guide the user through the process of gathering missing information, step by step and helpfully.
    
    4. Check URLs - Verify that the URL provided by the user is a valid Trendyol product URL. The URL should start with "https://www.trendyol.com" and contain a product ID.
    
    5. Analyze first, then act. Make sure you fully understand the user's request before calling the appropriate tool.
    
    6. Use clear and understandable sentences that follow Turkish language structure.
    
    7. Consider the habits and preferences of Turkish users. Use a friendly tone.
    """
    
    # Seçilen modele göre API yapılandırması
    if api_provider == "openai":
        # OpenAI modelini yapılandır
        model = OpenAIServerModel(
            model_id=model_id,
            api_key=api_key,
            system_prompt=custom_system_prompt
        )
    elif api_provider == "gemini" and HAS_GEMINI:
        # Gemini modelini yapılandır
        model = LiteLLMModel(
            model_id=model_id,
            api_key=api_key,
            system_prompt=custom_system_prompt
        )
    else:
        raise ValueError("Desteklenmeyen API sağlayıcısı veya Gemini modülleri yüklü değil")
    
    # Initialize and return agent
    return ToolCallingAgent(tools=tools, model=model)

def main():
    """Main function to run the application."""
    # Create chat UI with our agent creator function
    chat_ui = ChatUI(create_agent, openai_models=OPENAI_MODELS, gemini_models=GEMINI_MODELS)
    
    # Launch the UI - Hugging Face Spaces için share=True
    demo = chat_ui.launch_ui(share=True)
    return demo

if __name__ == "__main__":
    # Doğrudan çalıştırıldığında
    main()
else:
    # Hugging Face Spaces için demo nesnesi
    demo = main() 
