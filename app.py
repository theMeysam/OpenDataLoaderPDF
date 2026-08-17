import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import gradio as gr

APP_TITLE = "OpenDataLoader PDF"
OUTPUT_FORMATS = ["markdown", "json", "html", "text", "pdf", "tagged-pdf"]
OCR_LANGUAGES = {
    "Persian + English (recommended)": {"easyocr": "ar,en", "tesseract": "fas,eng"},
    "Persian only": {"easyocr": "ar", "tesseract": "fas"},
    "Arabic + English": {"easyocr": "ar,en", "tesseract": "ara,eng"},
    "English": {"easyocr": "en", "tesseract": "eng"},
}


def _safe_name(path: str, index: int) -> str:
    name = Path(path).name or f"document-{index}.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, process: subprocess.Popen, timeout: int = 600) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Hybrid OCR backend exited during startup (code {process.returncode}).")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError("Hybrid OCR backend did not become ready within 10 minutes.")


def _stop_process(process):
    if not process:
        return
    try:
        process.terminate()
        process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def convert_pdfs(
    files,
    document_type,
    ocr_engine,
    ocr_language,
    tesseract_psm,
    formats,
    pages,
    table_method,
    reading_order,
    image_output,
    include_header_footer,
    keep_line_breaks,
    use_struct_tree,
    detect_strikethrough,
    sanitize,
    threads,
):
    if not files:
        return "Please select at least one PDF file.", None
    if not formats:
        return "Please select at least one output format.", None

    job_id = uuid.uuid4().hex[:10]
    workspace = Path(tempfile.mkdtemp(prefix=f"odl-{job_id}-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = []
    used_names = set()
    hybrid_process = None
    hybrid_log_path = workspace / "hybrid.log"
    hybrid_log_handle = None

    try:
        for index, file_path in enumerate(files, start=1):
            source = Path(file_path)
            if source.suffix.lower() != ".pdf":
                return f"Only PDF files are supported: {source.name}", None

            filename = _safe_name(str(source), index)
            stem, suffix = Path(filename).stem, Path(filename).suffix
            candidate, counter = filename, 2
            while candidate in used_names:
                candidate = f"{stem}-{counter}{suffix}"
                counter += 1
            used_names.add(candidate)

            destination = input_dir / candidate
            shutil.copy2(source, destination)
            input_paths.append(str(destination))

        command = [
            "opendataloader-pdf",
            *input_paths,
            "-o", str(output_dir),
            "-f", ",".join(formats),
            "--table-method", table_method,
            "--reading-order", reading_order,
            "--image-output", image_output,
            "--threads", str(int(threads)),
        ]

        scanned = document_type == "Scanned / image-based PDF (OCR)"
        if scanned:
            port = _free_port()
            lang = OCR_LANGUAGES[ocr_language][ocr_engine]
            backend_command = [
                "opendataloader-pdf-hybrid",
                "--host", "127.0.0.1",
                "--port", str(port),
                "--force-ocr",
                "--ocr-engine", ocr_engine,
                "--ocr-lang", lang,
                "--device", "cpu",
            ]
            if ocr_engine == "tesseract":
                backend_command.extend(["--psm", str(int(tesseract_psm))])

            hybrid_log_handle = open(hybrid_log_path, "w+", encoding="utf-8")
            hybrid_process = subprocess.Popen(
                backend_command,
                stdout=hybrid_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
            )
            _wait_for_port(port, hybrid_process)

            command.extend([
                "--hybrid", "docling-fast",
                "--hybrid-url", f"http://127.0.0.1:{port}",
                "--hybrid-mode", "full",
                "--hybrid-timeout", "0",
            ])
        elif use_struct_tree:
            command.append("--use-struct-tree")

        if pages and pages.strip():
            command.extend(["--pages", pages.strip()])
        if include_header_footer:
            command.append("--include-header-footer")
        if keep_line_breaks:
            command.append("--keep-line-breaks")
        if detect_strikethrough:
            command.append("--detect-strikethrough")
        if sanitize:
            command.append("--sanitize")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60 * 60,
            env=os.environ.copy(),
        )

        if result.returncode != 0:
            details = (result.stderr or result.stdout or "Unknown conversion error").strip()
            if scanned and hybrid_log_path.exists():
                hybrid_log_handle.flush()
                backend_log = hybrid_log_path.read_text(encoding="utf-8", errors="replace")
                details += "\n\n--- Hybrid OCR backend ---\n" + backend_log[-5000:]
            return f"Conversion failed:\n\n{details[-10000:]}", None

        zip_path = Path(tempfile.gettempdir()) / f"opendataloader-{job_id}.zip"
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
            for output_file in output_dir.rglob("*"):
                if output_file.is_file():
                    archive.write(output_file, output_file.relative_to(output_dir))

        mode = "Hybrid OCR" if scanned else "Native digital PDF"
        engine = f" / {ocr_engine} / {OCR_LANGUAGES[ocr_language][ocr_engine]}" if scanned else ""
        return f"Conversion completed for {len(input_paths)} PDF file(s). Mode: {mode}{engine}", str(zip_path)

    except subprocess.TimeoutExpired:
        return "Conversion timed out after 60 minutes.", None
    except Exception as exc:
        extra = ""
        if hybrid_log_handle:
            try:
                hybrid_log_handle.flush()
                extra = "\n\n" + hybrid_log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
            except Exception:
                pass
        return f"Conversion failed: {exc}{extra}", None
    finally:
        _stop_process(hybrid_process)
        if hybrid_log_handle:
            hybrid_log_handle.close()
        shutil.rmtree(workspace, ignore_errors=True)


with gr.Blocks(title=APP_TITLE) as demo:
    gr.Markdown("""
# OpenDataLoader PDF

Upload PDF files and extract structured Markdown/JSON/HTML. For scanned Persian PDFs choose **Scanned / image-based PDF (OCR)** and start with **Tesseract + Persian + English**.
    """)

    with gr.Row():
        with gr.Column(scale=3):
            files = gr.File(label="PDF files", file_count="multiple", file_types=[".pdf"], type="filepath")
            document_type = gr.Radio(
                choices=["Digital PDF (selectable text)", "Scanned / image-based PDF (OCR)"],
                value="Digital PDF (selectable text)",
                label="Document type",
            )
            formats = gr.CheckboxGroup(choices=OUTPUT_FORMATS, value=["markdown", "json"], label="Output formats")
            pages = gr.Textbox(label="Pages (optional)", placeholder="Examples: 1,3,5-7 — empty = all pages")

        with gr.Column(scale=2):
            gr.Markdown("### OCR settings")
            ocr_engine = gr.Dropdown(
                choices=["tesseract", "easyocr"],
                value="tesseract",
                label="OCR engine",
                info="Tesseract is recommended first for Persian. EasyOCR is useful for comparison.",
            )
            ocr_language = gr.Dropdown(
                choices=list(OCR_LANGUAGES.keys()),
                value="Persian + English (recommended)",
                label="OCR language",
            )
            tesseract_psm = gr.Dropdown(
                choices=[3, 4, 6, 11, 12],
                value=3,
                label="Tesseract PSM",
                info="3 = automatic page segmentation; 6 = one text block; 11 = sparse text.",
            )

    with gr.Row():
        table_method = gr.Dropdown(choices=["default", "cluster"], value="default", label="Table detection")
        reading_order = gr.Dropdown(choices=["xycut", "off"], value="xycut", label="Reading order")
        image_output = gr.Dropdown(choices=["external", "embedded", "off"], value="external", label="Image output")
        threads = gr.Slider(minimum=1, maximum=max(1, min(8, os.cpu_count() or 1)), value=1, step=1, label="Worker threads")

    with gr.Accordion("Advanced options", open=False):
        include_header_footer = gr.Checkbox(label="Include headers and footers", value=False)
        keep_line_breaks = gr.Checkbox(label="Keep original line breaks", value=False)
        use_struct_tree = gr.Checkbox(label="Use PDF structure tree (digital PDFs only)", value=False)
        detect_strikethrough = gr.Checkbox(label="Detect strikethrough text (experimental)", value=False)
        sanitize = gr.Checkbox(label="Sanitize sensitive data", value=False)

    gr.Markdown("**Persian OCR note:** RTL reading order is still a limitation in OpenDataLoader/Docling. If one engine gives poor word order, compare Tesseract and EasyOCR outputs.")

    convert_button = gr.Button("Convert PDF", variant="primary")
    status = gr.Textbox(label="Status", lines=6, interactive=False)
    download = gr.File(label="Download ZIP", interactive=False)

    convert_button.click(
        fn=convert_pdfs,
        inputs=[files, document_type, ocr_engine, ocr_language, tesseract_psm, formats, pages,
                table_method, reading_order, image_output, include_header_footer, keep_line_breaks,
                use_struct_tree, detect_strikethrough, sanitize, threads],
        outputs=[status, download],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        show_error=True,
        theme=gr.themes.Soft(),
    )
