#!/usr/bin/env bash
# =============================================================================
#  M0-1 现场环境验收脚本
#  用途：现场交给学生，在其本机环境运行，判断"开发环境是否真的搭好了"
#  用法：bash check_env.sh            （只做检查）
#        bash check_env.sh --fix      （尝试给出修复提示，不代替学生动手）
#
#  设计原则：
#    - 只做「可客观判定」的检查，主观项（踩坑记录质量）由答辩打分
#    - 每一项给出 PASS/FAIL/WARN 与可复现的证据
#    - 允许现场修复：学生可以边改边重跑，直到全绿
# =============================================================================

set -u

FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

PASS=0
FAIL=0
WARN=0

c_ok()   { printf '\033[32m[PASS]\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
c_bad()  { printf '\033[31m[FAIL]\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
c_warn() { printf '\033[33m[WARN]\033[0m %s\n' "$1"; WARN=$((WARN+1)); }
c_info() { printf '       %s\n' "$1"; }

hint() {
    [ "$FIX" = "1" ] && printf '\033[36m  -> 提示: %s\033[0m\n' "$1"
    return 0
}

echo "=============================================================="
echo "  M0-1 开发环境验收  ($(date '+%F %T'))"
echo "=============================================================="

# ---------------------------------------------------------------- 1. 操作系统
echo
echo "--- 1. 操作系统 ---"
if [ -r /etc/os-release ]; then
    . /etc/os-release
    c_info "发行版: ${PRETTY_NAME:-unknown}"
    if echo "${VERSION_ID:-}" | grep -q '^22\.04'; then
        c_ok "Ubuntu 22.04"
    else
        c_warn "非 22.04（版本 ${VERSION_ID:-未知}）—— 需在 README 说明为何可用"
        hint "ROS2 Humble 官方支持 22.04，其他版本请说明兼容性做法"
    fi
else
    c_bad "无法读取 /etc/os-release"
fi

# ------------------------------------------------------------ 2. 虚拟化/环境
echo
echo "--- 2. 运行形态（物理机 / WSL2 / 虚拟机 三选一） ---"
if grep -qi microsoft /proc/version 2>/dev/null; then
    c_ok "运行在 WSL2"
    c_info "$(grep -i microsoft /proc/version | head -1)"
elif systemd-detect-virt >/dev/null 2>&1 && [ "$(systemd-detect-virt)" != "none" ]; then
    c_ok "运行在虚拟机: $(systemd-detect-virt)"
else
    c_ok "运行在物理机"
fi

# ------------------------------------------------------------------ 3. 内核/架构
echo
echo "--- 3. 系统信息 ---"
c_info "内核: $(uname -r)"
c_info "架构: $(uname -m)"

# -------------------------------------------------------------------- 4. shell
echo
echo "--- 4. Shell 与基础工具 ---"
for t in bash git gcc g++ make cmake; do
    if command -v "$t" >/dev/null 2>&1; then
        c_ok "$t -> $(command -v "$t")"
    else
        c_bad "缺少 $t"
        hint "sudo apt install -y build-essential cmake git"
    fi
done

# ------------------------------------------------------------------- 5. Python
echo
echo "--- 5. Python 环境 ---"
if command -v python3 >/dev/null 2>&1; then
    PYV="$(python3 --version 2>&1)"
    c_ok "python3: $PYV ($(command -v python3))"
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
        c_ok "Python 版本 >= 3.10"
    else
        c_bad "Python 版本过低（ROS2 Humble 需 >= 3.10）"
    fi
    # pip
    if python3 -m pip --version >/dev/null 2>&1; then
        c_ok "pip 可用: $(python3 -m pip --version 2>&1 | cut -d' ' -f1-2)"
    else
        c_bad "pip 不可用"
        hint "sudo apt install -y python3-pip"
    fi
    # 虚拟环境
    echo
    echo "--- 6. Python 虚拟环境 (uv 或 conda) ---"
    if command -v uv >/dev/null 2>&1; then
        c_ok "uv: $(uv --version 2>&1)"
    elif command -v conda >/dev/null 2>&1; then
        c_ok "conda: $(conda --version 2>&1)"
    else
        c_bad "未发现 uv 或 conda"
        hint "uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        hint "conda: 参考 https://www.anaconda.com/docs/getting-started/main"
    fi
    # 是否真的在虚拟环境里
    if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_PREFIX:-}" ]; then
        c_ok "当前处于虚拟环境: ${VIRTUAL_ENV:-$CONDA_PREFIX}"
    else
        c_warn "当前 shell 未激活虚拟环境（M0-4 要求使用虚拟环境）"
        hint "uv venv && source .venv/bin/activate   或   conda activate <env>"
    fi
else
    c_bad "未安装 python3"
fi

# ----------------------------------------------------------------------- 7. ROS
echo
echo "--- 7. ROS2 Humble ---"
if [ -f /opt/ros/humble/setup.bash ]; then
    c_ok "发现 /opt/ros/humble/setup.bash"
    # 在子 shell 中 source，避免污染当前环境
    if bash -c 'set +u; source /opt/ros/humble/setup.bash >/dev/null 2>&1; command -v ros2 >/dev/null' ; then
        c_ok "source 后 ros2 命令可用"
        ROSD="$(bash -c 'set +u; source /opt/ros/humble/setup.bash >/dev/null 2>&1; ros2 --version 2>/dev/null || echo unknown')"
        c_info "ros2: ${ROSD:-unknown}"
    else
        c_bad "source 后 ros2 仍不可用（安装不完整）"
        hint "参考 https://docs.ros.org/en/humble/ 或 https://fishros.org.cn/forum/"
    fi
    # 是否写进 shell 配置
    if grep -qs 'ros/humble/setup.bash' "$HOME/.bashrc" "$HOME/.zshrc" 2>/dev/null; then
        c_ok "已将 ROS 环境写入 shell 配置"
    else
        c_warn "未在 ~/.bashrc 中 source ROS 环境"
        hint "echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc"
    fi
else
    c_bad "未安装 ROS2 Humble（找不到 /opt/ros/humble）"
    hint "参考 https://docs.ros.org/en/humble/Installation.html"
fi

# ------------------------------------------------------------------------ 8. Git
echo
echo "--- 8. Git 配置 ---"
if command -v git >/dev/null 2>&1; then
    GNAME="$(git config --global user.name 2>/dev/null || true)"
    GMAIL="$(git config --global user.email 2>/dev/null || true)"
    [ -n "$GNAME" ]  && c_ok "user.name = $GNAME"   || { c_bad "未配置 user.name";  hint 'git config --global user.name "你的名字"'; }
    [ -n "$GMAIL" ] && c_ok "user.email = $GMAIL"  || { c_bad "未配置 user.email"; hint 'git config --global user.email "you@example.com"'; }
    if [ -n "$GNAME" ] && [ -n "$GMAIL" ]; then
        c_info "最近一次提交签名: $(git log -1 --format='%an <%ae>' 2>/dev/null || echo '无仓库')"
    fi
fi

# ----------------------------------------------------------------------- 9. 编辑器
echo
echo "--- 9. VS Code ---"
if command -v code >/dev/null 2>&1; then
    c_ok "code: $(code --version 2>/dev/null | head -1)"
    EXTS="$(code --list-extensions 2>/dev/null || true)"
    if [ -n "$EXTS" ]; then
        for e in ms-python.python ms-vscode.cpptools ms-vscode-remote.remote-wsl ms-vscode-remote.remote-ssh; do
            if echo "$EXTS" | grep -qi "^${e}$"; then
                c_ok "插件已装: $e"
            else
                c_warn "缺少插件: $e"
                hint "code --install-extension $e"
            fi
        done
    else
        c_warn "无法列出插件（headless 环境属正常）"
    fi
else
    c_bad "未发现 code 命令"
    hint "VS Code 安装后在命令面板执行 'Shell Command: Install code command'"
fi

# ------------------------------------------------------------------ 10. 远程登录
echo
echo "--- 10. 远程登录能力 ---"
for t in ssh scp ssh-keygen rsync; do
    if command -v "$t" >/dev/null 2>&1; then
        c_ok "$t 可用"
    else
        c_bad "缺少 $t"
        hint "sudo apt install -y openssh-client rsync"
    fi
done
if [ -f "$HOME/.ssh/id_ed25519.pub" ] || [ -f "$HOME/.ssh/id_rsa.pub" ]; then
    c_ok "已生成 SSH 公钥"
else
    c_warn "未发现 SSH 公钥"
    hint "ssh-keygen -t ed25519 -C 'you@example.com'"
fi
# 是否有已知主机记录（证明真的连过远程机器）
if [ -s "$HOME/.ssh/known_hosts" ]; then
    c_ok "~/.ssh/known_hosts 非空（有连接过远程主机的痕迹）"
else
    c_warn "known_hosts 为空：现场需要实际登录一次开发板/服务器"
fi

# ------------------------------------------------------------------ 11. 目录规范
echo
echo "--- 11. 仓库结构 ---"
REPO="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO" ]; then
    # 退化为逐级向上查找（应对在仓库外运行脚本的情况）
    d="$PWD"
    while [ "$d" != "/" ]; do
        if [ -d "$d/.git" ]; then REPO="$d"; break; fi
        d="$(dirname "$d")"
    done
