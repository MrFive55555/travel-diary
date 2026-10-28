#!/usr/bin/env python3
"""本地开发预览工具 (Local Development & Preview Server)

运行方式：
    python preview.py

功能：
1. 启动本地 8080 端口开发服务器；
2. 自动模拟 Nginx 的随机场景封面替换；
3. 自动模拟本地感言数据库与相册照片 (diary_local.db / uploads_local/)，本地测试不污染云端；
4. 自动在浏览器中打开页面进行真机/调试测试。
"""
import base64
import http.server
import json
import os
import random
import sqlite3
import sys
import urllib.parse
import uuid
import webbrowser
from datetime import datetime

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")
LOCAL_DB = os.path.join(BASE_DIR, "diary_local.db")
LOCAL_UPLOADS = os.path.join(BASE_DIR, "uploads_local")

SCENES = ["sea", "city", "sunset", "market", "camp"]
SCENE_ALTS = {
    "sea": "小哭包和宝宝在海边草地上依偎看轮船与海浪",
    "city": "小哭包和宝宝在城市霓虹灯下的河边依偎",
    "sunset": "小哭包和宝宝在夕阳下的河畔依偎",
    "market": "小哭包和宝宝在夜市里分享小吃",
    "camp": "小哭包和宝宝在星空下的帐篷旁露营",
}


def init_local_db():
    os.makedirs(LOCAL_UPLOADS, exist_ok=True)
    conn = sqlite3.connect(LOCAL_DB)
    cursor = conn.cursor()
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id TEXT DEFAULT 'chongqing',
        filename TEXT NOT NULL,
        caption TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()


class LocalPreviewHandler(http.server.BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="text/html; charset=utf-8"):
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

        # 模拟感言 API
        if parsed.path == "/api/notes":
            activity_id = query.get("activity", [None])[0]
            conn = sqlite3.connect(LOCAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if activity_id:
                cursor.execute(
                    "SELECT id, nickname, content, mood, activity_id, created_at FROM notes WHERE activity_id = ? ORDER BY id DESC LIMIT 50",
                    (activity_id,)
                )
            else:
                cursor.execute("SELECT id, nickname, content, mood, activity_id, created_at FROM notes ORDER BY id DESC LIMIT 50")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            self._set_headers(200, "application/json; charset=utf-8")
            self.wfile.write(json.dumps({"success": True, "data": rows}, ensure_ascii=False).encode("utf-8"))
            return

        # 模拟相册 API
        if parsed.path == "/api/photos":
            activity_id = query.get("activity", [None])[0]
            conn = sqlite3.connect(LOCAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if activity_id:
                cursor.execute(
                    "SELECT id, activity_id, filename, caption, created_at FROM photos WHERE activity_id = ? ORDER BY id DESC",
                    (activity_id,)
                )
            else:
                cursor.execute("SELECT id, activity_id, filename, caption, created_at FROM photos ORDER BY id DESC")
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                d["url"] = f"/uploads/{d['filename']}"
                rows.append(d)
            conn.close()
            self._set_headers(200, "application/json; charset=utf-8")
            self.wfile.write(json.dumps({"success": True, "data": rows}, ensure_ascii=False).encode("utf-8"))
            return

        # 本地查看上传的照片
        if parsed.path.startswith("/uploads/"):
            fname = os.path.basename(parsed.path)
            fpath = os.path.join(LOCAL_UPLOADS, fname)
            if os.path.isfile(fpath):
                self._set_headers(200, "image/jpeg")
                with open(fpath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"404 Not Found")
            return

        # 模拟首页 HTML 与 Nginx 随机占位符替换
        if parsed.path in ["/", "/index.html"]:
            html_path = os.path.join(SITE_DIR, "index.html")
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()

            scene = random.choice(SCENES)
            alt = SCENE_ALTS.get(scene, "小哭包和宝宝的周末旅行日记")
            content = content.replace("__HERO__", scene).replace("__HERO_ALT__", alt)

            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(content.encode("utf-8"))
            return

        # 静态资源处理
        rel_path = parsed.path.lstrip("/")
        file_path = os.path.join(SITE_DIR, rel_path)
        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".webp": "image/webp",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".svg": "image/svg+xml",
                ".css": "text/css",
                ".js": "application/javascript",
            }
            content_type = mime_map.get(ext, "application/octet-stream")
            with open(file_path, "rb") as f:
                data = f.read()
            self._set_headers(200, content_type)
            self.wfile.write(data)
        else:
            self._set_headers(404, "text/plain")
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        # 1. 模拟发表感言
        if parsed.path == "/api/notes":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(body)
            nickname = str(data.get("nickname", "小哭包和宝宝")).strip()[:30] or "小哭包和宝宝"
            content = str(data.get("content", "")).strip()[:500]
            mood = str(data.get("mood", "💕 超开心")).strip()[:30]
            activity_id = str(data.get("activity_id", "chongqing")).strip()[:40] or "chongqing"

            if not content:
                self._set_headers(400, "application/json")
                self.wfile.write(json.dumps({"error": "内容不能为空"}).encode("utf-8"))
                return

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = sqlite3.connect(LOCAL_DB)
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
            self._set_headers(201, "application/json; charset=utf-8")
            self.wfile.write(json.dumps({"success": True, "data": new_note}, ensure_ascii=False).encode("utf-8"))

        # 2. 模拟上传照片
        elif parsed.path == "/api/photos":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(body)
            activity_id = str(data.get("activity_id", "chongqing")).strip()[:40] or "chongqing"
            caption = str(data.get("caption", "")).strip()[:100]
            image_data = data.get("image_data", "")

            if not image_data or not isinstance(image_data, str):
                self._set_headers(400, "application/json")
                self.wfile.write(json.dumps({"error": "缺少照片数据"}).encode("utf-8"))
                return

            ext = ".jpg"
            if "," in image_data:
                header, b64_str = image_data.split(",", 1)
                if "webp" in header:
                    ext = ".webp"
                elif "png" in header:
                    ext = ".png"
            else:
                b64_str = image_data

            img_bytes = base64.b64decode(b64_str)
            timestamp = int(datetime.now().timestamp())
            random_tag = uuid.uuid4().hex[:6]
            filename = f"{activity_id}_{timestamp}_{random_tag}{ext}"
            file_path = os.path.join(LOCAL_UPLOADS, filename)

            with open(file_path, "wb") as f:
                f.write(img_bytes)

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = sqlite3.connect(LOCAL_DB)
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
            self._set_headers(201, "application/json; charset=utf-8")
            self.wfile.write(json.dumps({"success": True, "data": new_photo}, ensure_ascii=False).encode("utf-8"))

        # 3. 模拟删除照片
        elif parsed.path == "/api/photos/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(body)
            photo_id = data.get("id")

            conn = sqlite3.connect(LOCAL_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM photos WHERE id = ?", (photo_id,))
            row = cursor.fetchone()
            if row:
                fname = row[0]
                fpath = os.path.join(LOCAL_UPLOADS, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
                cursor.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
                conn.commit()
            conn.close()
            self._set_headers(200, "application/json")
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        else:
            self._set_headers(404, "application/json")
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))


def main():
    init_local_db()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), LocalPreviewHandler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"=" * 60)
    print(f"小哭包和宝宝的旅行日记 · 本地开发预览服务已启动！")
    print(f"本地访问地址: {url}")
    print(f"按 Ctrl + C 可以随时停止服务。")
    print(f"=" * 60)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地预览服务已停止。")


if __name__ == "__main__":
    main()
