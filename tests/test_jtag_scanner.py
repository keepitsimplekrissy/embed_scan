import pytest

from features.jtag.jtag_scanner import JtagScanner


def test_bit_read_basic():
    # 0b1010 -> bits: index 0 LSB = 0, index 1 = 1, index 2 = 0, index 3 = 1
    assert JtagScanner.bit_read(0b1010, 0) == 0
    assert JtagScanner.bit_read(0b1010, 1) == 1
    assert JtagScanner.bit_read(0b1010, 2) == 0
    assert JtagScanner.bit_read(0b1010, 3) == 1


def test_bit_read_non_int_raises_typeerror():
    with pytest.raises(TypeError):
        JtagScanner.bit_read("not-an-int", 1)


def test_bit_read_negative_index_raises_valueerror():
    # Shifting by a negative count raises ValueError in Python
    with pytest.raises(ValueError):
        JtagScanner.bit_read(1, -1)
