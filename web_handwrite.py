import io
import base64
import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from handwrite.cli import converters

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "web_font_cache"
FONT_NAME = "HandwriteWeb"
FONT_PATH = CACHE_DIR / f"{FONT_NAME}.ttf"
SAMPLE_IMAGE = BASE_DIR / "tests" / "test_data" / "sheettopng" / "excellent.jpg"

HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Handwrite Web</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #f5f5f5;
      margin: 0;
      padding: 32px;
      color: #222;
    }
    .container {
      max-width: 980px;
      margin: 0 auto;
      background: white;
      border-radius: 16px;
      box-shadow: 0 12px 30px rgba(0,0,0,0.08);
      padding: 28px;
    }
    h1 {
      margin-top: 0;
      font-size: 2rem;
    }
    textarea {
      width: 100%;
      min-height: 130px;
      font-size: 1.1rem;
      padding: 14px;
      border: 1px solid #ccc;
      border-radius: 10px;
      resize: vertical;
      box-sizing: border-box;
    }
    .controls {
      margin-top: 18px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .status {
      min-height: 1.2em;
      margin-top: 12px;
      color: #555;
    }
    button {
      background: #222;
      color: white;
      border: none;
      border-radius: 10px;
      padding: 12px 18px;
      font-size: 1rem;
      cursor: pointer;
    }
    button:hover {
      background: #111;
    }
    .preview {
      margin-top: 24px;
      display: grid;
      gap: 24px;
    }
    .page {
      padding: 18px;
      border: 1px solid #ddd;
      background: #eee;
      border-radius: 12px;
    }
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .page img {
      width: min(100%, 620px);
      height: auto;
      display: block;
      margin: 0 auto;
      box-shadow: 0 3px 12px rgba(0,0,0,0.12);
    }
    .empty {
      color: #666;
      font-style: italic;
      padding: 32px;
      text-align: center;
    }
    .legend {
      display: flex;
      gap: 18px;
      margin-top: 12px;
      color: #555;
      font-size: 0.9rem;
    }
    .legend span::before {
      content: '';
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 7px;
    }
    .black-ink::before {
      background: #141414;
    }
    .blue-ink::before {
      background: #1e40a0;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Handwrite Web</h1>
    <textarea id="textInput" placeholder="Paste text here...">Hello from Handwrite!</textarea>
    <div class="controls">
      <button id="generateBtn">Generate handwritten image</button>
      <button id="copyPagesBtn" disabled>Copy all pages for Word</button>
      <button id="printPdfBtn" disabled>Print / Save as PDF</button>
    </div>
    <div class="status" id="status" role="status" aria-live="polite"></div>
    <div class="legend">
      <span class="black-ink">Main headings and questions</span>
      <span class="blue-ink">Answers</span>
    </div>
    <div class="preview" id="preview">
      <div class="empty">Your handwritten image will appear here.</div>
    </div>
  </div>

  <script>
    const preview = document.getElementById('preview');
    const textInput = document.getElementById('textInput');
    const generateBtn = document.getElementById('generateBtn');
    const copyPagesBtn = document.getElementById('copyPagesBtn');
    const printPdfBtn = document.getElementById('printPdfBtn');
    const status = document.getElementById('status');
    let generatedPages = [];

    function buildPageDocument() {
      const pageImages = generatedPages.map((page, index) => {
        const pageBreak = index < generatedPages.length - 1
          ? 'page-break-after: always; break-after: page;'
          : '';
        return `<div class="page" style="${pageBreak}"><img src="data:image/png;base64,${page.png}" width="794" height="1123" style="display:block;width:210mm;height:297mm;" alt="Handwritten page ${page.number}"></div>`;
      }).join('');
      return `<!doctype html><html><head><meta charset="utf-8"><title>Handwritten pages</title><style>@page{size:A4;margin:0}html,body{margin:0;padding:0}.page{width:210mm;height:297mm;page-break-after:always;break-after:page}.page:last-child{page-break-after:auto;break-after:auto}img{display:block;width:210mm;height:297mm}</style></head><body>${pageImages}</body></html>`;
    }

    async function copyAllPages() {
      if (!generatedPages.length) return;
      if (!navigator.clipboard || !window.ClipboardItem) {
        status.textContent = 'Clipboard copy is unavailable in this browser. Use Download PNG on each page or Print / Save as PDF.';
        return;
      }
      try {
        const html = buildPageDocument();
        const plainText = `Handwritten document (${generatedPages.length} A4 pages).`;
        await navigator.clipboard.write([
          new ClipboardItem({
            'text/html': new Blob([html], { type: 'text/html' }),
            'text/plain': new Blob([plainText], { type: 'text/plain' })
          })
        ]);
        status.textContent = `Copied all ${generatedPages.length} A4 pages. Paste into Word.`;
      } catch (error) {
        status.textContent = `Copy failed: ${error.message || 'clipboard access was denied.'}`;
      }
    }

    function printPdf() {
      if (!generatedPages.length) return;
      const printWindow = window.open('', '_blank');
      if (!printWindow) {
        status.textContent = 'The print window was blocked. Allow pop-ups and try again.';
        return;
      }
      printWindow.document.open();
      printWindow.document.write(buildPageDocument());
      printWindow.document.close();
      status.textContent = 'Preparing A4 pages for printing...';
      Promise.all(Array.from(printWindow.document.images).map((image) =>
        image.decode().catch(() => undefined)
      )).then(() => {
        printWindow.focus();
        printWindow.print();
        status.textContent = 'In the print dialog, choose Save as PDF to create your PDF.';
      }).catch((error) => {
        status.textContent = `Could not prepare pages for printing: ${error.message}`;
      });
    }

    async function generateImage() {
      const text = textInput.value.trim();
      if (!text) {
        preview.innerHTML = '<div class="empty">Please enter some text first.</div>';
        return;
      }

      preview.innerHTML = '<div class="empty">Generating...</div>';
      generateBtn.disabled = true;
      try {
        const response = await fetch('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || 'Could not generate image.');
        }

        generatedPages = result.pages;
        preview.innerHTML = '';
        result.pages.forEach((page) => {
          const card = document.createElement('section');
          card.className = 'page';
          const header = document.createElement('div');
          header.className = 'page-header';
          const label = document.createElement('strong');
          label.textContent = `Page ${page.number} of ${result.pages.length}`;
          const download = document.createElement('a');
          download.href = `data:image/png;base64,${page.png}`;
          download.download = `handwritten-page-${page.number}.png`;
          download.textContent = 'Download PNG';
          const img = document.createElement('img');
          img.src = download.href;
          img.alt = `Handwritten text, page ${page.number}`;
          header.append(label, download);
          card.append(header, img);
          preview.appendChild(card);
        });
        copyPagesBtn.disabled = false;
        printPdfBtn.disabled = false;
        status.textContent = `${result.pages.length} A4 page${result.pages.length === 1 ? '' : 's'} ready.`;
      } catch (error) {
        preview.innerHTML = '';
        generatedPages = [];
        copyPagesBtn.disabled = true;
        printPdfBtn.disabled = true;
        const message = document.createElement('div');
        message.className = 'empty';
        message.textContent = error.message || 'Could not generate image.';
        preview.appendChild(message);
      } finally {
        generateBtn.disabled = false;
      }
    }

    generateBtn.addEventListener('click', generateImage);
    copyPagesBtn.addEventListener('click', copyAllPages);
    printPdfBtn.addEventListener('click', printPdf);
    textInput.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        generateImage();
      }
    });
    generateImage();
  </script>
