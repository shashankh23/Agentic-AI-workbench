import ollama
from router.router import get_target_model
from sandbox.sandbox import execute_python_code
from docgen.docgen import generate_word_report
from vision.vision import analyze_image

def process_user_request(prompt: str, image_path: str = None):
    print(f"\n--- Processing: {prompt} ---")
    
    # 1. Route to the right model
    model = get_target_model(prompt)
    print(f"[Router] Selected model: {model}")
    
    # 2. Execute specific workflow based on the task
    if "image" in prompt.lower() and image_path:
        print("[Agent] Initiating Vision Task...")
        result = analyze_image(prompt, image_path)
        return result
        
    elif "report" in prompt.lower() or "document" in prompt.lower():
        print("[Agent] Initiating Extraction -> DocGen Task...")
        # Step A: Get LLM to extract data
        response = ollama.chat(model=model, messages=[
            {'role': 'system', 'content': 'You are an extraction assistant. Summarize the user text into 3 key bullet points.'},
            {'role': 'user', 'content': prompt}
        ])
        extracted_text = response['message']['content']
        # Step B: Save to Word
        return generate_word_report(extracted_text)
        
    elif "code" in prompt.lower():
        print("[Agent] Initiating Code Generation & Sandbox Task...")
        # Step A: Get LLM to write code
        response = ollama.chat(model=model, messages=[
            {'role': 'system', 'content': 'Write only raw Python code to solve the user prompt. No explanations.'},
            {'role': 'user', 'content': prompt}
        ])
        code = response['message']['content']
        # Step B: Execute code safely
        return execute_python_code(code)
        
    else:
        # Fallback to standard chat
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
