import sys
import os
from typing import Any, Generator

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from liteparse import LiteParse
    print("✅ Successfully imported LiteParse")
except ImportError:
    print("❌ Error: 'liteparse' not found. Please run 'pip install -r requirements.txt'")
    sys.exit(1)

# Mocking Dify Plugin structures for standalone testing
class MockToolInvokeMessage:
    def __init__(self, message: str):
        self.message = message
    def __str__(self):
        return f"Message: {self.message}"

class TestLiteParse:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.provider_credentials = {"api_key": api_key}

    def create_text_message(self, text: str) -> MockToolInvokeMessage:
        return MockToolInvokeMessage(text)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[MockToolInvokeMessage, None, None]:
        # Implementation copied from tools/dify-liteparse.py but adapted for testing
        api_key = tool_parameters.get('api_key') or self.provider_credentials.get('api_key')
        file_obj = tool_parameters.get('file')

        if not api_key:
            yield self.create_text_message("Error: LlamaCloud API Key is missing.")
            return
        
        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        try:
            # Initialize LiteParse
            parser = LiteParse(api_key=api_key)

            # Handle the file (mocking Dify's file object)
            if isinstance(file_obj, list):
                file_obj = file_obj[0]
            
            if isinstance(file_obj, dict):
                file_path = file_obj.get('path')
            else:
                file_path = file_obj

            if not file_path:
                yield self.create_text_message("Error: File path could not be determined.")
                return

            print(f"🚀 Parsing file: {file_path}")
            documents = parser.load_data(file_path)
            
            if not documents:
                yield self.create_text_message("Warning: No content extracted.")
                return
                
            final_text = "\n\n".join([doc.text for doc in documents])
            yield self.create_text_message(final_text)

        except Exception as e:
            yield self.create_text_message(f"Parsing failed with error: {str(e)}")

if __name__ == "__main__":
    # Get API key from environment or input
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        api_key = input("Enter your LlamaCloud API Key: ")

    if not api_key:
        print("❌ Error: API Key is required.")
        sys.exit(1)

    # Path to the sample document
    sample_doc_path = os.path.join(os.path.dirname(__file__), "sample_doc.txt")
    
    # Create the tester
    tester = TestLiteParse(api_key=api_key)
    
    # Run the invoke logic
    print("--- Starting Test ---")
    results = tester._invoke({"file": {"path": sample_doc_path}})
    
    for res in results:
        print(res)
    print("--- Test Completed ---")
