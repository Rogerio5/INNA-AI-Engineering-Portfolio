from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED_SECRET = "[REDACTED_SECRET]"
REDACTED_PERSONAL_DATA = "[REDACTED_PERSONAL_DATA]"
REDACTED_FINANCIAL_DATA = "[REDACTED_FINANCIAL_DATA]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_DOCUMENT = "[REDACTED_DOCUMENT]"
REDACTED_CARD = "[REDACTED_CARD]"
REDACTED_IP = "[REDACTED_IP]"
REDACTED_AUTH = "[REDACTED_AUTH]"
REDACTED_DATABASE_URL = "[REDACTED_DATABASE_URL]"
REDACTED_PIX = "[REDACTED_PIX]"
REDACTED_VALUE = "[REDACTED]"
REDACTED_BINARY = "[REDACTED_BINARY]"
TRUNCATED = "[TRUNCATED]"
MAX_DEPTH_REACHED = "[MAX_DEPTH_REACHED]"


DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_ITEMS = 250
DEFAULT_MAX_STRING_LENGTH = 10_000
DEFAULT_EXTERNAL_MAX_STRING_LENGTH = 5_000
DEFAULT_HASH_DIGEST_SIZE = 16


SENSITIVE_KEYS = {
    "access_key",
    "access_token",
    "admin_password",
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "aws_access_key_id",
    "aws_secret_access_key",
    "bearer_token",
    "client_secret",
    "connection_string",
    "cookie",
    "cookies",
    "database_password",
    "database_url",
    "db_password",
    "db_url",
    "encryption_key",
    "gemini_api_key",
    "google_api_key",
    "hmac_secret",
    "id_token",
    "internal_api_signing_secret",
    "jwt",
    "openai_api_key",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "secret_key",
    "senha",
    "session_cookie",
    "session_token",
    "signing_secret",
    "smtp_password",
    "token",
    "wandb_api_key",
    "webhook_secret",
}


PERSONAL_DATA_KEYS = {
    "address",
    "birth_date",
    "birthday",
    "cep",
    "city",
    "cnpj",
    "cpf",
    "document",
    "document_id",
    "email",
    "endereco",
    "full_name",
    "home_address",
    "last_name",
    "name",
    "nome",
    "phone",
    "phone_number",
    "postal_code",
    "rg",
    "street",
    "telefone",
    "user_email",
    "user_name",
    "username",
}


FINANCIAL_SENSITIVE_KEYS = {
    "account_number",
    "bank_account",
    "bank_details",
    "card_cvv",
    "card_expiration",
    "card_number",
    "credit_card",
    "current_balance",
    "debt",
    "debts",
    "divida",
    "dividas",
    "expenses",
    "financial_data",
    "financial_inputs",
    "fixed_expenses",
    "gastos",
    "income",
    "monthly_income",
    "pix_key",
    "pix_keys",
    "reserve",
    "renda",
    "routing_number",
    "salary",
    "savings",
    "variable_expenses",
}


AUTHORIZATION_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-inna-signature",
    "x-internal-token",
}


SAFE_HEADER_KEYS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "content-length",
    "content-type",
    "host",
    "user-agent",
    "x-request-id",
    "x-trace-id",
}


EMAIL_PATTERN = re.compile(
    r"\b"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@"
    r"[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)+"
    r"\b"
)


PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"(?:\+?55[\s.-]*)?"
    r"\(\d{2}\)"
    r"[\s.-]*"
    r"9?\d{4}"
    r"[\s.-]?"
    r"\d{4}"
    r"|"
    r"\+?55"
    r"[\s.-]*"
    r"\d{2}"
    r"[\s.-]*"
    r"9\d{4}"
    r"[\s.-]?"
    r"\d{4}"
    r"|"
    r"\d{2}"
    r"[\s.-]+"
    r"9\d{4}"
    r"[-.]"
    r"\d{4}"
    r")"
    r"(?!\d)"
)


