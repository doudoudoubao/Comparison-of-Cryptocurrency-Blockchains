"""地址识别测试。

正面用例里，公开可查的地址直接写死；其余（Cardano / 恒星 / TON 等）在测试里
按各自规范现场构造，避免把记错的字符串当成基准。
"""

import base64
import unittest

from chainmatch import address
from chainmatch._crypto import bech32_encode, convertbits, crc16_xmodem


def chains_of(text):
    hits = address.identify(text)
    return hits[0].chains if hits else ()


def top_hit(text):
    hits = address.identify(text)
    return hits[0] if hits else None


class TestEvm(unittest.TestCase):
    USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

    def test_recognised_as_evm_family(self):
        hit = top_hit(self.USDT)
        self.assertEqual(hit.kind, "evm")
        self.assertEqual(hit.family, "evm")
        self.assertIn("ethereum", hit.chains)
        self.assertIn("bsc", hit.chains)
        self.assertIn("polygon", hit.chains)

    def test_warns_that_address_cannot_identify_chain(self):
        """EVM 地址跨链通用，必须明确告诉用户光看地址定不了链。"""
        self.assertIn("无法判断", top_hit(self.USDT).warning)

    def test_checksum_failure_is_flagged(self):
        broken = self.USDT[:-1] + ("8" if self.USDT[-1] != "8" else "9")
        hit = top_hit(broken)
        self.assertLess(hit.confidence, 0.5)
        self.assertIn("校验和不通过", hit.warning)

    def test_all_lowercase_is_accepted(self):
        hit = top_hit(self.USDT.lower())
        self.assertGreater(hit.confidence, 0.8)
        self.assertEqual(hit.warning and "无法判断" in hit.warning, True)


class TestTron(unittest.TestCase):
    USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    def test_valid(self):
        hit = top_hit(self.USDT)
        self.assertEqual(hit.chains, ("tron",))
        self.assertGreater(hit.confidence, 0.9)

    def test_corrupted_is_flagged_not_silently_accepted(self):
        hit = top_hit(self.USDT[:-1] + "X")
        self.assertEqual(hit.chains, ("tron",))
        self.assertLess(hit.confidence, 0.5)
        self.assertIn("校验失败", hit.warning)


class TestBitcoinFamily(unittest.TestCase):
    def test_p2pkh_is_shared_with_bch(self):
        hit = top_hit("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        self.assertEqual(hit.chains, ("bitcoin", "bitcoin-cash"))
        self.assertIn("比特现金", hit.warning)

    def test_bech32(self):
        self.assertEqual(chains_of("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"), ("bitcoin",))

    def test_p2sh_is_ambiguous(self):
        hit = top_hit("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
        self.assertIn("bitcoin", hit.chains)
        self.assertIn("litecoin", hit.chains)

    def test_testnet_is_rejected_with_warning(self):
        hit = top_hit("tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx")
        self.assertEqual(hit.chains, ())
        self.assertIn("测试网", hit.warning)

    def test_litecoin_and_dogecoin(self):
        self.assertEqual(chains_of("LM2WMpR1Rp6j3Sa59cMXMs1SPzj9eXpGc1"), ("litecoin",))
        self.assertEqual(chains_of("DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L"), ("dogecoin",))


class TestOtherChains(unittest.TestCase):
    def test_solana(self):
        self.assertEqual(chains_of("So11111111111111111111111111111111111111112"), ("solana",))

    def test_ripple(self):
        hit = top_hit("rN7n7otQDd6FczFgLdSqtcsAUxDkw6fzRH")
        self.assertEqual(hit.chains, ("ripple",))
        self.assertIn("Tag", hit.warning)

    def test_polkadot(self):
        self.assertEqual(
            chains_of("15oF4uVJwmo4TdGW7VfQxNLavjCXviqxT9S1MgbjMNHr6Sp5"), ("polkadot",))

    def test_cosmos_bech32_prefixes(self):
        self.assertEqual(chains_of("cosmos1qypqxpq9qcrsszg2pvxq6rs0zqg3yyc5lzv7xu"), ("cosmos",))
        self.assertEqual(
            chains_of("bnb1grpf0955h0ykzq3ar5nmum7y6gdfl6lxfn46h2"), ("bnb-beacon-chain",))

    def test_cardano_shelley(self):
        payload = bytes(range(57))
        addr = bech32_encode("addr", convertbits(payload, 8, 5))
        self.assertEqual(chains_of(addr), ("cardano",))

    def test_stellar(self):
        body = b"\x30" + bytes(range(32))
        addr = base64.b32encode(body + crc16_xmodem(body).to_bytes(2, "little")).decode()
        hit = top_hit(addr)
        self.assertEqual(hit.chains, ("stellar",))
        self.assertGreater(hit.confidence, 0.9)
        self.assertIn("Memo", hit.warning)

    def test_stellar_corrupted(self):
        body = b"\x30" + bytes(range(32))
        bad = base64.b32encode(body + b"\x00\x00").decode()
        self.assertLess(top_hit(bad).confidence, 0.5)

    def test_ton(self):
        body = b"\x11\x00" + bytes(range(32))
        addr = base64.urlsafe_b64encode(
            body + crc16_xmodem(body).to_bytes(2, "big")).decode().rstrip("=")
        hit = top_hit(addr)
        self.assertEqual(hit.chains, ("ton",))
        self.assertGreater(hit.confidence, 0.9)

    def test_aptos_sui_are_ambiguous(self):
        hit = top_hit("0x" + "ab" * 32)
        self.assertIn("aptos", hit.chains)
        self.assertIn("sui", hit.chains)
        self.assertIn("网络名", hit.warning)

    def test_hex64_warns_it_is_probably_a_tx_hash(self):
        """0x+64hex 最常见的其实是交易哈希，不能默默当成 Aptos 地址。"""
        hit = top_hit("0x5c504ed432cb51138bcf09aa5e8a410dd4a1e204ef84bfed1be16dfba1b22060")
        self.assertIn("交易哈希", hit.warning)
        self.assertLess(hit.confidence, 0.5)

    def test_bare_hex64_warns_about_private_keys(self):
        """不带 0x 的 64 位十六进制正是私钥的样子，必须先警告私钥。"""
        hit = top_hit("4c0883a69102937d6231471b5dbb6204fe512961708279f2f3f0e1c0cbb2a2d1")
        self.assertIn("私钥", hit.warning)

    def test_uppercase_evm_address(self):
        """全大写是合法写法，OCR 也常这么输出。"""
        hit = top_hit("0XDAC17F958D2EE523A2206206994597C13D831EC7")
        self.assertEqual(hit.kind, "evm")
        self.assertGreater(hit.confidence, 0.8)

    def test_near_named_account(self):
        self.assertEqual(chains_of("alice.near"), ("near",))

    def test_hedera(self):
        self.assertEqual(chains_of("0.0.123456"), ("hedera",))


class TestNonAddresses(unittest.TestCase):
    def test_plain_words_are_not_addresses(self):
        for text in ("ERC20", "以太坊", "hello world", "USDT", "", "1234"):
            self.assertEqual(address.identify(text), [], text)


class TestScan(unittest.TestCase):
    def test_finds_address_inside_a_sentence(self):
        text = "请转到这个地址 TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t 谢谢"
        found = address.scan(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        self.assertEqual(found[0][1][0].chains, ("tron",))

    def test_finds_multiple(self):
        text = ("ETH: 0xdAC17F958D2ee523a2206206994597C13D831ec7\n"
                "BTC: bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        self.assertEqual(len(address.scan(text)), 2)


if __name__ == "__main__":
    unittest.main()
