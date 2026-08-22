import ollama

def analyze_image(prompt: str, image_path: str) -> str:
    """Sends an image and prompt to the local vision model."""
    try:
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }]
        )
        return response['message']['content']
    except Exception as e:
        return f"Vision Error: {str(e)}"