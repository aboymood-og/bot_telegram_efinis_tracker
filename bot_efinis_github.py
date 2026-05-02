import telebot
import requests
from bs4 import BeautifulSoup
import time
import threading
from datetime import datetime, timedelta
import json
import re
from urllib.parse import urlparse, parse_qs

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
TOKEN_TELEGRAM = "TU_TOKEN_DE_TELEGRAM_AQUI"
RUT_EFINIS = "tu_rut_aqui"
PASS_EFINIS = "tu_contraseña_aqui"
CHAT_ID_DESTINO = "TU_CHAT_ID"

bot = telebot.TeleBot(TOKEN_TELEGRAM)

URL_LOGIN = "https://efinis.uft.cl/index.php"
URL_CURSOS = "https://efinis.uft.cl/user_portal.php"

#Inicializamos la sesión a nivel GLOBAL para que guarde las cookies entre revisiones
session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 2. FUNCIONES AUXILIARES (CASOS DE USO)
# ==========================================
def log_terminal(mensaje):
    """Genera un log en la terminal con la fecha y hora exactas y un salto de línea."""
    hora_actual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n[{hora_actual}] {mensaje}")


    
def rastrear_documento_nuevo(url_carpeta, nombre_curso, session, ruta_actual=""):
    """
    Navega por las carpetas buscando el archivo más reciente (últimos 35 mins).
    Usa recursividad para entrar en subcarpetas.
    """
    # --- EL hack DE LA PAGINACIÓN ---
    # Revisamos si la URL ya tiene el símbolo '?' para saber si añadir un '&' o un '?'
    separador = '&' if '?' in url_carpeta else '?'
    
    # Inyectamos el parámetro brutal que descubriste (le pongo 1000 por si algún profe enloquece subiendo cosas)
    url_optimizada = f"{url_carpeta}{separador}student_table_per_page=1000"
    
    # Hacemos la petición a la carpeta forzando a que muestre todo
    response = session.get(url_optimizada)
    response = session.get(url_carpeta)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Buscamos la tabla de documentos
    tabla = soup.find('table', class_='data_table')
    
    # Caso: Tabla no existe (Sección vacía o bloqueada)
    if not tabla:
        if ruta_actual: # Significa que crearon una carpeta y no le pusieron nada dentro
            return f"📁 *{nombre_curso}*\n   • Se detectó la creación de la carpeta `{ruta_actual}` (actualmente vacía).\n   • [Enlace a la carpeta]({url_carpeta})"
        else: # Oculto en la raíz
            return f"❓ *{nombre_curso}*\n   • Se añadió un archivo pero está oculto por el profesor o hubo un error.\n   • [Enlace a Documentos]({url_carpeta})"
            
    filas = tabla.find_all('tr')[1:] # Ignoramos la primera fila (los encabezados)
    
    elemento_mas_reciente = None
    fecha_maxima = datetime.min
    # Usamos 35 mins de margen para evitar perder algo si el ciclo se retrasa unos segundos
    limite_tiempo = datetime.now() - timedelta(minutes=35) 
    
    # Recorremos cada fila para extraer fechas
    for fila in filas:
        columnas = fila.find_all('td')
        if len(columnas) < 4: continue
        
        # 1. ¿Es carpeta o archivo? (Miramos el ícono en la primera columna)
        es_carpeta = False
        img_tag = columnas[0].find('img')
        if img_tag and 'folder' in img_tag.get('src', ''):
            es_carpeta = True
            
        # 2. Nombre y Link (Segunda columna)
        a_tag = columnas[1].find('a')
        nombre = a_tag.text.strip()
        link = a_tag['href']
        if link.startswith('/'): # Prevenir rutas relativas
            link = "https://efinis.uft.cl" + link
            
        # 3. Extraer la fecha del span oculto (Cuarta columna)
        span_fecha = columnas[3].find('span')
        if span_fecha:
            try:
                # Convertimos el string "2026-04-30 08:48:21" a un objeto de tiempo real
                fecha_obj = datetime.strptime(span_fecha.text.strip(), "%Y-%m-%d %H:%M:%S")
                
                # Vamos guardando siempre el que sea más nuevo
                if fecha_obj > fecha_maxima:
                    fecha_maxima = fecha_obj
                    elemento_mas_reciente = {
                        "nombre": nombre,
                        "link": link,
                        "es_carpeta": es_carpeta,
                        "fecha": fecha_obj
                    }
            except ValueError:
                continue

    # ==========================================
    # LÓGICA DE DECISIÓN BASADA EN LO ENCONTRADO
    # ==========================================
    
    # Si encontramos algo y ese algo fue subido en los últimos 35 minutos
    if elemento_mas_reciente and elemento_mas_reciente['fecha'] >= limite_tiempo:
        
        if elemento_mas_reciente['es_carpeta']:
            # RECURSIVIDAD: Si es carpeta, construimos la ruta y volvemos a llamar a la función
            nueva_ruta = f"{ruta_actual}/{elemento_mas_reciente['nombre']}"
            return rastrear_documento_nuevo(elemento_mas_reciente['link'], nombre_curso, session, nueva_ruta)
            
        else:
            # ES ARCHIVO: Fin de la búsqueda, tenemos a nuestro ganador
            ruta_final = f"{ruta_actual}/{elemento_mas_reciente['nombre']}"
            return f"📄 *{nombre_curso}*\n   • Se añadió un archivo: `{ruta_final}`\n   • [Descargar/Ver archivo]({elemento_mas_reciente['link']})"
            
    else:
        # Nada superó el límite de tiempo. Es el caso de archivos ocultos o carpetas vacías.
        if ruta_actual:
            return f"📁 *{nombre_curso}*\n   • Se detectó una nueva carpeta vacía o con archivos ocultos en: `{ruta_actual}`\n   • [Ver carpeta]({url_carpeta})"
        else:
            return f"❓ *{nombre_curso}*\n   • Se añadió un archivo pero está oculto por el profesor o hubo un error de plataforma.\n   • [Enlace a Documentos]({url_carpeta})"

