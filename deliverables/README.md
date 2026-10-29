# TradeLoop 最终交付目录

本目录保存可直接打开的离线交付材料。HTML 路演和 SVG 海报已经生成，但在最终提交前仍需替换二维码占位、补入真实页面截图、核对最新功能状态，并按主办方规格导出最终文件。

## 当前内容

- `poster/CONTENT_CHECKLIST.md`：0.8m × 1.8m 海报的尺寸、版面和内容验收清单。
- `poster/tradeloop_poster.svg`：物理尺寸为 800mm × 1800mm 的可编辑矢量海报。
- `pitch/THREE_MINUTE_SCRIPT.md`：三分钟路演逐段脚本、页面操作和计时验收表。
- `pitch/index.html`：五页离线路演，可用浏览器直接打开并打印为 PDF。

## 打开三分钟路演

在文件资源管理器中双击 `pitch/index.html`，或在 PowerShell 中执行：

```powershell
Start-Process .\deliverables\pitch\index.html
```

操作方式：

- 使用底部数字导航跳转到指定页面。
- 使用左右方向键、Page Up、Page Down 或空格切换页面。
- Home 跳到第一页，End 跳到第五页。
- 路演不加载网络字体、脚本或图片，可以离线打开。

打印或导出 PDF：

1. 在 Edge 或 Chrome 中打开 HTML。
2. 按 `Ctrl+P`。
3. 选择“另存为 PDF”。
4. 版式选择横向，边距选择无，启用背景图形。
5. 检查输出应为五页，每页比例接近 16:9，无内容裁切。

## 打开和导出海报

浏览器可以直接预览 `poster/tradeloop_poster.svg`。需要编辑或印刷导出时，使用支持 SVG 和物理尺寸的矢量编辑软件打开，不要先截图或转成低分辨率位图。

导出前必须：

- 向主办方确认纵向版式、出血、色彩模式、PDF 版本和图片分辨率。
- 用最终仓库或演示地址生成真实二维码，替换“二维码占位”。
- 复核海报描述与最终 Git 提交一致。
- 核对 SVG 根元素仍为 `width="800mm"` 和 `height="1800mm"`。
- 导出的 PDF 页面物理尺寸仍为 800mm × 1800mm。
- 确认材料写明：User/ProjectMember 最小权限已实现，但本地用户选择不是生产登录认证；真实模型 API 若未完成 live 验证，必须明确标注未验证。

PowerShell 尺寸检查：

```powershell
Select-String -Path .\deliverables\poster\tradeloop_poster.svg -Pattern 'width="800mm"','height="1800mm"','viewBox="0 0 800 1800"'
```

浏览器预览只用于检查排版，不代表印刷尺寸已经通过。最终应在 PDF 属性或印前软件中再次确认页面尺寸。

## 最终应补充

- 按主办方要求导出的海报 PDF/PNG。
- 三分钟路演 PDF；如主办方要求 PPT，再根据 HTML 内容制作 PPT。
- 最终页面截图，截图中不得包含密钥、真实个人信息或未授权数据。
- 最终仓库或演示地址二维码。
- 若使用第三方图标、字体或图片，补充来源和授权记录。

最终文件必须基于实际运行页面制作，不得把尚未实现的能力画成已经完成。
