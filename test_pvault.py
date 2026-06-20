#!/usr/bin/env python3

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile


MASTER_PASSWORD = "TestMaster123!"
VAULT_DIR = os.path.join(os.path.expanduser("~"), ".pvault")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PVAULT_PY = os.path.join(PROJECT_DIR, "pvault.py")


def run_pvault(args, env_extra=None, expect_success=None, capture=True):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, PVAULT_PY] + args
    if capture:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    else:
        result = subprocess.run(cmd, env=env, timeout=60)
        return result
    if expect_success is True and result.returncode != 0:
        print(f"[FAIL] 预期成功但失败: {' '.join(args)}")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        raise AssertionError(f"命令失败: {args}")
    if expect_success is False and result.returncode == 0:
        print(f"[FAIL] 预期失败但成功: {' '.join(args)}")
        print(f"  stdout: {result.stdout}")
        raise AssertionError(f"命令意外成功: {args}")
    return result


def clean_vault():
    if os.path.exists(VAULT_DIR):
        import time
        last_err = None
        for attempt in range(10):
            try:
                shutil.rmtree(VAULT_DIR)
                return
            except Exception as e:
                last_err = e
                time.sleep(0.3)
        raise last_err


def banner(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def assert_contains(text, needle, desc):
    if needle not in text:
        raise AssertionError(f"[{desc}] 期望包含 '{needle}', 实际:\n{text}")
    print(f"  [OK] {desc}")


def assert_not_contains(text, needle, desc):
    if needle in text:
        raise AssertionError(f"[{desc}] 不应包含 '{needle}', 实际:\n{text}")
    print(f"  [OK] {desc}")


def assert_regex(text, pattern, desc):
    if not re.search(pattern, text):
        raise AssertionError(f"[{desc}] 期望匹配正则 '{pattern}', 实际:\n{text}")
    print(f"  [OK] {desc}")


def test_01_not_initialized():
    banner("测试1：未初始化时各命令的错误提示")
    clean_vault()

    r = run_pvault(["list"], expect_success=False)
    assert_contains(r.stdout, "未初始化", "list 提示未初始化")
    assert r.returncode != 0, "应有非零退出码"
    print(f"       退出码: {r.returncode}")

    r = run_pvault(["add", "--master-password", MASTER_PASSWORD], expect_success=False)
    assert_contains(r.stdout, "未初始化", "add 提示未初始化")

    r = run_pvault(["search", "test", "--master-password", MASTER_PASSWORD], expect_success=False)
    assert_contains(r.stdout, "未初始化", "search 提示未初始化")

    r = run_pvault(["modify", "1", "--master-password", MASTER_PASSWORD], expect_success=False)
    assert_contains(r.stdout, "未初始化", "modify 提示未初始化")

    r = run_pvault(["delete", "1", "--master-password", MASTER_PASSWORD], expect_success=False)
    assert_contains(r.stdout, "未初始化", "delete 提示未初始化")


def test_02_init():
    banner("测试2：初始化保险箱")
    clean_vault()

    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}
    r = run_pvault(["init"], env_extra=env, expect_success=True)
    assert_contains(r.stdout, "初始化完成", "init 成功提示")
    assert os.path.exists(VAULT_DIR), "~/.pvault 目录应存在"
    assert os.path.exists(os.path.join(VAULT_DIR, "salt.bin")), "salt.bin 应存在"
    assert os.path.exists(os.path.join(VAULT_DIR, ".master_hash")), ".master_hash 应存在"
    assert os.path.exists(os.path.join(VAULT_DIR, "vault.db")), "vault.db 应存在"
    print("  [OK] 所有必要文件已创建")

    r = run_pvault(["init"], env_extra=env, expect_success=False)
    assert_contains(r.stdout, "已存在", "重复 init 提示已存在")
    print("  [OK] 重复初始化被正确阻止")


