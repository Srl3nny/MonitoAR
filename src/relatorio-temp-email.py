#!/usr/bin/env python3
import os
import sqlite3
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta

import socket

def get_local_ip(prefer_gateway: str = "1.1.1.1") -> str:
    """
    Retorna o IP local que o Raspberry está usando para sair na rede.
    Não precisa que 1.1.1.1 responda; é só para o SO escolher a interface.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((prefer_gateway, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "IP_DESCONHECIDO"


def build_hourly_report(db_path: str, hours: int = 24) -> str:
    """
    Gera um relatório hora a hora (médias) das últimas X horas.
    Requer que data_hora esteja em formato ISO: 'YYYY-MM-DD HH:MM:SS' (ou YYYY-MM-DDTHH:MM:SS).
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Banco não encontrado: {db_path}")

    since_dt = datetime.now() - timedelta(hours=hours)
    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Normaliza possíveis formatos: 'YYYY-MM-DDTHH:MM:SS' -> 'YYYY-MM-DD HH:MM:SS'
    # e agrupa por hora (YYYY-MM-DD HH).
    query = """
    SELECT
      substr(replace(data_hora, 'T', ' '), 1, 13) AS hora,
      ROUND(AVG(temperatura), 2) AS temp_media,
      ROUND(MIN(temperatura), 2) AS temp_min,
      ROUND(MAX(temperatura), 2) AS temp_max,
      ROUND(AVG(umidade), 2) AS umid_media,
      ROUND(MIN(umidade), 2) AS umid_min,
      ROUND(MAX(umidade), 2) AS umid_max,
      COUNT(*) AS amostras
    FROM dados_climaticos
    WHERE replace(data_hora, 'T', ' ') >= ?
    GROUP BY hora
    ORDER BY hora ASC;
    """

    cur.execute(query, (since_str,))
    rows = cur.fetchall()
    conn.close()

    # Monta tabela em texto (ASCII), simples de ler no e-mail
    header = (
        "Hora              | TempM | Tmin | Tmax | UmidM | Umin | Umax | N\n"
        "------------------+-------+------+------+-------+------+------+---\n"
    )
    lines = [header]
    for hora, tm, tmin, tmax, um, umin, umax, n in rows:
        # hora vem como "YYYY-MM-DD HH"
        lines.append(
            f"{hora}:00           | {tm:>5} | {tmin:>4} | {tmax:>4} | {um:>5} | {umin:>4} | {umax:>4} | {n:>2}\n"
        )

    if len(rows) == 0:
        return f"Nenhum dado encontrado nas últimas {hours} horas (desde {since_str})."

    return "".join(lines)


def send_email_smtp(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    mail_from: str,
    mail_to: str,
    subject: str,
    body_text: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.set_content(body_text)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def main():

    ip = get_local_ip()
    grafico_url = f"http://{ip}/"  # ajuste o caminho se for /ultimos100.html ou outro

    # --- CONFIG via variáveis de ambiente (mais seguro que hardcode) ---
    DB_PATH = os.environ.get("CLIMA_DB", "/caminho/para/seu_banco.db")
    HOURS = int(os.environ.get("CLIMA_HOURS", "24"))

    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")

    MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)
    MAIL_TO = os.environ.get("MAIL_TO", "")
    SUBJECT_PREFIX = os.environ.get("SUBJECT_PREFIX", "Relatório Climático")

    if not SMTP_USER or not SMTP_PASS or not MAIL_TO:
        raise SystemExit(
            "Faltam variáveis de ambiente. Defina SMTP_USER, SMTP_PASS e MAIL_TO (e CLIMA_DB)."
        )

    report = build_hourly_report(DB_PATH, hours=HOURS)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f" {ip} {SUBJECT_PREFIX} - últimas {HOURS}h - {now_str}"

    send_email_smtp(
        smtp_host=SMTP_HOST,
        smtp_port=SMTP_PORT,
        smtp_user=SMTP_USER,
        smtp_pass=SMTP_PASS,
        mail_from=MAIL_FROM,
        mail_to=MAIL_TO,
        subject=subject,
        body_text=report,
    )


if __name__ == "__main__":
    main()

