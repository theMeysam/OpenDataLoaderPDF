# OpenDataLoader PDF Web UI

A minimal self-hosted web interface for `opendataloader-pdf`, designed for simple manual PDF conversion on CapRover.

## Features

- Upload one or more PDF files
- Export Markdown, JSON, HTML, text, PDF, or tagged PDF
- Select page ranges
- Configure table detection, reading order, image output, and worker threads
- Optional structure-tree parsing, header/footer inclusion, line-break preservation, strikethrough detection, and sanitization
- Download all generated output as one ZIP file
- No database and no external API required

## CapRover deployment

1. Create an app in CapRover.
2. Connect this GitHub repository.
3. Deploy from the `main` branch.
4. Set **Container HTTP Port** to `7860`.
5. Enable HTTPS and attach your desired domain.

No persistent volume is required for the current workflow. Uploaded files and conversion workspaces are temporary; the generated ZIP is returned through the web UI.

## Runtime

The Docker image includes:

- Python 3.11
- OpenJDK 17
- `opendataloader-pdf`
- Gradio

Default JVM memory settings:

```text
-Xms256m -Xmx2048m
```

You can override `JAVA_TOOL_OPTIONS` in CapRover if the server has more or less available memory.

## Local Docker run

```bash
docker build -t opendataloader-pdf-ui .
docker run --rm -p 7860:7860 opendataloader-pdf-ui
```

Then open `http://localhost:7860`.
