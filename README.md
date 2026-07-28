# Gold MA14 Cross Monitor

每30分钟监控黄金（XAU/USD）价格与14期移动平均线（MA14）的交叉信号。

## 工作原理

- 数据来源：Twelve Data API（主）+ XAUS（回退）
- K线周期：30分钟
- 信号检测：价格与MA14的交叉（金叉/死叉）
- 通知：Telegram Bot 推送

## 文件说明

| 文件 | 用途 |
|------|------|
| `gold_ma14_twelve.py` | 主监控脚本 |
| `gold_ma14_status.json` | 当前状态（价格、MA14、信号） |
| `gold_ma14_signal_memory.json` | 上一个信号记录（避免重复通知） |
| `gold_ma14_history.csv` | 交叉事件历史记录 |
| `gold_ma14_twelve_report.html` | 可视化HTML报告 |

## GitHub Actions

`.github/workflows/gold-ma14-monitor.yml` 每30分钟执行一次：
1. 运行监控脚本
2. 提交更新的状态文件
3. 上传HTML报告为 Artifact

## 配置

编辑脚本顶部的 `CONFIG` 区域设置 API Key 和 Telegram 凭据。