def procesar_anuncio_nuevo(url_anuncios, nombre_curso, session):
    """
    Consulta la API AJAX de Chamilo para obtener los anuncios.
    Filtra los recientes y extrae información extra (como adjuntos).
    """
    # 1. Extraer el 'cidReq' (ID del curso) de la URL que nos llega del Dashboard
    # Ej: de "https://.../announcements.php?cidReq=2621902&..." sacamos "2621902"
    
    parsed_url = urlparse(url_anuncios)
    cid_req = parse_qs(parsed_url.query).get('cidReq', [None])[0]
    
    if not cid_req:
        return f"❓ *{nombre_curso}*\n   • Hubo un error procesando el enlace del anuncio.\n   • [Enlace a Anuncios]({url_anuncios})"

    # 2. Armar la URL de la API secreta de jqGrid (la que descubrimos en el HTML)
    api_url = f"https://efinis.uft.cl/main/inc/ajax/model.ajax.php?a=get_course_announcements&cidReq={cid_req}&id_session=0&gidReq=0&gradebook=0&origin=&title_to_search=&user_id_to_search=0&rows=20&page=1"
    
    response = session.get(api_url)
    
    try:
        data = response.json()
        filas = data.get('rows', [])
    except json.JSONDecodeError:
        return f"❓ *{nombre_curso}*\n   • Error al leer los anuncios (la plataforma no respondió correctamente).\n   • [Enlace a Anuncios]({url_anuncios})"

    if not filas:
         return f"❓ *{nombre_curso}*\n   • Se detectó un anuncio pero la lista aparece vacía.\n   • [Enlace a Anuncios]({url_anuncios})"

    # Usamos 35 mins de margen
    limite_tiempo = datetime.now() - timedelta(minutes=35) 
    
    mensajes_novedades = []

    # 3. Procesar las filas del JSON
    # jqGrid devuelve una lista de diccionarios. La clave 'cell' contiene los datos.
    for fila in filas:
        celdas = fila.get('cell', [])
        if len(celdas) < 4: continue
        
        html_titulo = celdas[0]
        # Usamos bs4 rapidito para limpiar el HTML que viene dentro del JSON
        soup_titulo = BeautifulSoup(html_titulo, 'html.parser')
        
        a_tag = soup_titulo.find('a')
        if not a_tag: continue
        
        titulo_limpio = a_tag.text.strip()
        link_anuncio = a_tag['href']
        
        # Revisamos si hay ícono de clip (Adjunto)
        tiene_adjunto = bool(soup_titulo.find('i', class_='fa-paperclip'))
        
        html_autor = celdas[1]
        soup_autor = BeautifulSoup(html_autor, 'html.parser')
        autor_limpio = soup_autor.text.strip()
        
        fecha_str = celdas[2] # Ej: "30 de Abril 2026 a las 08:48 AM"
        
        # Aquí viene un truco: Como la fecha viene en texto muy coloquial en español, 
        # intentar parsearla con datetime es un infierno.
        # Estrategia: Asumiremos que si el script llegó hasta aquí empujado por el ícono 
        # de la campanita del Dashboard (que ya filtró por "última visita"), 
        # entonces los primeros anuncios de la lista SON la novedad.
        
        # Extraemos el contenido del anuncio haciendo una petición a su vista individual
        response_vista = session.get(link_anuncio)
        soup_vista = BeautifulSoup(response_vista.text, 'html.parser')
        
        # 1. Aislamos el contenido central (Ignoramos el menú superior para no agarrar tu nombre/correo)
        area_central = soup_vista.find('section', id='cm-content') or soup_vista
        
        cuerpo_anuncio = ""
        
        # 2. Buscamos el panel principal donde Chamilo guarda el texto del anuncio
        panel_contenido = area_central.find('div', class_='panel-body')
        
        if panel_contenido:
            # El truco de oro: get_text(separator) respeta los <br> y <p> como saltos de línea reales
            cuerpo_anuncio = panel_contenido.get_text(separator='\n\n', strip=True)
        else:
             # Fallback seguro: buscar párrafos solo en el área central (sin el menú)
             textos = [p.get_text(separator='\n', strip=True) for p in area_central.find_all('p')]
             cuerpo_anuncio = "\n\n".join(textos).strip()
             
        # Lógica de [Leer más]
        # Le subimos el límite a 450 porque los saltos de línea ocupan "espacio"
        if len(cuerpo_anuncio) > 450: 
             cuerpo_anuncio = cuerpo_anuncio[:450] + "...\n\n[Leer más]"

        # Armado del Mensaje Final
        mensaje = f"🔔 *NUEVO ANUNCIO EN:* {nombre_curso}\n"
        mensaje += f"   • *Asunto:* {titulo_limpio}\n"
        mensaje += f"   • *Autor:* {autor_limpio}\n"
        mensaje += f"   • *Fecha:* {fecha_str}\n"
        
        if tiene_adjunto:
             mensaje += f"   • 📎 *¡Atención!* Este anuncio incluye un archivo adjunto.\n"
             
        mensaje += f"\n   *Mensaje:*\n   _{cuerpo_anuncio}_\n"
        mensaje += f"\n   • [Ir al Anuncio]({link_anuncio})"
        
        mensajes_novedades.append(mensaje)
        
        # Solo procesamos el primer (o primeros) anuncios nuevos de la lista para no saturar.
        # Si hay más de uno, la paginación u otras revisiones lo atraparán.
        break # Detenemos el loop tras el anuncio más reciente (el primero en la lista JSON)

    if mensajes_novedades:
        return "\n\n".join(mensajes_novedades)
    else:
        return f"❓ *{nombre_curso}*\n   • No se pudo extraer la información del anuncio nuevo.\n   • [Enlace a Anuncios]({url_anuncios})"

