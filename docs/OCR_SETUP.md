# OCR 配置

BL TradeLoop 使用本地 Tesseract，不会把企业文件发送到第三方 OCR 服务。普通 PDF 先使用原生文字层；没有文字层的页面才进入 OCR。

## Windows

1. 安装 Tesseract OCR，并在安装时选择 English 和 Simplified Chinese (`chi_sim`) 语言包。
2. 在 PowerShell 检查：

```powershell
tesseract --version
tesseract --list-langs
```

3. 如果不在 PATH 中，配置路径：

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
$env:TRADELOOP_OCR_LANGUAGES = 'eng+chi_sim'
```

4. 重新启动 Streamlit。缺少 Tesseract 或语言包时，解析结果会显示配置提示并保持 `needs_ocr`，不会伪造成功。

OCR 依赖的 Python 包是 `pymupdf`、`pytesseract` 和 `Pillow`，已列入项目依赖。OCR 结果包含页码、文本块、置信度和 PDF 坐标；低于 70 的结果会提示人工核对。

## 常见问题

- `OCR_NOT_CONFIGURED`：Tesseract 未安装、未加入 PATH，或未设置 `TESSERACT_CMD`。
- `OCR_LANGUAGES_MISSING`：运行 `tesseract --list-langs`，确认 `eng` 和 `chi_sim` 存在。
- 扫描页没有识别到文字：检查图片清晰度、语言包和页面是否为空。
- 加密 PDF：先解密后再上传，系统不会绕过密码保护。
