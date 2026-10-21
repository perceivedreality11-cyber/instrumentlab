# 上传 GitHub

本项目仓库：[perceivedreality11-cyber/instrumentlab](https://github.com/perceivedreality11-cyber/instrumentlab)。以下步骤也可用于将源码上传到其他个人仓库。

建议仓库名：`instrumentlab`。

建议仓库描述：

> Python instrumentation workstation with TCP acquisition, FFT, calibration, alarms and SQLite recording.

建议 Topics：`python`、`instrumentation`、`data-acquisition`、`signal-processing`、`fft`、`tkinter`、`sqlite`。

## 通过 Git 上传

1. 在 GitHub 新建空仓库 `instrumentlab`。不要让 GitHub 自动生成 README、许可证或 .gitignore，本项目已经包含这些文件。
2. 在本项目目录打开终端，执行：

```bash
git init -b main
git add .
git commit -m "Build InstrumentLab measurement workstation"
git remote add origin https://github.com/YOUR_USERNAME/instrumentlab.git
git push -u origin main
```

将 `YOUR_USERNAME` 替换为你的 GitHub 用户名，按 GitHub 提示完成登录。.gitignore 已排除录制数据、缓存和虚拟环境。上传的是项目目录内的内容，不要把整个上一级工作区上传。

3. 打开仓库首页，确认 README 图片可以显示；在 Actions 页面查看测试结果。
4. 在仓库 About 中填写描述和 Topics，在个人主页置顶该仓库。

## 通过网页上传

也可以解压交付的源码 ZIP，在仓库中选择 Add file → Upload files，上传解压后的项目内容。确保 `.github/workflows/tests.yml`、`.gitignore` 等隐藏文件也包含在上传内容中。README 需要与 `instrumentlab/`、`docs/`、`tests/` 同级。

## 可直接放在作品集里的链接

```text
https://github.com/YOUR_USERNAME/instrumentlab
```

后续更新已有仓库时，在对应 Git 工作副本提交修改，再执行 `git push`。首次新建仓库才需要执行上面的 `git init` 和 `git remote add`。
