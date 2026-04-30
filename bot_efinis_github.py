import telebot
import requests
from bs4 import BeautifulSoup
import time
import threading
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
TOKEN_TELEGRAM = "TU_TOKEN_DE_TELEGRAM_AQUI"
RUT_EFINIS = "tu_rut_aqui"
PASS_EFINIS = "tu_contraseña_aqui"
CHAT_ID_DESTINO = "TU_CHAT_ID" # Necesitamos tu ID para los mensajes automáticos

bot = telebot.TeleBot(TOKEN_TELEGRAM)

URL_LOGIN = "https://efinis.uft.cl/index.php"
URL_CURSOS = "https://efinis.uft.cl/user_portal.php"

# Inicializamos la sesión a nivel GLOBAL para que guarde las cookies entre revisiones
session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 2. FUNCIÓN DE SCRAPING (OPTIMIZADA)
# ==========================================
def revisar_efinis():
    global session # Usamos la sesión global
    
    try:
        # 1. INTENTAR ACCESO DIRECTO PRIMERO
        response_cursos = session.get(URL_CURSOS, headers=headers)
        
        # Verificamos si realmente estamos en el portal (buscamos algo único de logueado)
        if "Mis cursos" not in response_cursos.text or "Ocurrió un error" in response_cursos.text:
            print("Sesión expirada o no iniciada. Ejecutando Login...")
            
            payload_login = {
                "login": RUT_EFINIS,
                "password": PASS_EFINIS,
                "submitAuth": "",
                "_qf_formLogin": ""
            }
            # Hacer POST para loguearse
            response_login = session.post(URL_LOGIN, data=payload_login, headers=headers)
            
            # Verificar si el login falló
            if "Contraseña incorrecta" in response_login.text:
                return ["Error al iniciar sesión. Revisa credenciales."]
            
            # Si el login fue bien, volvemos a pedir la página de cursos
            response_cursos = session.get(URL_CURSOS, headers=headers)

        # 2. EXTRACCIÓN DE DATOS (Igual que antes)
        soup = BeautifulSoup(response_cursos.text, 'html.parser')
        novedades_encontradas = []
        
        semestre_actual = soup.find('div', class_='panel-group')
        if not semestre_actual:
            return ["No se encontró el bloque del semestre."]

        cursos = semestre_actual.find_all('div', class_='row')

        for curso in cursos:
            titulo_tag = curso.find('h4', class_='course-items-title')
            if not titulo_tag: continue
            
            nombre_curso = titulo_tag.find('a').text.strip()
            iconos_nuevos = titulo_tag.find_all('img', alt=lambda value: value and 'Desde su última visita' in value)
            
            if iconos_nuevos:
                mensaje_curso = f"🔔 *NOVEDAD EN:* {nombre_curso}\n"
                for icono in iconos_nuevos:
                    detalle = icono.get('alt')
                    link = icono.parent.get('href')
                    mensaje_curso += f"   • {detalle}\n   • [Enlace directo]({link})\n"
                
                novedades_encontradas.append(mensaje_curso)
                
        return novedades_encontradas

    except Exception as e:
        print(f"Error técnico: {e}")
        return [f"Error técnico: {e}"]

# ==========================================
# 3. BUCLE AUTOMÁTICO (Programado a las :00 y :30)
# ==========================================
def bucle_automatico():
    while True:
        ahora = datetime.now()
        
        # Calculamos cuántos minutos faltan para el próximo :00 o :30
        if ahora.minute < 30:
            minutos_faltantes = 30 - ahora.minute
        else:
            minutos_faltantes = 60 - ahora.minute
            
        # Lo convertimos a segundos y le restamos los segundos actuales para ser 100% exactos
        segundos_a_esperar = (minutos_faltantes * 60) - ahora.second
        
        hora_proxima = ahora.minute + minutos_faltantes
        if hora_proxima == 60: hora_proxima = "00"
        
        print(f"Zzz... El bot dormirá {minutos_faltantes} minutos. Próxima revisión exacta a las XX:{hora_proxima}")
        
        # El bot se pausa exactamente el tiempo necesario
        time.sleep(segundos_a_esperar)
        
        # --- DESPIERTA A LA HORA EN PUNTO ---
        print("⏰ ¡Hora en punto! Ejecutando revisión automática...")
        novedades = revisar_efinis()
        
        if novedades and "Error" not in novedades[0] and "No se encontró" not in novedades[0]:
            for novedad in novedades:
                bot.send_message(CHAT_ID_DESTINO, novedad, parse_mode='Markdown')

# ==========================================
# 4. INTERACCIÓN CON TELEGRAM
# ==========================================
@bot.message_handler(commands=['start', 'ayuda'])
def enviar_bienvenida(message):
    bot.reply_to(message, f"¡Hola! Tu Chat ID es: `{message.chat.id}`. Ponlo en la configuración del script.")

@bot.message_handler(commands=['revisar'])
def comando_revisar(message):
    bot.send_message(message.chat.id, "⏳ Revisando eFinis...")
    novedades = revisar_efinis()
    
    if not novedades:
        bot.send_message(message.chat.id, "✅ Todo limpio.")
    else:
        for novedad in novedades:
            bot.send_message(message.chat.id, novedad, parse_mode='Markdown')

# ==========================================
# 5. ARRANQUE
# ==========================================
if __name__ == '__main__':
    # Arrancamos el hilo automático en segundo plano
    hilo_revision = threading.Thread(target=bucle_automatico)
    hilo_revision.daemon = True # Esto hace que el hilo se cierre si detienes el script
    hilo_revision.start()
    
    print("Bot iniciado y escuchando comandos...")
    bot.infinity_polling()