def test_03_wrong_master_password():
    banner("测试3：主密码错误场景")
    clean_vault()
    run_pvault(["init"], env_extra={"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}, expect_success=True)

    r = run_pvault(["list"], env_extra={"PVAULT_MASTER_PASSWORD": "WrongPass"}, expect_success=False)
    assert_contains(r.stdout, "主密码不正确", "错误主密码提示")
    assert r.returncode != 0, "应有非零退出码"
    print(f"       退出码: {r.returncode}")


def test_04_add_entries():
    banner("测试4：添加密码条目")
    clean_vault()
    run_pvault(["init"], env_extra={"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}, expect_success=True)

    env = {
        "PVAULT_MASTER_PASSWORD": MASTER_PASSWORD,
        "PVAULT_SITE": "github.com",
        "PVAULT_USERNAME": "alice",
        "PVAULT_PASSWORD": "GithubPass123!",
        "PVAULT_NOTES": "开发账号，用于开源项目",
    }
    r = run_pvault(["add"], env_extra=env, expect_success=True)
    assert_contains(r.stdout, "已添加条目: github.com", "add 成功提示")

    env2 = {
        "PVAULT_MASTER_PASSWORD": MASTER_PASSWORD,
        "PVAULT_SITE": "gitlab.com",
        "PVAULT_USERNAME": "bob",
        "PVAULT_PASSWORD": "GitlabPass@456",
        "PVAULT_NOTES": "工作账号",
    }
    r = run_pvault(["add"], env_extra=env2, expect_success=True)
    assert_contains(r.stdout, "已添加条目: gitlab.com", "add 第二条成功")

    print("  [OK] 两条条目均已添加")


def test_05_list_masked():
    banner("测试5：列表默认脱敏展示")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}
    r = run_pvault(["list"], env_extra=env, expect_success=True)
    print("  输出:")
    for line in r.stdout.strip().split("\n"):
        print(f"    {line}")

    assert_contains(r.stdout, "github.com", "列表包含 github.com")
    assert_contains(r.stdout, "gitlab.com", "列表包含 gitlab.com")
    assert_contains(r.stdout, "alice", "列表包含用户名 alice")
    assert_contains(r.stdout, "bob", "列表包含用户名 bob")
    assert_not_contains(r.stdout, "GithubPass123!", "列表不显示明文 Github 密码")
    assert_not_contains(r.stdout, "GitlabPass@456", "列表不显示明文 Gitlab 密码")
    assert_not_contains(r.stdout, "开发账号，用于开源项目", "列表不显示明文备注")

    assert_regex(r.stdout, r"G\*+!", "密码脱敏显示 - 首末位+多星号")
    assert_regex(r.stdout, r"G\*+6", "Gitlab 密码脱敏显示")
    print("  [OK] 默认脱敏展示，无明文密码泄露")


def test_06_list_show_password():
    banner("测试6：--show-password 显示明文密码")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}
    r = run_pvault(["list", "--show-password"], env_extra=env, expect_success=True)
    print("  输出:")
    for line in r.stdout.strip().split("\n"):
        print(f"    {line}")

    assert_contains(r.stdout, "GithubPass123!", "--show-password 显示明文密码1")
    assert_contains(r.stdout, "GitlabPass@456", "--show-password 显示明文密码2")
    assert_contains(r.stdout, "开发账号，用于开源项目", "--show-password 显示明文备注")
    print("  [OK] --show-password 正确显示明文")


def test_07_search():
    banner("测试7：搜索功能")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}

    r = run_pvault(["search", "github"], env_extra=env, expect_success=True)
    assert_contains(r.stdout, "github.com", "搜索 github 命中")
    assert_not_contains(r.stdout, "gitlab.com", "搜索 github 不命中 gitlab")
    assert_not_contains(r.stdout, "GithubPass123!", "搜索默认不显示明文")
    print("  [OK] 搜索关键词过滤正确，默认脱敏")

    r = run_pvault(["search", "alice"], env_extra=env, expect_success=True)
    assert_contains(r.stdout, "alice", "搜索用户名命中")

    r = run_pvault(["search", "nonexistent_xyz"], env_extra=env, expect_success=False)
    assert_contains(r.stdout, "未找到匹配", "搜索不存在关键词提示")
    print("  [OK] 搜索无结果时正确提示")

    r = run_pvault(["search", "github", "--show-password"], env_extra=env, expect_success=True)
    assert_contains(r.stdout, "GithubPass123!", "搜索 --show-password 显示明文")
    print("  [OK] 搜索 --show-password 正常工作")


def test_08_modify_entry():
    banner("测试8：修改条目")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}
    r = run_pvault(["list"], env_extra=env, expect_success=True)
    print("  修改前列表:")
    for line in r.stdout.strip().split("\n"):
        print(f"    {line}")

    modify_env = {
        "PVAULT_MASTER_PASSWORD": MASTER_PASSWORD,
        "PVAULT_SITE": "github-new.com",
        "PVAULT_PASSWORD": "NewGithubPass789$",
        "PVAULT_NOTES": "已更新备注内容",
    }
    r = run_pvault(["modify", "1"], env_extra=modify_env, expect_success=True)
    assert_contains(r.stdout, "已更新条目 ID=1", "modify 成功提示")

    r = run_pvault(["list", "--show-password"], env_extra=env, expect_success=True)
    print("  修改后列表:")
    for line in r.stdout.strip().split("\n"):
        print(f"    {line}")
    assert_contains(r.stdout, "github-new.com", "站点已更新")
    assert_contains(r.stdout, "alice", "用户名未变（未传则保留）")
    assert_contains(r.stdout, "NewGithubPass789$", "密码已更新")
    assert_contains(r.stdout, "已更新备注内容", "备注已更新")

    r = run_pvault(["modify", "9999"], env_extra=env, expect_success=False)
    assert_contains(r.stdout, "未找到 ID=9999", "修改不存在的 ID 报错")
    print("  [OK] 修改功能正常，边界情况处理正确")


