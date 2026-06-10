# This script wraps the picoh-mcp executable, forwarding its stdout and stderr to the console.
# This is so that the picoh-python library can be used 
# It filters stdout lines, only printing those that look like JSON (starting with '{') to standard output, while all other lines are printed to standard error. This allows for structured logging from the picoh-mcp process while still capturing any regular log messages or errors. 
import subprocess
import sys

project_dir = r"D:\Projects\picoh-mcp"
exe = project_dir + r"\.venv\Scripts\picoh-mcp.exe"

p = subprocess.Popen(
    [exe],
    cwd=project_dir,
    stdin=sys.stdin,
    stdout=subprocess.PIPE,
    stderr=sys.stderr,
    text=True,
    bufsize=1
)

for line in p.stdout:
    s = line.lstrip()
    if s.startswith("{"):
        sys.stdout.write(line)
        sys.stdout.flush()
    else:
        print(line.rstrip(), file=sys.stderr)