CPF_PATTERN = re.compile(
    r"(?<!\d)"
    r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"
    r"(?!\d)"
)


CNPJ_PATTERN = re.compile(
    r"(?<!\d)"
    r"\d{2}\.?\d{3}\.?\d{3}"
    r"/?"
    r"\d{4}-?\d{2}"
    r"(?!\d)"
)


CARD_CANDIDATE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\d[ -]?){13,19}"
    r"(?!\d)"
)


JWT_PATTERN = re.compile(
    r"\b"
    r"eyJ[A-Za-z0-9_-]+"
    r"\."
    r"[A-Za-z0-9_-]+"
    r"\."
    r"[A-Za-z0-9_-]+"
    r"\b"
)


BEARER_PATTERN = re.compile(
    r"(?i)"
    r"\bbearer\s+"
    r"[A-Za-z0-9._~+/=-]+"
)


BASIC_AUTH_PATTERN = re.compile(
    r"(?i)"
    r"\bbasic\s+"
    r"[A-Za-z0-9+/=]+"
)


SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)"
    r"\b("
    r"api[_-]?key"
    r"|access[_-]?token"
    r"|auth[_-]?token"
    r"|refresh[_-]?token"
    r"|session[_-]?token"
    r"|bearer[_-]?token"
    r"|token"
    r"|password"
    r"|passwd"
    r"|senha"
    r"|secret"
    r"|private[_-]?key"
    r"|database[_-]?url"
    r"|connection[_-]?string"
    r")"
    r"\s*[:=]\s*"
    r"['\"]?"
    r"[^\s,'\";)\]}]+"
)


DATABASE_URL_PATTERN = re.compile(
    r"(?i)"
    r"\b("
    r"postgres(?:ql)?"
    r"|mysql"
    r"|mariadb"
    r"|mongodb(?:\+srv)?"
    r"|redis"
    r"|amqp"
    r")"
    r"://"
    r"[^\s<>'\"]+"
)


PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN "
    r"(?:RSA |EC |OPENSSH )?"
    r"PRIVATE KEY-----"
    r".*?"
    r"-----END "
    r"(?:RSA |EC |OPENSSH )?"
    r"PRIVATE KEY-----",
    flags=re.DOTALL,
)


IPV4_PATTERN = re.compile(
    r"(?<![\d.])"
    r"(?:\d{1,3}\.){3}\d{1,3}"
    r"(?![\d.])"
)


UUID_PATTERN = re.compile(
    r"\b"
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}"
    r"\b"
)


PIX_EMAIL_PATTERN = EMAIL_PATTERN


PIX_PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"\+?55"
    r"\d{10,11}"
    r"(?!\d)"
)


PIX_RANDOM_KEY_PATTERN = UUID_PATTERN


def normalize_key(
    key: Any,
) -> str:
    """
    Normaliza nomes de campos para comparação com listas de proteção.
    """

    normalized = str(key).strip().lower()

    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        normalized,
    )

    return normalized.strip("_")


def _only_digits(
    value: str,
) -> str:
    """Retorna somente os dígitos de uma string."""

    return re.sub(
        r"\D",
        "",
        value,
    )


def _validate_limits(
    *,
    max_depth: int,
    max_items: int,
    max_string_length: int,
) -> None:
    """Valida os limites usados pelo sanitizador."""

    if max_depth < 1:
        raise ValueError(
            "max_depth deve ser maior que zero."
        )

    if max_items < 1:
        raise ValueError(
            "max_items deve ser maior que zero."
        )

    if max_string_length < 1:
        raise ValueError(
            "max_string_length deve ser maior que zero."
        )


