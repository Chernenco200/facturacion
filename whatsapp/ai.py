from .openai_client import client
from .prompts import PROMPT_OPTICA_IC

def responder_con_openai(texto_cliente):
    try:
        print("OPENAI INICIO")

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": PROMPT_OPTICA_IC},
                {"role": "user", "content": texto_cliente},
            ],
            max_output_tokens=200,
        )

        print("OPENAI RESPONSE OK")

        respuesta = response.output_text.strip()

        if not respuesta:
            print("OPENAI RESPUESTA VACIA")
            return "Claro 😊 ¿Podrías contarme un poco más para ayudarte mejor?"

        return respuesta

    except Exception as e:
        print("ERROR OPENAI TIPO:", type(e))
        print("ERROR OPENAI DETALLE:", repr(e))
        return (
            "Disculpa, en este momento no puedo responder esa consulta automáticamente. "
            "Un asesor de Óptica IC continuará con la atención 😊"
        )