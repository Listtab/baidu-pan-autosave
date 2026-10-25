# 踩坑记录

配这套东西的过程中撞上的问题，大致按遇到的顺序写。改脚本或排查异常之前翻一下，能省不少时间。

## Git Bash 会把以 / 开头的参数当成路径

现象很迷惑：百度返回 `error_code: 31062, message: 文件名非法`，而报错里的路径显示成 `/C:` 开头。

原因是 MSYS2 的参数转换。执行下面这句的时候，

```bash
gh secret set SAVE_DIR --body "/示例文件夹"
```

实际传给 `gh` 的值已经变成 `C:/Program Files/Git/示例文件夹`。Windows 路径被当成网盘路径发给了百度，自然不合法。

三种解法，任选：

```bash
# 关掉本次转换
MSYS_NO_PATHCONV=1 gh secret set SAVE_DIR --body "/示例文件夹"

# 或者让值走 stdin，不经过命令行参数
printf '%s' "/示例文件夹" > /tmp/v.txt
gh secret set SAVE_DIR --repo owner/repo < /tmp/v.txt
```

本技能的脚本用 `subprocess` 加 `input=` 传值，不经过 shell，所以不受影响。只有手工在 bash 里敲命令时才会踩到。

## gh api 的端点参数也中招

同一个转换，换了个地方出现：

```bash
gh api /user        # invalid API endpoint "C:/Program Files/.../user"
gh api user         # 正确，去掉前导斜杠
```

`gh api` 的报错信息本身会提示这件事，但第一次见容易看不懂。凡是以 `/` 开头的命令行参数，在 Git Bash 下都有这个风险。

顺带一提，PowerShell 有另一套毛病：URL 里的 `%2F` 会被当成环境变量语法，直接拦截命令，跟 MSYS 无关但同样烦人。

## 工作流里的 Python 版本和依赖要求打架

CI 在 Install dependencies 这一步就失败：

```
ERROR: Could not find a version that satisfies the requirement requests==2.33.0
```

`requirements.txt` 要 `requests==2.33.0`，这版本要求 Python 3.10 以上，而 `.github/workflows/baidu-transfer.yml` 里 `python-version` 写的是 `'3.9'`。上游自己的两处配置矛盾，跟使用者无关。

改工作流里的版本号到 `3.12` 即可。

## 改完版本，编译又挂了

```
File ".../vendor/BaiduPCS-Py/build.py", line 3, in <module>
    from setuptools import setup
ModuleNotFoundError: No module named 'setuptools'
```

Python 3.12 起 `ensurepip` 不再附带 setuptools，而 `vendor/BaiduPCS-Py` 的 Cython 扩展还是走 `setup.py` 构建。

在 `requirements.txt` 末尾加 `setuptools>=68`。

这两件事必须一起解决。只改 Python 版本会让问题从"装不上依赖"变成"编译失败"，看起来像换了个新问题，其实是同一个链条上的下一步。

## Fork 出来的工作流要先手动注册

`gh workflow list` 没有任何输出，`gh workflow enable <文件名>` 返回

```
HTTP 404: workflow not found on the default branch
```

但文件明明在。`gh api repos/{o}/{r}/contents/.github/workflows` 能看到 `baidu-transfer.yml` 和 `test-on-push.yml`。

原因是 GitHub 对 Fork 仓库默认不注册工作流，防止有人 Fork 完立刻刷 Actions 额度。这一步 API 做不到。

处理办法是打开 `https://github.com/<owner>/<repo>/actions`，点横幅上的确认按钮，之后工作流才会出现在列表里，状态可能是 `disabled_fork`。这时候才能用 API 激活：

```bash
gh api -X PUT repos/{owner}/{repo}/actions/workflows/{id}/enable
```

注意按 ID 启用，不要按名字。中文界面下 `gh workflow enable "Baidu Transfer Task"` 会匹配失败，报"找不到名为 xxx 的工作流"。

## 别用 MCP 连接器做这些事

试过，都不行，记下来免得后面又想走这条路：

`fork_repository` 返回 `403 Resource not accessible by integration`，因为 MCP 连接器是以 GitHub App 身份运行的，没有"在用户账号下创建仓库"的权限。MCP 也没有写 Actions Secrets 的工具。

所以建 Fork 和写 Secret 必须用 `gh` CLI 或者自己的 PAT。

另外 `gh auth login --web` 的 device flow 能跑，但 GitHub 会要求 sudo 模式二次验证，输密码或通行密钥。这一步只能账号本人做，代不了。

