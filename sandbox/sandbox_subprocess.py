import subprocess
import os

# This gets injected at the top of every generated script.
# It disables network access at the socket level before the user code runs.
NETWORK_BLOCK_SNIPPET = """
import socket

class NetworkBlockedError(Exception):
    pass

def _blocked_socket(*args, **kwargs):
    raise NetworkBlockedError("Network access is disabled in this sandbox.")

socket.socket = _blocked_socket
socket.create_connection = _blocked_socket
"""

def execute_python_code(code_string: str) -> dict:
    """Executes Python code safely with a timeout, no network access, and isolated workspace."""
    filename = "temp_workspace.py"

    if "```python" in code_string:
        code_string = code_string.split("```python")[1].split("```")[0].strip()
    elif "```" in code_string:
        code_string = code_string.split("```")[1].split("```")[0].strip()

    # Inject the network block before the actual code
    full_code = NETWORK_BLOCK_SNIPPET + "\n\n" + code_string

    with open(filename, "w") as f:
        f.write(full_code)

    try:
        result = subprocess.run(
            ["python", filename],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        output = result.stdout if success else result.stderr
        return {"success": success, "output": output, "code_used": code_string}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Error: Code execution timed out.", "code_used": code_string}
    finally:
        if os.path.exists(filename):
            os.remove(filename)