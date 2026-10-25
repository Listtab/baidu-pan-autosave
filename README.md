# baidu-pan-autosave

一个 WorkBuddy 技能。给它百度网盘分享链接和一份 Cookie，它在你自己的 GitHub 账号里配一套定时任务，定期把分享里新出现的文件补进你的网盘。

## 原理

整件事跑在 GitHub 的服务器上，你的电脑不需要开着。

核心是一条 GitHub Actions 定时任务，到点就拉起一个 Python 脚本。脚本干三件事。

先拿你的 Cookie 登录百度网盘，打开分享链接，把里面的文件清单拉下来，每个文件带一个 MD5 值。

然后扫你自己网盘里的目标目录，同样拿到每个文件的 MD5。两边按文件名对上，逐个比 MD5。

最后只对"本地没有"的文件发起转存，其余跳过。所以同一份配置反复跑，不会产生副本，只会在分享方加了新文件时把那几个补上。

有两条路径。如果目标目录压根不存在，比如第一次跑，它走整目录直接转存，把整个文件夹一次搬过去，快。如果目标目录已经存在，才走上面说的逐文件比对。日志里能看到"尝试整目录直接转存"和"回退逐文件对比转存"这两种字样，就是这两条路。

转存动作本身调用的是开源项目 [baidu-autosave](https://github.com/Jack261108/baidu-autosave) 的代码，跑在你自己 Fork 出来的仓库里。本仓库只放配置脚本和说明，不含它的源码，也不是它的 Fork。

## 使用

### 准备

装 GitHub CLI，然后 `gh auth login`。登录时令牌需要 `repo` 和 `workflow` 两个 scope，后者用来提交工作流文件的改动。

Python 3.9 以上，脚本只用标准库，没有第三方依赖。

### 安装

目录名必须是 `baidu-pan-autosave`，技能靠目录名识别。

```bash
git clone https://github.com/Listtab/baidu-pan-autosave.git ~/.workbuddy/skills/baidu-pan-autosave
```

Windows：

```powershell
git clone https://github.com/Listtab/baidu-pan-autosave.git "$env:USERPROFILE\.workbuddy\skills\baidu-pan-autosave"
```

### 取 Cookie

只能手工取，浏览器把 Cookie 值加密了，脚本读不出来。

登录 `pan.baidu.com`，按 F12，切到「应用 / Application」，左边点 Cookie 下的 `https://pan.baidu.com`。表格上方的筛选框输入 `BDUSS`，双击值那一格复制；再把筛选词换成 `STOKEN`，同样复制一次。存到一个文本文件里，格式是 `BDUSS=xxx; STOKEN=xxx`，中间是分号加一个空格。

### 配置并运行

四条命令，按顺序走。

```bash
# 看当前状态
python scripts/baidu_autosave.py status

# 建 Fork、修依赖、打开工作流。重复执行是安全的
python scripts/baidu_autosave.py provision --cron "17 10,11 * * *"

# 写 Cookie 和分享链接
python scripts/baidu_autosave.py configure \
    --cookie-file C:/cookie.txt \
    --share-url "https://pan.baidu.com/s/1xxxxx?pwd=abcd" \
    --save-dir "/"

# 触发一次，等它跑完并打印结果
python scripts/baidu_autosave.py run
```

不写子命令的话用 `all`，等于把后三条连着跑一遍。

在 WorkBuddy 里不用敲命令，直接说「把这个转存到我的网盘：链接」就会触发。

### 两个参数要留意

`--cron` 用 UTC 计时，北京时间减 8 小时。`17 10,11 * * *` 对应每天北京时间的 18:17 和 19:17。

`--save-dir` 填的是父目录，不是目标文件夹。填 `/`，分享里的 `示例文件夹` 会落到 `/示例文件夹`；填 `/示例文件夹`，会变成 `/示例文件夹/示例文件夹`。默认给的是 `/`。

### 跑完之后

结果在 Actions 页面能看，脚本的 `run` 也会直接打印四项数字：分享里共几个文件、网盘已有几个、冲突几个、实际转存几个。

冲突的意思是文件名对得上但 MD5 不一样，也就是分享方换了文件内容。这种情况工具不会覆盖你网盘里的旧版本，只跳过。想更新得先手动删掉旧文件，下一轮才会补。

### 定时改了怎么生效

改 `--cron` 重新跑一次 `provision` 就会覆盖。也可以用 `gh workflow disable` 临时停掉。

## 许可

MIT。上游 baidu-autosave 同样是 MIT，版权归原作者，本仓库不含它的源码。
