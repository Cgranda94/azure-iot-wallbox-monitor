import azure.functions as func
import logging
import json
import uuid
import os
import google.generativeai as genai

# Intento de importar la librería de Cosmos. 
# Si falla, es porque falta el pip install, pero evitamos que rompa toda la app.
try:
    import azure.cosmos.cosmos_client as cosmos_client
except ImportError:
    logging.error("ERROR CRITICO: No tienes instalada la librería 'azure-cosmos'. Ejecuta 'pip install azure-cosmos' en la terminal.")

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# --- FUNCIÓN 1: RECEPCION (ESCRIBIR) ---
@app.route(route="RecepcionCargador")
@app.cosmos_db_output(arg_name="documentoSalida", 
                      database_name="WallboxDB", 
                      container_name="Telemetria.", 
                      connection="AzureCosmosDBConnectionString")
def RecepcionCargador(req: func.HttpRequest, documentoSalida: func.Out[func.Document]) -> func.HttpResponse:
    logging.info('Procesando datos del cargador...')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("JSON invalido", status_code=400)

    charger_id = req_body.get('chargerId')
    status = req_body.get('status')
    power = req_body.get('powerKW')

    # Lógica de alerta
    es_error = False
    if status == "Faulted":
        es_error = True
        msg = "Alerta guardada."
    else:
        msg = "Datos guardados."

    nuevo_registro = {
        "id": str(uuid.uuid4()),
        "chargerId": charger_id,
        "status": status,
        "powerKW": power,
        "isError": es_error,
        "timestamp": str(uuid.uuid1())
    }

    documentoSalida.set(func.Document.from_json(json.dumps(nuevo_registro)))

    return func.HttpResponse(
            json.dumps({"status": "Accepted", "message": msg}),
            mimetype="application/json",
            status_code=200
    )

# --- FUNCIÓN 2: CONSULTA (LEER) ---
@app.route(route="ConsultarEstado", methods=["GET"])
def ConsultarEstado(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Consultando estado...')
    
    charger_id = req.params.get('chargerId')
    if not charger_id:
        return func.HttpResponse("Falta el parametro ?chargerId=XYZ en la URL", status_code=400)

    try:
        # Conexión manual
        conn_str = os.environ["AzureCosmosDBConnectionString"]
        client = cosmos_client.CosmosClient.from_connection_string(conn_str)
        database = client.get_database_client("WallboxDB")
        container = database.get_container_client("Telemetria.")

        # Query SQL
        query = "SELECT TOP 1 * FROM c WHERE c.chargerId = @cid ORDER BY c._ts DESC"
        params = [{"name": "@cid", "value": charger_id}]

        items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

        if items:
            dato = items[0]
            respuesta = {
                "Cargador": dato.get("chargerId"),
                "Estado_Actual": dato.get("status"),
                "Tiene_Error": dato.get("isError")
            }
            return func.HttpResponse(json.dumps(respuesta), mimetype="application/json", status_code=200)
        else:
            return func.HttpResponse("Cargador no encontrado en base de datos", status_code=404)

    except Exception as e:
        return func.HttpResponse(f"Error interno: {str(e)}", status_code=500)
    
    # --- FUNCIÓN 3: AGENTE DE SOPORTE (VERSIÓN GEMINI) ---
@app.route(route="AgenteSoporte", methods=["POST"])
def AgenteSoporte(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Agente Gemini iniciado...')

    # 1. Recibir datos del usuario
    try:
        req_body = req.get_json()
        pregunta_usuario = req_body.get('mensaje')
        charger_id = req_body.get('chargerId')
    except ValueError:
        return func.HttpResponse("JSON inválido", status_code=400)

    # 2. Consultar Cosmos DB (Igual que antes)
    estado_real = "Desconocido"
    tiene_error = False
    potencia = 0
    
    try:
        # Importamos cliente aquí para asegurar que la librería existe
        import azure.cosmos.cosmos_client as cosmos_client
        
        conn_str = os.environ["AzureCosmosDBConnectionString"]
        client = cosmos_client.CosmosClient.from_connection_string(conn_str)
        database = client.get_database_client("WallboxDB")
        container = database.get_container_client("Telemetria.")
        
        query = "SELECT TOP 1 * FROM c WHERE c.chargerId = @cid ORDER BY c._ts DESC"
        params = [{"name": "@cid", "value": charger_id}]
        items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
        
        if items:
            estado_real = items[0].get("status")
            tiene_error = items[0].get("isError")
            potencia = items[0].get("powerKW")
            
    except Exception as e:
        logging.error(f"Error BD: {str(e)}")

    # 3. INTELIGENCIA CON GEMINI
    # Recuperamos la clave de las variables de entorno (o ponla directa aquí para probar rápido)
    gemini_key = os.environ.get("GEMINI_API_KEY") 
    
    respuesta_bot = ""

    if gemini_key:
        try:
            # Configurar Gemini
            genai.configure(api_key=gemini_key)
            
            # Usamos el modelo rápido "gemini-1.5-flash"
            model = genai.GenerativeModel('gemini-2.5-flash')

            # Construimos el Prompt
            prompt_completo = f"""
            Actúa como un ingeniero de soporte técnico experto de Wallbox.
            
            CONTEXTO TÉCNICO DEL CARGADOR {charger_id}:
            - Estado actual en base de datos: {estado_real}
            - ¿Tiene error activo?: {tiene_error}
            - Potencia actual: {potencia} kW
            
            PREGUNTA DEL CLIENTE:
            "{pregunta_usuario}"
            
            INSTRUCCIONES:
            - Analiza el estado técnico y responde al cliente.
            - Si el estado es 'Faulted', sé empático y sugiere reiniciar las protecciones.
            - Si es 'Charging', confirma que todo está bien.
            - Responde en español, sé breve y profesional.
            """

            # Generar respuesta
            response = model.generate_content(prompt_completo)
            respuesta_bot = response.text

        except Exception as e:
            respuesta_bot = f"Error conectando con Gemini: {str(e)}"
    else:
        respuesta_bot = "[ERROR] No configuraste la GEMINI_API_KEY en local.settings.json"

    return func.HttpResponse(
        json.dumps({"respuesta": respuesta_bot}),
        mimetype="application/json",
        status_code=200
    )