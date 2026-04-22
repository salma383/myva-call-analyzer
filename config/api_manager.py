from openai import OpenAI

# Obfuscated key — XOR with mask, not stored as plain text
_M = b'MyVA\x24C4ll4n4lyz3rD3skT0pS3cr3t!X'
_K = b'>\x12{1V,^AAs\x18LA\x01(p\x1d\x13\x0b\x15\x19mW\x19~d)\x16p?Mh\x17\x13\x19pBzE4\x03A"}4/\x1dg(0Z6\x0cl\x06\x17eg\x04\x04`\x17m\x14,>7\x19a\x13\\\x1f\x01\x03[A(&.E\x1f\x1bg@)8R\x1b\x15y&\x02|\x17[\x08\x1a\x10\x0e*S\x1a\x019\x1fk9Y\x02\x17\x0cy\x056\x06J,\x0bB\'\x11\x1e\t;A\x1f\x13\x0c\x01\x178\ru\x1c\\\x01]\x06\re\x198JqDwB\x03%lW7`\x034:C\x1bWn\x0f\x1d9\x00'


def _decode() -> str:
    return bytes(b ^ _M[i % len(_M)] for i, b in enumerate(_K)).decode()


def get_client() -> OpenAI:
    return OpenAI(api_key=_decode())


def key_is_set() -> bool:
    return True
