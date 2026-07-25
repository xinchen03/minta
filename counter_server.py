#!/usr/bin/env python
"""Counter panel API server for 反例收集 system.
Serves the knowledge base HTML and provides CRUD API for counter-inbox.md.
"""

import http.server
import json
import os
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

PORT = 18720

# Resolve project root: ~/.minta/config.json engine_root -> script parent fallback
def _resolve_project_root() -> Path:
    """Resolve the Minta-next project root for counter file paths."""
    # Priority 1: ~/.minta/config.json engine_root
    try:
        minta_cfg = Path.home() / '.minta' / 'config.json'
        if minta_cfg.exists():
            cfg = json.loads(minta_cfg.read_text(encoding='utf-8'))
            er = cfg.get('engine_root', '')
            if er:
                p = Path(er)
                if p.exists():
                    return p
    except Exception:
        pass
    # Priority 2: Script parent directory (Minta-next root)
    return Path(__file__).resolve().parent

PROJECT_ROOT = _resolve_project_root()
INBOX_FILE = PROJECT_ROOT / '.remember' / 'counter-inbox.md'
FEEDBACK_FILE = PROJECT_ROOT / '.remember' / 'feedback_counter-examples.md'
KB_HTML = PROJECT_ROOT / '知识库.html'

# JSONL candidate queue (same path as hook fallback)
CANDIDATE_QUEUE = Path.home() / '.minta' / 'counter' / 'candidate-queue.jsonl'

# ── Markdown ↔ JSON conversion ──────────────────────────────────────────

ITEM_RE = re.compile(
    r'^- \[(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)]\s*'
    r'\[conf:([\d.]+)]\s*'
    r'\[status:(\w+)]\s*'
    r'(?:\[cid:([^\]]+)]\s*)?'
    r'(.*?)\s*'
    r'(#[\w一-鿿-]+(?:\s+#[\w一-鿿-]+)*)?$'
)

def parse_inbox():
    """Parse counter-inbox.md into structured items."""
    items = []
    if not INBOX_FILE.exists():
        return items
    text = INBOX_FILE.read_text(encoding='utf-8')
    for line in text.split('\n'):
        line = line.strip()
        if not line.startswith('- ['):
            continue
        m = ITEM_RE.match(line)
        if not m:
            # Try simpler parse
            m2 = re.match(r'^- \[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})]\s*(.*)', line)
            if m2:
                items.append({
                    'id': str(len(items)),
                    'date': m2.group(1),
                    'text': m2.group(2).strip(),
                    'confidence': 0.7,
                    'status': 'pending',
                    'tags': [],
                    'contradictionWith': None
                })
            continue
        date_str, conf_str, status, cid, text, tags_str = m.groups()
        tags = []
        if tags_str:
            tags = [t.strip().lstrip('#') for t in tags_str.strip().split() if t.strip()]
        items.append({
            'id': str(len(items)),
            'date': date_str.strip(),
            'text': text.strip(),
            'confidence': float(conf_str),
            'status': status.strip(),
            'tags': tags,
            'candidate_id': cid.strip() if cid else None,
            'contradictionWith': None
        })
    return items

def write_inbox(items):
    """Write items back to counter-inbox.md."""
    lines = ['# 反例收件箱', '',
              '> 零格式草稿本。Claude 自动捕获纠正信号写入，或手动 `/反例` 追加。',
              '> 定期在知识库面板中处理 → 格式化归档到 feedback_counter-examples.md → 清空。',
              '', '---', '', '## 待处理', '']
    for item in items:
        if item.get('status') == 'archived':
            continue
        date = item.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))
        conf = item.get('confidence', 0.7)
        status = item.get('status', 'pending')
        text = item.get('text', '')
        cid = item.get('candidate_id', '')
        tags = ' '.join('#' + t for t in item.get('tags', []) if t.strip())
        line = f"- [{date}] [conf:{conf:.1f}] [status:{status}]"
        if cid:
            line += f' [cid:{cid}]'
        line += f' {text}'
        if tags:
            line += ' ' + tags
        lines.append(line)
    lines.append('')
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INBOX_FILE.write_text('\n'.join(lines), encoding='utf-8')

