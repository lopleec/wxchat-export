# wxchat-export

`wxchat-export` 是一个本地命令行微信聊天记录导出工具。

它的目标很单纯：在你自己的机器上，把微信本地加密数据库里的聊天记录导出成可读的 `Markdown` 和便于后续处理的 `JSONL`。

当前版本是纯文本 MVP，优先保证这条主链路可用：

`账号发现 -> 获取数据库 key -> 读取加密数据库 -> 解析会话/消息 -> 导出`

## 当前支持

### 完整支持

- macOS arm64
- Linux x86_64
- 微信 4.1.5
- 自动抓取数据库 key
- 基于 Mach-O / ELF 静态扫描 + `lldb` / `gdb` 断点抓取数据库 key
- 会话列表导出
- 文本消息导出
- 系统消息导出
- 常见媒体/卡片消息占位文案
- `Markdown` / `JSONL` 双格式输出

### 部分支持

- Windows
- 已知数据库 key 时的离线解析与导出
- 自定义微信数据目录和可执行文件路径

Windows 当前仍然不支持自动抓 key；如果你已经拿到 `64` 位十六进制数据库 key，仍然可以用这个 CLI 做账号发现、会话读取和导出。

## 当前不支持

- 朋友圈
- 图片、语音、视频正文解密
- GUI
- 非文本富媒体还原

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/wxchat-export
./scripts/bootstrap.sh
```

如果你想走纯 Python 方式，或当前环境没有 bash，也可以：

```bash
python scripts/bootstrap.py
```

这一步会：

- 如缺失则尝试自动安装 `sqlcipher`
- 创建本地虚拟环境 `.venv`
- 以 editable 模式安装 `wxchat-export`

如果不是 macOS，脚本会优先尝试复用系统里已有的 `sqlcipher`；没找到时会提示你用系统包管理器手动安装。

Linux 如果要自动抓 key，还需要额外安装 `gdb`。

常见 Linux 依赖安装示例：

```bash
# Ubuntu / Debian
sudo apt install sqlcipher gdb

# Fedora
sudo dnf install sqlcipher gdb

# Arch Linux
sudo pacman -S sqlcipher gdb
```

### 2. 激活环境

```bash
source .venv/bin/activate
```

Windows PowerShell 可以用：

```powershell
.venv\Scripts\Activate.ps1
```

### 3. 保持微信运行

自动抓数据库 key 的前提是：

- 微信已经启动
- 目标账号已经登录

### 4. 运行体检

```bash
wxchat-export doctor
```

正常情况下会检查：

- WeChat binary
- WeChat data root
- Accounts discovered
- sqlcipher
- WeChat PID
- 平台相关调试器与权限检查
- Hook candidate address
- 调试附加权限

其中：

- macOS 会检查 `lldb`、`DevToolsSecurity`、`_developer` group、`SIP`、`hardened runtime`
- Linux 会检查 `gdb`、`ptrace_scope`、Hook VA 和 `gdb attach`
- Windows 目前仍以手动 `--db-key` 为主

### Linux 快速路径

如果你是在 Linux 上使用，推荐先按这个顺序做：

1. 安装 `sqlcipher` 和 `gdb`
2. 保持微信进程正在运行
3. 运行 `wxchat-export doctor`
4. 如果 `doctor` 通过，再运行 `sessions` 或 `export`

一个最短示例：

```bash
source .venv/bin/activate
wxchat-export doctor
wxchat-export accounts
wxchat-export sessions --account <account_id>
wxchat-export export --account <account_id> --session all --out ./out
```

Linux 下当前实现优先尝试这些默认位置：

- 微信二进制：`wechat`、`wechat-uos`、`weixin`、`/usr/bin/wechat`、`/opt/wechat/wechat`
- 数据目录：`~/.xwechat/xwechat_files`、`~/.xwechat`、`~/.local/share/xwechat_files`

如果你的安装路径不同，请显式传：

```bash
wxchat-export doctor \
  --root /path/to/xwechat_files \
  --wechat-binary /path/to/wechat
```

## 基本用法

### 列出账号

```bash
wxchat-export accounts
```

输出示例：

```text
wxid_xxx_1234    wxid_xxx    /path/to/xwechat_files/wxid_xxx_1234
```

第一列就是后续命令需要的 `account_id`。

### 列出会话

```bash
wxchat-export sessions --account wxid_xxx_1234
```

### 导出单个会话

```bash
wxchat-export export \
  --account wxid_xxx_1234 \
  --session friend_username \
  --out ./out
```

### 导出全部会话

```bash
wxchat-export export \
  --account wxid_xxx_1234 \
  --session all \
  --out ./out
```

### 指定导出格式

```bash
wxchat-export export \
  --account wxid_xxx_1234 \
  --session all \
  --out ./out \
  --format both
```

可选值：

- `md`
- `jsonl`
- `both`

### 已知 key 时手动指定

如果你已经拿到数据库 key，可以绕过自动抓取：

```bash
wxchat-export export \
  --account wxid_xxx_1234 \
  --session all \
  --out ./out \
  --db-key <64位hex>
```

### 自定义路径

如果你的微信安装目录或数据目录不在默认位置，可以显式传参：

```bash
wxchat-export doctor \
  --root /path/to/xwechat_files \
  --wechat-binary /path/to/WeChat
```

其他命令也支持同样的参数：

- `accounts --root ...`
- `sessions --root ... --wechat-binary ...`
- `export --root ... --wechat-binary ...`

### 环境变量覆盖

也可以用环境变量长期覆盖默认路径：

```bash
export WXCHAT_EXPORT_DATA_ROOT=/path/to/xwechat_files
export WXCHAT_EXPORT_WECHAT_BINARY=/path/to/WeChat
export WXCHAT_EXPORT_SQLCIPHER=/path/to/sqlcipher
export WXCHAT_EXPORT_LLDB=/path/to/lldb
export WXCHAT_EXPORT_GDB=/path/to/gdb
```

## 输出结构

```text
<out>/
├── manifest.json
└── sessions/
    ├── <display_name>__<username>.md
    └── <display_name>__<username>.jsonl
