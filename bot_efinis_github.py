import telebot
import requests
from bs4 import BeautifulSoup
import time
import threading

# ==========================================
# 1. CONFIGURACIÓN (REEMPLAZA ESTOS DATOS)
# ==========================================
# El token que te dio BotFather
TOKEN_TELEGRAM = "TU_TOKEN_DE_TELEGRAM_AQUI" 

# Tus credenciales de la universidad
RUT_EFINIS = "tu_rut_aqui"
PASS_EFINIS = "tu_contraseña_aqui"

# Inicializamos el bot
bot = telebot.TeleBot(TOKEN_TELEGRAM)

# URL para el login
URL_LOGIN = "https://efinis.uft.cl/index.php" # Generalmente el POST se hace a index
# URL a la que queremos ir después de loguearnos (donde están los cursos)
URL_CURSOS = "https://efinis.uft.cl/user_portal.php"

# ==========================================
# 2. FUNCIÓN DE SCRAPING (NÚCLEO)
# ==========================================
def revisar_efinis():
    print("Iniciando revisión de eFinis...")
    
    # Creamos una sesión persistente (guarda las cookies por nosotros)
    session = requests.Session()
    
    # El Payload que descubriste en F12
    payload_login = {
        "login": RUT_EFINIS,
        "password": PASS_EFINIS,
        "submitAuth": "",
        "_qf_formLogin": ""
    }
    
    # Cabeceras para simular que somos un navegador real y no un script
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # Paso A: Hacemos el POST de login
        response_login = session.post(URL_LOGIN, data=payload_login, headers=headers)
        
        # Comprobamos si el login falló (a veces responden con código 200 pero el HTML dice "error")
        if "Contraseña incorrecta" in response_login.text or "Error" in response_login.text:
             print("Error de credenciales al loguear.")
             return ["Error al iniciar sesión en eFinis. Revisa tus credenciales."]

        # Paso B: Vamos a la página de los cursos (la sesión lleva las cookies automáticamente)
        response_cursos = session.get(URL_CURSOS, headers=headers)
        
        # Extraemos el HTML
        soup = BeautifulSoup(response_cursos.text, 'html.parser')
        
        # --- AQUÍ VA LA LÓGICA QUE PROBAMOS ANTES ---
        novedades_encontradas = []
        
        # 1. Buscar el semestre actual (el primer bloque)
        semestre_actual = soup.find('div', class_='panel-group')
        
        if not semestre_actual:
            return ["No se encontró el bloque del semestre. ¿Cambió el diseño de la página?"]

        # 2. Buscar cursos dentro de ese semestre
        cursos = semestre_actual.find_all('div', class_='row')

        for curso in cursos:
            titulo_tag = curso.find('h4', class_='course-items-title')
            if not titulo_tag: continue
            
            nombre_curso = titulo_tag.find('a').text.strip()
            
            # Buscar íconos de "Novedad"
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
        print(f"Error técnico durante el scraping: {e}")
        return [f"Ocurrió un error técnico al intentar revisar eFinis: {e}"]

# ==========================================
# 3. INTERACCIÓN CON TELEGRAM
# ==========================================

# Comando /start
@bot.message_handler(commands=['start', 'ayuda'])
def enviar_bienvenida(message):
    bot.reply_to(message, "¡Hola Alonso! Soy tu bot rastreador de eFinis 🎓.\nUsa el comando /revisar para forzar una comprobación manual ahora mismo.")

# Comando /revisar (Para probar manualmente sin esperar 30 mins)
@bot.message_handler(commands=['revisar'])
def comando_revisar(message):
    bot.send_message(message.chat.id, "⏳ Conectando con eFinis y buscando novedades...")
    
    # Ejecutamos la función núcleo
    novedades = revisar_efinis()
    
    if not novedades:
        bot.send_message(message.chat.id, "✅ Todo limpio. No hay novedades desde tu última visita.")
    else:
        # Si hay novedades, enviamos un mensaje por cada curso
        for novedad in novedades:
            # parse_mode='Markdown' permite usar negritas (*) y links agradables
            bot.send_message(message.chat.id, novedad, parse_mode='Markdown')

# ==========================================
# 4. BUCLE PRINCIPAL (ARRANQUE)
# ==========================================
if __name__ == '__main__':
    print("Bot iniciado y escuchando comandos...")
    # Esto mantiene al script corriendo y escuchando a Telegram
    bot.infinity_polling()