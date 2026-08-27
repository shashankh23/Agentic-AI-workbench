import ollama
import os
from router.router import get_target_model
from sandbox.sandbox import execute_python_code
from docgen.docgen import generate_word_report
from vision.vision import analyze_image
from ledger.ledger import log_action
from docgen.pdf_reader import extract_pdf_text
from docgen.table_extractor import extract_tables_from_pdf
from vision.document_processor import process_document_image

def run_code_with_self_correction(model: str, prompt: str, history: list = None, max_attempts: int = 3) -> str:
    if history is None:
        history = []
    
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
            *history,
            {'role': 'user', 'content': current_prompt}
        ])
        code = response['message']['content']

        result = execute_python_code(code)
        log_action("sandbox_exec", model_used=model, details=f"Success: {result['success']}")

        if result["success"]:
            return (
                f"[Succeeded on attempt {attempt}]\n\n"
                f"**Code:**\n```python\n{result['code_used']}\n```\n\n"
                f"**Output:**\n```\n{result['output']}\n```"
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
        f"**Last error:**\n```\n{result['output']}\n```"
    )

def process_user_request(prompt: str, image_path: str = None, history: list = None):
    if history is None:
        history = []
    history = history[-10:]
    print(f"\n--- Processing: {prompt} ---")

    # 1. Route to the right model
    model = get_target_model(prompt)
    log_action("model_selection", model_used=model, details=f"Prompt: {prompt[:100]}")
    print(f"[Router] Selected model: {model}")

    # 2. Execute specific workflow based on the task
    if "image" in prompt.lower() and image_path:
        print("[Agent] Initiating Vision Task...")
        result = analyze_image(prompt, image_path)
        return result

    elif "report" in prompt.lower() or "document" in prompt.lower():
        print("[Agent] Initiating Extraction -> DocGen Task...")

        # Nested file-type checking inside the report branch
        if image_path and image_path.endswith(".pdf"):
            pdf_text, is_scanned = extract_pdf_text(image_path)
            
            if is_scanned:
                from pdf2image import convert_from_path
                pages = convert_from_path(image_path)
                page_texts = []
                for i, page_img in enumerate(pages):
                    temp_page_path = f"temp_page_{i}.png"
                    page_img.save(temp_page_path)
                    res = process_document_image(temp_page_path)
                    page_texts.append(res["full_text"])
                    os.remove(temp_page_path)
                source_text = "\n\n".join(page_texts)
            else:
                source_text = pdf_text
                tables = extract_tables_from_pdf(image_path)
                if tables:
                    source_text += "\n\n" + "\n\n".join(tables)
        
        elif image_path and image_path.endswith((".png", ".jpg", ".jpeg")):
            res = process_document_image(image_path)
            source_text = res["full_text"]
        
        else:
            source_text = prompt

        response = ollama.chat(model=model, messages=[
            {'role': 'system', 'content': 'You are an extraction assistant. Summarize the document text into 3 key bullet points.'},
            *history,
            {'role': 'user', 'content': source_text}
        ])
        extracted_text = response['message']['content']
        result = generate_word_report(extracted_text)
        log_action("file_write", model_used=model, details="Generated AI_Report.docx")
        return result

    elif "code" in prompt.lower():
        print("[Agent] Initiating Code Generation & Sandbox Task (with self-correction)...")
        return run_code_with_self_correction(model, prompt, history=history)

    else:
        # Fallback to standard chat
        response = ollama.chat(model=model, messages=[*history, {'role': 'user', 'content': prompt}])
        return response['message']['content']