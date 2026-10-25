#!/usr/bin/env python3
"""百度网盘分享自动转存 —— 一键配置与验证。

把 GitHub Actions 版 baidu-autosave 仓库的配置流程固化为确定性脚本，
规避手工操作中的已知陷阱：

  * Git Bash(MSYS) 会把以 / 开头的参数改写成 Windows 路径
    -> 本脚本全部通过 stdin 传值给 gh，不做任何 shell 拼接
  * 上游工作流写死 Python 3.9，但 requests==2.33.0 要求 >=3.10
    -> provision 自动改到 3.12
  * Python 3.12 起 ensurepip 不带 setuptools，Cython 扩展编译失败
    -> provision 自动补 requirements.txt
  * Fork 仓库的定时工作流默认 disabled_fork，且首次不出现在 API 里
    -> provision 能自动启用则启用，不能则明确提示需要网页点一次

用法：
    python baidu_autosave.py status
    python baidu_autosave.py provision [--cron "17 10,11 * * *"]
    python baidu_autosave.py configure --cookie-file C:/c.txt --share-url "https://pan.baidu.com/s/xxx?pwd=abcd"
    python baidu_autosave.py run
    python baidu_autosave.py all --cookie-file C:/c.txt --share-url "..."

Cookie 只经 stdin 传递，永不打印、不落盘。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

DEFAULT_UPSTREAM = "Jack261108/baidu-autosave"
DEFAULT_REPO_NAME = "baidu-autosave"
BRANCH = "master"
WORKFLOW_PATH = ".github/workflows/baidu-transfer.yml"
REQ_PATH = "requirements.txt"

WORKFLOW_NEEDS_REGISTRATION = (
    "该 Fork 的工作流尚未在 GitHub 侧注册（Fork 仓库的默认安全行为）。\n"
    "需要人工完成一次：\n"
    "  1. 用浏览器打开 https://github.com/{repo}/actions\n"
    "  2. 点击横幅上的 “I understand my workflows, go ahead and enable them”\n"
    "  3. 回到这里重新执行 provision\n"
)


def find_gh() -> str:
    for cand in (
        shutil.which("gh"),
        r"C:\Program Files\GitHub CLI\gh.exe",
        "/usr/bin/gh",
        "/usr/local/bin/gh",
    ):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("找不到 gh CLI。请先安装 GitHub CLI 并执行 gh auth login。")


GH = find_gh()


def sh(args: list[str], stdin: str | None = None, check: bool = True) -> str:
    proc = subprocess.run(
        [GH, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} 失败:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def api(path: str, method: str = "GET", payload: dict | None = None, jq: str | None = None) -> str:
    args = ["api", path]
    if method != "GET":
        args += ["-X", method]
    if jq:
        args += ["-q", jq]
    stdin = None
    if payload is not None:
        args += ["--input", "-"]
        stdin = json.dumps(payload)
    return sh(args, stdin=stdin)


def api_optional(path: str) -> str | None:
    try:
        return api(path)
    except RuntimeError:
        return None


def current_login() -> str:
    return api("user", jq=".login").strip()


def target_repo(explicit: str | None) -> str:
    if explicit:
        return explicit
    return f"{current_login()}/{DEFAULT_REPO_NAME}"


def repo_exists(repo: str) -> bool:
    return api_optional(f"repos/{repo}") is not None


# ---------------------------------------------------------------- provision

def patch_workflow(repo: str, cron: str | None) -> list[str]:
    raw = sh(["api", f"repos/{repo}/contents/{WORKFLOW_PATH}",
              "-H", "Accept: application/vnd.github.raw"])
    sha = api(f"repos/{repo}/contents/{WORKFLOW_PATH}", jq=".sha").strip()
    notes: list[str] = []
    patched = raw

    m = re.search(r"python-version:\s*'([0-9.]+)'", patched)
    if m:
        cur = m.group(1)
        try:
            needs_bump = tuple(int(x) for x in cur.split(".")[:2]) < (3, 10)
        except ValueError:
            needs_bump = True
        if needs_bump:
            patched = patched[: m.start(1)] + "3.12" + patched[m.end(1):]
            notes.append(f"Python 版本 {cur} -> 3.12（requests 要求 >=3.10）")

    if cron:
        m = re.search(r"-\s*cron:\s*'([^']+)'", patched)
        if m:
            if m.group(1) != cron:
                patched = patched[: m.start(1)] + cron + patched[m.end(1):]
                notes.append(f"定时 {m.group(1)} -> {cron}")
        else:
            notes.append("警告：未找到 cron 行，定时未修改")

    if patched != raw:
        payload = {
            "message": "chore(skill): align CI runtime and schedule",
            "content": _b64(patched),
            "sha": sha,
            "branch": BRANCH,
        }
        api(f"repos/{repo}/contents/{WORKFLOW_PATH}", "PUT", payload)
    return notes


def patch_requirements(repo: str) -> list[str]:
    raw = sh(["api", f"repos/{repo}/contents/{REQ_PATH}",
              "-H", "Accept: application/vnd.github.raw"])
    if "setuptools" in raw:
        return []
    sha = api(f"repos/{repo}/contents/{REQ_PATH}", jq=".sha").strip()
    new = raw if raw.endswith("\n") else raw + "\n"
    new += "setuptools>=68\n"
    payload = {
        "message": "chore(skill): add setuptools for Cython build",
        "content": _b64(new),
        "sha": sha,
        "branch": BRANCH,
    }
    api(f"repos/{repo}/contents/{REQ_PATH}", "PUT", payload)
    return ["requirements.txt 补充 setuptools>=68（Python 3.12 编译扩展所需）"]


def _b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def ensure_fork(repo: str, upstream: str) -> list[str]:
    if repo_exists(repo):
        return [f"仓库已存在：{repo}"]
    owner, name = repo.split("/", 1)
    login = current_login()
    if owner != login:
        raise SystemExit(f"仓库 {repo} 不存在，且不属于当前登录账号 {login}，无法自动 Fork")
    sh(["repo", "fork", upstream, "--clone=false"])
    for _ in range(20):
        if repo_exists(repo):
            return [f"已 Fork：{upstream} -> {repo}"]
        time.sleep(3)
    raise SystemExit("Fork 请求已提交但仓库尚未可用，稍后重试 provision")


def enable_workflows(repo: str) -> list[str]:
    data = json.loads(api(f"repos/{repo}/actions/workflows"))
    flows = data.get("workflows") or []
    if not flows:
        raise SystemExit(WORKFLOW_NEEDS_REGISTRATION.format(repo=repo))

    notes = []
    for wf in flows:
        state = wf.get("state")
        if state != "active":
            api(f"repos/{repo}/actions/workflows/{wf['id']}/enable", "PUT")
            notes.append(f"启用工作流：{wf.get('name')} ({state} -> active)")
        else:
            notes.append(f"工作流已激活：{wf.get('name')}")
    return notes


def cmd_provision(args) -> int:
    repo = target_repo(args.repo)
    notes = ensure_fork(repo, args.upstream)
    notes += patch_workflow(repo, args.cron)
    notes += patch_requirements(repo)
    notes += enable_workflows(repo)
    for n in notes:
        print("  -", n)
    return 0


# ---------------------------------------------------------------- configure

KEY_RE = re.compile(r"\b(BDUSS|STOKEN)\s*[=:]\s*([^\s;,\n]+)")


def normalize_cookie(raw: str) -> str:
    found = {}
    for key, val in KEY_RE.findall(raw):
        found.setdefault(key, val)
    missing = [k for k in ("BDUSS", "STOKEN") if k not in found]
    if missing:
        raise SystemExit(f"Cookie 缺少字段：{', '.join(missing)}（需要 BDUSS 与 STOKEN）")
    return f"BDUSS={found['BDUSS']}; STOKEN={found['STOKEN']}"


def read_cookie(args) -> str | None:
    if args.cookie_file:
        with open(args.cookie_file, encoding="utf-8") as f:
            return f.read()
    if args.cookie:
        return args.cookie
    return None


def set_secret(repo: str, name: str, value: str) -> None:
    sh(["secret", "set", name, "--repo", repo], stdin=value)


def cmd_configure(args) -> int:
    repo = target_repo(args.repo)
    if not repo_exists(repo):
        raise SystemExit(f"仓库 {repo} 不存在，先执行 provision")

    notes = []
    raw_cookie = read_cookie(args)
    if raw_cookie:
        cookie = normalize_cookie(raw_cookie)
        set_secret(repo, "BAIDU_COOKIES", cookie)
        notes.append(f"BAIDU_COOKIES 已写入（BDUSS {len(cookie)} 字符，值不回显）")

    if args.share_url:
        set_secret(repo, "SHARE_URLS", "\n".join(args.share_url))
        notes.append(f"SHARE_URLS 已写入（{len(args.share_url)} 条链接）")

    if args.save_dir is not None:
        set_secret(repo, "SAVE_DIR", args.save_dir)
        notes.append(f"SAVE_DIR = {args.save_dir!r}")

    listed = json.loads(api(f"repos/{repo}/actions/secrets")).get("secrets", [])
    names = sorted(s["name"] for s in listed)
    notes.append("当前 Secrets：" + (", ".join(names) if names else "（空）"))

    required = {"BAIDU_COOKIES", "SHARE_URLS"}
    lacking = sorted(required - set(names))
    for n in notes:
        print("  -", n)
    if lacking:
        print(f"\n仍缺少必需项：{', '.join(lacking)}（补齐后才能运行）")
    return 0


# ---------------------------------------------------------------- run / status

SUMMARY_PATTERNS = (
    "候选分析完成",
    "批量转存完成",
    "整目录直接转存",
    "回退逐文件对比转存",
    "转存完成",
    "冲突",
)


def latest_run(repo: str) -> dict | None:
    out = sh(["run", "list", "--repo", repo, "--limit", "1",
              "--json", "databaseId,status,conclusion,createdAt,event"])
    data = json.loads(out)
    return data[0] if data else None


def summarize_log(repo: str, run_id: int) -> None:
    try:
        log = sh(["run", "view", str(run_id), "--repo", repo, "--log"])
    except RuntimeError as exc:
        print("  读取日志失败：", exc)
        return
    hits = []
    for line in log.splitlines():
        body = line.split("\t")[-1]
        body = re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s*", "", body).strip()
        if any(p in body for p in SUMMARY_PATTERNS):
            hits.append(body)
    for h in hits[-12:]:
        print("   ", h)
    if not hits:
        print("    （日志中未匹配到统计行，请到 Actions 页面查看）")


def cmd_run(args) -> int:
    repo = target_repo(args.repo)
    wf_id = args.workflow_id
    if not wf_id:
        data = json.loads(api(f"repos/{repo}/actions/workflows"))
        flows = data.get("workflows") or []
        if not flows:
            raise SystemExit(WORKFLOW_NEEDS_REGISTRATION.format(repo=repo))
        wf_id = flows[0]["id"]

    print(f"触发展开：{repo} workflow {wf_id}")
    sh(["workflow", "run", str(wf_id), "--repo", repo, "--ref", BRANCH])
    time.sleep(8)

    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        run = latest_run(repo)
        if run:
            if run["status"] == "completed":
                last = run
                break
            if run["status"] != last:
                last = run["status"]
                print(f"  状态：{run['status']}")
        time.sleep(10)

    if not last:
        print("等待超时，请稍后用 status 查看")
        return 1

    print(f"\n运行 {last['databaseId']} 结论：{last['conclusion']}")
    print("关键统计：")
    summarize_log(repo, last["databaseId"])
    return 0 if last["conclusion"] == "success" else 1


def cmd_status(args) -> int:
    repo = target_repo(args.repo)
    if not repo_exists(repo):
        raise SystemExit(f"仓库 {repo} 不存在")
    flows = json.loads(api(f"repos/{repo}/actions/workflows")).get("workflows", [])
    secrets = json.loads(api(f"repos/{repo}/actions/secrets")).get("secrets", [])
    print(f"仓库：{repo}")
    print("工作流：" + (", ".join(f"{f['name']}={f['state']}" for f in flows) or "未注册"))
    print("Secrets：" + (", ".join(s["name"] for s in secrets) or "（空）"))

    out = sh(["run", "list", "--repo", repo, "--limit", "5",
              "--json", "databaseId,status,conclusion,createdAt"])
    runs = json.loads(out)
    if not runs:
        print("暂无运行记录")
        return 0
    print("\n最近运行：")
    for r in runs:
        print(f"  {r['createdAt']}  {r['status']:<12} {r['conclusion'] or '-':<10} {r['databaseId']}")
    newest = runs[0]
    if newest["status"] == "completed":
        print("\n最新一次的关键统计：")
        summarize_log(repo, newest["databaseId"])
    return 0


# ---------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="百度网盘自动转存配置/验证")
    p.add_argument("action", choices=["provision", "configure", "run", "status", "all"])
    p.add_argument("--repo", help="形如 owner/name，默认取当前 gh 账号下的 baidu-autosave")
    p.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    p.add_argument("--cron", help="UTC cron 表达式，如 '17 10,11 * * *'")
    p.add_argument("--cookie", help="Cookie 字符串（含 BDUSS 与 STOKEN）")
    p.add_argument("--cookie-file", help="从文件读取 Cookie")
    p.add_argument("--share-url", action="append", metavar="URL",
                   help="分享链接，可多次指定；可写成 '链接 目录'")
    p.add_argument("--save-dir", help="保存父目录，默认 '/'（分享文件夹落在根目录）")
    p.add_argument("--workflow-id", type=int)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()

    if args.action == "provision":
        return cmd_provision(args)
    if args.action == "configure":
        return cmd_configure(args)
    if args.action == "run":
        return cmd_run(args)
    if args.action == "status":
        return cmd_status(args)

    rc = cmd_provision(args)
    if rc:
        return rc
    print()
    rc = cmd_configure(args)
    if rc:
        return rc
    print()
    return cmd_run(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except RuntimeError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        sys.exit(1)
