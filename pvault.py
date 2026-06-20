#!/usr/bin/env python3

import argparse
import getpass
import hashlib
import os
import sqlite3
import sys
import base64

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("[错误] 缺少依赖 cryptography。请先运行: pip install -r requirements.txt")
    sys.exit(2)

VAULT_DIR = os.path.join(os.path.expanduser("~"), ".pvault")
DB_PATH = os.path.join(VAULT_DIR, "vault.db")
SALT_PATH = os.path.join(VAULT_DIR, "salt.bin")
KEY_FILE = os.path.join(VAULT_DIR, ".master_hash")


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DEP_MISSING = 2
EXIT_NOT_INIT = 3
EXIT_WRONG_MASTER = 4
EXIT_NOT_FOUND = 5
EXIT_INVALID_ARGS = 6


def _mask_password(pwd: str) -> str:
    if not pwd:
        return "(空)"
    if len(pwd) <= 2:
        return "*" * len(pwd)
    return pwd[0] + "*" * (len(pwd) - 2) + pwd[-1]


def _mask_notes(notes: str) -> str:
    if not notes:
        return "(空)"
    if len(notes) <= 4:
        return "*" * len(notes)
    return notes[:2] + "*" * (len(notes) - 4) + notes[-2:]


def _derive_key(master_password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))


def _check_initialized():
    if not os.path.exists(SALT_PATH) or not os.path.exists(KEY_FILE) or not os.path.exists(DB_PATH):
        print("[错误] 保险箱未初始化，请先运行: pvault init")
        sys.exit(EXIT_NOT_INIT)


def _get_fernet(master_password: str) -> Fernet:
    _check_initialized()
    with open(SALT_PATH, "rb") as f:
        salt = f.read()
    key = _derive_key(master_password, salt)
    return Fernet(key)


def _verify_master(master_password: str) -> bool:
    if not os.path.exists(KEY_FILE):
        return False
    with open(KEY_FILE, "r") as f:
        stored_hash = f.read().strip()
    current_hash = hashlib.sha256(master_password.encode()).hexdigest()
    return current_hash == stored_hash


def _encrypt(text: str, fernet: Fernet) -> str:
    return fernet.encrypt(text.encode()).decode()


def _decrypt(token: str, fernet: Fernet) -> str:
    return fernet.decrypt(token.encode()).decode()


def _get_connection():
    _check_initialized()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_master_password(args, prompt: str = "主密码: ") -> str:
    mp = getattr(args, "master_password", None) or os.environ.get("PVAULT_MASTER_PASSWORD")
    if mp:
        return mp
    return getpass.getpass(prompt)


def _authenticate(args):
    _check_initialized()
    master = _get_master_password(args)
    if not _verify_master(master):
        print("[错误] 主密码不正确。")
        sys.exit(EXIT_WRONG_MASTER)
    return _get_fernet(master)


def _input(prompt: str, args, argname: str, envname: str, hidden: bool = False, default: str = "") -> str:
    val = getattr(args, argname, None) or os.environ.get(envname)
    if val is not None:
        return val
    if hidden:
        return getpass.getpass(prompt)
    user_input = input(prompt)
    return user_input if user_input else default


def cmd_init(args):
    if os.path.exists(DB_PATH) and os.path.exists(SALT_PATH) and os.path.exists(KEY_FILE):
        print("[提示] 保险箱已存在。如需重置，请先删除 ~/.pvault 目录。")
        sys.exit(EXIT_ERROR)
    os.makedirs(VAULT_DIR, exist_ok=True)

    master = getattr(args, "master_password", None) or os.environ.get("PVAULT_MASTER_PASSWORD")
    if master:
        confirm = master
    else:
        master = getpass.getpass("设置主密码: ")
        confirm = getpass.getpass("确认主密码: ")

    if not master:
        print("[错误] 主密码不能为空。")
        sys.exit(EXIT_INVALID_ARGS)
    if master != confirm:
        print("[错误] 两次密码不一致。")
        sys.exit(EXIT_ERROR)

    salt = os.urandom(16)
    with open(SALT_PATH, "wb") as f:
        f.write(salt)
    master_hash = hashlib.sha256(master.encode()).hexdigest()
    with open(KEY_FILE, "w") as f:
        f.write(master_hash)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL,
            username TEXT NOT NULL,
            password_enc TEXT NOT NULL,
            notes_enc TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()
    print("[成功] 保险箱初始化完成。")
    sys.exit(EXIT_OK)


def cmd_add(args):
    fernet = _authenticate(args)
    conn = _get_connection()

    site = _input("站点: ", args, "site", "PVAULT_SITE")
    username = _input("用户名: ", args, "username", "PVAULT_USERNAME")
    password = _input("密码: ", args, "password", "PVAULT_PASSWORD", hidden=True)
    notes = _input("备注 (可留空): ", args, "notes", "PVAULT_NOTES")

    if not site or not username or not password:
        print("[错误] 站点、用户名、密码不能为空。")
        conn.close()
        sys.exit(EXIT_INVALID_ARGS)

    enc_pwd = _encrypt(password, fernet)
    enc_notes = _encrypt(notes, fernet)
    conn.execute(
        "INSERT INTO entries (site, username, password_enc, notes_enc) VALUES (?, ?, ?, ?)",
        (site, username, enc_pwd, enc_notes),
    )
    conn.commit()
    conn.close()
    print(f"[成功] 已添加条目: {site}")
    sys.exit(EXIT_OK)


def _display_row(row, fernet, show_password: bool):
    eid, site, username, enc_pwd, enc_notes, created, *_ = row
    try:
        pwd = _decrypt(enc_pwd, fernet)
        notes = _decrypt(enc_notes, fernet)
    except Exception:
        pwd = "<解密失败>"
        notes = "<解密失败>"

    display_pwd = pwd if show_password else _mask_password(pwd)
    display_notes = notes if show_password else _mask_notes(notes)

    print(f"{eid:<5} {site:<20} {username:<20} {display_pwd:<20} {display_notes:<20} {str(created):<20}")


def cmd_list(args):
    fernet = _authenticate(args)
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc, created_at, updated_at FROM entries ORDER BY id"
    ).fetchall()
    conn.close()
    if not rows:
        print("[提示] 保险箱为空。")
        sys.exit(EXIT_OK)
    print(f"{'ID':<5} {'站点':<20} {'用户名':<20} {'密码':<20} {'备注':<20} {'创建时间':<20}")
    print("-" * 105)
    show = getattr(args, "show_password", False)
    for row in rows:
        _display_row(row, fernet, show)
    sys.exit(EXIT_OK)


def cmd_search(args):
    fernet = _authenticate(args)
    keyword = args.keyword
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc, created_at FROM entries WHERE site LIKE ? OR username LIKE ?",
        (f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"[提示] 未找到匹配「{keyword}」的条目。")
        sys.exit(EXIT_NOT_FOUND)
    print(f"搜索结果 (关键词: {keyword})")
    print(f"{'ID':<5} {'站点':<20} {'用户名':<20} {'密码':<20} {'备注':<20} {'创建时间':<20}")
    print("-" * 105)
    show = getattr(args, "show_password", False)
    for row in rows:
        _display_row(row, fernet, show)
    sys.exit(EXIT_OK)


def cmd_modify(args):
    fernet = _authenticate(args)
    entry_id = args.id
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc FROM entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    if not row:
        print(f"[错误] 未找到 ID={entry_id} 的条目。")
        conn.close()
        sys.exit(EXIT_NOT_FOUND)
    _, site, username, enc_pwd, enc_notes = row
    try:
        old_pwd = _decrypt(enc_pwd, fernet)
        old_notes = _decrypt(enc_notes, fernet)
    except Exception:
        print("[错误] 解密失败，无法修改。")
        conn.close()
        sys.exit(EXIT_ERROR)

    non_interactive = any([
        getattr(args, "site", None),
        getattr(args, "username", None),
        getattr(args, "password", None),
        getattr(args, "notes", None),
        os.environ.get("PVAULT_SITE"),
        os.environ.get("PVAULT_USERNAME"),
        os.environ.get("PVAULT_PASSWORD"),
        os.environ.get("PVAULT_NOTES"),
    ])

    if non_interactive:
        new_site = getattr(args, "site", None) or os.environ.get("PVAULT_SITE") or site
        new_username = getattr(args, "username", None) or os.environ.get("PVAULT_USERNAME") or username
        new_pwd = getattr(args, "password", None) or os.environ.get("PVAULT_PASSWORD") or old_pwd
        new_notes = getattr(args, "notes", None) if getattr(args, "notes", None) is not None else (os.environ.get("PVAULT_NOTES") if os.environ.get("PVAULT_NOTES") is not None else old_notes)
    else:
        print(f"当前站点: {site}")
        new_site = input(f"新站点 (回车保留原值 [{site}]): ").strip() or site
        print(f"当前用户名: {username}")
        new_username = input(f"新用户名 (回车保留原值 [{username}]): ").strip() or username
        print(f"当前密码: {_mask_password(old_pwd)}")
        new_pwd_raw = getpass.getpass("新密码 (回车保留原值): ").strip()
        new_pwd = new_pwd_raw if new_pwd_raw else old_pwd
        print(f"当前备注: {_mask_notes(old_notes)}")
        new_notes_raw = input(f"新备注 (回车保留原值): ").strip()
        new_notes = new_notes_raw if new_notes_raw is not None else old_notes

    if not new_site or not new_username or not new_pwd:
        print("[错误] 站点、用户名、密码不能为空。")
        conn.close()
        sys.exit(EXIT_INVALID_ARGS)

    enc_pwd_new = _encrypt(new_pwd, fernet)
    enc_notes_new = _encrypt(new_notes if new_notes is not None else "", fernet)
    conn.execute(
        "UPDATE entries SET site=?, username=?, password_enc=?, notes_enc=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_site, new_username, enc_pwd_new, enc_notes_new, entry_id),
    )
    conn.commit()
    conn.close()
    print(f"[成功] 已更新条目 ID={entry_id}")
    sys.exit(EXIT_OK)


