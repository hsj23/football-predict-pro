"""
Silent startup script - run by pythonw.exe (no console window).
Waits for MySQL, starts uvicorn backend.
"""
import os, sys, time, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)) + '\\backend')

# --- Wait for MySQL ---
for i in range(10):
    try:
        import pymysql
        conn = pymysql.connect(host='localhost', user='root', password='123456', database='football_predict', connect_timeout=2)
        conn.close()
        break
    except:
        time.sleep(1)

# --- Kill old processes on port 8000 ---
try:
    result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if ':8000' in line and 'LISTENING' in line:
            parts = line.strip().split()
            pid = parts[-1]
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
except:
    pass

time.sleep(1)

# --- Clear bytecode caches only (not data caches) ---
for root, dirs, files in os.walk('.'):
    for d in dirs:
        if d == '__pycache__':
            try:
                import shutil
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            except:
                pass

# --- Start backend ---
subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    cwd=os.getcwd()
)
