"""Protocol coverage with a fake register bus; physical RF behavior is not simulated."""
from unittest.mock import Mock
import pytest
from modules.rfid_auth.rc522 import RC522Chip, crc_a, RC522Reader


def protocol(replies):
    chip = object.__new__(RC522Chip)
    chip.bus = Mock()
    chip.bus.read.return_value = 0x92
    chip.exchange = Mock(side_effect=replies)
    return chip


def block(values):
    return [*values, values[0] ^ values[1] ^ values[2] ^ values[3]]


def sak(value):
    return [value, *crc_a([value])]


def test_crc_halt_reference():
    assert crc_a([0x50, 0x00]) == [0x57, 0xcd]


@pytest.mark.parametrize('parts,expected', [
    ([[0x04, 0xa1, 0xb2, 0xc3]], '04A1B2C3'),
    ([[0x88, 0x04, 0xa1, 0xb2], [0xc3, 0xd4, 0xe5, 0xf6]], '04A1B2C3D4E5F6'),
    ([[0x88, 0x04, 0xa1, 0xb2], [0x88, 0xc3, 0xd4, 0xe5], [0xf6, 0x07, 0x08, 0x09]], '04A1B2C3D4E5F6070809'),
])
def test_uid_cascade_levels(parts,expected):
    replies = [[0x04,0x00]]
    for i,part in enumerate(parts):
        replies.extend([block(part),sak(0x04 if i < len(parts)-1 else 0x08)])
    replies.append(None)  # Halt has no reply.
    chip = protocol(replies)
    assert chip.read_uid() == expected


def test_corrupt_bcc_or_sak_is_rejected():
    chip = protocol([[0x04,0x00],[1,2,3,4,0xff]])
    assert chip.read_uid() is None
    chip = protocol([[0x04,0x00],block([1,2,3,4]),[8,0,0]])
    assert chip.read_uid() is None


def test_missing_reader_and_no_card():
    chip = protocol([None])
    assert chip.read_uid() is None
    chip.bus.read.return_value = 0xff
    with pytest.raises(RuntimeError,match='connection lost'):chip.read_uid()


def test_initialization_failure_closes_bus():
    bus = Mock()
    bus.read.return_value = 0
    with pytest.raises(RuntimeError,match='not detected'):RC522Reader(bus)
    bus.close.assert_called_once()


def test_exchange_timeout_clears_start_send():
    chip = object.__new__(RC522Chip)
    chip.bus = Mock()
    chip.bus.read.return_value = 1  # TimerIrq
    assert chip.exchange([0x26],last_bits=7) is None
    chip.bus.write.assert_called_with(0x0d,7)
