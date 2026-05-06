# Skills Directory

This folder contains hot-pluggable agent skills as Markdown files.

Format: Markdown with a YAML front matter header.

Example:

```md
---
name: event-understanding-default
agent: event-understanding
description: Default skill for event understanding.
inputs: [uploaded_file, text]
outputs: [event_text, incident_extract_draft]
resources:
  - trip_ai.resources.ocr_tool.OcrTool
  - SiliconFlow vision
---

## Action Guide
1) Do X...
```