## Cookie 三条自动化路线全封死

值带 `v20` 前缀，是 Chrome 127 / Edge 同期引入的应用绑定加密。

试过的三条路和结果：

用 DPAPI 解 `Local State` 里的 `encrypted_key`，成功拿到主密钥，但 `v20` 的数据不是这套算法加密的，解不开。这条路算是确认了"旧方法失效"。

对真实的默认配置目录开 `--remote-debugging-port`，Chromium 156 起静默禁用，端口根本不监听。它只允许非默认的 user-data-dir。

把整个 `User Data` 复制到临时目录，在副本上开调试端口。端口通了，`Storage.getCookies` 也能调，但只返回 30 个新生成的 msn/bing Cookie，原有的一条都没有。加密密钥绑定了配置路径，换了位置就解不开，浏览器干脆把它们全丢弃了。

顺带说一句，`document.cookie` 也读不到，因为 `BDUSS` 和 `STOKEN` 都是 HttpOnly。

结论就是只能人工复制。别再在这上面花时间了。

## SAVE_DIR 是父目录，不是目标文件夹

分享是单个文件夹时，实际落点等于 `SAVE_DIR` 加斜杠加分享文件夹名。

填 `/示例文件夹` 会得到 `/示例文件夹/示例文件夹`。之后就算改回 `/`，那个嵌套目录也不会自己消失，得手动去网盘删掉。

判断有没有踩这个坑：日志里出现「尝试整目录直接转存」并且成功，而你原本以为目标目录已经存在，那就是了。

## 错误码对照

`31062 文件名非法`：路径里有非法字符，或者路径被改写过，回去看第一节。

`-65`：百度风控限频。停几个小时，别缩周期也别反复重试。

未登录、登录态失效：Cookie 过期了，重新取 `BDUSS` 和 `STOKEN`。

`创建目录失败: 文件名非法`：跟 31062 是同一回事。

## Secret 只写不可读

保存之后谁都看不到原值，包括你自己，只能覆盖。

`SHARE_URLS` 这种多行内容尤其要注意，本地必须留一份原始清单。不然想加一条链接的时候，你已经不知道现在里面有哪些了。

日志脱敏是子串级的，`SHARE_URLS` 里的片段也会被打码。日志里出现 `【1***1】` 这种奇怪的东西是正常的，不是程序出错。

## 定时用的是 UTC

cron 按 UTC 算，北京时间要减 8 小时。

整点最容易堵，GitHub 的调度器在 `:00` 那会儿排队最长，可能延迟十几分钟。用 `:17`、`:43` 这种错开的分钟数会稳一些。

频率别低于每 6 小时一次，密了容易触发 `-65`。

## 同步上游会覆盖本地修改

这个仓库是 Fork，master 上有三类本地提交：CI 修复、定时调整，以及曾经放过的技能目录（后来拆走了）。

```bash
gh repo sync --force   # 把 master 强制指向上游，本地提交全没
gh repo sync           # 非强制，无法快进时会拒绝，不会覆盖
```

要长期保留本地改动，要么别用 force，要么同步前先建个备份分支。

## 通知设置查不到，也改不了

`GET /user/notification_settings` 这个端点不存在，返回 404。公开资料里的 `email` 字段常常是 `null`，说明用户隐藏了邮箱。想读私有邮箱列表需要 `user` scope，最小权限配置下通常没有。

所以"还会不会收到邮件"只能去网页看：`Settings → Notifications → System → Actions`。

有个间接的判断办法。GitHub 只在工作流失败时通知触发者，所以可以先看有没有失败的运行记录：

```bash
gh run list --repo owner/repo --limit 10 --json conclusion,createdAt
```

如果有 `failure`，就问用户那会儿有没有收到标题类似 `Run failed` 的邮件。没收到就说明通知确实关了，比翻设置页还直接。

## 空仓库不能直接建 blob

Git Data API 在没有任何提交的仓库上会报 409：

```
{"message":"Git Repository is empty."}
```

得先用 Contents API 落一个初始提交，之后 blob、tree、commit 那一套才能用：

```bash
gh api -X PUT repos/{o}/{r}/contents/README.md --input payload.json
```

## 一次删多个文件用 tree 就行

在 `POST /git/trees` 里把条目的 `sha` 设成 `null`，一次提交就能删掉多个路径，不用逐个调 DELETE 产生一堆提交。

```json
{
  "base_tree": "<当前 tree>",
  "tree": [
    {"path": "a/b.md", "mode": "100644", "type": "blob", "sha": null}
  ]
}
```
