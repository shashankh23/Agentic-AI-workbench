import os
import ollama
from router.router import get_target_model
from sandbox.sandbox import execute_python_code
from docgen.docgen import generate_word_report
from vision.vision import analyze_image
from ledger.ledger import log_action
from docgen.pdf_reader import extract_pdf_text
from docgen.table_extractor import extract_tables_from_pdf
from vision.document_processor import process_document_image
from memory.cache import check_cache, store_cache


def stream_chat_response(model: str, messages: list):
    """Generator yielding token chunks in real-time from Ollama."""
    stream = ollama.chat(model=model, messages=messages, stream=True)
    for chunk in stream:
        yield chunk['message']['content']


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


def process_user_request(
    prompt: str, 
    image_path: str = None, 
    preloaded_text: str = None, 
    history: list = None
):
    """
    Generator-based dispatcher supporting streaming tokens, semantic caching, 
    multimodal OCR, and document-level provenance linkage.
    """
    if history is None:
        history = []
    history = history[-10:]
    print(f"\n--- Processing: {prompt} ---")

    # 1. Semantic Cache Check
    if not image_path and not preloaded_text and not any(w in prompt.lower() for w in ["code", "report", "document", "python"]):
        cached_result, sim_score = check_cache(prompt)
        if cached_result:
            log_action("cache_hit", model_used="semantic_cache", details=f"Similarity: {sim_score:.3f}")
            yield f"*(Served instantly from Local Semantic Cache — Sim: {sim_score*100:.1f}%)*\n\n" + cached_result
            return

    # 2. Vector Intent Routing & Ledger Action Registration
    model = get_target_model(prompt)
    log_entry = log_action("model_selection", model_used=model, details=f"Prompt: {prompt[:60]}")
    ledger_hash = getattr(log_entry, "current_hash", "local-verified-hash")

    # 3. Vision Task Branch
    if "image" in prompt.lower() and image_path and image_path.endswith((".png", ".jpg", ".jpeg")):
        result = analyze_image(prompt, image_path)
        provenance_footer = f"\n\n---\n`Source Asset: {os.path.basename(image_path)}` | `Audit Hash: {ledger_hash[:12]}`"
        yield result + provenance_footer
        return

    # 4. Report & Document Generation Branch
    elif "report" in prompt.lower() or "document" in prompt.lower() or preloaded_text:
        source_name = "User Input Prompt"
        if preloaded_text:
            source_text = preloaded_text
            source_name = os.path.basename(image_path) if image_path else "Attached Asset"
        elif image_path and image_path.endswith(".pdf"):
            source_name = os.path.basename(image_path)
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
            source_name = os.path.basename(image_path)
            res = process_document_image(image_path)
            source_text = res["full_text"]
        else:
            source_text = prompt

        response = ollama.chat(model=model, messages=[
            {'role': 'system', 'content': 'You are an extraction assistant. Summarize into 3 structured bullet points.'},
            *history,
            {'role': 'user', 'content': source_text}
        ])
        extracted_text = response['message']['content']
        
        # Generate Word doc with attached provenance
        doc_path = generate_word_report(
            content=extracted_text, 
            filename="AI_Report.docx", 
            source_name=source_name,
            ledger_hash=ledger_hash
        )
        log_action("file_write", model_used=model, details=f"Generated {doc_path}")
        
        yield (
            f"### Executive Report Generated\n\n"
            f"**Extracted Findings:**\n{extracted_text}\n\n"
            f"**File Saved Locally:** `{doc_path}`\n\n"
            f"---\n`Source Asset: {source_name}` | `Audited Hash: {ledger_hash[:12]}`"
        )
        return

    # 5. Code Execution Branch
    elif "code" in prompt.lower() or "python" in prompt.lower() or "script" in prompt.lower():
        result = run_code_with_self_correction(model, prompt, history=history)
        yield result + f"\n\n---\n`Environment: Subprocess Sandbox` | `Audit Hash: {ledger_hash[:12]}`"
        return

    # 6. Standard Conversational Stream
    else:
        messages = [*history, {'role': 'user', 'content': prompt}]
        full_response = ""
        for chunk in stream_chat_response(model, messages):
            full_response += chunk
            yield chunk
        
        provenance_footer = f"\n\n---\n`Audit Hash: {ledger_hash[:12]}`"
        yield provenance_footer
        
        store_cache(prompt, full_response + provenance_footer, model)