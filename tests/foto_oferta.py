"""Foto mínima, mas com assinatura e estrutura de JPEG real, para publicar ofertas nos testes."""
import json
from io import BytesIO

# SOI, APP0 (JFIF), SOS com dois bytes de imagem e EOI
JPEG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34\xff\xd9")


def com_foto(corpo, foto=JPEG, nome="validade.jpg"):
    """Corpo multipart de POST /reconecta/excedentes: `dados` em JSON e a `foto`."""
    return {"dados": json.dumps(corpo), "foto": (BytesIO(foto), nome)}
