#!/usr/bin/env python3
import json
import os
import sqlite3
import smtplib
import ssl
from sqlite3 import Error
import datetime
import time
from email.message import EmailMessage
import Adafruit_DHT
import RPi.GPIO as GPIO

database = "/home/pi/projeto-monitoAR/dados_temp.db"
ENV_FILE = "/home/pi/projeto-monitoAR/env.sh"
ALERT_STATE_FILE = "/home/pi/projeto-monitoAR/.temp-alert-state.json"
TEMP_MIN = 5
TEMP_MAX = 45
UMIDADE_MIN = 10
UMIDADE_MAX = 100
TEMP_DELTA_MAX = 5
UMIDADE_DELTA_MAX = 20
CONFIRMACOES = 3
ALERT_TEMP = 35.0
ALERT_RESET_TEMP = 34.0
ALERT_REPEAT_HOURS = 6

def connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file, timeout=15)
        print(sqlite3.version)
    except Error as e:
        print(e)
    finally:
        if conn:
            conn.close()

def create_table():
    conn = sqlite3.connect(database, timeout=15)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dados_climaticos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT,
    temperatura REAL,
    umidade REAL
    )
    ''')
    conn.commit()
    conn.close()
def inserir_dados(data_hora, temp, umidade):
    conn = sqlite3.connect(database, timeout=15)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dados_climaticos (data_hora, temperatura, umidade)
        VALUES (?, ?, ?)
    ''', (data_hora, temp, umidade))
    conn.commit()
    conn.close()

def carregar_env_file(path):
    valores = {}

    if not os.path.exists(path):
        return valores

    with open(path, "r", encoding="utf-8") as env_file:
        for linha in env_file:
            linha = linha.strip()
            if not linha.startswith("export ") or "=" not in linha:
                continue

            chave, valor = linha[len("export "):].split("=", 1)
            valores[chave.strip()] = valor.strip().strip("\"'")

    return valores

