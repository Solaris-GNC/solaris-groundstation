from cryptography.exceptions import InvalidTag

class AESGCMFramer:

    LENGTH_SIZE = 2
    NONCE_SIZE = 12
    TAG_SIZE = 16

    def __init__(self, aesgcm, key):
        self.aesgcm = aesgcm
        self.key = key

    def extract(self, buffer):

        while True:

            raw = buffer.peek()

            # Necesitamos al menos la longitud
            if len(raw) < self.LENGTH_SIZE:
                return None

            # Longitud del frame cifrado
            encrypted_len = int.from_bytes(raw[:2], "little")

            # Longitud absurda -> probablemente estamos desincronizados
            if encrypted_len < self.NONCE_SIZE + self.TAG_SIZE:
                buffer.consume(1)
                continue

            total_size = self.LENGTH_SIZE + encrypted_len

            # Esperar más datos
            if len(raw) < total_size:
                return None

            frame = raw[:total_size]

            encrypted = frame[2:]

            nonce = encrypted[:12]
            ciphertext = encrypted[12:-16]
            tag = encrypted[-16:]

            try:

                plaintext = self.aesgcm.decrypt(
                    nonce,
                    ciphertext + tag,
                    None
                )

            except InvalidTag:

                print("GCM ERROR -> resincronizando")

                # Igual que hacías con el CRC:
                # eliminar un byte e intentar otra vez.
                buffer.consume(1)
                continue

            # Frame correcto
            buffer.consume(total_size)

            return plaintext