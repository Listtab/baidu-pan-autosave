---
name: baidu-pan-autosave
description: 配置并维护百度网盘分享链接的定时自动转存（走 GitHub Actions 上的 baidu-autosave 仓库）。当用户给出百度网盘分享链接和 Cookie（BDUSS/STOKEN），要把分享内容定时转存到自己网盘、只补缺失文件，或者排查转存失败（未登录、文件名非法、限频 -65、目录嵌套）时使用。关键词：百度网盘、转存、分享链接、pwd 提取码、BDUSS、STOKEN、pan.baidu.com、自动保存、自动同步。
agent_created: true
---

# 百度网盘自动转存

## 原理

用户的 GitHub 账号里跑一条 Actions 定时任务，到点拉起 Python 脚本。脚本用 Cookie 登录百度网盘，读分享的文件清单拿到每个文件的 MD5，再扫用户网盘的目标目录，两边按文件名对上逐个比 MD5，只转存本地没有的那些。所以重复跑不产生副本，只在分享方加了新文件时补齐。

目标目录不存在时走整目录直接转存，整包搬一次；已存在时走逐文件比对。转存动作调用开源项目 `Jack261108/baidu-autosave`，跑在用户自己的 Fork 里。

## 怎么用

所有操作都在 `scripts/baidu_autosave.py`，Python 3.9+，只用标准库。通过 `gh` CLI 干活，Cookie 只走 stdin，不打印也不落盘。

```bash
python scripts/baidu_autosave.py status
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"
python scripts/baidu_autosave.py configure --cookie-file <路径> --share-url "<链接>" --save-dir "/"
python scripts/baidu_autosave.py run
```

`all` 等于后三条连着跑。目标仓库默认取「当前 gh 账号 / baidu-autosave」，可用 `--repo owner/name` 指定。`provision` 幂等，重复跑不会产生多余提交。前提是 `gh` 已登录且令牌带 `repo` 和 `workflow` 两个 scope。

个人默认值（目标仓库、保存目录、定时、通知偏好）放在 `references/personal-defaults.md`，不进版本库。文件不存在时用通用默认值：`SAVE_DIR=/`、cron `17 10,11 * * *`、不配通知渠道。

## 交代给用户时必须说清的三点

Cookie 只能手工取，浏览器加密了读不到。登录 `pan.baidu.com`，F12 切到「应用 / Application」，点 Cookie 下的 `https://pan.baidu.com`，筛选 `BDUSS` 复制值，再换 `STOKEN`，拼成 `BDUSS=xxx; STOKEN=xxx`。如果用户把值发到对话里，要讲明白 GitHub 那边加密存、日志脱敏，但聊天记录是明文，而 BDUSS 等于网盘登录凭证。

`--save-dir` 是父目录不是目标文件夹。填 `/` 才会落到 `/分享文件夹名`，填具体文件夹名会产生嵌套，多占空间且不会自动清理。

工具只补缺不覆盖。同名文件 MD5 不同算冲突，跳过。用户说「更新」时要问清是新增文件还是同名换版本，后者必须人工先删旧文件。

## 三件脚本做不到的事

Fork 后首次注册工作流：新 Fork 的 `gh workflow list` 是空的，API 返回 404，必须让用户打开 `https://github.com/<repo>/actions` 点横幅上的确认按钮，之后才能用 API 启用。脚本检测到会给提示并退出。

GitHub 失败通知邮件：账号级设置，`Settings → Notifications → System → Actions`，API 改不了。

删除网盘里的文件：脚本没有写网盘的能力。

## 汇报方式

四句话讲完：分享里共几个文件、网盘已有几个、冲突几个、实际转存几个。不要给用户看 `候选分析完成` 这类原始日志行，也不要回显 Cookie 任何片段。用户说「看不懂」就把技术细节全部去掉，只讲结果和下一步。
