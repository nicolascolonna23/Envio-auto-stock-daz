import os
import re
import json
import time
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL_LOGIN      = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_CONSUMOS   = "https://cloud.dazsistemas.com.ar/stock/Consumos_Mensuales.aspx"
SPREADSHEET_ID = "1u7cckay0IJ60bfoKk2OZo-TjCvTbH9O1wKxNFdSKDCQ"
HOJA           = "GASTOS REPARACIONES"

USUARIO           = os.environ["CUBIERTAS_USUARIO"]
PASSWORD          = os.environ["CUBIERTAS_PASSWORD"]
GOOGLE_CREDS_RAW  = os.environ["GOOGLE_CREDENTIALS"]
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
GMAIL_DEST        = os.environ["GMAIL_DEST"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Patentes argentinas: ABC123 o AB123CD
REGEX_PATENTE = re.compile(r'^[A-Z]{2,3}[0-9]{3}[A-Z]{0,2}[0-9]{0,2}$')

IDX_PATENTE = 2   # columna Patente (0-based)
IDX_TOTAL   = 11  # columna Total   (0-based)


def crear_driver():
    opciones = Options()
    opciones.add_argument("--headless=new")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--disable-gpu")
    opciones.add_argument("--window-size=1920,1400")
    return webdriver.Chrome(options=opciones)


def login(driver):
    driver.get(URL_LOGIN)
    wait = WebDriverWait(driver, 20)
    campo_usuario = wait.until(EC.presence_of_element_located((By.ID, "txtUsuario")))
    driver.find_element(By.ID, "txtPass").send_keys(PASSWORD)
    campo_usuario.send_keys(USUARIO)
    driver.find_element(By.ID, "btnLogin").click()
    wait.until(EC.url_contains("/menu/"))


def _entrar_stock(driver):
    wait = WebDriverWait(driver, 20)
    wait.until(lambda d: d.execute_script("return typeof openLink === 'function';"))
    ventanas_antes = set(driver.window_handles)
    driver.execute_script("openLink('W255TK', '853', '/stock/Login.aspx?empresa=853');")
    time.sleep(3)
    nuevas = set(driver.window_handles) - ventanas_antes
    if nuevas:
        driver.switch_to.window(nuevas.pop())
    wait.until(EC.url_contains("/stock/"))
    time.sleep(2)


def mes_anterior():
    hoy = date.today()
    ultimo_mes = hoy.replace(day=1) - timedelta(days=1)
    return ultimo_mes.month, ultimo_mes.year


def buscar_consumos(driver, mes, anio):
    driver.get(URL_CONSUMOS)
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.XPATH, "//input")))
    time.sleep(1)

    campo_mes = driver.find_element(By.XPATH,
        "//input[contains(@id,'Mes') or contains(@name,'Mes') or "
        "contains(@id,'mes') or contains(@name,'mes')]")
    campo_anio = driver.find_element(By.XPATH,
        "//input[contains(@id,'Anio') or contains(@name,'Anio') or "
        "contains(@id,'Year') or contains(@name,'Year') or "
        "contains(@id,'anio') or contains(@id,'Año')]")

    campo_mes.clear()
    campo_mes.send_keys(str(mes).zfill(2))
    campo_anio.clear()
    campo_anio.send_keys(str(anio))

    driver.find_element(By.XPATH,
        "//a[contains(normalize-space(),'Buscar')] | "
        "//input[@value='Buscar'] | //button[contains(normalize-space(),'Buscar')]"
    ).click()

    wait.until(EC.url_contains("Reportes"))
    time.sleep(4)


def _parsear_numero(txt):
    limpio = txt.replace("$", "").replace(" ", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(limpio)
    except ValueError:
        return None


def _extraer_tabla_actual(driver):
    driver.switch_to.default_content()
    resultado = []

    contextos = [None] + driver.find_elements(By.TAG_NAME, "iframe")
    for i, ctx in enumerate(contextos):
        if ctx is not None:
            try:
                driver.switch_to.frame(ctx)
                print(f"  [iframe {i}]")
            except Exception:
                continue
        else:
            print(f"  [contexto principal]")

        tablas = driver.find_elements(By.TAG_NAME, "table")
        print(f"  Tablas encontradas: {len(tablas)}")

        for j, tabla in enumerate(tablas):
            filas_tabla = tabla.find_elements(By.TAG_NAME, "tr")
            print(f"  Tabla {j}: {len(filas_tabla)} filas")
            # Mostrar primeras 3 filas para ver estructura
            for k, fila in enumerate(filas_tabla[:3]):
                celdas = fila.find_elements(By.TAG_NAME, "td")
                textos = [c.text.strip()[:20] for c in celdas]
                print(f"    Fila {k} ({len(celdas)} celdas): {textos}")

        driver.switch_to.default_content()

    return resultado


def extraer_todos_los_datos(driver):
    todos = []
    while True:
        filas = _extraer_tabla_actual(driver)
        print(f"  Página: {len(filas)} filas encontradas")
        todos.extend(filas)

        # Buscar botón "siguiente página"
        try:
            siguiente = driver.find_element(By.XPATH,
                "//input[@title='Next Page' or @title='Página siguiente' or @title='next page'] | "
                "//a[@title='Next Page' or @title='Página siguiente']")
            if not siguiente.is_enabled():
                break
            siguiente.click()
            time.sleep(3)
        except Exception:
            break

    return todos


def escribir_en_hoja(filas, mes, anio):
    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDS_RAW), scopes=SCOPES)
    hoja = gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(HOJA)

    periodo_str = f"{mes:02d}/{anio}"
    if periodo_str in hoja.col_values(1):
        print(f"Período {periodo_str} ya existe, se omite.")
        return

    nuevas = [[periodo_str, patente, total] for patente, total in filas]
    hoja.append_rows(nuevas, value_input_option="USER_ENTERED")
    print(f"Agregadas {len(nuevas)} filas para {periodo_str}.")


def enviar_error(error_txt):
    msg = EmailMessage()
    msg["Subject"] = "ERROR - Consumos mensuales DAZ"
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_DEST
    msg.set_content(
        "Ocurrió un error al procesar los consumos mensuales.\n\n"
        f"Detalle:\n{error_txt}"
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


if __name__ == "__main__":
    driver = crear_driver()
    try:
        mes, anio = mes_anterior()
        print(f"Procesando período: {mes:02d}/{anio}")
        login(driver)
        _entrar_stock(driver)
        buscar_consumos(driver, mes, anio)
        filas = extraer_todos_los_datos(driver)
        print(f"Total filas extraídas: {len(filas)}")
        if not filas:
            raise RuntimeError("No se encontraron datos en el reporte.")
        escribir_en_hoja(filas, mes, anio)
    except Exception as e:
        try:
            enviar_error(str(e))
        except Exception:
            pass
        raise
    finally:
        driver.quit()