fi
if [ -n "$REPO" ]; then
    c_ok "发现 git 仓库: $REPO"
    NCOMMIT="$(git -C "$REPO" rev-list --count HEAD 2>/dev/null || echo 0)"
    c_info "提交总数: $NCOMMIT"
    if [ "$NCOMMIT" -ge 3 ] 2>/dev/null; then
        c_ok "提交次数 >= 3（满足多次提交要求）"
    else
        c_warn "提交次数偏少（$NCOMMIT）—— 铁律要求多次有意义的提交"
    fi
    # 是否按模块分目录
    FOUND=0
    for m in M0 M1 M2 M3 M4 M5 M6 m0 m1 m2 m3 m4 m5 m6; do
        [ -d "$REPO/$m" ] && FOUND=$((FOUND+1))
    done
    if [ "$FOUND" -gt 0 ]; then
        c_ok "存在按模块划分的目录（$FOUND 个）"
    else
        c_warn "未发现 M0/M1/... 形式的模块目录"
        hint "建议结构: M0/M0-1/ M0/M0-2/ ... 每题目录内含 README + 代码 + 记录"
    fi
else
    c_bad "当前目录不在 git 仓库中"
fi

# -------------------------------------------------------------------- 汇总
echo
echo "=============================================================="
printf '  汇总: \033[32mPASS=%d\033[0m  \033[31mFAIL=%d\033[0m  \033[33mWARN=%d\033[0m\n' "$PASS" "$FAIL" "$WARN"
echo "=============================================================="
if [ "$FAIL" -eq 0 ]; then
    echo "  环境验收: 通过（WARN 项请现场向考官说明）"
    echo "  下一步: 登录开发板完成 M0-2"
    exit 0
else
    echo "  环境验收: 未通过 —— 请修复 FAIL 项后重新运行本脚本"
    echo "  允许现场修复，直到本脚本全绿。"
    exit 1
fi