def config_email():
    env_file = carregar_env_file(ENV_FILE)

    def obter(chave, padrao=""):
        return os.environ.get(chave) or env_file.get(chave, padrao)

    return {
        "smtp_host": obter("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(obter("SMTP_PORT", "587")),
        "smtp_user": obter("SMTP_USER"),
        "smtp_pass": obter("SMTP_PASS"),
        "mail_from": obter("MAIL_FROM", obter("SMTP_USER")),
        "mail_to": obter("MAIL_TO"),
        "subject_prefix": obter("SUBJECT_PREFIX", "Alerta Climatico"),
    }

def enviar_email(subject, body_text):
    config = config_email()
    if not config["smtp_user"] or not config["smtp_pass"] or not config["mail_to"]:
        print("Alerta de temperatura nao enviado: configuracao SMTP incompleta")
        return False

    msg = EmailMessage()
    msg["From"] = config["mail_from"]
    msg["To"] = config["mail_to"]
    msg["Subject"] = subject
    msg.set_content(body_text)

    context = ssl.create_default_context()
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"], timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(config["smtp_user"], config["smtp_pass"])
        server.send_message(msg)

    return True

def carregar_estado_alerta():
    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": False, "last_sent": None}

def salvar_estado_alerta(estado):
    tmp_path = f"{ALERT_STATE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as state_file:
        json.dump(estado, state_file)
    os.replace(tmp_path, ALERT_STATE_FILE)

def alerta_deve_repetir(estado, agora):
    last_sent = estado.get("last_sent")
    if not last_sent:
        return True

    try:
        ultimo_envio = datetime.datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True

    intervalo = datetime.timedelta(hours=ALERT_REPEAT_HOURS)
    return agora - ultimo_envio >= intervalo

def verificar_alerta_temperatura(temp, umidade, data_hora):
    agora = datetime.datetime.strptime(data_hora, "%Y-%m-%d %H:%M:%S")
    estado = carregar_estado_alerta()

    if temp < ALERT_RESET_TEMP:
        if estado.get("active"):
            estado["active"] = False
            salvar_estado_alerta(estado)
            print("Alerta de temperatura rearmado")
        return

    if temp < ALERT_TEMP:
        return

    if estado.get("active") and not alerta_deve_repetir(estado, agora):
        return

    config = config_email()
    subject = f"{config['subject_prefix']} - alerta: temperatura {temp:.1f} C"
    body = (
        "Alerta automatico do monitor de temperatura e umidade.\n\n"
        f"Data/hora: {data_hora}\n"
        f"Temperatura registrada: {temp:.1f} C\n"
        f"Umidade registrada: {umidade:.1f}%\n"
        f"Limite configurado: {ALERT_TEMP:.1f} C\n"
        f"Rearme automatico abaixo de: {ALERT_RESET_TEMP:.1f} C\n"
    )

    try:
        if enviar_email(subject, body):
            estado["active"] = True
            estado["last_sent"] = data_hora
            salvar_estado_alerta(estado)
            print(f"Alerta de temperatura enviado: {temp:.1f} C")
    except Exception as e:
        print(f"Falha ao enviar alerta de temperatura: {e}")

def ultima_leitura():
    conn = sqlite3.connect(database, timeout=15)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT temperatura, umidade
        FROM dados_climaticos
        WHERE temperatura BETWEEN ? AND ?
          AND umidade BETWEEN ? AND ?
        ORDER BY data_hora DESC
        LIMIT 1
    ''', (TEMP_MIN, TEMP_MAX, UMIDADE_MIN, UMIDADE_MAX))
    row = cursor.fetchone()
    conn.close()
    return row

def dentro_da_faixa(temp, umidade):
    return (
        temp is not None and umidade is not None
        and TEMP_MIN <= temp <= TEMP_MAX
        and UMIDADE_MIN <= umidade <= UMIDADE_MAX
    )

def leitura_estavel(temp, umidade, anterior):
    if not dentro_da_faixa(temp, umidade):
        return False

    if anterior is None:
        return True

    temp_anterior, umidade_anterior = anterior
    return (
        abs(temp - temp_anterior) <= TEMP_DELTA_MAX
        and abs(umidade - umidade_anterior) <= UMIDADE_DELTA_MAX
    )

def ler_sensor_confirmado(sensor, pino_sensor):
    umidade, temp = Adafruit_DHT.read_retry(sensor, pino_sensor)
    anterior = ultima_leitura()

    if leitura_estavel(temp, umidade, anterior):
        return temp, umidade

    print(f"Leitura suspeita descartada inicialmente: {temp, umidade}")
    candidatos = []

    for tentativa in range(CONFIRMACOES):
        time.sleep(2)
        umidade_extra, temp_extra = Adafruit_DHT.read_retry(sensor, pino_sensor)
        if leitura_estavel(temp_extra, umidade_extra, anterior):
            candidatos.append((temp_extra, umidade_extra))
        else:
            print(f"Confirmacao {tentativa + 1} suspeita: {temp_extra, umidade_extra}")

    if not candidatos:
        return None, None

    if anterior is None:
        candidatos.sort()
        return candidatos[len(candidatos) // 2]

    temp_anterior, umidade_anterior = anterior
    return min(
        candidatos,
        key=lambda item: abs(item[0] - temp_anterior) + abs(item[1] - umidade_anterior)
    )

if __name__ == '__main__':
    connection(database)
 #   create_table()

    #define tipo de sensor
    sensor = Adafruit_DHT.DHT11

    GPIO.setmode(GPIO.BOARD)

    #define a gpio conectada ao pino de dados do sensor
    pino_sensor = 25

    print("Lendo valores de temperatura e umidade")

    while (1):
        temp, umidade = ler_sensor_confirmado(sensor, pino_sensor)

        if umidade is not None and temp is not None:
            data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            inserir_dados(data_hora, temp, umidade)
            print(f"Leitura salva: {temp, umidade}")
            verificar_alerta_temperatura(temp, umidade, data_hora)
            time.sleep(120)
        else:
            print("Falha ao confirmar dados validos do sensor")
            time.sleep(30)
