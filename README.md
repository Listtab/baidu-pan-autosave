# baidu-pan-autosave

一个 WorkBuddy 技能，解决一件很小的事：从别人那儿拿到百度网盘分享链接，不想每次手动点转存，也不想盯着分享方什么时候更新。

装好之后给它一个链接、一份百度 Cookie，它会在你的 GitHub 账号里搭一套定时任务。之后每到你设的时间，它去看一眼分享里有哪些文件是你网盘里还没有的，有就补进去，没有就什么都不做。全程跑在 GitHub 的服务器上，电脑关着也不影响。

转存本身用的是开源项目 [baidu-autosave](https://github.com/Jack261108/baidu-autosave)。这个仓库不含它的源码，只放技能说明和几个配置脚本，所以它不是 Fork，上游怎么改都影响不到这里。

## 照上游 README 配，会连续失败三次

这是我第一次配的时候的真实顺序，不是假设。

装依赖就过不去。上游 `requirements.txt` 锁了 `requests==2.33.0`，这个版本要求 Python 3.10 以上，可工作流里 `python-version` 写死成 `'3.9'`。两个文件互相矛盾，pip 直接报 `No matching distribution found`。

把版本改到 3.12，依赖装上了，下一步又挂在编译。Python 3.12 起 `ensurepip` 不再自带 setuptools，而 `vendor/BaiduPCS-Py` 那个扩展还在用 `setup.py` 构建，于是 `ModuleNotFoundError: No module named 'setuptools'`。补一行 `setuptools>=68` 才过去。

等程序能跑，定时却一直不动。Fork 出来的仓库，Actions 工作流默认是关的，而且最开始根本不出现在 API 列表里，用 `gh workflow enable` 会直接返回 404。必须先去网页上点一次确认。

三处都是上游的问题，跟你的配置无关。`provision` 会自动处理掉，写在这里只是让人知道脚本里那些检查不是多余的。

## SAVE_DIR 填的不是目标文件夹

这个字段容易理解反。它问的不是"文件存到哪个文件夹"，而是"分享里的那个文件夹放到哪儿"。

假设分享本身是个叫 `示例文件夹` 的单文件夹。填 `/`，结果是 `/示例文件夹`，这是多数人想要的。填 `/示例文件夹`，结果变成 `/示例文件夹/示例文件夹`，白白多占一份空间，而且不会自己消失，得你去网盘里手动删。

所以默认值给的是 `/`。

## 装之前要有什么

GitHub CLI 装好，并且执行过 `gh auth login`。令牌需要 `repo` 和 `workflow` 两个 scope，后者是提交工作流文件改动必需的，缺了会在改 CI 那一步被拒。

Python 3.9 以上就行，脚本只用标准库，没有第三方依赖要装。

## 安装

目录名固定，必须是 `baidu-pan-autosave`，技能靠目录名识别，改名会失效。

```bash
git clone https://github.com/Listtab/baidu-pan-autosave.git ~/.workbuddy/skills/baidu-pan-autosave
```

Windows：

```powershell
git clone https://github.com/Listtab/baidu-pan-autosave.git "$env:USERPROFILE\.workbuddy\skills\baidu-pan-autosave"
```

重启对话，技能列表里能看到 `baidu-pan-autosave` 就算装好了。

## 用法

四条命令按顺序走一遍就能跑通。

```bash
# 看当前状态：仓库、工作流、已配的 Secret、最近一次运行的结果
python scripts/baidu_autosave.py status

# 第一次用或换机器：建 Fork、修上游那几个坑、把工作流打开
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"

# 写 Cookie 和链接
python scripts/baidu_autosave.py configure \
    --cookie-file C:/cookie.txt \
    --share-url "https://pan.baidu.com/s/1xxxxx?pwd=abcd" \
    --save-dir "/"

# 手动跑一次并等它结束
python scripts/baidu_autosave.py run
```

`provision` 重复执行不会产生多余提交，换机器重跑一遍是安全的。`all` 就是把 provision、configure、run 串起来跑一遍。

默认操作当前 `gh` 账号下的 `baidu-autosave`，要换目标用 `--repo owner/name`。

在 WorkBuddy 里不用敲命令，直接说「把这个转存到我的网盘：链接」就行。

## Cookie 只能手动复制

这块没办法偷懒，我试过三条自动化路线，全部走不通。

浏览器存的 Cookie 值带 `v20` 前缀，是 Chrome 127 之后引入的应用绑定加密。用 DPAPI 解 `Local State` 里的密钥，解不开；对默认配置目录开 `--remote-debugging-port`，Chromium 156 起直接静默禁用；把整个浏览器配置复制到临时目录再开调试端口，端口倒是通了，但加密密钥绑定了配置路径，原有 Cookie 全被丢弃，只剩几个无关站点新生成的 Cookie。

所以只能手工：

1. 浏览器登录 `pan.baidu.com`
2. 按 `F12`，切到「应用 / Application」，左边找 Cookie，点 `https://pan.baidu.com`
3. 表格上方的筛选框输入 `BDUSS`，双击值那一格复制；再把筛选词换成 `STOKEN`，同样复制
4. 拼成 `BDUSS=xxx; STOKEN=xxx`，中间是分号加一个空格，两段都不能少

建议先存成本地文件，用 `--cookie-file` 传给脚本。直接贴在对话里的话，GitHub 那边是加密存的、日志也脱敏，但聊天记录里是明文，而 BDUSS 相当于网盘账号的登录凭证，拿到就能读写删。

另外它不会过期，除非你主动让它失效。真怀疑泄露了，去百度网盘网页端「退出所有设备」，旧值立刻作废，再重新取一份。

## 几个容易忽略的点

工具只补缺，不覆盖。同名文件如果内容变了，MD5 不一样，它会把这种情况算作"冲突"跳过，不会替换。想更新只能先删掉网盘里的旧文件，下一轮才会补新的。它本身没有强制覆盖的开关。

频率别往密里调。默认一天两次，密度再高容易撞上百度的限频，报 `error_code: -65`，遇到就只能停几个小时，反复重试会更糟。

Fork 之后要先手动点一次确认。打开 `https://github.com/<你的账号>/baidu-autosave/actions`，页面上有一条横幅让你确认启用工作流，点掉之后 API 才能操作它。

## 目录结构

```
.
├── SKILL.md                      技能定义，AI 读这个
├── README.md                     本文件
├── LICENSE                       MIT
├── scripts/baidu_autosave.py     所有操作的实现
└── references/pitfalls.md        踩坑记录和错误码
```

`references/personal-defaults.md` 是可选的，用来存个人默认值（目标仓库、保存目录、定时），已经写进 `.gitignore`。有这个文件时技能优先读它，没有就用通用默认值。所以直接 clone 下来的仓库里看不到它，属于正常。

## 许可

MIT。上游 baidu-autosave 同样是 MIT，版权归原作者，这个仓库不含它的任何源码。
