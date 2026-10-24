import re
import unicodedata
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType
from prospector.config import STOPWORDS_NOME


def normalizar_nome(nome: str) -> str:
    """Remove acentos, converte para minúsculas e troca não-alfanuméricos por espaço."""
    if not nome:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(nome))
        if not unicodedata.combining(c)
    )
    limpo = re.sub(r"[^a-z0-9]+", " ", sem_acento.lower())
    return " ".join(limpo.split())


def nucleo_nome(nome: str) -> str:
    """Devolve o nome normalizado sem palavras genéricas (stopwords)."""
    palavras = [p for p in normalizar_nome(nome).split() if p not in STOPWORDS_NOME]
    return " ".join(palavras)


def normalizar_telefone(bruto: str, ddd: str = "") -> str:
    """Normaliza telefone brasileiro para formato E.164 (+55...) ou vazio se inválido."""
    if not bruto:
        return ""
    primeiro = str(bruto).split(";")[0].strip()
    if not primeiro:
        return ""

    ddd_limpo = "".join(c for c in str(ddd or "") if c.isdigit()).lstrip("0")
    if ddd_limpo:
        digitos = "".join(c for c in primeiro if c.isdigit())
        if digitos.startswith("0") and len(digitos) > 8:
            digitos = digitos[1:]
        if len(digitos) == 8 and digitos[0] in "6789":
            digitos = "9" + digitos
        candidato = ddd_limpo + digitos
    else:
        candidato = re.sub(r"^0+", "", primeiro)

    try:
        parsed = phonenumbers.parse(candidato, "BR")
    except NumberParseException:
        return ""

    if not phonenumbers.is_valid_number_for_region(parsed, "BR"):
        return ""

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def link_whatsapp(telefone_e164: str) -> str:
    """Gera link wa.me apenas quando o telefone E.164 é celular."""
    if not telefone_e164:
        return ""
    try:
        parsed = phonenumbers.parse(str(telefone_e164), "BR")
    except NumberParseException:
        return ""
    if phonenumbers.number_type(parsed) == PhoneNumberType.MOBILE:
        digitos = "".join(c for c in str(telefone_e164) if c.isdigit())
        return f"https://wa.me/{digitos}"
    return ""
