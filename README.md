# pvault - 命令行密码保险箱

本地加密存储密码的 Python CLI 工具。使用 SQLite + Fernet 对称加密，密码和备注在数据库中始终以密文形式保存。

---

## 功能特性

- 🔐 **端到端加密**：密码和备注使用 PBKDF2 + Fernet (AES-128-CBC + HMAC-SHA256) 加密存储
- 🚫 **默认脱敏**：列表/搜索默认隐藏明文密码，仅在指定 `--show-password` 时显示
- 🤖 **非交互模式**：支持命令行参数和环境变量，便于自动化脚本集成
- ❌ **完善错误处理**：未初始化、主密码错误、记录不存在等场景均有清晰提示和非零退出码
- 🔍 **搜索功能**：按站点或用户名关键词模糊搜索
- 💾 **SQLite 存储**：数据保存在 `~/.pvault/vault.db`，密码和备注从不明文入库

---

## 目录结构

```
gsb-0012/
├── pvault.py          # 主程序
├── requirements.txt   # 依赖清单
├── test_pvault.py     # 自动化验证脚本
└── README.md          # 本文档
```

---

## 1. 环境要求与依赖安装

- Python 3.8+
- cryptography >= 41.0.0, < 45.0.0

```bash
# 进入项目目录
cd gsb-0012

# 安装依赖
pip install -r requirements.txt
```

验证依赖安装成功：

```bash
python -c "import cryptography; print('cryptography', cryptography.__version__)"
```

---

## 2. 快速上手（交互式）

### 2.1 初始化保险箱

首次使用必须先初始化，设置主密码。主密码用于派生加密密钥，**忘记无法找回**。

```bash
python pvault.py init
```

交互提示：
```
设置主密码: ********
确认主密码: ********
[成功] 保险箱初始化完成。
```

> 💡 初始化后会在 `~/.pvault/` 下生成三个文件：
> - `salt.bin` - PBKDF2 盐值（16 字节随机）
> - `.master_hash` - 主密码 SHA-256 哈希（用于验证）
> - `vault.db` - SQLite 数据库（存储加密后的条目）

### 2.2 添加密码条目

```bash
python pvault.py add
```

交互提示：
```
主密码: ********
站点: github.com
用户名: alice
密码: ********
备注 (可留空): 开发账号
[成功] 已添加条目: github.com
```

### 2.3 列出所有条目（默认脱敏）

```bash
python pvault.py list
```

输出示例（密码和备注已脱敏）：
```
主密码: ********
ID    站点                 用户名                 密码                   备注                   创建时间
---------------------------------------------------------------------------------------------------------
1     github.com           alice                G******!              开******号             2025-06-20 10:00:00
```

### 2.4 显示明文密码

显式传入 `--show-password` 才会显示明文：

```bash
python pvault.py list --show-password
```

### 2.5 搜索条目

按站点或用户名关键词搜索：

```bash
python pvault.py search github
```

搜索时也支持 `--show-password`：

```bash
python pvault.py search github --show-password
```

### 2.6 修改条目

按 ID 修改，回车可保留原值：

```bash
python pvault.py modify 1
```

### 2.7 删除条目

```bash
python pvault.py delete 1
```

会提示确认，输入 `y` 后删除。

---

## 3. 非交互模式（自动化/脚本集成）

所有需要交互输入的字段都支持通过**命令行参数**或**环境变量**传入，优先级：命令行参数 > 环境变量 > 交互提示。

### 支持的环境变量

| 环境变量 | 对应字段 | 适用命令 |
|---|---|---|
| `PVAULT_MASTER_PASSWORD` | 主密码 | 所有命令（除 init 外必须） |
| `PVAULT_SITE` | 站点 | add, modify |
| `PVAULT_USERNAME` | 用户名 | add, modify |
| `PVAULT_PASSWORD` | 密码 | add, modify |
| `PVAULT_NOTES` | 备注 | add, modify |
| `PVAULT_FORCE` | 强制不确认 | delete（设为 `1` 时跳过确认） |

### 3.1 非交互初始化

