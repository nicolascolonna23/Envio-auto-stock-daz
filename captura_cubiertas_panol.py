# captura_cubiertas_panol.py
# Login -> Cubiertas en pañol -> botón "Totales" -> captura del elemento -> enviar por Gmail

import os
import time
import smtplib
import tempfile
from email.message import EmailMessage
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =====================================================
# VARIABLES (se leen de variables de entorno, NUNCA escritas en el código)
# =====================================================
USUARIO   = os.environ["CUBIERTAS_USUARIO"]
PASSWORD  = os.environ["CUBIERTAS_PASSWORD"]

# --- Gmail: usar una "Contraseña de aplicación" de Google, NO la del correo ---
GMAIL_USER     = os.environ["GMAIL_USER"]          # tu_correo@gmail.com (el que envía)
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASSWORD"]  # contraseña de aplicación de 16 dígitos
DESTINATARIO   = os.environ.get("GMAIL_DEST", "nscolonna68@gmail.com")

# --- URLs ---
URL_LOGIN  = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_PANOL  = "https://cloud.dazsistemas.com.ar/cubiertas/Reportes/Stock_Panol.aspx"

ARCHIVO_PNG = "totales_cubiertas.png"

# =====================================================
# CHROME
# =====================================================
def crear_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1400")
    return webdriver.Chrome(options=options)

# =====================================================
# LOGIN
# =====================================================
def login(driver):
    wait = WebDriverWait(driver, 30)
    driver.get(URL_LOGIN)
    time.sleep(5)
    user = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
    pwd  = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    driver.execute_script("arguments[0].value='';", user)
    driver.execute_script("arguments[0].value='';", pwd)
    user.send_keys(USUARIO)
    pwd.send_keys(PASSWORD)
    pwd.send_keys(Keys.ENTER)
    time.sleep(8)
    print("URL POST LOGIN:", driver.current_url)

# =====================================================
# CAPTURAR TOTALES
# =====================================================
def capturar_totales(driver):
    # 1) Ir directo a la pantalla "Cubiertas en pañol"
    driver.get(URL_PANOL)
    time.sleep(8)

    # 2) Click en el botón "Totales" (lo busca por texto, tolerante a mayúsculas)
    candidatos = driver.find_elements(
        By.XPATH,
        "//button | //a | //span | //input[@type='button'] | //input[@type='submit']"
    )
    clickeado = False
    for e in candidatos:
        try:
            txt = (e.text or e.get_attribute("value") or "").strip().lower()
            if "total" in txt:
                driver.execute_script("arguments[0].click();", e)
                print("Click en:", txt)
                clickeado = True
                break
        except Exception:
            pass
    if not clickeado:
        print("[!] No se encontró el botón 'Totales'. Capturo la pantalla completa igual.")

    time.sleep(6)  # esperar que carguen los totales

    # 3) Captura SOLO del elemento de totales
    #    COMPLETAR el selector del contenedor de la tabla/sección de totales.
    #    Ejemplos: (By.ID, "gridTotales") | (By.CSS_SELECTOR, "table.totales")
    try:
        elemento = driver.find_element(By.CSS_SELECTOR, "table")  # <-- AJUSTAR selector
        elemento.screenshot(ARCHIVO_PNG)
        print("Captura del elemento guardada:", ARCHIVO_PNG)
    except Exception as ex:
        print("[!] No se pudo capturar el elemento, capturo pantalla completa:", ex)
        driver.save_screenshot(ARCHIVO_PNG)

    return ARCHIVO_PNG

# =====================================================
# ENVIAR POR GMAIL
# =====================================================
def enviar_gmail(ruta_png):
    msg = EmailMessage()
    hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg["Subject"] = f"Totales Cubiertas en pañol - {hoy}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = DESTINATARIO
    msg.set_content(f"Captura automática de Totales (Cubiertas en pañol) generada el {hoy}.")

    with open(ruta_png, "rb") as f:
        msg.add_attachment(f.read(), maintype="image", subtype="png",
                           filename=os.path.basename(ruta_png))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        smtp.send_message(msg)
    print("Correo enviado a:", DESTINATARIO)

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    driver = crear_driver()
    try:
        login(driver)
        png = capturar_totales(driver)
        enviar_gmail(png)
    finally:
        driver.quit()
