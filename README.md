# 🐾 PolyClaw - Polymarket 模拟交易平台

> 用假钱玩真市场，练手不烧钱

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![Flask](https://img.shields.io/badge/Flask-3.x-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ 功能

- 🔥 **实时市场数据** — 从 Polymarket 拉取热门预测市场，按交易量排序
- 🛒 **模拟交易** — $1,000 虚拟资金，买入/卖出 YES/NO 股份
- 📊 **持仓追踪** — 实时计算盈亏、收益率
- 🌙 **暗色主题** — 好看的深色 UI，支持手机端
- 🔄 **自动刷新** — 每 30 秒更新持仓数据

## 🚀 快速开始

```bash
# 克隆项目
git clone https://github.com/Timememo8210/polyclaw.git
cd polyclaw

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动
python app.py
```

打开浏览器访问 **http://localhost:8877** 🎉

## 📸 截图

暗色主题界面，实时显示 Polymarket 热门市场和模拟交易面板。

## 🎮 怎么玩

1. **浏览市场** — 首页显示按 24h 交易量排序的热门预测市场
2. **买入** — 点击任意市场，输入金额，选择买 YES 或 NO
3. **查看持仓** — 切换到「我的持仓」查看当前仓位和盈亏
4. **卖出** — 在持仓页面卖出
5. **重置** — 玩崩了？重置账户重新来过

## 🏗️ 技术栈

- **后端**: Python + Flask
- **前端**: 原生 HTML/CSS/JS（无框架依赖）
- **数据源**: Polymarket Gamma API（无需 API Key）
- **存储**: 本地 JSON 文件

## ⚠️ 声明

这是一个**模拟交易**工具，使用虚拟资金。不涉及真实交易或真实资金。仅供学习和娱乐用途。

## 📄 License

MIT
