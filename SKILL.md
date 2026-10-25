---
name: baidu-pan-autosave
description: 配置并维护「百度网盘分享链接自动转存」（基于 GitHub Actions 的 baidu-autosave 仓库）。当用户给出百度网盘分享链接和百度 Cookie（BDUSS/STOKEN），希望把分享内容定时自动转存到自己的网盘、只补齐缺失文件、或排查转存失败（未登录、文件名为非法、限频 -65、目录嵌套）时使用。关键词：百度网盘、转存、分享链接、pwd 提取码、BDUSS、STOKEN、pan.baidu.com、自动保存、自动同步。
agent_created: true
---

# 百度网盘自动转存

## 用途

把「用户给出分享链接 + 百度 Cookie → 定时自动转存到本人网盘」固化为可重复执行的流程。
底层依赖开源仓库 `Jack261108/baidu-autosave`，运行在用户的 GitHub Fork 上，由 Actions 定时调度，无需本地机器常开。

## 何时使用

- 用户提供百度网盘分享链接，要求「转存到我网盘」「只补没有的」「定时同步更新」
- Cookie 过期需要替换（现象：所有链接同时失败、报未登录）
- 查看最近转存结果、排查失败原因
- 调整执行时间

## 快速开始

脚本位于 `scripts/baidu_autosave.py`，全部操作经 `gh` CLI 完成，Cookie 只走 stdin，不打印、不落盘。需 Python 3.9+，仅用标准库。

```bash
# 1. 查看现状（仓库、工作流状态、Secrets、最近运行统计）
python scripts/baidu_autosave.py status

# 2. 首次搭建或修复环境（已配置过的仓库重复执行是安全的、幂等的）
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"

# 3. 写入 Cookie 与分享链接（--cookie 与 --cookie-file 二选一）
python scripts/baidu_autosave.py configure \
    --cookie-file C:/Users/xxx/baidu_cookie.txt \
    --share-url "https://pan.baidu.com/s/1xxxxx?pwd=abcd" \
    --save-dir "/"

# 4. 触发一次并等待结果（自动汇总关键统计行）
python scripts/baidu_autosave.py run
```

`all` 子命令等同于 provision + configure + run。
仓库默认取「当前 gh 登录账号 / baidu-autosave」，可用 `--repo owner/name` 指定。

前置条件：安装 `gh` 并完成 `gh auth login`，令牌需包含 `repo` 与 `workflow` 两个 scope（`workflow` 用于提交工作流文件修改）。

## 本机个性化默认值

本技能的发布版**不含任何个人配置**。执行前先读取 `references/personal-defaults.md`（该文件未纳入版本库，仅存在于本机），获取：目标仓库、保存目录、定时表达式、通知偏好。

若该文件不存在（例如在新机器上首次使用），按以下通用默认值处理，并在改动前向用户确认：

- `SAVE_DIR=/`（分享文件夹落在网盘根目录）
- cron `17 10,11 * * *`（每天北京时间 18:17、19:17）
- 不配置任何通知渠道

## 核心概念：SAVE_DIR 是父目录

最容易出错的一点。分享为单个文件夹时，实际落点 = `SAVE_DIR` + `/` + 分享文件夹名。

| `SAVE_DIR` | 实际落点 |
|---|---|
| `/` | `/示例文件夹` ✅ |
| `/示例文件夹` | `/示例文件夹/示例文件夹` ❌ 嵌套重复 |

默认取 `/`，才是用户期望的「转存到同名文件夹」。

## 转存行为：两种模式

- 目标目录**不存在** → 「整目录直接转存」，整包搬运，不做逐文件比对
- 目标目录**已存在** → 回退「逐文件对比转存」，按 MD5 判定：
  - 本地无此文件 → 转存
  - MD5 相同 → 跳过（计入「已存在」）
  - MD5 不同 → **跳过并记「冲突」**，不覆盖

因此：**新增文件/集数会自动补；同名文件内容更新不会覆盖**，需用户先删除旧的同名文件，下一轮才补。
回答用户关于「更新」的诉求时，先区分这两种含义，不要笼统承诺「会自动更新」。

## Cookie 获取（只能人工）

浏览器 Cookie 值带 `v20` 前缀，属 App-Bound Encryption。DPAPI 解密、CDP 调试端口、复制整个配置文件三条自动化路径均已实测失败（详见 pitfalls）。必须引导用户手工操作：

1. 浏览器登录 `pan.baidu.com`
2. `F12` → **应用 / Application** → **Cookie** → `https://pan.baidu.com`
3. 表格上方筛选框输入 `BDUSS`，复制「值」列；再输入 `STOKEN`，同样复制
4. 拼成 `BDUSS=xxx; STOKEN=xxx`（分号 + 空格，两段都不能少）

用户若把值发到对话里，需如实告知：GitHub Secret 侧加密存储且日志脱敏（脱敏很激进，连 `1/1` 都会变成 `1***1`），但**对话记录里是明文**；`BDUSS` 是长期令牌，泄露等同网盘完全控制权。可提供免对话方案：用户「退出所有设备」→ 重取 → 存入本地文件 → 脚本用 `--cookie-file` 读取，值全程不进对话。

## 无法自动化的三件事（必须交给用户）

1. **Fork 后首次注册工作流**：新 Fork 的 `gh workflow list` 为空，API 返回 404（状态 `disabled_fork` 时可用 API 启用，但未注册时不行）。必须让用户打开 `https://github.com/<repo>/actions`，点击横幅「I understand my workflows, go ahead and enable them」，之后再执行 provision。脚本会给出该提示并退出。
2. **GitHub 失败通知邮件**：账号级设置，`Settings → Notifications → System → Actions → 取消 Email`。API 无法修改。
3. **删除网盘内文件**（如清理嵌套重复目录）：脚本无写网盘能力。

## 已知陷阱

见 `references/pitfalls.md`。修改脚本或排查异常前先读该文件，重点为 MSYS 路径改写、CI 依赖版本、工作流注册三节。

## 输出要求

向用户汇报时把日志统计翻译成业务语言，固定四项：

- 分享内共 N 个文件
- 网盘已有（MD5 相同，跳过）N 个
- 冲突跳过 N 个（若有，说明需人工删除旧文件）
- 实际转存 N 个

不要向用户暴露 `候选分析完成` 这类原始日志行，也不要回显 Cookie 的任何片段。
若用户反馈「看不懂 / 太复杂」，改用最简表述：只讲结果与下一步动作，不给技术细节。
