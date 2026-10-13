"""MFRC522 UID reader using the existing GPIO Zero dependency.

UID-only ISO14443A scanning, including 4/7/10-byte cascade UIDs. Present one
card at a time; collisions are rejected. This is identification, not secure
card authentication. Register definitions: NXP MFRC522 datasheet; UID flow:
NXP AN10927. No card contents, keys or memory blocks are read or written.
"""
import logging
import os
from threading import Event, Thread
from time import monotonic

logger = logging.getLogger(__name__)


def crc_a(data):
    crc = 0x6363
    for byte in data:
        byte ^= crc & 0xff
        byte ^= (byte << 4) & 0xff
        crc = ((crc >> 8) ^ (byte << 8) ^ (byte << 3) ^ (byte >> 4)) & 0xffff
    return [crc & 0xff, crc >> 8]


class GPIORegisterBus:
    def __init__(self, port=0, device=0, reset_pin=25):
        from gpiozero import SPIDevice, DigitalOutputDevice
        self.spi = self.reset = None
        try:
            self.reset = DigitalOutputDevice(reset_pin, initial_value=True)
            self.spi = SPIDevice(port=port, device=device)
        except BaseException:
            self.close()
            raise

    def read(self, register):
        return self.spi._spi.transfer([0x80 | ((register << 1) & 0x7e), 0])[1]

    def write(self, register, value):
        self.spi._spi.transfer([(register << 1) & 0x7e, value & 0xff])

    def close(self):
        try:
            if self.spi:
                self.spi.close()
        finally:
            if self.reset:
                self.reset.close()


class RC522Chip:
    def __init__(self, bus):
        self.bus = bus
        self.bus.write(0x01, 0x0f)  # SoftReset
        deadline = monotonic() + .1
        while self.bus.read(0x01) & 0x10:
            if monotonic() >= deadline:
                raise RuntimeError('RC522 reset timed out; check power and SPI wiring.')
            Event().wait(.001)
        if self.bus.read(0x37) in (0x00, 0xff):
            raise RuntimeError('RC522 not detected; check 3.3V power, SPI and reset wiring.')
        for register, value in ((0x2a, 0x8d), (0x2b, 0x3e), (0x2c, 0), (0x2d, 30), (0x15, 0x40), (0x11, 0x3d)):
            self.bus.write(register, value)
        self.bus.write(0x14, self.bus.read(0x14) | 0x03)

    def exchange(self, data, last_bits=0):
        self.bus.write(0x01, 0)  # Idle
        self.bus.write(0x04, 0x7f)  # Clear interrupt flags
        self.bus.write(0x0a, 0x80)  # Flush FIFO
        for byte in data:
            self.bus.write(0x09, byte)
        self.bus.write(0x0d, last_bits)
        self.bus.write(0x01, 0x0c)  # Transceive
        self.bus.write(0x0d, last_bits | 0x80)  # StartSend
        deadline = monotonic() + .05
        try:
            while monotonic() < deadline:
                irq = self.bus.read(0x04)
                if irq & 0x01:  # Timer expired; no card response
                    return None
                if irq & 0x30:  # RxIRq or IdleIRq
                    if self.bus.read(0x06) & 0x1b:  # Overflow, collision, parity, protocol
                        return None
                    count = self.bus.read(0x0a)
                    if not 0 < count <= 64 or self.bus.read(0x0c) & 0x07:
                        return None
                    return [self.bus.read(0x09) for _ in range(count)]
                Event().wait(.001)
            return None
        finally:
            self.bus.write(0x0d, last_bits)

    def read_uid(self):
        if self.bus.read(0x37) in (0x00, 0xff):
            raise RuntimeError('RC522 connection lost.')
        atqa = self.exchange([0x52], last_bits=7)  # WUPA, including halted cards
        if atqa is None or len(atqa) != 2:
            return None
        uid = []
        for level in (0x93, 0x95, 0x97):
            block = self.exchange([level, 0x20])
            if block is None or len(block) != 5 or block[0] ^ block[1] ^ block[2] ^ block[3] != block[4]:
                return None
            select = [level, 0x70, *block]
            sak = self.exchange(select + crc_a(select))
            if sak is None or len(sak) != 3 or crc_a(sak[:1]) != sak[1:]:
                return None
            cascade = bool(sak[0] & 0x04)
            if cascade:
                if block[0] != 0x88 or level == 0x97:
                    return None
                uid.extend(block[1:4])
            else:
                uid.extend(block[:4])
                halt = [0x50, 0x00]
                self.exchange(halt + crc_a(halt))  # HLTA intentionally has no reply
                return ''.join(f'{byte:02X}' for byte in uid)
        return None


class RC522Reader:
    def __init__(self, bus=None, poll_seconds=.1):
        self.bus = bus or GPIORegisterBus(
            port=int(os.getenv('SENTINELAI_RFID_SPI_PORT', '0')),
            device=int(os.getenv('SENTINELAI_RFID_SPI_DEVICE', '0')),
            reset_pin=int(os.getenv('SENTINELAI_RFID_RESET_PIN', '25')))
        self.callbacks, self.thread = [], None
        self.stop_event, self.poll_seconds = Event(), poll_seconds
        self.last_error = None
        try:
            self.chip = RC522Chip(self.bus)
        except BaseException:
            self.bus.close()
            raise

    @property
    def ready(self):
        return bool(self.thread and self.thread.is_alive() and not self.last_error)

    def on_card(self, callback):
        self.callbacks.append(callback)
        if self.thread:
            return
        def run():
            previous, last_seen = None, 0.0
            while not self.stop_event.is_set():
                try:
                    uid = self.chip.read_uid()
                    self.last_error = None
                    if uid:
                        if uid != previous:
                            for handler in tuple(self.callbacks):
                                handler(uid)
                        previous, last_seen = uid, monotonic()
                    elif monotonic() - last_seen >= .5:
                        previous = None
                except Exception as error:
                    if self.last_error is None:
                        logger.exception('RC522 scan failed')
                    self.last_error = type(error).__name__
                self.stop_event.wait(self.poll_seconds)
        self.thread = Thread(target=run, name='sentinel-rc522', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError('RFID callback has not stopped; reader shutdown timed out.')
        self.bus.close()


def create_reader():
    return RC522Reader()
