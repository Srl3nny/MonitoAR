#!/usr/bin/env python3
import sqlite3
from sqlite3 import Error
import datetime
import random, time
import Adafruit_DHT
import RPi.GPIO as GPIO

database = "/home/pi/projeto-monitoAR/dados_temp.db"

def connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        print(sqlite3.version)
    except Error as e:
        print(e)
    finally:
        if conn:
            conn.close()

def create_table():
    conn = sqlite3.connect(database)
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
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dados_climaticos (data_hora, temperatura, umidade)
        VALUES (?, ?, ?)
    ''', (data_hora, temp, umidade))
    conn.commit()
    conn.close()

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
        #Efetua a leitura do sensor
        umidade, temp = Adafruit_DHT.read_retry(sensor, pino_sensor)

        if umidade is not None and temp is not None:
            data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            inserir_dados(data_hora, temp, umidade)
            print(f"{temp,umidade}")
            time.sleep(120)
        else:
            print("Falha ao ler os dados do sensor")
