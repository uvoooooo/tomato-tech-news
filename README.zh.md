**Language / 语言**: [English](README.md) | **简体中文**

# TomatoNews（Tomato AI Daily）

定时从 **RSS** 拉取当日条目，经 **大模型（OpenRouter）** 归类与摘要后，生成 **静态 HTML / PDF**，并可通过 **GitHub Actions** 自动发布到 **GitHub Pages**；可选 **SMTP** 邮件通知。

---

## 功能简介

| 能力 | 说明 |
|------|------|
| 数据源 | 默认 `news.smol.ai` RSS，可通过环境变量 `RSS_URL` 更换 |
| 内容加工 | 使用 OpenRouter 兼容 API，对新闻做分类、要点与关键词提炼 |
| 产出物 | `docs/` 下日报 HTML、归档 `index.html`、样式 `css/styles.css`，本地/CI 中可另存 **PDF**（Playwright） |
| 自动化 | `.github/workflows/daily.yml`：定时运行流水线并部署 Pages |
| 通知 | 成功 / 无内容 / 失败时发送 HTML + 纯文本双版本邮件（需配置 SMTP） |

---

## 报告长什么样

在 `docs/` 中带有一份固定示例（与流水线导出版式一致），**无需另做配图**：在 GitHub 上打开下列文件即可预览整页效果。

| 类型 | 文件 | 说明 |
|------|------|------|
| **PDF**（推荐当「整版截图」看） | [`docs/2026-04-16-zh.pdf`](./docs/2026-04-16-zh.pdf) | 与 CI 里 Playwright 生成的 PDF 相同；在仓库文件页可翻页预览 |
| **HTML** | [`docs/2026-04-16-zh.html`](./docs/2026-04-16-zh.html) | 同一期中文日报：深色极简排版、**Today's Highlights**、按「模型 / 产品 / 研究」等分组的卡片、外链与关键词页脚 |
| **归档首页** | [`docs/index.html`](./docs/index.html) | 按日期列表入口，链到各期 HTML |

> 若在本地克隆后想更新示例，重新运行一次 `scripts/main.py` 并提交 `docs/` 中对应文件即可（`.gitignore` 仅放行上述示例与 `docs/css/`，其它日期仍会被忽略）。

---

## 使用步骤

### 1. 克隆与 Python 环境

```bash
git clone https://github.com/<你的用户名>/TomatoNews.git
cd TomatoNews
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

首次使用 **PDF** 导出时，需安装浏览器内核：

```bash
playwright install chromium
```

### 2. 配置环境变量

复制示例并按注释填写：

```bash
cp .env.example .env
```

| 变量 | 是否必填 | 作用 |
|------|----------|------|
| `OPENROUTER_API_KEY` | **必填** | 调用模型 |
| `OPENROUTER_BASE_URL` | 可选 | 默认 `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | 可选 | 默认 `openai/gpt-4o` |
| `RSS_URL` | 可选 | RSS 地址 |
| `OUTPUT_DIR` | 可选 | 输出目录，默认 `docs` |
| `SKIP_WEEKENDS` | 可选 | 默认 `true`：在 **`NEWS_DATE_TZ` 时区的周六、周日** 不跑主流程（仍可用 `--date` / `--force` 或设为 `false` 绕过） |
| `NEWS_DATE_TZ` | 可选 | 不设则用 **`scripts/config.py`** 里的 **`DEFAULT_NEWS_DATE_TZ`**（仓库模板当前为英国 **`Europe/London`**）。fork 后改默认值或设本变量（如 **`Asia/Shanghai`**、**`Etc/UTC`**）即可，不必改业务代码。CI 可在 **Repository variables** 里设同名变量，由 workflow 传入 |
| `GITHUB_PAGES_URL` | 可选 | 站点根 URL，用于邮件中的「打开报告」链接；在 GitHub Actions 里工作流会注入，一般可不填 |
| `SMTP_*` | 可选 | 发信账号；不配则跳过邮件 |
| `NOTIFICATION_TO` | 可选 | **传统**：单一收件人列表（可逗号分隔），邮件文案语言跟随 `--language` |
| `NOTIFICATION_TO_ZH` / `NOTIFICATION_TO_EN` | 可选 | **分流**：分别填中文信/英文信的收件人（逗号分隔）。**至少一侧有邮箱**即进入分流模式：会按侧生成 **中文 / 英文** 报告（各一次模型调用），中文列表只收中文邮件+`…-zh.html` 链接，英文列表只收英文邮件+`…-en.html` 链接；此时 **`NOTIFICATION_TO` 不再用于收件人路由**。若两侧都为空，则回退为仅 `--language` 一种报告，并继续使用 `NOTIFICATION_TO` |
| `ENABLE_IMAGE_GENERATION` | 可选 | 设为 `true` 时需配 `FIREFLY_API_KEY` 等（见 `scripts/config.py`） |

### 3. 本地生成一期日报

```bash
export PYTHONPATH="$(pwd)/scripts${PYTHONPATH:+:$PYTHONPATH}"
python scripts/main.py --days 1          # 默认：「上一工作日」（时区见 config.DEFAULT_NEWS_DATE_TZ 或 NEWS_DATE_TZ）
# python scripts/main.py --days 2        # 按 UTC 往前数自然日（非工作日历）
# python scripts/main.py --date 2026-04-16 --language zh
# python scripts/main.py --language en
```

完成后查看 `docs/` 下新生成的 `YYYY-MM-DD-<语言>.html` 与可选 PDF。

### 4. 用 GitHub Actions 每天自动跑

1. 将本仓库推送到 GitHub。  
2. **Settings → Secrets and variables → Actions** 中至少配置 **`OPENROUTER_API_KEY`**；其余密钥与工作流 `daily.yml` 中 `env` 一致即可。  
3. **Settings → Pages**  
   - **Build and deployment → Source** 请选择 **GitHub Actions**（本仓库已使用 `upload-pages-artifact` + `deploy-pages`，不再依赖仅推 `gh-pages` 分支的旧方式）。  
4. 在 **Actions** 中手动运行一次 **Tomato Tech News Daily Automation**，确认 `build` 与 `deploy` 均成功。  
5. 站点根地址一般为：`https://<owner>.github.io/<repo>/`（与 `GITHUB_REPOSITORY` 对应）。工作流里已为邮件注入 `GITHUB_PAGES_URL`，与上述地址一致。

定时：**仅工作日（UTC 周一至周五）每天 08:00** 触发（北京时间 16:00）；周末不跑定时任务。默认 **`--days 1`** 取 **上一工作日**（UTC）：例如 **周一** 构建的是 **上周五** 的 RSS 日期，**周二** 为 **周一**，以此类推。手动 **Run workflow** 或 **push** 触发的运行若在周末，默认也会被脚本跳过（与 `SKIP_WEEKENDS` 有关）；周末补跑可设 **`SKIP_WEEKENDS=false`**、传 **`--force`**，或使用 **`--date YYYY-MM-DD`** 指定要生成的日期（不视为「日常定时」）。

---

## 仓库结构（简要）

```
scripts/           # 流水线：RSS、LLM、HTML、PDF、邮件
docs/              # 站点与示例（部分文件在 .gitignore 中白名单跟踪）
.github/workflows/ # daily.yml 定时构建与 Pages 发布
requirements.txt
.env.example
```
