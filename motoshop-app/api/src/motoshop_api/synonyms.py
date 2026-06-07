"""Diccionario de sinónimos compartido entre pipeline y API en runtime.

Pipeline: enrich_sku_text() → enriquece el nombre del SKU con sinónimos antes de embeber.
API:      expand_query()   → expande la query del usuario con sinónimos antes de feature_extraction.

Keys ordenadas por longitud descendente para evitar falsos positivos
("filtro aire" antes que "filtro").
"""

SYNONYMS = [
    ("filtro aceite", "filtro aceite oil filter elemento cárter"),
    ("filtro aire", "filtro aire air filter elemento depurador admisión"),
    ("pastilla freno", "pastilla freno brake pad disco delantera trasera brembo"),
    ("disco freno", "disco freno brake disc rotor"),
    ("guaya acelerador", "guaya acelerador cable bowden acelerador"),
    ("manija freno", "manija freno embrague clutch manilla maneta"),
    ("amortiguador trasero", "amortiguador trasero monoshock shock suspensión"),
    ("bateria yuasa", "batería yuasa acumulador battery ytz yb"),
    ("bujia ngk", "bujía ngk spark plug cr8e cr9e denso encendido"),
    ("aceite sintetico", "aceite sintético lubricante motor mobil castros 20w50 4t"),
    ("aceite mobil", "aceite mobil lubricante motor sintético 4t 20w50 super"),
    ("cadena transmision", "cadena transmisión chain rk did 428 520 530"),
    ("llanta moto", "llanta moto neumático rin pirelli michelin cubierta"),
    ("bobina encendido", "bobina alta tensión coil ignition spark"),
    ("aceite", "aceite lubricante oil motor sintético 4t 20w50 mobil castros"),
    ("filtro", "filtro elemento depurador filter"),
    ("bujia", "bujía spark plug encendido ngk denso bosch champion"),
    ("bujía", "bujía spark plug encendido ngk denso bosch champion"),
    ("mobil", "mobil aceite lubricante motor 4t 20w50 sintético super"),
    ("ngk", "ngk bujía spark plug encendido"),
    ("yuasa", "yuasa batería acumulador battery ytz yb"),
    ("freno", "freno brake"),
    ("cadena", "cadena chain transmisión rk did 428 520"),
    ("llanta", "llanta neumático rin cubierta tire"),
    ("cubierta", "cubierta llanta neumático tire"),
    ("bateria", "batería acumulador battery yuasa magna mf ytz yb"),
    ("batería", "batería acumulador battery yuasa magna mf ytz yb"),
    ("bobina", "bobina alta tensión coil ignition encendido"),
    ("transmision", "transmisión cadena correa relación 428 520"),
    ("amortiguador", "amortiguador monoshock shock suspensión"),
    ("carburador", "carburador carb mikuni keihin alimentación"),
    ("luz", "luz farola bombillo led halogen lámpara"),
    ("espejo", "espejo retrovisor mirror"),
    ("manija", "manija maneta manilla clutch embrague"),
    ("maneta", "maneta manija freno embrague clutch"),
    ("clutch", "clutch manija maneta embrague disco"),
    ("cable", "cable guaya bowden acelerador embrague"),
    ("guaya", "guaya cable acelerador embrague bowden"),
    ("manguera", "manguera tubo hose líquido refrigerante"),
]


def enrich_sku_text(nombre: str, categoria: str | None = None) -> str:
    """Enriquece el texto de un SKU con sinónimos para el embedding.

    Se usa en el pipeline (Mac) al generar los vectores de cada producto.
    El texto resultante se pasa al modelo de embeddings.

    Args:
        nombre: nombre del producto (ej. "FILTRO ACEITE YAMAHA YBR125")
        categoria: código de grupo o categoría (ej. "IV2")

    Returns:
        Texto enriquecido para el modelo de embeddings.
    """
    text = nombre.lower()
    parts = [nombre]

    if categoria:
        parts.append(f"categoría: {categoria}")

    additions = []
    for key, expansion in SYNONYMS:
        if key in text:
            additions.append(expansion)

    if additions:
        parts.append(" ".join(additions))

    return " | ".join(parts)


def expand_query(query: str) -> str:
    """Expande una query del usuario con sinónimos.

    Se usa en el API (Render) antes de llamar a HuggingFace Inference API.
    La query expandida produce un embedding más rico que captura
    mejor la intención del vendedor.

    Args:
        query: texto que escribe el usuario (ej. "aceite sintetico")

    Returns:
        Query expandida con términos relacionados.
    """
    text_lower = query.lower()
    additions = []
    for key, expansion in SYNONYMS:
        if key in text_lower:
            additions.append(expansion)

    if additions:
        return f"{query} {' '.join(additions)}"
    return query


def expand_keyword_terms(word: str) -> list[str]:
    """Expande una palabra clave con variantes de acentuación y ortografía.

    NO expande a sinónimos conceptuales (eso lo hace el embedding semántico).
    Solo corrige acentos y variantes comunes del catálogo real de MotoShop.
    """
    mapping = {
        "bujia": ["bujia", "bujía", "bujias", "bujías"],
        "bujía": ["bujía", "bujia", "bujias", "bujías"],
        "bateria": ["bateria", "batería", "baterias", "baterías"],
        "batería": ["batería", "bateria", "baterias", "baterías"],
        "transmision": ["transmision", "transmisión"],
        "transmisión": ["transmisión", "transmision"],
        "manija": ["manija", "manigueta"],
        "manigueta": ["manigueta", "manija"],
        "maneta": ["maneta", "manigueta"],
        "clutch": ["clutch"],
        "llanta": ["llanta", "llantas"],
        "cubierta": ["cubierta", "cubiertas"],
        "amortiguador": ["amortiguador", "amortiguadores"],
    }
    result = []
    seen = set()
    for term in mapping.get(word.lower(), [word.lower()]):
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result


def split_keywords(query: str) -> list[str]:
    """Extrae palabras clave individuales del query para keyword match.

    Ignora palabras muy cortas (<3 chars) y muy comunes.

    Returns:
        Lista de palabras en minúscula.
    """
    stopwords = {"de", "la", "el", "en", "un", "una", "los", "las", "del", "para", "con", "por", "y", "o"}
    words = [w.strip() for w in query.lower().split() if len(w.strip()) >= 3 and w.strip() not in stopwords]
    return words
