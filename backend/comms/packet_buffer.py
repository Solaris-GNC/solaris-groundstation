class PacketBuffer: 
    def __init__(self):
        self.buffer = bytearray()               # Version mutable de "bytes"

    def write(self, data: bytes):
        self.buffer.extend(data)

    def size(self):
        return len(self.buffer)

    def consume(self, n: int):
        del self.buffer[:n]

    def peek(self):
        return bytes(self.buffer)               # Convertimos a "bytes" para blindar nuestro buffer haciendolo inmutable

