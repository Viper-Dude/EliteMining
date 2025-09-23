import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

try:
    import markdown
except Exception:
    print('markdown package not found, attempting to install...')
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'markdown'])
    import markdown

HERE = os.path.dirname(__file__)
README_MD = os.path.join(HERE, 'README.md')
OUT_HTML = os.path.join(HERE, 'README_preview.html')

with open(README_MD, 'r', encoding='utf-8') as f:
    md = f.read()

html = markdown.markdown(md, extensions=['tables', 'fenced_code', 'toc', 'attr_list'])
full = f"<html><head><meta charset='utf-8'><title>README Preview</title></head><body>{html}</body></html>"

with open(OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(full)

print('Generated:', OUT_HTML)

os.chdir(HERE)
port = 8000
print(f"Starting HTTP server at http://127.0.0.1:{port}/ (serving {HERE})")

server = HTTPServer(('127.0.0.1', port), SimpleHTTPRequestHandler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    print('Server stopped')
    server.server_close()