```bash
# 使用命令行参数
python pvault.py init --master-password "MyMasterPass123!"

# 或使用环境变量
export PVAULT_MASTER_PASSWORD="MyMasterPass123!"
python pvault.py init
```

### 3.2 非交互添加

```bash
# 全部通过命令行参数
python pvault.py add \
  --master-password "MyMasterPass123!" \
  --site "gitlab.com" \
  --username "bob" \
  --password "GitlabPass@456" \
  --notes "工作账号-管理员"

# 全部通过环境变量
export PVAULT_MASTER_PASSWORD="MyMasterPass123!"
export PVAULT_SITE="gitlab.com"
export PVAULT_USERNAME="bob"
export PVAULT_PASSWORD="GitlabPass@456"
export PVAULT_NOTES="工作账号-管理员"
python pvault.py add
```

### 3.3 非交互修改

```bash
# 修改 ID=1 的站点和密码，其余字段保留原值
python pvault.py modify 1 \
  --master-password "MyMasterPass123!" \
  --site "github-new.com" \
  --password "NewPass789$"
```

### 3.4 非交互删除（跳过确认）

```bash
# 使用 --force 参数
python pvault.py delete 1 --master-password "MyMasterPass123!" --force

# 或使用环境变量
export PVAULT_FORCE=1
python pvault.py delete 1 --master-password "MyMasterPass123!"
```

---

## 4. 退出码说明

| 退出码 | 含义 | 常量名 |
|---|---|---|
| 0 | 成功 | `EXIT_OK` |
| 1 | 通用错误（重复初始化、解密失败等） | `EXIT_ERROR` |
| 2 | 依赖缺失（cryptography 未安装） | `EXIT_DEP_MISSING` |
| 3 | 保险箱未初始化 | `EXIT_NOT_INIT` |
| 4 | 主密码错误 | `EXIT_WRONG_MASTER` |
| 5 | 记录不存在 / 搜索无结果 | `EXIT_NOT_FOUND` |
| 6 | 参数无效（空主密码、空必填字段等） | `EXIT_INVALID_ARGS` |

在 shell 脚本中判断：

```bash
python pvault.py list --master-password "wrong"
if [ $? -eq 4 ]; then
  echo "主密码错误！"
fi
```

---

## 5. 加密安全说明

### 5.1 密钥派生流程

```
主密码 (用户输入)
    │
    ▼  PBKDF2-HMAC-SHA256
盐值 (16 字节随机, 480,000 次迭代)
    │
    ▼  base64 urlsafe 编码
32 字节 Fernet 密钥
    │
    ▼  AES-128-CBC + HMAC-SHA256
每条记录的密码和备注独立加密
```

### 5.2 数据库字段（vault.db → entries 表）

| 字段 | 是否加密 | 说明 |
|---|---|---|
| `id` | 否 | 自增主键 |
| `site` | 否 | 站点名称（明文，便于搜索） |
| `username` | 否 | 用户名（明文，便于搜索） |
| `password_enc` | **是** | Fernet 加密后的密码密文 |
| `notes_enc` | **是** | Fernet 加密后的备注明文 |
| `created_at` | 否 | 创建时间戳 |
| `updated_at` | 否 | 更新时间戳 |

### 5.3 验证数据库无明文

运行以下命令直接检查数据库文件，确认不包含任何明文密码或备注：

```bash
# 先添加一条测试数据
export PVAULT_MASTER_PASSWORD="Test123!"
python pvault.py init
python pvault.py add --site "test.com" --username "user1" --password "MySecretPass!2024" --notes "私密备注内容"

# 方法1：用 Python 直接查询数据库字段
python -c "
import sqlite3
conn = sqlite3.connect('$HOME/.pvault/vault.db')
rows = conn.execute('SELECT password_enc, notes_enc FROM entries').fetchall()
for p, n in rows:
    print('password_enc:', p[:40] + '...')
    print('notes_enc:', n[:40] + '...')
    assert 'MySecretPass' not in p, '密码明文泄露！'
    assert '私密备注' not in n, '备注明文泄露！'
print('✅ 数据库字段不包含明文！')
"

# 方法2：直接 grep 数据库二进制文件
strings ~/.pvault/vault.db | grep -E "MySecretPass|私密备注" || echo "✅ 数据库二进制中未找到明文关键词"
```

