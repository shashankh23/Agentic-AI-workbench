import subprocess
import os
import uuid
import re
from pathlib import Path

def extract_raw_code(text: str) -> str:
    """Extracts raw python code from LLM responses safely."""
    # Match ```python ... ``` or ``` ... ```
    match = re.search(r"```(?:python)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def execute_python_code(code_string: str) -> dict:
    """Executes Python code inside an isolated, network-disabled Docker container."""

    # Safely extract code without string split errors
    cleaned_code = extract_raw_code(code_string)

    run_id = str(uuid.uuid4())[:8]
    workspace_dir = os.path.join(os.getcwd(), "sandbox_runs")
    os.makedirs(workspace_dir, exist_ok=True)
    filename = os.path.join(workspace_dir, f"temp_{run_id}.py")

    with open(filename, "w", encoding="utf-8") as f:
        f.write(cleaned_code)

    # Convert Windows path to POSIX format for Docker volume mount compatibility
    posix_path = Path(filename).resolve().as_posix()

    try:
        result = subprocess.run(
            [
                "docker", "run",
                "--rm",
                "--network", "none",
                "--memory", "256m",
                "--cpus", "1.0",
                "--pids-limit", "50",
                "-v", f"{posix_path}:/sandbox/script.py:ro",
                "sovereign-sandbox",
                "python3", "/sandbox/script.py"
            ],
            capture_output=True,
            text=True,
            timeout=12
        )
        success = (result.returncode == 0)
        output = result.stdout if success else result.stderr
        return {"success": success, "output": output.strip(), "code_used": cleaned_code}

    except subprocess.TimeoutExpired:
        return {"success": False, "output": "ExecutionError: Code execution exceeded 12s timeout limit.", "code_used": cleaned_code}
    except Exception as e:
        return {"success": False, "output": f"DockerSandboxError: {str(e)}", "code_used": cleaned_code}

    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass