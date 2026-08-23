import ollama
from router.router import get_target_model
from sandbox.sandbox import execute_python_code
from docgen.docgen import generate_word_report
from vision.vision import analyze_image

def run_code_with_self_correction(model: str, prompt: str, max_attempts: int = 3) -> str:
    """Generates code, runs it in the sandbox, and self-corrects on failure."""
    
    current_prompt = prompt
    system_msg = (
        'Write only raw, general-purpose Python code to solve the user prompt. '
        'Define reusable functions with clear parameters. Include a small example '
        'usage with print statements. No explanations, only code.'
    )

    for attempt in range(1, max_attempts + 1):
        print(f"[Agent] Code attempt {attempt}/{max_attempts}...")
        
        response = ollama.chat(model=model, messages=[
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': current_prompt}
        ])
        code = response['message']['content']

        result = execute_python_code(code)

        if result["success"]:
            return (
                f"[Succeeded on attempt {attempt}]\n\n"
                f"Code:\n{result['code_used']}\n\n"
                f"Output:\n{result['output']}"
            )

        # Failed — build a correction prompt for the next attempt
        print(f"[Agent] Attempt {attempt} failed: {result['output'][:200]}")
        current_prompt = (
            f"The following code failed:\n{result['code_used']}\n\n"
            f"Error:\n{result['output']}\n\n"
            f"Fix the code to correctly: {prompt}"
        )

    return (
        f"[Failed after {max_attempts} attempts]\n\n"
        f"Last error:\n{result['output']}"
    )

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
        print("[Agent] Initiating Code Generation & Sandbox Task (with self-correction)...")
        return run_code_with_self_correction(model, prompt)
        
    else:
        # Fallback to standard chat
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