---

## 6. 完整自动化验证流程

项目提供 `test_pvault.py` 自动化验证脚本，覆盖全部核心流程。

### 6.1 运行完整验证

```bash
cd gsb-0012
python test_pvault.py
```

### 6.2 验证内容清单

脚本包含 12 个测试用例：

| # | 测试名称 | 验证内容 |
|---|---|---|
| 1 | 未初始化错误 | 5 个命令在未初始化时均报错并返回非零 |
| 2 | 初始化 | 创建所有必要文件，阻止重复初始化 |
| 3 | 主密码错误 | 错误密码返回退出码 4 并提示 |
| 4 | 添加条目 | 通过环境变量添加两条记录 |
| 5 | 列表默认脱敏 | 列表中不出现明文密码和备注 |
| 6 | --show-password | 显式参数后正确显示明文 |
| 7 | 搜索功能 | 关键词过滤、无结果提示、--show-password |
| 8 | 修改条目 | 非交互修改、ID 不存在提示 |
| 9 | 删除条目 | 强制删除、ID 不存在提示 |
| 10 | 数据库无明文 | SQL 查询和二进制扫描均无明文 |
| 11 | 参数优先级 | CLI 参数覆盖环境变量 |
| 12 | 空保险箱提示 | 空列表正确提示 |

### 6.3 手动逐步验证（复制即可执行）

以下命令序列在 **PowerShell** 中可直接复制执行（使用独立测试主密码，避免污染现有数据）：

```powershell
# 0. 清理旧数据（警告：删除现有保险箱！）
Remove-Item -Recurse -Force "$env:USERPROFILE\.pvault" -ErrorAction SilentlyContinue

# 1. 安装依赖
pip install -r requirements.txt

# 2. 未初始化时应报错
python pvault.py list
echo "退出码: $LASTEXITCODE"    # 应为 3 (EXIT_NOT_INIT)

# 3. 初始化
$env:PVAULT_MASTER_PASSWORD = "TestMaster123!"
python pvault.py init
echo "退出码: $LASTEXITCODE"    # 应为 0

# 4. 主密码错误测试
$env:PVAULT_MASTER_PASSWORD = "WrongPassword"
python pvault.py list
echo "退出码: $LASTEXITCODE"    # 应为 4 (EXIT_WRONG_MASTER)
$env:PVAULT_MASTER_PASSWORD = "TestMaster123!"

# 5. 添加条目（使用环境变量）
$env:PVAULT_SITE = "github.com"
$env:PVAULT_USERNAME = "alice_dev"
$env:PVAULT_PASSWORD = "GithubAlice!2024"
$env:PVAULT_NOTES = "个人开发账号 - 2FA已启用"
python pvault.py add

$env:PVAULT_SITE = "gitlab.com"
$env:PVAULT_USERNAME = "bob_ops"
$env:PVAULT_PASSWORD = "GitlabBob@Ops2024"
$env:PVAULT_NOTES = "运维团队共享账号"
python pvault.py add

Remove-Item Env:PVAULT_SITE, Env:PVAULT_USERNAME, Env:PVAULT_PASSWORD, Env:PVAULT_NOTES

# 6. 列表（默认脱敏 - 不应出现明文密码）
python pvault.py list
echo "退出码: $LASTEXITCODE"    # 应为 0

# 7. 列表 --show-password（显示明文）
python pvault.py list --show-password

# 8. 搜索
python pvault.py search alice
python pvault.py search alice --show-password
python pvault.py search nonexistent_xyz
echo "退出码: $LASTEXITCODE"    # 应为 5 (EXIT_NOT_FOUND)

# 9. 修改（修改 ID=1 的密码和备注）
$env:PVAULT_PASSWORD = "UpdatedAlice!2025"
$env:PVAULT_NOTES = "已更新 - 密码于2025年轮换"
python pvault.py modify 1
Remove-Item Env:PVAULT_PASSWORD, Env:PVAULT_NOTES
python pvault.py list --show-password

# 10. 删除 ID=2（强制跳过确认）
$env:PVAULT_FORCE = "1"
python pvault.py delete 2
Remove-Item Env:PVAULT_FORCE
python pvault.py list --show-password

# 11. 删除不存在的 ID
python pvault.py delete 9999 --force
echo "退出码: $LASTEXITCODE"    # 应为 5 (EXIT_NOT_FOUND)

# 12. 验证数据库中无明文
python -c "
import sqlite3, os
db = os.path.expanduser('~/.pvault/vault.db')
conn = sqlite3.connect(db)
rows = conn.execute('SELECT password_enc, notes_enc FROM entries').fetchall()
all_text = ' '.join([p + n for p,n in rows])
secrets = ['GithubAlice!2024', 'UpdatedAlice!2025', '个人开发账号', '已更新']
for s in secrets:
    assert s not in all_text, f'泄露: {s}'
with open(db, 'rb') as f:
    raw = f.read()
for s in secrets:
    assert s.encode('utf-8') not in raw, f'二进制泄露: {s}'
print('✅ 数据库安全验证通过 - 无明文密码/备注')
"

# 13. 清理测试数据
Remove-Item -Recurse -Force "$env:USERPROFILE\.pvault"
Remove-Item Env:PVAULT_MASTER_PASSWORD
Write-Host "✅ 所有手动验证步骤完成！"
```