def cmd_delete(args):
    fernet = _authenticate(args)
    entry_id = args.id
    conn = _get_connection()
    row = conn.execute("SELECT id, site, username FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        print(f"[错误] 未找到 ID={entry_id} 的条目。")
        conn.close()
        sys.exit(EXIT_NOT_FOUND)

    force = getattr(args, "force", False) or os.environ.get("PVAULT_FORCE") == "1"
    if not force:
        confirm = input(f"确认删除 ID={entry_id} (站点={row[1]}, 用户名={row[2]})？[y/N]: ").strip().lower()
        if confirm != "y":
            print("[取消] 已取消删除。")
            conn.close()
            sys.exit(EXIT_OK)

    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    print(f"[成功] 已删除条目 ID={entry_id}")
    sys.exit(EXIT_OK)


def _add_common_auth(p):
    p.add_argument("--master-password", dest="master_password", default=None,
                   help="主密码（也可通过环境变量 PVAULT_MASTER_PASSWORD 传入）")


def _add_common_entry_fields(p):
    p.add_argument("--site", dest="site", default=None,
                   help="站点名称（也可通过环境变量 PVAULT_SITE 传入）")
    p.add_argument("--username", dest="username", default=None,
                   help="用户名（也可通过环境变量 PVAULT_USERNAME 传入）")
    p.add_argument("--password", dest="password", default=None,
                   help="密码（也可通过环境变量 PVAULT_PASSWORD 传入）")
    p.add_argument("--notes", dest="notes", default=None,
                   help="备注（也可通过环境变量 PVAULT_NOTES 传入）")


def _add_show_password(p):
    p.add_argument("--show-password", dest="show_password", action="store_true", default=False,
                   help="显示明文密码（默认脱敏显示）")


def main():
    parser = argparse.ArgumentParser(
        prog="pvault",
        description="命令行密码保险箱 - 本地加密存储密码",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    p_init = sub.add_parser("init", help="初始化保险箱")
    _add_common_auth(p_init)

    p_add = sub.add_parser("add", help="添加密码条目")
    _add_common_auth(p_add)
    _add_common_entry_fields(p_add)

    p_search = sub.add_parser("search", help="搜索密码条目")
    p_search.add_argument("keyword", help="搜索关键词")
    _add_common_auth(p_search)
    _add_show_password(p_search)

    p_list = sub.add_parser("list", help="列出所有条目")
    _add_common_auth(p_list)
    _add_show_password(p_list)

    p_modify = sub.add_parser("modify", help="修改密码条目")
    p_modify.add_argument("id", type=int, help="条目 ID")
    _add_common_auth(p_modify)
    _add_common_entry_fields(p_modify)

    p_delete = sub.add_parser("delete", help="删除密码条目")
    p_delete.add_argument("id", type=int, help="条目 ID")
    p_delete.add_argument("--force", dest="force", action="store_true", default=False,
                          help="不提示确认直接删除（也可设置环境变量 PVAULT_FORCE=1）")
    _add_common_auth(p_delete)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(EXIT_OK)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "list": cmd_list,
        "search": cmd_search,
        "modify": cmd_modify,
        "delete": cmd_delete,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
