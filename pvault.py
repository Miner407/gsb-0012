#!/usr/bin/env python3

import argparse
import getpass
import hashlib
import os
import sqlite3
import sys
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VAULT_DIR = os.path.join(os.path.expanduser("~"), ".pvault")
DB_PATH = os.path.join(VAULT_DIR, "vault.db")
SALT_PATH = os.path.join(VAULT_DIR, "salt.bin")
KEY_FILE = os.path.join(VAULT_DIR, ".master_hash")


def _derive_key(master_password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))


def _get_fernet(master_password: str) -> Fernet:
    if not os.path.exists(SALT_PATH):
        print("[错误] 保险箱未初始化，请先运行: pvault init")
        sys.exit(1)
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
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def cmd_init(args):
    if os.path.exists(DB_PATH):
        print("[提示] 保险箱已存在。如需重置，请先删除 ~/.pvault 目录。")
        return
    os.makedirs(VAULT_DIR, exist_ok=True)
    master = getpass.getpass("设置主密码: ")
    confirm = getpass.getpass("确认主密码: ")
    if master != confirm:
        print("[错误] 两次密码不一致。")
        sys.exit(1)
    salt = os.urandom(16)
    with open(SALT_PATH, "wb") as f:
        f.write(salt)
    master_hash = hashlib.sha256(master.encode()).hexdigest()
    with open(KEY_FILE, "w") as f:
        f.write(master_hash)
    conn = _get_connection()
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


def _authenticate():
    master = getpass.getpass("主密码: ")
    if not _verify_master(master):
        print("[错误] 主密码不正确。")
        sys.exit(1)
    return _get_fernet(master)


def cmd_add(args):
    fernet = _authenticate()
    conn = _get_connection()
    site = input("站点: ")
    username = input("用户名: ")
    password = getpass.getpass("密码: ")
    notes = input("备注 (可留空): ")
    enc_pwd = _encrypt(password, fernet)
    enc_notes = _encrypt(notes, fernet)
    conn.execute(
        "INSERT INTO entries (site, username, password_enc, notes_enc) VALUES (?, ?, ?, ?)",
        (site, username, enc_pwd, enc_notes),
    )
    conn.commit()
    conn.close()
    print(f"[成功] 已添加条目: {site}")


def cmd_list(args):
    fernet = _authenticate()
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc, created_at, updated_at FROM entries ORDER BY id"
    ).fetchall()
    conn.close()
    if not rows:
        print("[提示] 保险箱为空。")
        return
    print(f"{'ID':<5} {'站点':<20} {'用户名':<20} {'密码':<20} {'备注':<20} {'创建时间':<20}")
    print("-" * 105)
    for row in rows:
        eid, site, username, enc_pwd, enc_notes, created, updated = row
        try:
            pwd = _decrypt(enc_pwd, fernet)
            notes = _decrypt(enc_notes, fernet)
        except Exception:
            pwd = "<解密失败>"
            notes = "<解密失败>"
        print(f"{eid:<5} {site:<20} {username:<20} {pwd:<20} {notes:<20} {created:<20}")


def cmd_search(args):
    fernet = _authenticate()
    keyword = args.keyword
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc, created_at FROM entries WHERE site LIKE ? OR username LIKE ?",
        (f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"[提示] 未找到匹配「{keyword}」的条目。")
        return
    print(f"搜索结果 (关键词: {keyword})")
    print(f"{'ID':<5} {'站点':<20} {'用户名':<20} {'密码':<20} {'备注':<20} {'创建时间':<20}")
    print("-" * 105)
    for row in rows:
        eid, site, username, enc_pwd, enc_notes, created = row
        try:
            pwd = _decrypt(enc_pwd, fernet)
            notes = _decrypt(enc_notes, fernet)
        except Exception:
            pwd = "<解密失败>"
            notes = "<解密失败>"
        print(f"{eid:<5} {site:<20} {username:<20} {pwd:<20} {notes:<20} {created:<20}")


def cmd_modify(args):
    fernet = _authenticate()
    entry_id = args.id
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, site, username, password_enc, notes_enc FROM entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    if not row:
        print(f"[错误] 未找到 ID={entry_id} 的条目。")
        conn.close()
        return
    _, site, username, enc_pwd, enc_notes = row
    try:
        old_pwd = _decrypt(enc_pwd, fernet)
        old_notes = _decrypt(enc_notes, fernet)
    except Exception:
        print("[错误] 解密失败，无法修改。")
        conn.close()
        return
    print(f"当前站点: {site}")
    new_site = input(f"新站点 (回车保留原值 [{site}]): ").strip()
    print(f"当前用户名: {username}")
    new_username = input(f"新用户名 (回车保留原值 [{username}]): ").strip()
    print(f"当前密码: {old_pwd}")
    new_pwd = getpass.getpass("新密码 (回车保留原值): ").strip()
    print(f"当前备注: {old_notes}")
    new_notes = input(f"新备注 (回车保留原值 [{old_notes}]): ").strip()
    site = new_site if new_site else site
    username = new_username if new_username else username
    pwd = new_pwd if new_pwd else old_pwd
    notes = new_notes if new_notes else old_notes
    enc_pwd_new = _encrypt(pwd, fernet)
    enc_notes_new = _encrypt(notes, fernet)
    conn.execute(
        "UPDATE entries SET site=?, username=?, password_enc=?, notes_enc=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (site, username, enc_pwd_new, enc_notes_new, entry_id),
    )
    conn.commit()
    conn.close()
    print(f"[成功] 已更新条目 ID={entry_id}")


def cmd_delete(args):
    _authenticate()
    entry_id = args.id
    conn = _get_connection()
    row = conn.execute("SELECT id, site, username FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        print(f"[错误] 未找到 ID={entry_id} 的条目。")
        conn.close()
        return
    confirm = input(f"确认删除 ID={entry_id} (站点={row[1]}, 用户名={row[2]})？[y/N]: ").strip().lower()
    if confirm != "y":
        print("[取消] 已取消删除。")
        conn.close()
        return
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    print(f"[成功] 已删除条目 ID={entry_id}")


def main():
    parser = argparse.ArgumentParser(
        prog="pvault",
        description="命令行密码保险箱 - 本地加密存储密码",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    sub.add_parser("init", help="初始化保险箱")

    sub.add_parser("add", help="添加密码条目")

    p_search = sub.add_parser("search", help="搜索密码条目")
    p_search.add_argument("keyword", help="搜索关键词")

    sub.add_parser("list", help="列出所有条目")

    p_modify = sub.add_parser("modify", help="修改密码条目")
    p_modify.add_argument("id", type=int, help="条目 ID")

    p_delete = sub.add_parser("delete", help="删除密码条目")
    p_delete.add_argument("id", type=int, help="条目 ID")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

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