def _luhn_is_valid(
    value: str,
) -> bool:
    """
    Valida candidatos a cartão pelo algoritmo de Luhn.

    Isso evita remover sequências numéricas comuns que não representam
    números de cartão.
    """

    digits = _only_digits(value)

    if not 13 <= len(digits) <= 19:
        return False

    if len(set(digits)) == 1:
        return False

    total = 0
    parity = len(digits) % 2

    for index, character in enumerate(digits):
        digit = int(character)

        if index % 2 == parity:
            digit *= 2

            if digit > 9:
                digit -= 9

        total += digit

    return total % 10 == 0


def _redact_card_candidates(
    text: str,
) -> str:
    """Substitui números de cartão válidos pelo marcador seguro."""

    def replace(
        match: re.Match[str],
    ) -> str:
        candidate = match.group(0)

        if _luhn_is_valid(candidate):
            return REDACTED_CARD

        return candidate

    return CARD_CANDIDATE_PATTERN.sub(
        replace,
        text,
    )


def _redact_valid_ipv4(
    text: str,
) -> str:
    """Remove apenas endereços IPv4 válidos."""

    def replace(
        match: re.Match[str],
    ) -> str:
        candidate = match.group(0)

        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return candidate

        return REDACTED_IP

    return IPV4_PATTERN.sub(
        replace,
        text,
    )