</body>
</html>
"""


def ensure_font() -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not FONT_PATH.exists():
        converters(
            str(SAMPLE_IMAGE),
            str(CACHE_DIR),
            config=None,
            metadata={"filename": FONT_NAME},
        )
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Could not generate font at {FONT_PATH}")
    return str(FONT_PATH)


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
PAGE_MARGIN = 48
FONT_SIZE = 48
LINE_SPACING = 24
PARAGRAPH_SPACING = 18
BLACK_INK = (20, 20, 20)
BLUE_INK = (30, 64, 160)


def _is_heading(line: str) -> bool:
    title = re.sub(r"^\s*(?:#{1,6}\s*|(?:\d+|[A-Za-z])[.)]\s+)", "", line).strip()
    if title != line.strip() or re.match(r"^\s*#{1,6}\s+", line):
        return True
    if re.match(r"^[A-Za-z][A-Za-z \-]{0,40}\s*:", title):
        return True
    letters = [character for character in title if character.isalpha()]
    if letters and all(character.isupper() for character in letters):
        return True
    words = title.split()
    small_words = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
    }
    return (
        1 <= len(words) <= 10
        and not title.endswith((".", "!", "?", ";", ","))
        and all(word[0].isupper() or word.lower() in small_words for word in words)
    )


def _is_question(line: str) -> bool:
    if "?" in line:
        return True
    return bool(
        re.match(
            r"^\s*(?:Q\s*\d+\s*[.):]\s*|Q\s*[:.)-]\s*|"
            r"(?:who|what|when|where|why|how|which|whose|whom|"
            r"can|could|do|does|did|is|are|was|were|will|would|"
            r"should|may|might|has|have|had|explain|describe|discuss|"
            r"define|compare|contrast|identify|list|state|give|"
            r"outline|summarize|name|calculate|show|prove)\b)",
            line,
            flags=re.IGNORECASE,
        )
    )


def _is_explicit_answer(line: str) -> bool:
    return bool(re.match(r"^\s*(?:A|Ans(?:wer)?)\s*[:.)-]\s*", line, re.I))


def _append_wrapped_text(entries, draw, font, text: str, color, max_width: int):
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue
        if current:
            entries.append((current, color))
            current = ""
        remaining = word
        while remaining and draw.textbbox((0, 0), remaining, font=font)[2] > max_width:
            split_at = 1
            while (
                split_at < len(remaining)
                and draw.textbbox((0, 0), remaining[: split_at + 1], font=font)[2]
                <= max_width
            ):
                split_at += 1
            entries.append((remaining[:split_at], color))
            remaining = remaining[split_at:]
        current = remaining
    if current:
        entries.append((current, color))


def _wrap_text(draw, font, text: str, max_width: int):
    entries = []
    question_continues = False
    answer_mode = False
    for raw_line in text.splitlines() or [""]:
        if not raw_line.strip():
            if entries and entries[-1] is not None:
                entries.append(None)
            question_continues = False
            continue

        explicit_answer = _is_explicit_answer(raw_line)
        starts_question = _is_question(raw_line)
        is_heading = _is_heading(raw_line) and not starts_question
        answer_match = re.match(
            r"^(\s*(?:A|Ans(?:wer)?)\s*[:.)-]\s*)(.*)$", raw_line, re.I
        )

        if explicit_answer:
            answer_mode = True
            question_continues = False
            color = BLACK_INK
        elif starts_question:
            answer_mode = False
            question_continues = not re.search(r'[.!?]["\u2019\u201d\']?\s*$', raw_line)
            color = BLACK_INK
        elif question_continues:
            question_continues = not re.search(r'[.!?]["\u2019\u201d\']?\s*$', raw_line)
            color = BLACK_INK
        elif is_heading:
            color = BLACK_INK
        else:
            color = BLUE_INK if answer_mode else BLACK_INK

        line = re.sub(r"^\s*#{1,6}\s*", "", raw_line).strip()
        if answer_match:
            prefix, answer_text = answer_match.groups()
            _append_wrapped_text(
                entries, draw, font, prefix.strip(), BLACK_INK, max_width
            )
            answer_text = answer_text.strip()
            if answer_text:
                answer_color = BLACK_INK if _is_heading(answer_text) else BLUE_INK
                _append_wrapped_text(
                    entries, draw, font, answer_text, answer_color, max_width
                )
        else:
            _append_wrapped_text(entries, draw, font, line, color, max_width)

    while entries and entries[-1] is None:
        entries.pop()
    return entries or [("", BLACK_INK)]


def render_handwritten_pages(text: str) -> list[bytes]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Please enter some text.")
    font_path = ensure_font()
    font = ImageFont.truetype(font_path, FONT_SIZE)
    probe = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(probe)
    max_width = PAGE_WIDTH - 2 * PAGE_MARGIN
    lines = _wrap_text(draw, font, text.strip(), max_width)
    font_bbox = font.getbbox("Ag")
    line_height = font_bbox[3] - font_bbox[1]
    step = line_height + LINE_SPACING
    page_capacity = PAGE_HEIGHT - 2 * PAGE_MARGIN
    page_lines = []
    current_page = []
    used_height = 0
    for entry in lines:
        if entry is None:
            if current_page and current_page[-1] is not None:
                current_page.append(None)
                used_height += PARAGRAPH_SPACING
            continue
        if current_page and used_height + step > page_capacity:
            while current_page and current_page[-1] is None:
                current_page.pop()
            page_lines.append(current_page)
            current_page = []
            used_height = 0
        current_page.append(entry)
        used_height += step
    while current_page and current_page[-1] is None:
        current_page.pop()
    if current_page:
        page_lines.append(current_page)

    pages = []
    for lines_on_page in page_lines:
        img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
        page_draw = ImageDraw.Draw(img)
        y = PAGE_MARGIN
        for entry in lines_on_page:
            if entry is None:
                y += PARAGRAPH_SPACING
            else:
                line, color = entry
                bbox = page_draw.textbbox((0, 0), line, font=font)
                page_draw.text(
                    (PAGE_MARGIN - bbox[0], y - bbox[1]),
                    line,
                    font=font,
                    fill=color,
                )
                y += step
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", dpi=(150, 150))
        pages.append(buffer.getvalue())
    return pages


class HandwriteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(HTML_PAGE.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/generate":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json_error(400, "Invalid content length")
            return

        if length > 2_000_000:
            self._send_json_error(413, "Text is too large to process.")
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            text = payload.get("text") if isinstance(payload, dict) else None
            pages = render_handwritten_pages(text)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json_error(400, str(exc))
            return
        except Exception as exc:
            traceback.print_exc()
            self._send_json_error(500, f"Image generation failed: {exc}")
            return

        response = json.dumps(
            {
                "pages": [
                    {
                        "number": number,
                        "png": base64.b64encode(page).decode("ascii"),
                    }
                    for number, page in enumerate(pages, start=1)
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _send_json_error(self, status: int, message: str):
        response = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    try:
        ensure_font()
    except Exception as exc:
        print(f"Font generation failed: {exc}")
        raise

    server = ThreadingHTTPServer(("0.0.0.0", 8000), HandwriteHandler)
    print("Handwrite web app running at http://localhost:8000")
    server.serve_forever()
