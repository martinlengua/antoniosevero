import subprocess
from openai import OpenAI
import vosk
import sounddevice as sd
import queue
import json
import time
import assist
import os
import re

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

# Inicializa el cliente de OpenAI (asegúrate de tener tus credenciales configuradas correctamente)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Cola para capturar el audio
q = queue.Queue()

# Callback para capturar el audio en tiempo real
def callback(indata, frames, time, status):
    q.put(bytes(indata))

def get_azure_access_token():
    """Obtiene el token de acceso de Azure CLI para interactuar con la API de Azure."""
    try:
        # Ejecutar el comando az para obtener el token
        result = subprocess.run(["az", "account", "get-access-token"], capture_output=True, text=True, check=True)
        # Parsear el resultado JSON y obtener el token de acceso
        token_info = json.loads(result.stdout)
        access_token = token_info['accessToken']
        return access_token
    except subprocess.CalledProcessError as e:
        print(f"Error al obtener el token de acceso: {e.stderr}")
        return None

# Inicializar la lista que guardará el contexto de la conversación
conversation_history = []

# Función para agregar un mensaje al historial de la conversación
def update_conversation_history(role, content):
    conversation_history.append({"role": role, "content": content})

def ask_openai(question):

    # Obtener el token de acceso de Azure CLI
    access_token = get_azure_access_token()

    # Actualizamos el historial con la nueva entrada del usuario
    update_conversation_history("user", question)
    
    # Llamada a OpenAI para obtener el comando az cli
    response = client.chat.completions.create(
        model="gpt-4",  # Usa el modelo adecuado
        messages=conversation_history,  # Enviar todo el historial de la conversación
        max_tokens=150,
        n=1,
        stop=None,
        temperature=0.5
    )
    
    # Obtener la respuesta
    answer = response.choices[0].message.content.strip()
    
    # Actualizar el historial con la respuesta de la IA
    update_conversation_history("assistant", answer)
    
    return answer

def start_listening(model):
    """Inicia la captura de audio y transcripción usando Vosk."""
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        rec = vosk.KaldiRecognizer(model, 16000)

        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = rec.Result()
                result_dict = json.loads(result)
                current_text = result_dict.get("text", "")

                if current_text:
                    print(f"User: {current_text}")
                    return current_text
            else:
                partial_result = rec.PartialResult()
                print(json.loads(partial_result).get("partial", ""))

def extraer_comando_az(output):
    try:
        # Expresión regular que busca una línea que comience con 'az' seguida de cualquier otra cosa
        match = re.search(r'\baz\s+.*', output)
        
        if match:
            # Extraer el comando encontrado
            comando_limpio = match.group(0).strip()
            return comando_limpio
        else:
            return "No se encontró un comando de az CLI en el texto proporcionado."
    
    except Exception as e:
        return f"Ocurrió un error: {str(e)}"

# Llama a la función con el output y filtra el comando
comando_az = extraer_comando_az(output)
print(f"Comando extraído: {comando_az}")


def execute_command(command):
    """Ejecuta un comando en el sistema usando subprocess."""
    show_session="az account list"
    try:
        session = subprocess.run(show_session, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Resultado del comando:\n{result.stdout.decode()}")
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el comando:\n{e.stderr.decode()}")

if __name__ == '__main__':
    # Cargar el modelo de vosk en español
    ####model = vosk.Model("/Users/martinlengua_1/Downloads/vosk-model-es-0.42")  # Reemplaza con la ruta a tu modelo de Vosk

    hot_words = ["travis"]
    skip_hot_word_check = True

    print("Diga algo en español...")

    while True:
        # Escuchar el audio y obtener el texto transcrito
        current_text = "dame la lista de subscripciones de mi tenant"
#####        current_text = start_listening(model)

        if any(hot_word in current_text.lower() for hot_word in hot_words) or skip_hot_word_check:
            # Concatenar la fecha y hora al texto hablado
            current_text = current_text + " " + time.strftime("%Y-%m-%d %H-%M-%S")

            # Consultar a OpenAI el comando AZ CLI basado en la conversación
            print("Consultando ChatGPT para obtener el comando AZ CLI...")
            response = ask_openai(f"Genera un comando de az cli para lo siguiente: {current_text}")

            # Imprimir el comando sugerido por OpenAI
            print("Comando sugerido por OpenAI: " + response)

            #Filtrar comando
            extraer_comando_az(response)

            # Confirmar si el usuario quiere ejecutar el comando
            confirm = input("¿Quieres ejecutar este comando? (si/no): ").strip().lower()
            if confirm == "si":
                # Ejecutar el comando mediante subprocess
                print("Ejecutando el comando...")
                print(response)
                execute_command(response)

            # Usar TTS para responder en voz (si tienes esa función en assist)
            done = assist.TTS(response)

            # Pausa un momento antes de reiniciar la captura de audio
            time.sleep(2)

            # Continuar escuchando después de procesar la respuesta
            skip_hot_word_check = True if "?" in response else False