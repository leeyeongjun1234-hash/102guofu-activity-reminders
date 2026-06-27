# 国服活动提醒

这个仓库用于从活动排期表生成每日活动提醒页面。

## 本地生成

```bash
python3 generate_reminders.py
python3 daily_reminder.py
python3 build_reminders_html.py
```

生成文件：

- `活动设置提醒.tsv`
- `每日活动提醒.txt`
- `全部每日提醒.html`
- `index.html`
- `site/index.html`

## 日常更新

### Mac

编辑并保存 `102国服活动排期表.xlsx` 后，双击：

```text
一键同步GitHub.command
```

它会自动完成：

- 重新生成提醒文本和 HTML
- 提交本地修改
- 拉取 GitHub 最新内容
- 推送到 GitHub

如果只想本地自动更新 HTML、不推送 GitHub，双击：

```text
自动更新HTML.command
```

打开后保持窗口不关；之后每次保存 `102国服活动排期表.xlsx` 或 `活动与礼包对应关系.xlsx`，都会自动重新生成 `活动设置提醒.tsv`、`每日活动提醒.txt`、`全部每日提醒.html`、`index.html` 和 `site/index.html`。

自动更新也会监听 `工作休日日历.xlsx`。普通活动的设置日期如果落在休息日，会自动提前到最近的工作日；`1000905：国服-拯救蚜虫-跨服` 和 `1000927：飞蜥之战` 保持固定周末设置。

### Windows

编辑并保存 `102国服活动排期表.xlsx` 后，双击：

```text
一键同步GitHub.bat
```

如果只想本地生成、不推送 GitHub，双击：

```text
一键更新提醒.bat
```

## 协作规则

- 每次改排期表之前，先从 GitHub 拉取最新版本。
- 同一时间尽量只让一个人编辑 `102国服活动排期表.xlsx`，避免 xlsx 冲突。
- 改完后保存 xlsx，再运行一键同步脚本。
- 如果同步时提示冲突，先不要强推，手动确认谁的表格版本是最新的。

## GitHub Pages

推荐在 GitHub 仓库设置里开启 Pages：

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/ (root)`

仓库里的 GitHub Actions 会每天按北京时间自动重建页面，并提交更新后的 `index.html`。