def test_09_delete_entry():
    banner("测试9：删除条目")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}

    r = run_pvault(["list"], env_extra=env, expect_success=True)
    initial_count = len([l for l in r.stdout.strip().split("\n") if re.match(r"^\d+\s", l.strip())])
    print(f"  删除前共有 {initial_count} 条记录")

    delete_env = {
        "PVAULT_MASTER_PASSWORD": MASTER_PASSWORD,
        "PVAULT_FORCE": "1",
    }
    r = run_pvault(["delete", "1"], env_extra=delete_env, expect_success=True)
    assert_contains(r.stdout, "已删除条目 ID=1", "delete 成功提示")

    r = run_pvault(["list"], env_extra=env, expect_success=True)
    assert_not_contains(r.stdout, "github-new.com", "删除后站点不再出现")

    r = run_pvault(["delete", "9999"], env_extra=delete_env, expect_success=False)
    assert_contains(r.stdout, "未找到 ID=9999", "删除不存在的 ID 报错")
    print("  [OK] 删除功能正常")


def test_10_database_no_plaintext():
    banner("测试10：数据库中不存储明文密码/备注")
    env = {"PVAULT_MASTER_PASSWORD": MASTER_PASSWORD}

    add_env = {
        "PVAULT_MASTER_PASSWORD": MASTER_PASSWORD,
        "PVAULT_SITE": "testdb.com",
        "PVAULT_USERNAME": "user_db",
        "PVAULT_PASSWORD": "DB_Secret_Pass!2024",
        "PVAULT_NOTES": "这是一条私密备注内容",
    }
    run_pvault(["add"], env_extra=add_env, expect_success=True)

    db_path = os.path.join(VAULT_DIR, "vault.db")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT site, username, password_enc, notes_enc FROM entries").fetchall()
    conn.close()

    print(f"  数据库中共 {len(rows)} 条记录")
    for i, row in enumerate(rows, 1):
        site, username, pwd_enc, notes_enc = row
        print(f"  记录 {i}:")
        print(f"    site (明文): {site}")
        print(f"    username (明文): {username}")
        print(f"    password_enc: {pwd_enc[:40]}... (长度={len(pwd_enc)})")
        print(f"    notes_enc: {notes_enc[:40]}... (长度={len(notes_enc)})")

    conn2 = sqlite3.connect(db_path)
    pwd_enc_check = conn2.execute("SELECT password_enc FROM entries").fetchall()[0][0]
    notes_enc_check = conn2.execute("SELECT notes_enc FROM entries WHERE site='testdb.com'").fetchall()[0][0]
    conn2.close()

    assert "DB_Secret_Pass!2024" not in pwd_enc_check, "密码明文不应在数据库中"
    assert "这是一条私密备注内容" not in notes_enc_check, "备注明文不应在数据库中"

    with open(db_path, "rb") as f:
        db_bytes = f.read()
    assert b"DB_Secret_Pass!2024" not in db_bytes, "数据库二进制内容中不应有明文密码"
    assert "这是一条私密备注内容".encode("utf-8") not in db_bytes, "数据库二进制内容中不应有明备注"

    print("  [OK] 数据库中确实不包含明文密码和备注")


