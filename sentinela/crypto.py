"""Criptografia AES-256-GCM em fluxo (streaming) para os arquivos de backup.

Formato do arquivo .enc:

    MAGIC (4 bytes "SNTL") | VERSÃO (1 byte) | NONCE (12 bytes) | CIPHERTEXT | TAG (16 bytes)

O cabeçalho (MAGIC + VERSÃO) é autenticado como dado associado (AAD), então
qualquer alteração no arquivo — no cabeçalho ou no conteúdo — é detectada na
verificação da tag GCM.
"""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import compat, settings

MAGIC = b"SNTL"
VERSION = 1
HEADER = MAGIC + bytes([VERSION])
NONCE_LEN = 12
TAG_LEN = 16
KEY_LEN = 32  # 256 bits

CHUNK = 1024 * 1024


class IntegrityError(Exception):
    """Arquivo corrompido, adulterado ou chave incorreta."""


# ---------------------------------------------------------------- chave mestra

def load_or_create_key(path=None):
    path = path or settings.KEY_PATH
    if path.exists():
        key = path.read_bytes()
        if len(key) != KEY_LEN:
            raise RuntimeError(f"Chave mestra inválida em {path} (tamanho {len(key)})")
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(KEY_LEN)
    fd = compat.open_private(path, exclusive=True)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def key_id(key):
    """Identificador público e curto de uma chave mestra (não revela a chave)."""
    return derive(key, "sentinela/key-id").hex()[:16]


def derive(key, label):
    """Deriva subchaves independentes a partir da chave mestra."""
    return hmac.new(key, label.encode(), hashlib.sha256).digest()


# ---------------------------------------------------------- cifra em streaming

class StreamEncryptor:
    """Criptografa em partes. Chame header() antes e finalize() no fim."""

    def __init__(self, key):
        self.nonce = os.urandom(NONCE_LEN)
        self._enc = Cipher(algorithms.AES(key), modes.GCM(self.nonce)).encryptor()
        self._enc.authenticate_additional_data(HEADER)

    def header(self):
        return HEADER + self.nonce

    def update(self, data):
        return self._enc.update(data)

    def finalize(self):
        return self._enc.finalize() + self._enc.tag


def _read_header(f):
    head = f.read(len(HEADER) + NONCE_LEN)
    if len(head) < len(HEADER) + NONCE_LEN or head[:4] != MAGIC:
        raise IntegrityError("Arquivo não é um backup criptografado do Sentinela")
    if head[4] != VERSION:
        raise IntegrityError(f"Versão de formato não suportada: {head[4]}")
    return head[len(HEADER):]


def decrypt_stream(src_path, key, sink=None):
    """Descriptografa ``src_path`` enviando o texto claro para ``sink(bytes)``.

    ATENÇÃO: os dados só estão autenticados quando a função retorna sem erro.
    Para restaurar, primeiro rode com ``sink=None`` (verificação) e só depois
    envie os dados ao destino.
    """
    size = os.path.getsize(src_path)
    with open(src_path, "rb") as f:
        nonce = _read_header(f)
        body_len = size - (len(HEADER) + NONCE_LEN) - TAG_LEN
        if body_len < 0:
            raise IntegrityError("Arquivo truncado")
        f.seek(size - TAG_LEN)
        tag = f.read(TAG_LEN)
        f.seek(len(HEADER) + NONCE_LEN)

        dec = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        dec.authenticate_additional_data(HEADER)
        remaining = body_len
        while remaining > 0:
            chunk = f.read(min(CHUNK, remaining))
            if not chunk:
                raise IntegrityError("Arquivo truncado")
            remaining -= len(chunk)
            out = dec.update(chunk)
            if sink and out:
                sink(out)
        try:
            out = dec.finalize()
        except Exception as e:  # InvalidTag
            raise IntegrityError("Falha na autenticação (arquivo adulterado ou chave incorreta)") from e
        if sink and out:
            sink(out)


# ------------------------------------------------------- segredos da aplicação

def seal(key, text):
    """Criptografa um segredo curto (ex.: senha do banco) para guardar no SQLite."""
    if not text:
        return ""
    k = derive(key, "sentinela/secrets")
    nonce = os.urandom(NONCE_LEN)
    enc = Cipher(algorithms.AES(k), modes.GCM(nonce)).encryptor()
    ct = enc.update(text.encode()) + enc.finalize()
    return base64.b64encode(nonce + ct + enc.tag).decode()


def unseal(key, blob):
    if not blob:
        return ""
    raw = base64.b64decode(blob)
    nonce, ct, tag = raw[:NONCE_LEN], raw[NONCE_LEN:-TAG_LEN], raw[-TAG_LEN:]
    k = derive(key, "sentinela/secrets")
    dec = Cipher(algorithms.AES(k), modes.GCM(nonce, tag)).decryptor()
    return (dec.update(ct) + dec.finalize()).decode()
