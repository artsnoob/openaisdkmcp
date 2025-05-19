import asyncio
from openai import OpenAI
import os
import sys

async def main():
    # Set base_url to include /v1
    ollama_base_url = os.getenv("OLLAMA_BASE_URL_V1", "http://localhost:11434/v1")
    
    # Use a dummy api_key as the client requires one for instantiation
    dummy_api_key = "ollama" 
    
    print(f"Attempting to connect to Ollama at: {ollama_base_url}")
    
    client = OpenAI(
        base_url=ollama_base_url,
        api_key=dummy_api_key 
    )
    
    # Get model name from command line argument or use default
    model_name = sys.argv[1] if len(sys.argv) > 1 else "phi4-mini:latest"
    
    print(f"\n--- Using model: {model_name} ---")
    
    # Start a conversation loop
    conversation_history = []
    
    try:
        while True:
            # Get user input
            user_input = input("\nYou: ")
            
            # Check for exit command
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting chat.")
                break
            
            # Add user message to conversation history
            conversation_history.append({"role": "user", "content": user_input})
            
            try:
                # Call the Ollama API
                response = client.chat.completions.create(
                    model=model_name,
                    messages=conversation_history,
                    stream=False
                )
                
                # Get the assistant's response
                assistant_message = response.choices[0].message.content
                
                # Print the response
                print(f"\nAssistant: {assistant_message}")
                
                # Add assistant message to conversation history
                conversation_history.append({"role": "assistant", "content": assistant_message})
                
            except Exception as e:
                print(f"Error: {e}")
                if hasattr(e, 'body'):
                    print(f"Error details: {e.body}")
    
    except KeyboardInterrupt:
        print("\nExiting chat due to keyboard interrupt.")

if __name__ == "__main__":
    asyncio.run(main())
