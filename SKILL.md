---
name: baidu-pan-autosave
description: 配置并维护百度网盘分享链接的定时自动转存（走 GitHub Actions 上的 baidu-autosave 仓库）。当用户给出百度网盘分享链接和 Cookie（BDUSS/STOKEN），要把分享内容定时转存到自己网盘、只补缺失文件，或者排查转存失败（未登录、文件名非法、限频 -65、目录嵌套）时使用。关键词：百度网盘、转存、分享链接、pwd 提取码、BDUSS、STOKEN、pan.baidu.com、自动保存、自动同步。
agent_created: true
---

# 百度网盘自动转存

## 这个技能做什么

用户给一个百度网盘分享链接和一份 Cookie，技能在用户自己的 GitHub 账号里配好一套定时任务，让 GitHub Actions 定期把分享里的新文件补进用户网盘。运行逻辑用的是开源项目 `Jack261108/baidu-autosave` 的用户 Fork，本机不需要常开。

## 什么时候用它

用户要转存分享、要「只补没有的」、要定时同步；或者 Cookie 过期需要替换（症状是所有链接同时失败、报未登录）；或者要查最近跑成什么样、排查失败原因。

## 先跑脚本，别手工拼命令

所有操作都在 `scripts/baidu_autosave.py` 里，需要 Python 3.9+，只用标准库。它通过 `gh` CLI 干活，Cookie 只走 stdin，不打印也不落盘。

```bash
python scripts/baidu_autosave.py status        # 看现状
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"
python scripts/baidu_autosave.py configure --cookie-file <路径> --share-url "<链接>" --save-dir "/"
python scripts/baidu_autosave.py run           # 触发并等结果
```

`all` 等于把 provision、configure、run 连着跑一遍。目标仓库默认取「当前 gh 账号 / baidu-autosave」，可以用 `--repo owner/name` 指定。

`provision` 是幂等的，重复跑不会产生多余提交，可以放心用来修复被改坏的环境。

前提：`gh` 已安装并登录，令牌要有 `repo` 和 `workflow` 两个 scope。

## 本机默认值放哪

不要在 SKILL.md 里写死个人配置。执行前先看 `references/personal-defaults.md`，那里面有目标仓库、保存目录、定时表达式和通知偏好。这个文件不进版本库，只存在于本机。

如果它不存在（比如在新机器上第一次用），按通用默认值处理并在改动前问一下用户：`SAVE_DIR=/`、cron `17 10,11 * * *`、不配任何通知渠道。

## SAVE_DIR 是父目录

这是最容易理解反的地方。它填的是「分享里的那个文件夹放到哪儿」，不是「文件存到哪个文件夹」。

分享是单文件夹时，实际落点 = `SAVE_DIR` + `/` + 分享文件夹名。

填 `/` 得到 `/示例文件夹`，这是对的。填 `/示例文件夹` 会得到 `/示例文件夹/示例文件夹`，多占一份空间还不自动清理。默认给 `/`。

## 它怎么判断该不该转存

目标目录不存在时走「整目录直接转存」，整包搬过去，不做逐文件比对。

目标目录已存在时回退到「逐文件对比转存」，按 MD5 判断：本地没有就转；MD5 相同就跳过并计入「已存在」；MD5 不同算「冲突」，跳过且不覆盖。

所以新增的文件和集数会自动补上，同名但内容更新过的不会替换。用户说「更新」的时候要问清是哪一种，别笼统答应会自动更新。

## Cookie 只能人工取

浏览器 Cookie 带 `v20` 前缀，属于应用绑定加密。DPAPI 解密、CDP 调试端口、复制整个浏览器配置文件三条路都实测失败，详见 pitfalls。不要在这上面浪费时间，直接引导用户手工操作：

登录 `pan.baidu.com`，按 F12，切到「应用 / Application」，左边点 Cookie 下的 `https://pan.baidu.com`。筛选框输入 `BDUSS` 复制值，再换 `STOKEN` 复制值，拼成 `BDUSS=xxx; STOKEN=xxx`，中间是分号加空格。

如果用户把值发到对话里，要如实讲清楚：GitHub 那边加密存储、日志也脱敏，但聊天记录是明文；BDUSS 是长期凭证，泄露等于网盘被人完全控制。可以给一个不进对话的方案：用户先去网页端「退出所有设备」，重取一份存成本地文件，脚本用 `--cookie-file` 读。这样值全程不出现。

## 三件脚本做不到的事

Fork 之后首次注册工作流。新 Fork 的仓库 `gh workflow list` 是空的，API 返回 404。必须让用户打开 `https://github.com/<repo>/actions`，点横幅上的确认按钮，之后才能用 API 启用。脚本检测到这种情况会给提示然后退出。

GitHub 的失败通知邮件。那是账号级设置，路径是 `Settings → Notifications → System → Actions`，取消 Email。API 改不了。

删除网盘里的文件。比如清理嵌套目录，脚本没有写网盘的能力。

## 其他坑

改脚本或者排查异常之前先读 `references/pitfalls.md`。里面记了 MSYS 路径改写、CI 依赖版本、工作流注册、Cookie 加密、同步上游覆盖本地提交这些，每条都有具体报错原文。

## 汇报方式

把日志里的统计翻成业务语言，四句话讲完：分享里一共几个文件、网盘已有几个（MD5 相同跳过）、冲突几个（有的话说明得人工删旧文件）、实际转存几个。

不要给用户看 `候选分析完成` 这类原始日志行，也不要回显 Cookie 的任何片段。

用户如果说「看不懂」「太复杂」，就把技术细节全部去掉，只讲结果和下一步要做什么。