def test_11_cli_args_priority():
    banner("测试11：命令行参数优先级（覆盖环境变量）")
    clean_vault()
    run_pvault(["init", "--master-password", MASTER_PASSWORD], expect_success=True)

    env = {
        "PVAULT_MASTER_PASSWORD": "WRONG_WRONG",
        "PVAULT_SITE": "from-env.com",
        "PVAULT_USERNAME": "env_user",
        "PVAULT_PASSWORD": "env_password",
    }
    args = [
        "add",
        "--master-password", MASTER_PASSWORD,
        "--site", "from-cli.com",
        "--username", "cli_user",
        "--password", "cli_password",
        "--notes", "CLI备注",
    ]
    r = run_pvault(args, env_extra=env, expect_success=True)
    assert_contains(r.stdout, "已添加条目: from-cli.com", "使用 CLI 参数而非环境变量")

    r = run_pvault(["list", "--show-password", "--master-password", MASTER_PASSWORD], expect_success=True)
    assert_contains(r.stdout, "from-cli.com", "站点是 CLI 传入的")
    assert_contains(r.stdout, "cli_user", "用户名是 CLI 传入的")
    assert_contains(r.stdout, "cli_password", "密码是 CLI 传入的")
    assert_not_contains(r.stdout, "from-env.com", "不应使用环境变量的站点")
    print("  [OK] 命令行参数优先级正确")


def test_12_empty_vault_list():
    banner("测试12：空保险箱列表提示")
    clean_vault()
    run_pvault(["init", "--master-password", MASTER_PASSWORD], expect_success=True)
    r = run_pvault(["list", "--master-password", MASTER_PASSWORD], expect_success=True)
    assert_contains(r.stdout, "保险箱为空", "空保险箱提示")
    print("  [OK] 空保险箱提示正确")


def main():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + "  pvault 自动化验证脚本".center(58) + "║")
    print("║" + "  覆盖核心流程与安全验证".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    print(f"Python: {sys.executable}")
    print(f"项目目录: {PROJECT_DIR}")
    print(f"测试用主密码: {MASTER_PASSWORD}")

    tests = [
        test_01_not_initialized,
        test_02_init,
        test_03_wrong_master_password,
        test_04_add_entries,
        test_05_list_masked,
        test_06_list_show_password,
        test_07_search,
        test_08_modify_entry,
        test_09_delete_entry,
        test_10_database_no_plaintext,
        test_11_cli_args_priority,
        test_12_empty_vault_list,
    ]

    passed = 0
    failed = 0
    failed_names = []

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
            print(f"\n  [PASS] {test_fn.__name__} 通过")
        except Exception as e:
            failed += 1
            failed_names.append(test_fn.__name__)
            print(f"\n  [FAIL] {test_fn.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()

    banner("验证结果汇总")
    total = passed + failed
    print(f"  总用例数: {total}")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    if failed_names:
        print(f"  失败用例: {', '.join(failed_names)}")

    print()
    if failed == 0:
        print("[SUCCESS] 所有测试通过！")
        return 0
    else:
        print("[FAILURE] 存在失败的测试，请检查代码。")
        return 1


if __name__ == "__main__":
    try:
        import cryptography
        print(f"cryptography 版本: {cryptography.__version__}")
    except ImportError:
        print("[错误] cryptography 未安装，请先运行: pip install -r requirements.txt")
        sys.exit(2)
    sys.exit(main())
