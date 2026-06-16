# captura_cubiertas_panol.py
# Login -> módulo Cubiertas (inicializa sesión) -> reporte Stock en Pañol
# -> botón "Totales" -> captura del ReportViewer -> enviar por Gmail

import os
import time
import smtplib
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
URL_LOGIN     = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_CUBIERTAS = "https://cloud.dazsistemas.com.ar/cubiertas/Default.aspx"   # inicializa Session("daz")
URL_PANOL     = "https://cloud.dazsistemas.com.ar/cubiertas/stock_panol.aspx"  # página del menú que prepara el reporte

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
def _buscar_totales(driver):
    """Busca el elemento 'Totales' y lo clickea. Devuelve True si pudo."""
    candidatos = driver.find_elements(
        By.XPATH,
        "//a | //button | //span | //td | //input[@type='button'] | //input[@type='submit']"
    )
    for e in candidatos:
        try:
            txt = (e.text or e.get_attribute("value") or "").strip().lower()
            if txt == "totales" or ("total" in txt and len(txt) < 15):
                driver.execute_script("arguments[0].click();", e)
                print("Click en 'Totales':", txt)
                return True
        except Exception:
            pass
    return False


def capturar_totales(driver):
    # 1) Entrar al módulo Cubiertas -> inicializa Session("daz") del lado del servidor
    driver.get(URL_CUBIERTAS)
    time.sleep(6)
    print("URL módulo cubiertas:", driver.current_url)

    # 2) Ahora sí, ir al reporte de stock en pañol (la sesión ya está armada)
    driver.get(URL_PANOL)
    time.sleep(12)  # el ReportViewer tarda en renderizar
    print("URL reporte:", driver.current_url)

    # 3) Click en "Totales" (busca en la página y, si no, dentro de iframes)
    clickeado = _buscar_totales(driver)
    if not clickeado:
        for fr in driver.find_elements(By.TAG_NAME, "iframe"):
            try:
                driver.switch_to.frame(fr)
                if _buscar_totales(driver):
                    clickeado = True
                    driver.switch_to.default_content()
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
    if not clickeado:
        print("[!] No se encontró 'Totales'. Capturo el reporte igual.")

    time.sleep(8)  # esperar que el reporte muestre los totales

    # 4) Capturar el área del ReportViewer (no la primera <table> cualquiera)
    selectores = [
        (By.CSS_SELECTOR, "div[id*='ReportViewer']"),
        (By.CSS_SELECTOR, "table[id*='ReportViewer']"),
        (By.CSS_SELECTOR, "div[id*='VisibleReportContent']"),
    ]
    elemento = None
    for by, sel in selectores:
        try:
            elemento = driver.find_element(by, sel)
            print("Capturando elemento:", sel)
            break
        except Exception:
            pass

    try:
        if elemento is not None:
            elemento.screenshot(ARCHIVO_PNG)
        else:
            print("[!] No se ubicó el ReportViewer, capturo pantalla completa.")
            driver.save_screenshot(ARCHIVO_PNG)
        print("Captura guardada:", ARCHIVO_PNG)
    except Exception as ex:
        print("[!] Fallo la captura del elemento, capturo pantalla completa:", ex)
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
