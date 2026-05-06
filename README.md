# TRIP - 高速事故工单智能研判（MVP）

Streamlit 应用：上传高速事故工单（图片/文本），图片走 PaddleOCR（AI Studio layout-parsing）解析，再调用硅基流动大模型做结构化抽取、风险研判与管控建议。

## 运行

1) 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) 配置密钥（不要把真实 key 写进代码或提交到仓库）

复制示例配置：

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

编辑 `.streamlit\secrets.toml`，填入：
- `PADDLE_OCR_TOKEN`：PaddleOCR layout-parsing 的 token
- `SILICONFLOW_API_KEYS`：硅基流动 API keys（逗号分隔）

3) 启动

```powershell
streamlit run app.py
```

## 说明

- OCR：调用 `layout-parsing` 接口，输出 Markdown 与文本
- LLM：通过 OpenAI 兼容接口（`/chat/completions`）调用硅基流动模型
- 结果：展示结构化要素、风险等级、建议措施，并提供 JSON 下载

