def get_target_model(prompt: str) -> str:
    """Routes the prompt to the appropriate Ollama model."""
    prompt_lower = prompt.lower()
    
    if any(word in prompt_lower for word in ["image", "picture", "scan", "look at"]):
        return "qwen2.5vl:7b"
        
    if any(word in prompt_lower for word in ["code", "python", "script", "debug"]):
        return "qwen2.5-coder:7b-instruct-q4_K_M"
        
    return "qwen2.5:7b-instruct-q4_K_M"


