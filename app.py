import os
from urllib.parse import urlparse

import psycopg2
from flask import Flask, render_template, request
from werkzeug.security import generate_password_hash

app = Flask(__name__)


def get_database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def get_connection():
    return psycopg2.connect(get_database_url())


def ensure_users_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        conn.commit()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    message = None
    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            error = "Заполните все поля."
        elif len(password) < 6:
            error = "Пароль должен содержать минимум 6 символов."
        else:
            try:
                ensure_users_table()
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO users (name, email, password_hash)
                            VALUES (%s, %s, %s)
                            RETURNING id
                            """,
                            (name, email, generate_password_hash(password)),
                        )
                        user_id = cur.fetchone()[0]
                    conn.commit()
                message = f"Регистрация выполнена. Ваш ID: {user_id}."
            except psycopg2.errors.UniqueViolation:
                error = "Пользователь с таким email уже зарегистрирован."
            except Exception as exc:
                app.logger.exception("Database error: %s", exc)
                error = "Не удалось сохранить данные в базе. Проверьте подключение к PostgreSQL."

    return render_template("register.html", message=message, error=error)


@app.route("/admin")
def admin():
    """Simple admin page showing registered users (without password hashes)."""
    try:
        ensure_users_table()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, email, created_at
                    FROM users
                    ORDER BY id DESC
                    """
                )
                users = cur.fetchall()
        return render_template("admin.html", users=users)
    except Exception as exc:
        app.logger.exception("Admin page database error: %s", exc)
        return render_template("admin.html", users=[], error="Не удалось получить данные из базы данных."), 500


@app.route("/health")
def health():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        app.logger.exception("Health check failed: %s", exc)
        return {"status": "error", "database": "unavailable"}, 500


if __name__ == "__main__":
    ensure_users_table()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)
