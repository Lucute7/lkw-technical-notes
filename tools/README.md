# 阅读版生成工具

在工作区根目录运行：

```sh
python3 tools/build_reader.py
```

工具把根目录说明、复习清单、编号技术分类及其章节合并为 `阅读版.html`，最后收录 `说明文档/` 中的使用与维护说明。公式在构建时转换为原生 MathML，阅读时不加载在线脚本、字体或公式服务。文件可直接用支持 MathML 的现代浏览器打开。

Markdown 是内容源，阅读版是生成结果。新增主题分类使用编号目录，已有文件内的相对 Markdown 链接会转为阅读版内部导航。工具不收录工作区规则、模板和工具自身说明。

行内公式统一使用 GitHub 官方的明确定界符，例如 ``$`a`$``、``$`\theta`$``，独立公式使用 `$$...$$`。这仍是数学公式语法，不是普通行内代码。构建工具兼容普通美元符号和上述明确写法；前者在紧邻中文标点时可能被 GitHub 漏解析，新增笔记应使用明确写法。相关约定见 [GitHub 公式文档](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/writing-mathematical-expressions)。

为兼容当前网页公式预览，构建时拒绝公式中的 `\operatorname`（含星号形式）。命名函数使用 `\mathrm{clip}`、`\mathrm{sgn}` 等正体写法，极值位置使用 `\mathrm{arg\,min}_{\theta}`；代码示例和说明中的字面文本不会触发此检查。本检查只覆盖已确认的不兼容宏，不能替代网页端显示验证。

需要 Python 3.10 或更新版本和 Node.js。系统 Python 版本较旧时，会自动切换到 Codex 已配置的 Python；Node.js 也优先使用 Codex 已配置的版本。已在 `vendor/` 保留离线依赖及许可证：`latex2mathml` 负责公式转换，`marked` 负责 Markdown 排版。后续更新笔记无需再次联网安装。
