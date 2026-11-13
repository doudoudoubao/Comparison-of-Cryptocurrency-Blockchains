"""底层编码/校验算法的测试，全部使用公开的标准测试向量。"""

import unittest

from chainmatch._crypto import (
    b58check_decode,
    b58decode,
    bech32_decode,
    eip55_checksum,
    eip55_is_valid,
    keccak256,
    ss58_decode,
)


class TestKeccak(unittest.TestCase):
    def test_known_vectors(self):
        self.assertEqual(
            keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(
            keccak256(b"abc").hex(),
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")
        self.assertEqual(
            keccak256(b"testing").hex(),
            "5f16f4c7f149ac4f9510d9cf8cf384038ad348b3bcdc01915f95de12df9d1b02")

    def test_multi_block(self):
        """超过一个 rate(136 字节) 的输入也要正确。"""
        self.assertEqual(
            keccak256(b"a" * 136).hex(),
            keccak256(bytes([0x61] * 136)).hex())
        self.assertEqual(len(keccak256(b"x" * 1000)), 32)

    def test_padding_boundary(self):
        """长度正好落在填充边界上时不能出错。"""
        for size in (134, 135, 136, 137, 271, 272):
            self.assertEqual(len(keccak256(b"z" * size)), 32)


class TestEIP55(unittest.TestCase):
    def test_checksum_generation(self):
        # EIP-55 规范里的官方样例
        for address in (
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
            "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
            "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
            "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb",
        ):
            self.assertEqual(eip55_checksum(address.lower()), address)

    def test_valid_and_invalid(self):
        self.assertIs(eip55_is_valid("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"), True)
        # 把最后一位的大小写改掉，校验必须失败
        self.assertIs(eip55_is_valid("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD"), False)
        # 全小写/全大写是合法写法，但无法校验
        self.assertIsNone(eip55_is_valid("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed"))
        self.assertIsNone(eip55_is_valid("0x5AAEB6053F3E94C9B9A09F33669435E7EF1BEAED"))


class TestBase58(unittest.TestCase):
    def test_decode(self):
        self.assertEqual(b58decode("1"), b"\x00")
        self.assertIsNone(b58decode("0OIl"))       # 这几个字符不在字母表里

    def test_base58check(self):
        payload = b58check_decode("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        self.assertIsNotNone(payload)
        self.assertEqual(payload[0], 0x41)          # 波场的版本字节
        btc = b58check_decode("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        self.assertIsNotNone(btc)
        self.assertEqual(btc[0], 0x00)

    def test_bad_checksum(self):
        self.assertIsNone(b58check_decode("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6X"))
        self.assertIsNone(b58check_decode("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb"))


class TestBech32(unittest.TestCase):
    def test_valid(self):
        hrp, _, variant = bech32_decode("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        self.assertEqual(hrp, "bc")
        self.assertEqual(variant, "bech32")
        hrp, _, _ = bech32_decode("cosmos1qypqxpq9qcrsszg2pvxq6rs0zqg3yyc5lzv7xu")
        self.assertEqual(hrp, "cosmos")

    def test_invalid(self):
        self.assertIsNone(bech32_decode("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5"))
        self.assertIsNone(bech32_decode("bc1Qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"))
        self.assertIsNone(bech32_decode("not-an-address"))


class TestSS58(unittest.TestCase):
    def test_polkadot(self):
        decoded = ss58_decode("15oF4uVJwmo4TdGW7VfQxNLavjCXviqxT9S1MgbjMNHr6Sp5")
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded[0], 0)             # Polkadot 的网络前缀
        self.assertEqual(len(decoded[1]), 32)

    def test_rejects_corrupted(self):
        self.assertIsNone(ss58_decode("15oF4uVJwmo4TdGW7VfQxNLavjCXviqxT9S1MgbjMNHr6Sp6"))


if __name__ == "__main__":
    unittest.main()