```

- `manifest.json`：本次导出的索引
- `*.md`：适合直接阅读
- `*.jsonl`：适合后续程序处理

Markdown 中每条消息大致是：

```text
[2026-04-17 12:34:56] 张三: 你好
```

## 命令总览

```bash
wxchat-export doctor
wxchat-export accounts
wxchat-export sessions --account <account_id> [--db-key <64位hex>]
wxchat-export export --account <account_id> --session <username|all> --out <dir> [--db-key <64位hex>]
```

## 依赖与限制

### `sqlcipher`

本项目不使用 Python 的 SQLCipher 绑定，而是直接调用系统里的 `sqlcipher` CLI。

如果命令不存在，重新运行：

```bash
./scripts/bootstrap.sh
```

### 微信必须运行

如果提示：

```text
[error] WeChat process not running
```

先打开微信并保持登录。

### 关于自动抓 key

当前默认方案在 macOS 和 Linux 上都已实现：

- macOS：依赖 `lldb` 附加到微信进程
- Linux：依赖 `gdb` / `ptrace` 附加到微信进程

这意味着它会受到以下因素影响：

- macOS：
  - 开发者工具权限
  - 完全磁盘访问权限
  - `DevToolsSecurity`
  - SIP / AMFI / Hardened Runtime
- Linux：
  - `gdb` 是否安装
  - `ptrace_scope`
  - 是否具备 `CAP_SYS_PTRACE` / root 权限

如果你看到：

```text
[error] LLDB attach permission: AMFI denied task_for_pid: target is release-signed / hardened ...
```

说明这不是普通权限勾选问题，而是当前 macOS 的系统策略拒绝了调试附加。

现在 `doctor` 会把几个关键前置条件单独打印出来，方便你先判断是哪一层出了问题：

- macOS：
  - `DevToolsSecurity`
  - `_developer` group
  - `SIP`
  - `WeChat hardened runtime`
  - `WeChat get-task-allow`
- Linux：
  - `gdb`
  - `ptrace_scope`
  - `GDB attach permission`

常见组合可以这样理解：

- `DevToolsSecurity: disabled`
  先执行 `sudo DevToolsSecurity -enable`
- `_developer group: current user is not in _developer`
  当前用户缺少常见调试组
- `SIP: enabled` 且 `LLDB attach permission` 仍然是 `AMFI denied ...`
  在部分环境里这通常意味着需要关闭 SIP，或者放弃 `lldb attach` 方案
- `WeChat hardened runtime: enabled` 且 `WeChat get-task-allow: absent`
  目标二进制本身就是 release / hardened 形态，运行时附加更容易被 AMFI 拒绝
- Linux 下 `ptrace_scope: 1` 或 `ptrace_scope: 2`
  这通常意味着当前用户不能直接调试附加其他进程，可能需要 root、`CAP_SYS_PTRACE`，或临时放宽 `ptrace_scope`
- Linux 下 `gdb not found in PATH`
  先安装 `gdb`，或者用 `WXCHAT_EXPORT_GDB` 指向自定义路径

这类情况下，自动抓 key 可能不可用。可行做法通常只有：

- 使用 `--db-key <64位hex>` 手动提供数据库 key
- 改用不依赖调试附加的其他取 key 方案

### Windows / Linux 怎么用

Windows 目前的定位仍然是“手动 key 模式”：

1. 自己拿到数据库 key
2. 用 `--db-key` 运行 `sessions` 或 `export`
3. 必要时用 `--root` / `--wechat-binary` 指向实际安装位置

例如：

```bash
wxchat-export export \
  --account wxid_xxx_1234 \
  --session all \
  --out ./out \
  --db-key <64位hex> \
  --root /path/to/xwechat_files
```

Linux 则优先建议直接先跑：

```bash
wxchat-export doctor
```

如果 `doctor` 显示：

- `[ok] gdb: ...`
- `[ok]` 或 `[warn] ptrace_scope: ...`
- `[ok] GDB attach permission: ok`

那就可以直接不带 `--db-key` 使用 `sessions` 和 `export`。

如果 Linux 上 `doctor` 失败，最常见的排查顺序是：

1. 先确认微信进程真的在运行
2. 再确认 `gdb` 已安装
3. 看 `ptrace_scope`
4. 必要时用 `sudo` 再跑一次 `doctor`
5. 仍然失败时先改用 `--db-key`

### 关于 SIP

不同机器、不同 macOS 版本、不同微信构建之间，`lldb attach` 的可行性并不完全一致。

如果你的环境里 WeFlow 或其他工具可以工作，而当前环境不行，最常见原因不是挂点扫描错了，而是系统层的调试策略不同。

## 项目清理

发布前可执行：

```bash
./scripts/clean.sh
```

它会清理：

- `__pycache__`
- `*.pyc`
- `*.egg-info`
- 常见 Python 缓存目录

`.gitignore` 已经排除了 `.venv/`、缓存目录和导出产物。

## 鸣谢

本项目在数据库 key 挂点定位和调试附加抓取这部分，参考了 WeFlow 公开文档中披露的原理说明与研究思路。

感谢 WeFlow 项目公开分享相关原理。

当前仓库是一个独立的 Python CLI / clean-room 实现，代码结构、CLI 设计和导出链路均为单独实现，与 WeFlow 官方项目没有从属关系。
