import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import gradio as gr


APP_TITLE = "OpenDataLoader PDF"
OUTPUT_FORMATS = ["markdown", "json", "html", "text", "pdf", "tagged-pdf"]


def _safe_name(path: str, index: int) -> str:
    name = Path(path).name or f"document-{index}.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name


def convert_pdfs(
    files,
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

    try:
        for index, file_path in enumerate(files, start=1):
            source = Path(file_path)
            if source.suffix.lower() != ".pdf":
                shutil.rmtree(workspace, ignore_errors=True)
                return f"Only PDF files are supported: {source.name}", None

            filename = _safe_name(str(source), index)
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            candidate = filename
            counter = 2
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
            "-o",
            str(output_dir),
            "-f",
            ",".join(formats),
            "--table-method",
            table_method,
            "--reading-order",
            reading_order,
            "--image-output",
            image_output,
            "--threads",
            str(int(threads)),
        ]

        if pages and pages.strip():
            command.extend(["--pages", pages.strip()])
        if include_header_footer:
            command.append("--include-header-footer")
        if keep_line_breaks:
            command.append("--keep-line-breaks")
        if use_struct_tree:
            command.append("--use-struct-tree")
        if detect_strikethrough:
            command.append("--detect-strikethrough")
        if sanitize:
            command.append("--sanitize")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60 * 60,
            env={**os.environ, "JAVA_TOOL_OPTIONS": os.getenv("JAVA_TOOL_OPTIONS", "-Xms256m -Xmx2048m")},
        )

        if result.returncode != 0:
            error = (result.stderr or result.stdout or "Unknown conversion error").strip()
            shutil.rmtree(workspace, ignore_errors=True)
            return f"Conversion failed:\n\n{error[-5000:]}", None

        zip_path = Path(tempfile.gettempdir()) / f"opendataloader-{job_id}.zip"
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
            for output_file in output_dir.rglob("*"):
                if output_file.is_file():
                    archive.write(output_file, output_file.relative_to(output_dir))

        shutil.rmtree(workspace, ignore_errors=True)
        return f"Conversion completed successfully for {len(input_paths)} PDF file(s).", str(zip_path)

    except subprocess.TimeoutExpired:
        shutil.rmtree(workspace, ignore_errors=True)
        return "Conversion timed out after 60 minutes.", None
    except Exception as exc:
        shutil.rmtree(workspace, ignore_errors=True)
        return f"Conversion failed: {exc}", None


with gr.Blocks(title=APP_TITLE, theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
# OpenDataLoader PDF

Upload one or more PDF files, choose the extraction settings, then download all generated files as a ZIP archive.
        """
    )

    with gr.Row():
        with gr.Column(scale=3):
            files = gr.File(
                label="PDF files",
                file_count="multiple",
                file_types=[".pdf"],
                type="filepath",
            )
            formats = gr.CheckboxGroup(
                choices=OUTPUT_FORMATS,
                value=["markdown", "json"],
                label="Output formats",
            )
            pages = gr.Textbox(
                label="Pages (optional)",
                placeholder="Examples: 1,3,5-7  — leave empty for all pages",
            )

        with gr.Column(scale=2):
            table_method = gr.Dropdown(
                choices=["default", "cluster"],
                value="default",
                label="Table detection",
            )
            reading_order = gr.Dropdown(
                choices=["xycut", "off"],
                value="xycut",
                label="Reading order",
            )
            image_output = gr.Dropdown(
                choices=["external", "embedded", "off"],
                value="external",
                label="Image output",
            )
            threads = gr.Slider(
                minimum=1,
                maximum=max(1, min(8, os.cpu_count() or 1)),
                value=1,
                step=1,
                label="Worker threads",
            )

    with gr.Accordion("Advanced options", open=False):
        include_header_footer = gr.Checkbox(label="Include headers and footers", value=False)
        keep_line_breaks = gr.Checkbox(label="Keep original line breaks", value=False)
        use_struct_tree = gr.Checkbox(label="Use PDF structure tree when available", value=False)
        detect_strikethrough = gr.Checkbox(label="Detect strikethrough text (experimental)", value=False)
        sanitize = gr.Checkbox(label="Sanitize sensitive data", value=False)

    convert_button = gr.Button("Convert PDF", variant="primary")
    status = gr.Textbox(label="Status", lines=4, interactive=False)
    download = gr.File(label="Download ZIP", interactive=False)

    convert_button.click(
        fn=convert_pdfs,
        inputs=[
            files,
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
        ],
        outputs=[status, download],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        show_error=True,
    )
