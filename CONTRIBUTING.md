# 参与开发

请先按 README 建立虚拟环境，阅读 docs/DEVELOPMENT.md 和用户手册。新修改从 main 建立功能分支，保持提交范围清晰；提交前运行相关测试，行为变更同步更新手册和 CHANGELOG。

```sh
git switch -c feature/your-change
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
git add <本次修改的文件>
git commit -m "说明本次改变的行为"
git push -u origin feature/your-change
```

项目文件和照片始终在本地；不要提交私人照片、EXIF 数据、账号凭据、虚拟环境或打包产物。测试优先使用程序生成的图像。外部素材须记录来源及许可证。

工具执行默认生成独立产物，不自动重算下游；只有无下游处理或组合引用的末端产物才允许显式保存修改。文件写入、撤销、回收站和旧项目兼容性应作为修改时的重点验证项。

新增工具通过工具注册表接入，保留参数版本与旧格式验证。UI 调整需核对实际窗口可用性；不要把纯模型测试表述为真实鼠标操作验证。
