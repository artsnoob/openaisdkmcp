import asyncio
from openai import OpenAI
import os

async def main():
    # Set base_url to include /v1, matching the curl command's successful endpoint
    ollama_base_url = os.getenv("OLLAMA_BASE_URL_V1", "http://localhost:11434/v1")
    
    # Use a dummy api_key as the client requires one for instantiation
    dummy_api_key = "ollama" 
    
    print(f"Attempting to connect to Ollama at: {ollama_base_url}")
    print(f"Using dummy API key: {dummy_api_key}")
    
    client = OpenAI(
        base_url=ollama_base_url,
        api_key=dummy_api_key 
    )
    
    models_to_test = ["phi4-mini:latest", "phi3:latest"] # Models from your ollama list
    
    for model_name in models_to_test:
        print(f"\n--- Testing model: {model_name} ---")
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "Say hi this is a test"}],
                stream=False # Simplest request form
            )
            print(f"Successfully received response from {model_name}:")
            if response.choices:
                print(response.choices[0].message.content)
            else:
                print("No choices in response.")
        except Exception as e:
            print(f"Error encountered with model {model_name}:")
            print(f"  Error type: {type(e)}")
            print(f"  Error message: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    # Try to get JSON, then text, then give up
                    if hasattr(e.response, 'json'):
                        data = e.response.json()
                        print(f"  Error body (JSON): {data}")
                    elif hasattr(e.response, 'text'):
                        text = e.response.text()
                        print(f"  Error body (text): {text}")
                    else:
                        print("  Could not retrieve error body.")
                except Exception as json_err:
                    print(f"  Error retrieving response body: {json_err}")
            elif hasattr(e, 'body') and e.body is not None: # For some openai.APIError instances
                 print(f"  Error body (from e.body): {e.body}")
            # else:
            #    print("  No additional error body information found.")


if __name__ == "__main__":
    asyncio.run(main())
