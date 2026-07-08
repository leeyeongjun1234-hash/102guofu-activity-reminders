# CLAUDE.md — 项目操作守则

本项目由 Claude 接管日常维护。完整规则见 `项目规则.md`，必读。以下是执行时的硬性守则。

## 职责范围

1. 按 lee 的口头指示修改 `102国服活动排期表.xlsx`、`工作休日日历.xlsx`、`活动与礼包对应关系.xlsx`。
2. 修改后依次运行 `generate_reminders.py` → `daily_reminder.py` → `build_reminders_html.py` 重新生成产物。
3. 需要上线时执行同步：`git pull --rebase --autostash origin main` → 重新生成 → `git add . && git commit` → 再 pull → `git push origin main`（等同 `一键同步GitHub.command`）。
4. 每日检查当天需设置的活动并汇报（见定时任务）。
5. 规则变化时修改 Python 脚本和 `.github/workflows/update-pages.yml`，并同步更新 `项目规则.md`。

## 硬性守则

- `102国服活动排期表.xlsx` 是 **UTF-8 TSV 文本**（扩展名伪装），编辑时必须保持制表符分隔文本格式，绝不能写成真正的 zip 格式 xlsx。
- 第 2 行为日期行（`M月D日`），年份写死 2026；改动日期列时保持此格式。
- `活动设置提醒.tsv`、`每日活动提醒.txt`、`index.html`、`全部每日提醒.html`、`site/index.html` 是生成产物，**永不手改**，只通过脚本重建。
- 任何改动前先 `git pull --rebase`；出现冲突时**停下来问 lee**，绝不 force push。
- push 前必须先本地跑一遍三个生成脚本确认无报错。
- 修改脚本逻辑（提前天数、固定例外、持续天数等）后，同步更新 `项目规则.md` 对应条目。
- 固定例外不动摇：`1000905 拯救蚜虫-跨服`、`1000927 飞蜥之战` 保持周末/休息日设置，其余活动设置日落休息日自动提前到工作日。

## 汇报口径

- 每日检查：读取/重新生成 `每日活动提醒.txt`，汇报今天需设置的活动；没有就说没有。
- 改表后：简述改了哪些活动、哪些日期，以及生成/同步结果。
