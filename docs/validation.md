# 本地验证记录

验证日期：2026-10-21（Asia/Shanghai）。

环境：Windows、CPython 3.14.6，带 Tcl/Tk 支持。以下是实际执行结果；不代表其他平台或真实仪器已通过验证。

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -v` | 26 项测试通过 |
| `python -m instrumentlab --headless --seconds 1 --csv data/demo.csv` | 成功录制并导出 1024 个样点 |
| 独立 TCP 仿真服务进程 + CLI 客户端，1 秒采集 | 通过实际本机 TCP 连接导出 1024 个样点 |
| `python tools/gui_smoke.py` | 真实 Tk 窗口启动、过载、保存、重启、告警复位通过 |
| 最小 1160×800 窗口布局 | 事件列表、频谱及导出按钮均可见且未超出窗口 |
| `python -m compileall -q instrumentlab` | 通过 |
| `python -m pip wheel . --no-build-isolation --no-deps --no-index --wheel-dir data/wheels` | 离线构建 wheel 成功 |

测试覆盖：FFT 对照直接 DFT、正弦幅值/RMS/频率、非整频点主频估计、直流与零信号、非法输入、告警回差和连续帧确认、线性标定、场景生成、实际 TCP 采集、协议拆包、非有限数值、过大响应、截断 JSON、超时、断线反馈、采样率不匹配、数据库保护、原始/校正数据一致性、CSV 时间连续性、显示积压与录制完整性。

`docs/screenshot.png` 是测试过程中截取的实际 Tk 窗口，展示周期过载场景。截图工具只需要开发环境中的 Pillow；运行程序和核心测试不需要它。

GitHub Actions 的多平台矩阵尚需上传后由 GitHub 执行。没有真实硬件测试、压力测试或计量精度测试报告。
