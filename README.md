# 国服活动提醒

这个仓库用于从活动排期表生成每日活动提醒页面。

## 本地生成

```bash
python3 daily_reminder.py
python3 build_reminders_html.py
```

生成文件：

- `每日活动提醒.txt`
- `全部每日提醒.html`
- `index.html`
- `site/index.html`

## GitHub Pages

推荐在 GitHub 仓库设置里开启 Pages：

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/ (root)`

仓库里的 GitHub Actions 会每天按北京时间自动重建页面，并提交更新后的 `index.html`。