对于 **Linux/macOS (Bash/Zsh)**，使用以下等价命令序列：

```bash
# 0. 清理
rm -rf ~/.pvault

# 1. 安装
pip install -r requirements.txt

# 2. 未初始化报错
python pvault.py list; echo "退出码: $?"   # 应为 3

# 3. 初始化
export PVAULT_MASTER_PASSWORD="TestMaster123!"
python pvault.py init; echo "退出码: $?"   # 应为 0

# 4. 主密码错误
PVAULT_MASTER_PASSWORD="Wrong" python pvault.py list; echo "退出码: $?"   # 应为 4

# 5. 添加条目
PVAULT_SITE="github.com" PVAULT_USERNAME="alice_dev" \
PVAULT_PASSWORD="GithubAlice!2024" PVAULT_NOTES="个人开发账号" \
python pvault.py add

PVAULT_SITE="gitlab.com" PVAULT_USERNAME="bob_ops" \
PVAULT_PASSWORD="GitlabBob@Ops2024" PVAULT_NOTES="运维团队共享账号" \
python pvault.py add

# 6~13. 其余步骤与 PowerShell 类似，参考 test_pvault.py
# 直接运行自动化脚本即可：
python test_pvault.py
```

---

## 7. 常见问题

### Q: 忘记主密码怎么办？
A: 无法找回。密钥由主密码派生，删除 `~/.pvault/` 目录重新初始化是唯一选择。

### Q: 如何迁移到另一台机器？
A: 复制整个 `~/.pvault/` 目录，在新机器上使用相同主密码即可。

### Q: 可以修改主密码吗？
A: 当前版本暂不支持，需要手动解密+重加密所有条目。

### Q: 数据库文件损坏怎么办？
A: 请定期备份 `~/.pvault/` 目录，特别是 `vault.db` 和 `salt.bin`。

---

## 8. 命令速查

```bash
# 帮助
python pvault.py --help
python pvault.py add --help

# 核心命令
python pvault.py init                                  # 初始化
python pvault.py add                                   # 添加
python pvault.py list                                  # 列表（脱敏）
python pvault.py list --show-password                  # 列表（明文）
python pvault.py search <关键词>                        # 搜索（脱敏）
python pvault.py search <关键词> --show-password        # 搜索（明文）
python pvault.py modify <ID>                           # 修改
python pvault.py delete <ID>                           # 删除
python pvault.py delete <ID> --force                   # 强制删除（不确认）
```