def procesar_tarea_nueva(url_tarea, nombre_curso, session):
    """
    Consulta la API AJAX para Tareas. 
    Busca la tarea más reciente (por ID) y detecta tareas a punto de vencer.
    """
    
    parsed_url = urlparse(url_tarea)
    cid_req = parse_qs(parsed_url.query).get('cidReq', [None])[0]
    
    if not cid_req:
        return f"❓ *{nombre_curso}*\n   • Hubo un error procesando el enlace de la tarea.\n   • [Ir a Tareas]({url_tarea})"

    api_url = f"https://efinis.uft.cl/main/inc/ajax/model.ajax.php?a=get_work_student&cidReq={cid_req}&id_session=0&gidReq=0&gradebook=0&origin=&rows=50&page=1"
    response = session.get(api_url)
    
    try:
        data = response.json()
        filas = data.get('rows', [])
    except Exception:
        return f"❓ *{nombre_curso}*\n   • Error al leer las tareas.\n   • [Ir a Tareas]({url_tarea})"

    if not filas:
         return f"❓ *{nombre_curso}*\n   • El ícono indica tarea, pero la lista está vacía.\n   • [Ir a Tareas]({url_tarea})"

    ahora = datetime.now()
    tareas_parseadas = []

    # 1. PARSEAR TODAS LAS TAREAS DE LA LISTA
    for fila in filas:
        celdas = fila.get('cell', [])
        if len(celdas) < 5: continue
        
        soup_titulo = BeautifulSoup(celdas[1], 'html.parser')
        a_tag = soup_titulo.find('a')
        if not a_tag: continue
        
        titulo_limpio = a_tag.text.strip()
        link_tarea = a_tag['href']
        if link_tarea.startswith('/'): link_tarea = "https://efinis.uft.cl" + link_tarea
            
        # Extraer el ID mágico de la tarea
        match_id = re.search(r'id=(\d+)', link_tarea)
        tarea_id = int(match_id.group(1)) if match_id else 0

        fecha_limite_str = celdas[2]
        ultima_subida_str = celdas[4]
        
        tiene_fecha_limite = bool(fecha_limite_str and "&nbsp;" not in fecha_limite_str)
        fecha_limite_obj = None
        
        if tiene_fecha_limite:
            fecha_limite_obj = datetime.strptime(fecha_limite_str, "%Y-%m-%d %H:%M:%S")
            str_imprimir_vencimiento = fecha_limite_obj.strftime("%d/%m/%Y a las %H:%M")
        else:
            str_imprimir_vencimiento = "Sin fecha límite"

        ya_entregada = bool(ultima_subida_str and "&nbsp;" not in ultima_subida_str)

        tareas_parseadas.append({
            'id': tarea_id,
            'titulo': titulo_limpio,
            'link': link_tarea,
            'vence_obj': fecha_limite_obj,
            'vence_str': str_imprimir_vencimiento,
            'ya_entregada': ya_entregada,
            'ultima_subida_str': ultima_subida_str
        })

    # ==========================================
    # LÓGICA DE DECISIÓN: NUEVA VS RECORDATORIO
    # ==========================================
    mensajes_finales = []
    
    # Encontramos la tarea con el ID más alto (La real "última subida por el profe")
    tarea_mas_nueva = max(tareas_parseadas, key=lambda x: x['id'])
    
    # Filtramos tareas que estén por vencer (menos de 48 horas y no entregadas)
    tareas_recordatorio = []
    for t in tareas_parseadas:
        if t['vence_obj'] and not t['ya_entregada']:
            tiempo_restante = t['vence_obj'] - ahora
            if 0 < tiempo_restante.total_seconds() <= (48 * 3600):
                # Evitamos duplicados si la tarea nueva TAMBIÉN es urgente
                if t['id'] != tarea_mas_nueva['id']:
                    tareas_recordatorio.append(t)

    # Función interna para no repetir código de scraping
    def obtener_instrucciones(link):
        resp = session.get(link)
        s = BeautifulSoup(resp.text, 'html.parser')
        area = s.find('section', id='cm-content') or s
        caja = area.find('div', class_='alert-info') or area.find('div', class_='description')
        if caja: return caja.get_text(separator='\n\n', strip=True)
        textos = [p.get_text(separator='\n', strip=True) for p in area.find_all('p')]
        return "\n\n".join(textos).strip()

    # --- ARMAR MENSAJE: TAREA NUEVA ---
    inst_nueva = obtener_instrucciones(tarea_mas_nueva['link'])
    if len(inst_nueva) > 300: inst_nueva = inst_nueva[:300] + "...\n\n[Leer más en eFinis]"
    elif not inst_nueva: inst_nueva = "Sin instrucciones adicionales."
    
    msg_nueva = f"📝 *NUEVA TAREA EN:* {nombre_curso}\n\n"
    msg_nueva += f"   • *Título:* {tarea_mas_nueva['titulo']}\n"
    msg_nueva += f"   • *Vence:* {tarea_mas_nueva['vence_str']}\n"
    
    if tarea_mas_nueva['ya_entregada']:
         f_subida = datetime.strptime(tarea_mas_nueva['ultima_subida_str'], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y a las %H:%M")
         msg_nueva += f"   • ✅ *ESTADO:* YA SUBISTE ESTA TAREA el {f_subida}\n"
    else:
         msg_nueva += f"   • ❌ *ESTADO:* Sin enviar\n"
         
    msg_nueva += f"\n   *Instrucciones:*\n   _{inst_nueva}_\n"
    msg_nueva += f"\n   • [Ir a la Tarea]({tarea_mas_nueva['link']})"
    
    mensajes_finales.append(msg_nueva)

    # --- ARMAR MENSAJE(S): RECORDATORIOS ---
    for tr in tareas_recordatorio:
        inst_rec = obtener_instrucciones(tr['link'])
        if len(inst_rec) > 300: inst_rec = inst_rec[:300] + "...\n\n[Leer más en eFinis]"
        elif not inst_rec: inst_rec = "Sin instrucciones."
        
        msg_rec = f"🚨 *RECORDATORIO URGENTE:* {nombre_curso}\n"
        msg_rec += f"   _¡Yapo, sube la tarea! Queda poco tiempo._\n\n"
        msg_rec += f"   • *Título:* {tr['titulo']}\n"
        msg_rec += f"   • *Vence:* {tr['vence_str']}\n"
        msg_rec += f"   • ❌ *ESTADO:* Sin enviar\n"
        msg_rec += f"\n   *Instrucciones:*\n   _{inst_rec}_\n"
        msg_rec += f"\n   • [Ir a la Tarea]({tr['link']})"
        
        mensajes_finales.append(msg_rec)

    # Devolvemos todos los mensajes juntos (por si hay una tarea nueva Y un recordatorio simultáneos)
    return "\n\n".join(mensajes_finales)

# ==========================================
# 3. FUNCIÓN DE SCRAPING (OPTIMIZADA)
# ==========================================
def revisar_efinis(origen="Automático"):
    global session 
    
    try:
        response_cursos = session.get(URL_CURSOS, headers=headers)
        
        if "Mis cursos" not in response_cursos.text or "Ocurrió un error" in response_cursos.text:
            log_terminal(f"⚠️ Sesión expirada o no iniciada. Ejecutando Login... (Origen: {origen})")
            
            payload_login = {
                "login": RUT_EFINIS,
                "password": PASS_EFINIS,
                "submitAuth": "",
                "_qf_formLogin": ""
            }
            response_login = session.post(URL_LOGIN, data=payload_login, headers=headers)
            
            if "Contraseña incorrecta" in response_login.text:
                log_terminal("❌ ERROR CRÍTICO: Contraseña incorrecta rechazada por el portal.")
                return ["Error al iniciar sesión. Revisa credenciales."]
            
            log_terminal("✅ Login exitoso. Sesión renovada.")
            response_cursos = session.get(URL_CURSOS, headers=headers)
        else:
            log_terminal(f"⚡ Sesión activa mantenida. Revisando plataforma... (Origen: {origen})")

        # 2. EXTRACCIÓN DE DATOS (El resto de tu función BeautifulSoup queda exactamente igual hacia abajo)
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
                for icono in iconos_nuevos:
                    detalle = icono.get('alt')
                    link = icono.parent.get('href')
                    
                    # Verificamos si el ícono corresponde a la carpeta de documentos
                    if 'folder_document.png' in icono.get('src', ''):
                        mensaje = rastrear_documento_nuevo(link, nombre_curso, session, ruta_actual="Documentos")
                        novedades_encontradas.append(mensaje)
                        
                    # NUEVO: Verificamos si el ícono corresponde a la campanita de Anuncios
                    elif 'valves.png' in icono.get('src', ''):
                        mensaje = procesar_anuncio_nuevo(link, nombre_curso, session)
                        novedades_encontradas.append(mensaje)

                    # NUEVO: Verificamos si el ícono corresponde al Lápiz de Tareas
                    elif 'works.png' in icono.get('src', ''):
                        mensaje = procesar_tarea_nueva(link, nombre_curso, session)
                        novedades_encontradas.append(mensaje)
                        
                    else:
                        mensaje_generico = f"🔔 *NOVEDAD EN:* {nombre_curso}\n   • {detalle}\n   • [Enlace directo]({link})"
                        novedades_encontradas.append(mensaje_generico)
                
        return novedades_encontradas

    except Exception as e:
        print(f"Error técnico: {e}")
        return [f"Error técnico: {e}"]

# ==========================================
# 4. BUCLE AUTOMÁTICO (Cada 15 mins + Modo Sueño)
# ==========================================
def bucle_automatico():
    while True:
        ahora = datetime.now()
        
        # --- MODO SUEÑO: De 00:00 a 07:59 ---
        # Si la hora es menor a 8 (es decir, 0, 1, 2, 3, 4, 5, 6 o 7)
        if 0 <= ahora.hour < 8:
            # Calculamos a qué hora exacta debe despertar (Hoy a las 08:00:00)
            hora_despertar = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
            
            # Calculamos los segundos que faltan hasta esa hora
            segundos_dormir = (hora_despertar - ahora).total_seconds()
            
            log_terminal("🌙 Entrando en MODO SUEÑO. Bucle automático pausado.")
            log_terminal(f"💤 El bot hibernará hasta las 08:00 AM ({(segundos_dormir/3600):.2f} horas).")
            
            # Dormimos el hilo automático de una sola vez
            time.sleep(segundos_dormir)
            log_terminal("☀️ ¡Buenos días! Saliendo del Modo Sueño.")
            
            # Al despertar, usamos 'continue' para reiniciar el ciclo while y sincronizar a los 15 mins
            continue 
        # ------------------------------------
        
        # Matemáticas elegantes para saltos de 15 en 15 (Solo llega aquí si está despierto)
        minutos_faltantes = 15 - (ahora.minute % 15)
        segundos_a_esperar = (minutos_faltantes * 60) - ahora.second
        
        hora_despertar_normal = ahora + timedelta(seconds=segundos_a_esperar)
        hora_str = hora_despertar_normal.strftime("%H:%M:%S")
        
        log_terminal(f"💤 Bot en pausa. Dormirá {minutos_faltantes} minutos. Próximo escaneo a las {hora_str}")
        
        time.sleep(segundos_a_esperar)
        
        log_terminal("⏰ ¡Hora en punto! Disparando revisión automática...")
        novedades = revisar_efinis(origen="Automático")
        
        if novedades and "Error" not in novedades[0] and "No se encontró" not in novedades[0]:
            log_terminal(f"📬 Se encontraron {len(novedades)} novedades. Despachando a Telegram...")
            for novedad in novedades:
                bot.send_message(CHAT_ID_DESTINO, novedad, parse_mode='Markdown')
        else:
            log_terminal("✅ Revisión automática finalizada. Nada nuevo reportado.")

# ==========================================
# 5. INTERACCIÓN CON TELEGRAM
# ==========================================
@bot.message_handler(commands=['start', 'ayuda'])
def enviar_bienvenida(message):
    bot.reply_to(message, f"¡Hola! Tu Chat ID es: `{message.chat.id}`. Ponlo en la configuración del script.")

@bot.message_handler(commands=['revisar'])
def comando_revisar(message):
    log_terminal(f"📱 Petición MANUAL recibida desde Telegram (Usuario: {message.chat.id})")
    bot.send_message(message.chat.id, "⏳ Revisando eFinis...")
    
    novedades = revisar_efinis(origen="Comando Telegram")
    
    if not novedades:
        bot.send_message(message.chat.id, "✅ Todo limpio.")
    else:
        for novedad in novedades:
            bot.send_message(message.chat.id, novedad, parse_mode='Markdown')

# ==========================================
# 6. ARRANQUE
# ==========================================
if __name__ == '__main__':
    # Arrancamos el hilo automático en segundo plano
    hilo_revision = threading.Thread(target=bucle_automatico)
    hilo_revision.daemon = True # Esto hace que el hilo se cierre si detienes el script
    hilo_revision.start()
    
    print("Bot iniciado y escuchando comandos...")
    bot.infinity_polling()