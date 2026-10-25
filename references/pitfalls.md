# 已知陷阱与排查手册

本文件记录构建过程中实测遇到的全部问题。修改脚本或排查异常前先读这里，可避免重复踩坑。

---

## 一、MSYS / Git Bash 路径改写

**症状**：百度返回 `error_code: 31062, message: 文件名非法`；脚本报错里的路径显示为 `/C:` 开头；日志出现警告「保存目录不以 / 开头」。

**原因**：Git Bash（MSYS2）会把以 `/` 开头的命令行参数自动转换成 Windows 路径。执行

```bash
gh secret set SAVE_DIR --body "/示例文件夹"
```

时，实际传给 `gh` 的值变成 `C:/Program Files/Git/示例文件夹`。

**修复**（任选其一）：

```bash
MSYS_NO_PATHCONV=1 gh secret set SAVE_DIR --body "/示例文件夹"
# 或：值走 stdin，不经过命令行参数
printf '%s' "/示例文件夹" > /tmp/v.txt && gh secret set SAVE_DIR --repo o/r < /tmp/v.txt
```

本技能脚本用 Python 的 `subprocess` + `input=` 传值，不经 shell，因此天然免疫。**只有手工用 bash 操作时才会踩到。**

同理，PowerShell 会把 URL 里的 `%2F` 误判为环境变量语法而拦截，打开含百分号编码的 URL 时改用其他方式。

**同一个坑的第二种形态**：`gh api` 的端点参数也中招。

```bash
gh api /user              # 报错：invalid API endpoint "C:/Program Files/.../user"
gh api user               # 正确，去掉前导斜杠
gh api /repos/o/r/...     # 同样会坏
```

规律：**任何以 `/` 开头的命令行参数**在 Git Bash 下都有风险。写脚本时优先考虑这条路会不会经过 shell。

---

## 二、CI 运行时版本不匹配

**症状**：Actions 在「Install dependencies」步骤失败：

```
ERROR: Could not find a version that satisfies the requirement requests==2.33.0
```

**原因**：上游 `requirements.txt` 锁定 `requests==2.33.0`（要求 Python ≥3.10），但 `.github/workflows/baidu-transfer.yml` 写死 `python-version: '3.9'`。属上游仓库自身缺陷，非用户配置问题。

**修复**：把工作流里的 `python-version` 改为 `'3.12'`（或任何 ≥3.10 的版本）。

---

## 三、setuptools 缺失

**症状**：依赖装完后，在「Run transfer task」步骤失败：

```
File ".../vendor/BaiduPCS-Py/build.py", line 3, in <module>
    from setuptools import setup
ModuleNotFoundError: No module named 'setuptools'
```

**原因**：Python 3.12 起 `ensurepip` 不再自带 setuptools，而 `vendor/BaiduPCS-Py` 的 Cython 扩展通过 `setup.py` 编译。

**修复**：在 `requirements.txt` 追加 `setuptools>=68`。

> 这也是为什么单纯把 Python 从 3.9 提到 3.12 不够，两个问题必须一起解决。

---

## 四、Fork 仓库的工作流注册

**症状**：`gh workflow list` 无输出；`gh workflow enable <file>` 返回 `HTTP 404: workflow not found`；但 `gh api repos/{o}/{r}/contents/.github/workflows` 能看到文件确实存在。

**原因**：GitHub 对 Fork 仓库默认不注册 Actions 工作流，这是安全策略（防止 Fork 后立即消耗额度）。API 无法完成注册。

**处理**：

1. 浏览器打开 `https://github.com/<owner>/<repo>/actions`
2. 点击横幅 **「I understand my workflows, go ahead and enable them」**
3. 之后 `gh workflow list --all` 会显示，状态可能是 `disabled_fork`
4. 用 API 激活：`gh api -X PUT repos/{o}/{r}/actions/workflows/{id}/enable`（按 **ID** 而非文件名，`gh workflow enable <name>` 中文环境下可能匹配失败）

**仍无法绕过**：调度定时任务在仓库 **60 天无活动**后会被 GitHub 自动禁用，需重新启用或手动跑一次保活。

---

## 五、GitHub 连接器（MCP）的能力边界

实测结论，避免重复尝试：

