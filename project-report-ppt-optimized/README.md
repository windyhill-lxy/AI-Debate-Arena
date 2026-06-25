# AI辩论场项目报告优化版

这是面向「AI智能体开发专项赛」重新整理的项目汇报幻灯片。内容优先参考原人工版 `AI辩论场-项目报告.pptx` 的表达方式，并结合项目源码、旧 HTML 版 PPT 与专项赛评分标准重组为 18 页。

## 交付文件

- HTML 演示版：`index.html`
- PDF：`output/AI辩论场-项目报告-优化版.pdf`
- PPTX：`output/AI辩论场-项目报告-优化版.pptx`
- 全页截图：`output/slide-01.png` 至 `output/slide-18.png`
- 总览图：`output/contact-sheet.jpg`

## 重新生成

在项目根目录执行：

```powershell
node project-report-ppt-optimized\build-deck.mjs
node project-report-ppt-optimized\export-deck.mjs
```

`build-deck.mjs` 会生成 `slides/*.html`、`deck-manifest.json` 和聚合演示页。`export-deck.mjs` 会使用 Playwright 截图并导出 PDF/PPTX。

## 注意

PPTX 为高保真整页图片版，每页是一张 16:9 图片，适合演示和提交；如需逐字编辑，请回到 HTML 源文件或 `build-deck.mjs` 修改文案后重新导出。

本次导出已确认：HTML 幻灯片 18 页、PDF 18 页、PPTX 包内 18 张 slide 与 18 张页面图片。
