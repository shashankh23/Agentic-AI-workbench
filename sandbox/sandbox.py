import subprocess
import os

def execute_python_code(code_string: str) -> str:
    """Executes Python code safely with a timeout."""
    filename = "temp_workspace.py"
    
    # Clean up the LLM output (remove markdown code blocks if present)
    if "```python" in code_string:
        code_string = code_string.split("```python")[1].split("```")[0].strip()
        
    with open(filename, "w") as f:
        f.write(code_string)
        
    try:
        # Run the code with a 10-second timeout
        result = subprocess.run(
            ["python", filename], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        output = result.stdout if result.stdout else result.stderr
        return f"Execution Result:\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Code execution timed out."
    finally:
        if os.path.exists(filename):
            os.remove(filename)