- `fork_repository` 返回 `403 Resource not accessible by integration` —— MCP 连接器以 GitHub App 身份运行，无「在用户账号下创建仓库」权限
- MCP 没有写入 Actions Secrets 的工具
- 因此 **Fork 与 Secrets 必须用 `gh` CLI 或 PAT**

`gh auth login --web` 的 device flow 可用，但 GitHub 会要求 sudo 模式二次验证（密码/通行码/2FA），该步骤必须由账号本人完成，不可代劳。

---

## 六、Cookie 自动化：三条路全部封死

浏览器 Cookie 值前缀 `v20`，属 **App-Bound Encryption**（Chrome 127+ / Edge 同期引入）。实测：

| 尝试 | 结果 |
|---|---|
| 读 Edge `Network/Cookies` 并用 DPAPI 解 `Local State` 密钥 | 检测到 `v20`，AES-GCM 解不开，DPAPI 不适用 |
| 对真实默认配置目录开 `--remote-debugging-port` | Chromium 156 起静默禁用（仅允许非默认 user-data-dir） |
| 把 User Data 复制到临时目录再开调试端口 | 端口可用，但 ABE 密钥绑定配置路径，**原有 Cookie 全部被丢弃**，只剩新生成的 msn/bing |

`Storage.getCookies` 只返回未受 ABE 保护的少数 Cookie。

**结论**：只能人工从 DevTools 复制。不要在这条路上再花时间。

**附注**：`document.cookie` 也读不到，因为 `BDUSS`/`STOKEN` 是 HttpOnly。

---

## 七、SAVE_DIR 语义

`SAVE_DIR` 是**父目录**。分享为单文件夹时，落点 = `SAVE_DIR/<分享文件夹名>`。

写成 `/示例文件夹` 会产生 `/示例文件夹/示例文件夹` 嵌套重复，白占一份空间。
之后即使改回 `/`，嵌套目录也不会自动消失，需用户在网盘里手动删除。

**判断是否踩坑**：日志出现「尝试整目录直接转存」并成功，且此前目标目录已存在，即为嵌套。

---

## 八、错误码速查

| 错误 | 含义 | 处理 |
|---|---|---|
| `31062 文件名非法` | 路径含非法字符，或路径被改写（见第一节） | 检查 `SAVE_DIR` 实际值 |
| `-65` | 触发百度风控限频 | 停跑数小时，勿缩短周期 |
| 未登录 / 登录态失效 | Cookie 过期 | 重取 `BDUSS`+`STOKEN` |
| 创建目录失败: 文件名非法 | 同上 31062 | 同上 |

---

## 九、Secret 机制

- Secret **只写不可读**，保存后任何人都无法查看原值，只能覆盖
- 多行 Secret（如 `SHARE_URLS`）必须由用户本地留一份原始清单，否则改动时容易丢链接
- 日志脱敏是子串级的：`SHARE_URLS` 的值中的片段也会被打码，日志里出现 `【1***1】` 属正常

---

## 十、定时任务

- cron 使用 **UTC**，北京时间需减 8 小时
- 整点（`:00`）最拥挤，建议用 `:17`、`:43` 等错峰分钟，否则可能延迟十几分钟
- 频率不要低于每 6 小时一次，否则容易触发 `-65`

---

## 十一、同步上游会覆盖本地修改

本仓库是 Fork，且 master 上有三类本地提交：CI 修复、定时调整、`skills/` 目录。

```bash
gh repo sync --force   # ❌ 把 master 强制指向上游，以上修改全部丢失
gh repo sync           # ✅ 非强制，无法快速前进时会拒绝而不是覆盖
```

需要长期维护本地改动时，更稳的做法是同步前先建备份分支，或把改动挪到独立分支日常使用。

---

## 十二、GitHub 通知设置无法通过 API 查询或修改

- `GET /user/notification_settings` 不存在，返回 404
- 公开资料里的 `email` 字段可能为 `null`（用户隐藏了邮箱）
- 读取私有邮箱列表需要 `user` scope，最小权限配置下通常不具备
- 因此「还会不会发邮件」只能看网页：`Settings → Notifications → System → Actions`

**实证判断法**：GitHub 只在工作流**失败**时通知触发者。可以查 `gh run list` 里是否有结论为
`failure` 的运行记录；若有，询问用户当时是否收到过标题类似 `Run failed` 的邮件——没收到即说明通知已关闭。