def format_feedback_entry(item):
    """Format a single item for feedback_counter-examples.md."""
    date = item.get('date', '')[:10]
    text = item.get('text', '')
    parts = text.split('→')
    error = parts[0].strip() if len(parts) > 0 else text
    correction = parts[1].strip() if len(parts) > 1 else ''
    reason = parts[2].strip() if len(parts) > 2 else '待补充'
    tags = item.get('tags', [])
    entry = f'\n### {date}: {text[:60]}\n'
    entry += f'- **错误**: {error}\n'
    entry += f'- **纠正**: {correction}\n'
    entry += f'- **原因**: {reason}\n'
    entry += f'- **标签**: {" ".join("#"+t for t in tags)}\n'
    return entry

def regenerate_hot_cache():
    """Rebuild the 近期高发 summary section in feedback_counter-examples.md."""
    if not FEEDBACK_FILE.exists():
        return
    content = FEEDBACK_FILE.read_text(encoding='utf-8')

    # Parse existing entries to count tags
    tag_counts = {}
    entry_re = re.compile(r'^- \*\*标签\*\*: (.+)$', re.MULTILINE)
    text_re = re.compile(r'^### \d{4}-\d{2}-\d{2}: (.+)$', re.MULTILINE)
    tag_examples = {}

    for m in entry_re.finditer(content):
        tags = [t.strip('#') for t in m.group(1).split('#') if t.strip()]
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    for m in text_re.finditer(content):
        text = m.group(1).split('→')[0].strip()[:40]
        # Find nearest tag line after this entry
        pos = m.end()
        tag_m = entry_re.search(content, pos, pos + 600)
        if tag_m:
            tags = [t.strip('#') for t in tag_m.group(1).split('#') if t.strip()]
            for t in tags:
                if t not in tag_examples:
                    tag_examples[t] = text

    # Build summary lines
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    summary_lines = []
    for tag, count in sorted_tags:
        example = tag_examples.get(tag, '')
        if example:
            summary_lines.append(f'- **#{tag}** ({count}次) — {example}')
        else:
            summary_lines.append(f'- **#{tag}** ({count}次)')

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total = sum(tag_counts.values()) if tag_counts else len(re.findall(r'^### \d{4}', content, re.MULTILINE))

    hot_block = f'\n> 最近归档: {now} | 累计: {total} 条\n\n'
    hot_block += '\n'.join(summary_lines) if summary_lines else '- 暂无'

    # Replace existing 近期高发 section or insert after frontmatter end
    hot_pattern = re.compile(
        r'## 近期高发（会话自动加载）.*?(?=## 反例列表)',
        re.DOTALL
    )
    if hot_pattern.search(content):
        content = hot_pattern.sub(
            f'## 近期高发（会话自动加载）\n\n{hot_block}\n\n',
            content
        )
    else:
        # Insert before 反例列表
        content = content.replace(
            '## 反例列表',
            f'## 近期高发（会话自动加载）\n\n{hot_block}\n\n## 反例列表'
        )

    FEEDBACK_FILE.write_text(content, encoding='utf-8')

# ── HTTP Server ──────────────────────────────────────────────────────────

class CounterHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Quiet

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def json_resp(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length > 0 else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.json_resp({'ok': True})
        elif self.path == '/api/counter':
            items = parse_inbox()
            self.json_resp({'items': items})
        elif self.path == '/api/counter/candidates':
            self.import_candidates()
        elif self.path == '/' or self.path == '/index.html':
            self.serve_kb_html()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/counter':
            data = self.read_body()
            items = data.get('items', [])
            write_inbox(items)
            self.json_resp({'success': True})
        elif self.path == '/api/counter/process':
            data = self.read_body()
            indices = data.get('indices', [])
            items = parse_inbox()
            entries = []
            for i in sorted(indices):
                if i < len(items):
                    items[i]['status'] = 'archived'
                    entries.append(format_feedback_entry(items[i]))
            if entries:
                stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                block = f'\n<!-- processed {stamp} -->' + ''.join(entries) + '\n'
                with open(FEEDBACK_FILE, 'a', encoding='utf-8') as f:
                    f.write(block)
                regenerate_hot_cache()
            write_inbox(items)
            self.json_resp({'success': True, 'count': len(entries)})
        elif self.path == '/api/counter/append':
            data = self.read_body()
            self._handle_append(data)
        else:
            self.send_error(404)

    def _handle_append(self, data: dict):
        """Handle /api/counter/append — supports both flat and structured payloads."""
        items = parse_inbox()

        # R5C.P1: Accept structured candidate payload from hook
        if 'schema_version' in data and data.get('schema_version') == '1.0':
            # Structured candidate from counter_capture.py hook
            candidate_id = data.get('candidate_id', '')
            # Dedup by candidate_id
            for existing in items:
                if existing.get('candidate_id') == candidate_id:
                    self.json_resp({'success': True, 'id': existing.get('id'), 'dedup': True})
                    return
            text = data.get('user_excerpt', '')
            confidence = data.get('confidence', 0.75)
            tags = ['candidate'] + data.get('signal_types', [])
            items.append({
                'id': str(len(items)),
                'date': data.get('captured_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
                'text': text,
                'confidence': confidence,
                'status': 'pending',
                'tags': tags,
                'candidate_id': candidate_id,
                'contradictionWith': None,
                'source': data.get('source', ''),
                'requires_review': data.get('requires_review', True),
            })
        else:
            # Legacy flat format: {text, confidence, tags}
            items.append({
                'id': str(len(items)),
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'text': data.get('text', ''),
                'confidence': data.get('confidence', 0.7),
                'status': 'pending',
                'tags': data.get('tags', []),
                'contradictionWith': None,
            })

        write_inbox(items)
        self.json_resp({'success': True, 'id': str(len(items) - 1)})

    def import_candidates(self):
        """GET /api/counter/candidates — import from JSONL fallback queue to inbox."""
        if not CANDIDATE_QUEUE.exists():
            self.json_resp({'imported': 0, 'message': 'No candidate queue found'})
            return

        items = parse_inbox()
        existing_ids = {i.get('candidate_id') for i in items if i.get('candidate_id')}
        imported = 0

        try:
            lines = CANDIDATE_QUEUE.read_text(encoding='utf-8').strip().split('\n')
            remaining = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cid = candidate.get('candidate_id', '')
                if cid and cid in existing_ids:
                    remaining.append(line)  # keep for retry
                    continue

                items.append({
                    'id': str(len(items)),
                    'date': candidate.get('captured_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
                    'text': candidate.get('user_excerpt', ''),
                    'confidence': candidate.get('confidence', 0.75),
                    'status': 'pending',
                    'tags': ['candidate', 'imported'] + candidate.get('signal_types', []),
                    'candidate_id': cid,
                    'contradictionWith': None,
                    'source': candidate.get('source', 'jsonl_import'),
                    'requires_review': candidate.get('requires_review', True),
                })
                imported += 1

            # Write back remaining (non-imported) lines
            if remaining:
                CANDIDATE_QUEUE.write_text('\n'.join(remaining) + '\n', encoding='utf-8')
            else:
                CANDIDATE_QUEUE.unlink(missing_ok=True)

            if imported:
                write_inbox(items)

            self.json_resp({'imported': imported, 'remaining': len(remaining)})
        except Exception as e:
            self.json_resp({'imported': imported, 'error': str(e)}, code=500)

    def serve_kb_html(self):
        if not KB_HTML.exists():
            self.send_error(404, 'KB HTML not found')
            return
        html = KB_HTML.read_text(encoding='utf-8')
        # Inject counter data
        items = parse_inbox()
        data_json = json.dumps(items, ensure_ascii=False)
        inject = f'<script>const EMBEDDED_COUNTER_DATA = {data_json};</script>'
        html = html.replace('</head>', f'{inject}\n</head>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_cors()
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))


def main():
    no_browser = '--no-browser' in sys.argv
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', PORT))
        s.close()
    except OSError:
        print(f'Server already running on http://127.0.0.1:{PORT}')
        if not no_browser:
            webbrowser.open(f'http://127.0.0.1:{PORT}/')
        return

    server = http.server.HTTPServer(('127.0.0.1', PORT), CounterHandler)
    print(f'Counter server: http://127.0.0.1:{PORT}/')
    if not no_browser:
        webbrowser.open(f'http://127.0.0.1:{PORT}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')


if __name__ == '__main__':
    main()