def _sanitize_url_credentials(
    text: str,
) -> str:
    """
    Remove usuário e senha embutidos em URLs HTTP e HTTPS.

    Exemplo:
        https://usuario:senha@servidor
    """

    url_pattern = re.compile(
        r"https?://[^\s<>'\"]+",
        flags=re.IGNORECASE,
    )

    def replace(
        match: re.Match[str],
    ) -> str:
        original = match.group(0)

        try:
            parsed = urlsplit(original)
        except ValueError:
            return original

        if parsed.username is None and parsed.password is None:
            return original

        hostname = parsed.hostname or ""

        try:
            port = parsed.port
        except ValueError:
            port = None

        if port is not None:
            hostname = f"{hostname}:{port}"

        return urlunsplit(
            (
                parsed.scheme,
                hostname,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )

    return url_pattern.sub(
        replace,
        text,
    )


def truncate_text(
    value: str,
    *,
    max_length: int = DEFAULT_MAX_STRING_LENGTH,
) -> str:
    """Limita o tamanho de textos exportados ou persistidos."""

    if max_length < 1:
        raise ValueError(
            "max_length deve ser maior que zero."
        )

    if len(value) <= max_length:
        return value

    remaining = len(value) - max_length

    return (
        value[:max_length]
        + f"\n{TRUNCATED}:{remaining}"
    )


def sanitize_text(
    value: str,
    *,
    max_length: int = DEFAULT_MAX_STRING_LENGTH,
    redact_uuid: bool = False,
) -> str:
    """
    Sanitiza segredos e dados pessoais em texto livre.

    Essa função é determinística e não utiliza LLM.
    """

    sanitized = str(value)

    sanitized = PRIVATE_KEY_PATTERN.sub(
        REDACTED_SECRET,
        sanitized,
    )

    sanitized = DATABASE_URL_PATTERN.sub(
        REDACTED_DATABASE_URL,
        sanitized,
    )

    sanitized = BEARER_PATTERN.sub(
        REDACTED_AUTH,
        sanitized,
    )

    sanitized = BASIC_AUTH_PATTERN.sub(
        REDACTED_AUTH,
        sanitized,
    )

    sanitized = JWT_PATTERN.sub(
        REDACTED_AUTH,
        sanitized,
    )

    sanitized = SECRET_ASSIGNMENT_PATTERN.sub(
        REDACTED_SECRET,
        sanitized,
    )

    sanitized = _sanitize_url_credentials(
        sanitized,
    )

    sanitized = EMAIL_PATTERN.sub(
        REDACTED_EMAIL,
        sanitized,
    )

    sanitized = CPF_PATTERN.sub(
        REDACTED_DOCUMENT,
        sanitized,
    )

    sanitized = CNPJ_PATTERN.sub(
        REDACTED_DOCUMENT,
        sanitized,
    )

    sanitized = _redact_card_candidates(
        sanitized,
    )

    sanitized = PHONE_PATTERN.sub(
        REDACTED_PHONE,
        sanitized,
    )

    sanitized = _redact_valid_ipv4(
        sanitized,
    )

    if redact_uuid:
        sanitized = UUID_PATTERN.sub(
            REDACTED_PERSONAL_DATA,
            sanitized,
        )

    return truncate_text(
        sanitized,
        max_length=max_length,
    )


def hash_identifier(
    value: str | int | None,
    *,
    salt: str,
    prefix: str = "usr",
    digest_size: int = DEFAULT_HASH_DIGEST_SIZE,
) -> str | None:
    """
    Cria um identificador pseudonimizado estável usando BLAKE2b.

    O salt deve vir de variável de ambiente e nunca deve ser persistido
    junto do identificador original.
    """

    if value is None:
        return None

    normalized_value = str(value).strip()

    if not normalized_value:
        return None

    normalized_salt = str(salt).strip()

    if not normalized_salt:
        raise ValueError(
            "O salt de hash_identifier não pode ser vazio."
        )

    if digest_size < 8:
        raise ValueError(
            "digest_size deve ser pelo menos 8."
        )

    if digest_size > 64:
        raise ValueError(
            "digest_size não pode ser maior que 64."
        )

    normalized_prefix = str(prefix).strip() or "id"

    digest = hashlib.blake2b(
        normalized_value.encode("utf-8"),
        key=normalized_salt.encode("utf-8"),
        digest_size=digest_size,
    ).hexdigest()

    return f"{normalized_prefix}_{digest}"


def content_hash(
    value: str | bytes,
    *,
    digest_size: int = DEFAULT_HASH_DIGEST_SIZE,
) -> str:
    """
    Cria hash de conteúdo sem usar salt.

    Pode ser usado para identificar documentos RAG sem armazenar o
    conteúdo original.
    """

    if digest_size < 8 or digest_size > 64:
        raise ValueError(
            "digest_size deve estar entre 8 e 64."
        )

    if isinstance(value, str):
        raw_value = value.encode("utf-8")
    else:
        raw_value = bytes(value)

    return hashlib.blake2b(
        raw_value,
        digest_size=digest_size,
    ).hexdigest()


def _is_sensitive_key(
    normalized_key: str,
) -> bool:
    """Verifica se o nome de um campo indica segredo."""

    if normalized_key in SENSITIVE_KEYS:
        return True

    sensitive_fragments = (
        "api_key",
        "password",
        "private_key",
        "secret",
        "token",
        "credential",
        "database_url",
        "connection_string",
        "signing_key",
    )

    return any(
        fragment in normalized_key
        for fragment in sensitive_fragments
    )


def _is_personal_key(
    normalized_key: str,
) -> bool:
    """Verifica se o nome indica dado pessoal."""

    return normalized_key in PERSONAL_DATA_KEYS


def _is_financial_key(
    normalized_key: str,
) -> bool:
    """Verifica se o nome indica dado financeiro sensível."""

    return normalized_key in FINANCIAL_SENSITIVE_KEYS


def _is_pix_key(
    normalized_key: str,
) -> bool:
    """Verifica se o campo representa uma chave Pix."""

    return (
        normalized_key in {
            "pix",
            "pix_key",
            "pix_keys",
            "chave_pix",
        }
        or "pix_key" in normalized_key
        or "chave_pix" in normalized_key
    )


def sanitize_mapping(
    value: Mapping[Any, Any],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    redact_personal_fields: bool = True,
    redact_financial_fields: bool = True,
    redact_uuid: bool = False,
    current_depth: int = 0,
) -> dict[str, Any]:
    """
    Sanitiza recursivamente um mapeamento.

    Segredos sempre são removidos. Dados pessoais e financeiros são
    controlados por parâmetros específicos.
    """

    _validate_limits(
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
    )

    if current_depth >= max_depth:
        return {
            "_sanitization": MAX_DEPTH_REACHED,
        }

    sanitized: dict[str, Any] = {}

    for index, (key, item) in enumerate(
        value.items()
    ):
        if index >= max_items:
            remaining = max(
                0,
                len(value) - max_items,
            )

            sanitized["_truncated_items"] = remaining
            break

        output_key = str(key)
        normalized_key = normalize_key(key)

        if _is_sensitive_key(normalized_key):
            sanitized[output_key] = REDACTED_SECRET
            continue

        if (
            redact_personal_fields
            and _is_personal_key(normalized_key)
        ):
            sanitized[output_key] = REDACTED_PERSONAL_DATA
            continue

        if (
            redact_financial_fields
            and _is_financial_key(normalized_key)
        ):
            sanitized[output_key] = REDACTED_FINANCIAL_DATA
            continue

        if _is_pix_key(normalized_key):
            sanitized[output_key] = REDACTED_PIX
            continue

        sanitized[output_key] = sanitize_value(
            item,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    return sanitized


def sanitize_sequence(
    value: Sequence[Any],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    redact_personal_fields: bool = True,
    redact_financial_fields: bool = True,
    redact_uuid: bool = False,
    current_depth: int = 0,
) -> list[Any]:
    """Sanitiza listas, tuplas e outras sequências."""

    _validate_limits(
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
    )

    if current_depth >= max_depth:
        return [
            MAX_DEPTH_REACHED,
        ]

    sanitized: list[Any] = []

    for index, item in enumerate(value):
        if index >= max_items:
            remaining = max(
                0,
                len(value) - max_items,
            )

            sanitized.append(
                f"{TRUNCATED}:{remaining}"
            )
            break

        sanitized.append(
            sanitize_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                redact_personal_fields=redact_personal_fields,
                redact_financial_fields=redact_financial_fields,
                redact_uuid=redact_uuid,
                current_depth=current_depth + 1,
            )
        )

    return sanitized


def sanitize_value(
    value: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    redact_personal_fields: bool = True,
    redact_financial_fields: bool = True,
    redact_uuid: bool = False,
    current_depth: int = 0,
) -> Any:
    """
    Sanitizador recursivo genérico.

    Suporta:

    - strings;
    - mappings;
    - dataclasses;
    - enums;
    - listas e tuplas;
    - exceções;
    - valores primitivos;
    - objetos Pydantic;
    - dados binários.
    """

    _validate_limits(
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
    )

    if current_depth >= max_depth:
        return MAX_DEPTH_REACHED

    if value is None:
        return None

    if isinstance(value, Enum):
        return sanitize_value(
            value.value,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    if is_dataclass(value) and not isinstance(
        value,
        type,
    ):
        return sanitize_mapping(
            asdict(value),
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    model_dump = getattr(
        value,
        "model_dump",
        None,
    )

    if callable(model_dump):
        try:
            dumped_value = model_dump(
                mode="python",
            )
        except TypeError:
            dumped_value = model_dump()

        return sanitize_value(
            dumped_value,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    if isinstance(value, BaseException):
        return sanitize_exception(
            value,
            max_string_length=max_string_length,
        )

    if isinstance(value, str):
        return sanitize_text(
            value,
            max_length=max_string_length,
            redact_uuid=redact_uuid,
        )

    if isinstance(value, Mapping):
        return sanitize_mapping(
            value,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    if isinstance(value, Sequence) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return sanitize_sequence(
            value,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            redact_personal_fields=redact_personal_fields,
            redact_financial_fields=redact_financial_fields,
            redact_uuid=redact_uuid,
            current_depth=current_depth + 1,
        )

    if isinstance(
        value,
        (
            bool,
            int,
            float,
        ),
    ):
        return value

    if isinstance(
        value,
        (
            bytes,
            bytearray,
        ),
    ):
        return (
            f"{REDACTED_BINARY}:"
            f"{len(value)} bytes"
        )

    return sanitize_text(
        repr(value),
        max_length=max_string_length,
        redact_uuid=redact_uuid,
    )


def sanitize_headers(
    headers: Mapping[str, Any],
    *,
    allow_only_safe_headers: bool = False,
) -> dict[str, Any]:
    """
    Sanitiza cabeçalhos HTTP.

    No modo allow_only_safe_headers, somente cabeçalhos explicitamente
    permitidos são mantidos.
    """

    sanitized: dict[str, Any] = {}

    for key, value in headers.items():
        output_key = str(key)
        normalized_key = output_key.strip().lower()

        if normalized_key in AUTHORIZATION_HEADERS:
            sanitized[output_key] = REDACTED_AUTH
            continue

        if (
            allow_only_safe_headers
            and normalized_key not in SAFE_HEADER_KEYS
        ):
            continue

        sanitized[output_key] = sanitize_text(
            str(value),
        )

    return sanitized


def sanitize_exception(
    exception: BaseException,
    *,
    include_type: bool = True,
    max_string_length: int = 2_000,
) -> dict[str, str]:
    """
    Gera representação segura de uma exceção.

    Não inclui traceback, variáveis locais ou argumentos originais.
    """

    message = sanitize_text(
        str(exception),
        max_length=max_string_length,
        redact_uuid=True,
    )

    result = {
        "message": message,
    }

    if include_type:
        result["type"] = type(exception).__name__

    return result


def sanitize_pix_key(
    value: str,
) -> str:
    """
    Sanitiza uma chave Pix independentemente de seu tipo.

    Pode receber:

    - CPF;
    - CNPJ;
    - e-mail;
    - telefone;
    - chave aleatória.
    """

    candidate = str(value).strip()

    if not candidate:
        return candidate

    if CPF_PATTERN.fullmatch(candidate):
        return REDACTED_PIX

    if CNPJ_PATTERN.fullmatch(candidate):
        return REDACTED_PIX

    if PIX_EMAIL_PATTERN.fullmatch(candidate):
        return REDACTED_PIX

    if PIX_PHONE_PATTERN.fullmatch(candidate):
        return REDACTED_PIX

    if PIX_RANDOM_KEY_PATTERN.fullmatch(candidate):
        return REDACTED_PIX

    return REDACTED_PIX


def safe_json_dumps(
    value: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = True,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    redact_personal_fields: bool = True,
    redact_financial_fields: bool = True,
    redact_uuid: bool = False,
) -> str:
    """
    Sanitiza e serializa um objeto para JSON.

    Deve ser usado antes de salvar artefatos de avaliação ou enviar
    payloads para ferramentas externas.
    """

    sanitized = sanitize_value(
        value,
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
        redact_personal_fields=redact_personal_fields,
        redact_financial_fields=redact_financial_fields,
        redact_uuid=redact_uuid,
    )

    return json.dumps(
        sanitized,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
        default=str,
    )


def contains_possible_secret(
    value: Any,
) -> bool:
    """
    Detecta indícios de segredo sem retornar o conteúdo encontrado.
    """

    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        serialized = repr(value)

    patterns = (
        PRIVATE_KEY_PATTERN,
        DATABASE_URL_PATTERN,
        BEARER_PATTERN,
        BASIC_AUTH_PATTERN,
        JWT_PATTERN,
        SECRET_ASSIGNMENT_PATTERN,
    )

    return any(
        pattern.search(serialized) is not None
        for pattern in patterns
    )


def contains_possible_personal_data(
    value: Any,
) -> bool:
    """
    Detecta possíveis dados pessoais em payloads.
    """

    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        serialized = repr(value)

    patterns = (
        EMAIL_PATTERN,
        PHONE_PATTERN,
        CPF_PATTERN,
        CNPJ_PATTERN,
    )

    return any(
        pattern.search(serialized) is not None
        for pattern in patterns
    )


def assert_safe_for_external_export(
    value: Any,
    *,
    block_personal_data: bool = True,
) -> None:
    """
    Bloqueia exportação quando o payload contém possíveis segredos ou
    dados pessoais.
    """

    if contains_possible_secret(value):
        raise ValueError(
            "O payload contém possível segredo e não pode ser "
            "exportado para uma plataforma externa."
        )

    if (
        block_personal_data
        and contains_possible_personal_data(value)
    ):
        raise ValueError(
            "O payload contém possível dado pessoal e não pode ser "
            "exportado para uma plataforma externa."
        )


def prepare_external_payload(
    value: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_EXTERNAL_MAX_STRING_LENGTH,
) -> Any:
    """
    Prepara um payload conservador para DeepEval, Phoenix ou Weave.

    Por padrão:

    - remove segredos;
    - remove dados pessoais;
    - remove dados financeiros;
    - remove chaves Pix;
    - remove UUIDs;
    - limita profundidade;
    - limita quantidade de itens;
    - limita tamanho de strings;
    - valida novamente o resultado.
    """

    sanitized = sanitize_value(
        value,
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
        redact_personal_fields=True,
        redact_financial_fields=True,
        redact_uuid=True,
    )

    assert_safe_for_external_export(
        sanitized,
        block_personal_data=True,
    )

    return sanitized


def prepare_internal_payload(
    value: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
) -> Any:
    """
    Prepara um payload para observabilidade interna.

    Segredos e dados pessoais são removidos. Dados financeiros podem ser
    preservados somente quando necessários para avaliação local.
    """

    sanitized = sanitize_value(
        value,
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
        redact_personal_fields=True,
        redact_financial_fields=False,
        redact_uuid=False,
    )

    if contains_possible_secret(sanitized):
        raise ValueError(
            "O payload interno ainda contém possível segredo."
        )

    return sanitized


def safe_artifact_name(
    value: str,
    *,
    default: str = "artifact",
    max_length: int = 120,
) -> str:
    """
    Gera nome seguro para arquivos de avaliação.

    Remove caracteres inválidos e impede caminhos relativos.
    """

    normalized = str(value).strip().lower()

    normalized = re.sub(
        r"[^a-z0-9._-]+",
        "-",
        normalized,
    )

    normalized = normalized.strip(
        ".-_",
    )

    if not normalized:
        normalized = default

    normalized = normalized.replace(
        "..",
        ".",
    )

    return normalized[:max_length]


__all__ = [
    "AUTHORIZATION_HEADERS",
    "DEFAULT_EXTERNAL_MAX_STRING_LENGTH",
    "DEFAULT_HASH_DIGEST_SIZE",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_MAX_STRING_LENGTH",
    "FINANCIAL_SENSITIVE_KEYS",
    "PERSONAL_DATA_KEYS",
    "REDACTED_AUTH",
    "REDACTED_BINARY",
    "REDACTED_CARD",
    "REDACTED_DATABASE_URL",
    "REDACTED_DOCUMENT",
    "REDACTED_EMAIL",
    "REDACTED_FINANCIAL_DATA",
    "REDACTED_IP",
    "REDACTED_PERSONAL_DATA",
    "REDACTED_PHONE",
    "REDACTED_PIX",
    "REDACTED_SECRET",
    "REDACTED_VALUE",
    "SAFE_HEADER_KEYS",
    "SENSITIVE_KEYS",
    "assert_safe_for_external_export",
    "contains_possible_personal_data",
    "contains_possible_secret",
    "content_hash",
    "hash_identifier",
    "normalize_key",
    "prepare_external_payload",
    "prepare_internal_payload",
    "safe_artifact_name",
    "safe_json_dumps",
    "sanitize_exception",
    "sanitize_headers",
    "sanitize_mapping",
    "sanitize_pix_key",
    "sanitize_sequence",
    "sanitize_text",
    "sanitize_value",
    "truncate_text",
]
