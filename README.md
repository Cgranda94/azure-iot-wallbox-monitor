# Sistema de Monitoreo IoT Wallbox con IA 🔌🤖

Este proyecto implementa una arquitectura Serverless en Azure para la gestión y diagnóstico de cargadores de vehículos eléctricos.

## Arquitectura 🏗️
1. **Ingesta IoT:** Azure Functions (Python) para recibir telemetría.
2. **Base de Datos:** Azure Cosmos DB (NoSQL) para persistencia en tiempo real.
3. **Agente de IA:** Integración con Google Gemini 2.5 Flash para interpretar códigos de error y dar soporte automatizado al cliente.

## Stack Tecnológico 🛠️
- Python 3.10
- Azure Functions (V2 Model)
- Azure Cosmos DB
- Google Generative AI (Gemini)

## Cómo funciona
El sistema recibe un JSON con el estado del cargador, detecta anomalías ("Faulted") y permite consultar a un agente inteligente que sugiere soluciones técnicas basadas en el estado real del dispositivo.
