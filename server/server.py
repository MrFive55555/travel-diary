#!/usr/bin/env python3
"""Lightweight persistent Diary & Photo Album API using Python stdlib (http.server + sqlite3).
Supports multi-activity adventure scoping, comment persistence, and photo uploads.
Zero external dependencies.
"""
import base64
import http.server
import json
import os
import sqlite3
import urllib.parse
import uuid
from datetime import datetime

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "diary.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")


def init_db():
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 感言便签表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT NOT NULL,
        content TEXT NOT NULL,
        mood TEXT DEFAULT '💕',
        activity_id TEXT DEFAULT 'chongqing',
        created_at TEXT NOT NULL
    )
    """)

    # 独家游玩相册表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id TEXT DEFAULT 'chongqing',
        filename TEXT NOT NULL,
        caption TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)

    # 检查 activity_id 字段是否存在
    cursor.execute("PRAGMA table_info(notes)")
    columns = [row[1] for row in cursor.fetchall()]
    if "activity_id" not in columns:
        cursor.execute("ALTER TABLE notes ADD COLUMN activity_id TEXT DEFAULT 'chongqing'")

    conn.commit()
    conn.close()


class DiaryHandler(http.server.BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        # 1. 查询感言列表
        if parsed.path == "/api/notes":
            activity_id = query.get("activity", [None])[0]
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if activity_id:
                cursor.execute(
                    "SELECT id, nickname, content, mood, activity_id, created_at FROM notes WHERE activity_id = ? ORDER BY id DESC LIMIT 50",
                    (activity_id,)
                )
            else:
                cursor.execute(
                    "SELECT id, nickname, content, mood, activity_id, created_at FROM notes ORDER BY id DESC LIMIT 50"
                )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._set_headers(200)
            self.wfile.write(json.dumps({"success": True, "data": rows}, ensure_ascii=False).encode("utf-8"))

        # 2. 查询相册照片列表
        elif parsed.path == "/api/photos":
            activity_id = query.get("activity", [None])[0]
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if activity_id:
                cursor.execute(
                    "SELECT id, activity_id, filename, caption, created_at FROM photos WHERE activity_id = ? ORDER BY id DESC",
                    (activity_id,)
                )
            else:
                cursor.execute(
                    "SELECT id, activity_id, filename, caption, created_at FROM photos ORDER BY id DESC"
                )
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                d["url"] = f"/uploads/{d['filename']}"
                rows.append(d)
            conn.close()
            self._set_headers(200)
            self.wfile.write(json.dumps({"success": True, "data": rows}, ensure_ascii=False).encode("utf-8"))

        # 3. 健康检查
        elif parsed.path == "/api/health":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

        # 4. 开发环境支持托管 uploads/ 目录
        elif parsed.path.startswith("/uploads/"):
            fname = os.path.basename(parsed.path)
            fpath = os.path.join(UPLOADS_DIR, fname)
            if os.path.isfile(fpath):
                self._set_headers(200, "image/jpeg")
                with open(fpath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self._set_headers(404)
                self.wfile.write(b"404 Not Found")
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        # 1. 发表感言
        if parsed.path == "/api/notes":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 1024 * 32:
                self._set_headers(413)
                self.wfile.write(json.dumps({"error": "Payload too large"}).encode("utf-8"))
                return

            body = self.rfile.read(content_length).decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

            nickname = str(data.get("nickname", "小哭包和宝宝")).strip()[:30] or "小哭包和宝宝"
            content = str(data.get("content", "")).strip()[:500]
            mood = str(data.get("mood", "💕 超开心")).strip()[:30]
            activity_id = str(data.get("activity_id", "chongqing")).strip()[:40] or "chongqing"

            if not content:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "内容不能为空"}).encode("utf-8"))
                return

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (nickname, content, mood, activity_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (nickname, content, mood, activity_id, created_at)
            )
            note_id = cursor.lastrowid
            conn.commit()
            conn.close()

            new_note = {
                "id": note_id,
                "nickname": nickname,
                "content": content,
                "mood": mood,
                "activity_id": activity_id,
                "created_at": created_at
            }
            self._set_headers(201)
            self.wfile.write(json.dumps({"success": True, "data": new_note}, ensure_ascii=False).encode("utf-8"))

        # 2. 上传照片到相册
        elif parsed.path == "/api/photos":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 1024 * 1024 * 16:  # 限制 16MB
                self._set_headers(413)
                self.wfile.write(json.dumps({"error": "照片体积过大（单张限16MB以内）"}).encode("utf-8"))
                return

            body = self.rfile.read(content_length).decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

            activity_id = str(data.get("activity_id", "chongqing")).strip()[:40] or "chongqing"
            caption = str(data.get("caption", "")).strip()[:100]
            image_data = data.get("image_data", "")

            if not image_data or not isinstance(image_data, str):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "缺少照片数据"}).encode("utf-8"))
                return

            # 解析 base64
            ext = ".jpg"
            if "," in image_data:
                header, b64_str = image_data.split(",", 1)
                if "webp" in header:
                    ext = ".webp"
                elif "png" in header:
                    ext = ".png"
            else:
                b64_str = image_data

            try:
                img_bytes = base64.b64decode(b64_str)
            except Exception:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "图片解码失败"}).encode("utf-8"))
                return

            timestamp = int(datetime.now().timestamp())
            random_tag = uuid.uuid4().hex[:6]
            filename = f"{activity_id}_{timestamp}_{random_tag}{ext}"
            file_path = os.path.join(UPLOADS_DIR, filename)

            with open(file_path, "wb") as f:
                f.write(img_bytes)

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO photos (activity_id, filename, caption, created_at) VALUES (?, ?, ?, ?)",
                (activity_id, filename, caption, created_at)
            )
            photo_id = cursor.lastrowid
            conn.commit()
            conn.close()

            new_photo = {
                "id": photo_id,
                "activity_id": activity_id,
                "filename": filename,
                "url": f"/uploads/{filename}",
                "caption": caption,
                "created_at": created_at
            }
            self._set_headers(201)
            self.wfile.write(json.dumps({"success": True, "data": new_photo}, ensure_ascii=False).encode("utf-8"))

        # 3. 删除照片
        elif parsed.path == "/api/photos/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

            photo_id = data.get("id")
            if not photo_id:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "缺少照片 ID"}).encode("utf-8"))
                return

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM photos WHERE id = ?", (photo_id,))
            row = cursor.fetchone()
            if row:
                filename = row[0]
                file_path = os.path.join(UPLOADS_DIR, filename)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                cursor.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
                conn.commit()
            conn.close()

            self._set_headers(200)
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))


if __name__ == "__main__":
    init_db()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), DiaryHandler)
    print(f"Diary & Photo Album API running on http://127.0.0.1:{PORT}")
    server.serve_forever()
