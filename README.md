# baidu-pan-autosave

WorkBuddy 技能：把「给出百度网盘分享链接 + Cookie → 定时自动转存到本人网盘」封装成可复用能力。

底层复用开源项目 [baidu-autosave](https://github.com/Jack261108/baidu-autosave)，运行在**使用者自己的 GitHub Fork** 上，由 GitHub Actions 定时调度，不需要本地机器常开。

本仓库与该上游项目**互相独立**：不包含上游源码，只包含技能说明与配置自动化脚本，因此不受上游变更影响。

## 为什么需要这个技能

上游项目本身可用，但开箱即用会连续失败三次。本技能把修复与配置流程固化：

| 上游缺陷 | 后果 | 处理 |
|---|---|---|
| 工作流写死 Python 3.9，而 `requests==2.33.0` 要求 ≥3.10 | 装依赖直接失败 | 自动改为 3.12 |
| Python 3.12 起 `ensurepip` 不再自带 setuptools | Cython 扩展编译失败 | 自动补 `requirements.txt` |
| Fork 仓库的定时工作流默认 `disabled_fork` | 定时不触发 | 检测后调 API 启用 |
| `SAVE_DIR` 是父目录，容易理解错 | 产生嵌套重复目录 | 默认 `/`，文档给出对照表 |

额外规避一个只在 Git Bash 下出现的隐蔽问题：以 `/` 开头的命令行参数会被 MSYS 改写成 Windows 路径，导致百度返回 `31062 文件名非法`。脚本全程用 `subprocess` + stdin 传值，不经过 shell。

## 前置条件

- 安装 [GitHub CLI](https://cli.github.com/) 并完成 `gh auth login`
- 令牌需含 `repo` 与 `workflow` 两个 scope（后者用于提交工作流文件修改）
- Python 3.9+（脚本只用标准库）

## 安装

把本仓库放进 WorkBuddy 的用户级技能目录，目录名必须是 `baidu-pan-autosave`：

```bash
git clone https://github.com/Listtab/baidu-pan-autosave.git ~/.workbuddy/skills/baidu-pan-autosave
```

Windows 可用：

```powershell
git clone https://github.com/Listtab/baidu-pan-autosave.git "$env:USERPROFILE\.workbuddy\skills\baidu-pan-autosave"
```

重启对话后，技能列表中出现 `baidu-pan-autosave` 即生效。

## 使用

```bash
# 查看现状：仓库、工作流状态、Secrets、最近运行的统计
python scripts/baidu_autosave.py status

# 首次搭建（Fork + 修复 + 启用）；已配置过的仓库重复执行是幂等的
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"

# 写入 Cookie 与分享链接
python scripts/baidu_autosave.py configure \
    --cookie-file C:/path/to/cookie.txt \
    --share-url "https://pan.baidu.com/s/1xxxxx?pwd=abcd" \
    --save-dir "/"

# 触发一次并等待结果
python scripts/baidu_autosave.py run
```

`all` 等同于 `provision` + `configure` + `run`。
目标仓库默认取「当前 gh 账号 / baidu-autosave」，可用 `--repo owner/name` 指定。

在 WorkBuddy 对话中，直接说「把这个转存到我的网盘：<链接>」，技能会自动触发。

## Cookie 怎么获取

浏览器 Cookie 值带 `v20` 前缀，属 **App-Bound Encryption**。DPAPI 解密、CDP 调试端口、复制整个浏览器配置文件三条自动化路径均已实测失败，只能手工复制：

1. 浏览器登录 `pan.baidu.com`
2. `F12` → **应用 / Application** → **Cookie** → `https://pan.baidu.com`
3. 筛选框输入 `BDUSS` 复制值；再输入 `STOKEN` 复制值
4. 拼成 `BDUSS=xxx; STOKEN=xxx`（分号 + 空格）

建议存成本地文件后用 `--cookie-file` 传入，避免凭证进入对话记录。

## 使用前必须知道的三件事

1. **只补缺，不覆盖。** 同名文件若内容已变化（MD5 不同），会被记为「冲突」并跳过，不会替换。要更新只能先删除网盘里的旧文件，下一轮才补。
2. **`SAVE_DIR` 是父目录。** 填 `/` 才会落到 `/分享文件夹名`；填具体文件夹名会产生嵌套。
3. **Fork 后首次需人工点一次。** 打开 `https://github.com/<你>/baidu-autosave/actions`，点击横幅「I understand my workflows, go ahead and enable them」，之后才能用 API 启用。

## 目录结构

```
.
├── SKILL.md                      技能定义（触发条件、工作流、约定）
├── README.md                     本文件
├── LICENSE                       MIT
├── scripts/baidu_autosave.py     全部操作的确定性实现
└── references/pitfalls.md        12 类坑的排查手册与错误码速查
```

## 维护提示

`references/personal-defaults.md` 是可选的本机配置文件（已列入 `.gitignore`），用于保存个人默认值（目标仓库、保存目录、定时）。若存在，技能优先读取它；不存在则用通用默认值。

## 许可

MIT。上游 baidu-autosave 亦为 MIT，版权归其作者所有；本项目不含上游源码。
