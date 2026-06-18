# sample1_database.py
# A database utility module with intentional bugs and security issues.
# Use this as: python main.py sample_code/sample1_database.py

import sqlite3

SECRET_KEY = "hardcoded-secret-123"   # Security: hardcoded credential


def get_user_by_id(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Security: SQL injection via f-string
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cursor.fetchone()
    # Bug: connection never closed
    return {"id": row[0], "username": row[1], "password": row[2]}  # Security: exposes password


def get_all_active_users():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE active = 1")
    users = cursor.fetchall()
    conn.close()
    return users


def delete_user(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Security: SQL injection
    cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
    conn.commit()
    conn.close()


def update_email(user_id, new_email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Security: SQL injection
    cursor.execute(f"UPDATE users SET email = '{new_email}' WHERE id = {user_id}")
    conn.commit()
    conn.close()
