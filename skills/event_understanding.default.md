---
name: event-understanding-default
agent: event-understanding
description: 事件理解默认技能：OCR/视觉理解→干净文本→要素抽取草稿。
inputs: [uploaded_file(bytes,mime,filename) | text]
outputs: [event_text, ocr_markdown, ocr_plain_text, incident_extract_draft]
resources:
  - trip_ai.resources.ocr_tool.OcrTool
  - SiliconFlow vision (Qwen/Qwen3.5-27B)
---

## Action Guide
1) 若有上传图片/PDF：调用 OCR 工具提取 `plain_text` 与 `markdown`，并保存 `raw`。
2) 若是图片且 OCR 文本过短/质量差：调用视觉模型做补充理解，输出“干净文本”（不解释、不Markdown）。
3) 产出 `event_text`：作为下游智能体的主输入文本。
4) 用文本模型抽取 `IncidentExtract` 草稿（严格 JSON）。
5) 记录资源调用与原始输出，便于追踪与复盘。

