"""名称 / 代币标准识别测试。"""

import unittest

from chainmatch import textmatch


def chains_of(text):
    """文本识别出的链（按证据置信度排序）。"""
    signals = textmatch.match_text(text)
    out = []
    for signal in sorted(signals, key=lambda s: -s.confidence):
        for chain_id in signal.chains:
            if chain_id not in out:
                out.append(chain_id)
    return out


class TestNormalize(unittest.TestCase):
    def test_full_width_and_case(self):
        self.assertEqual(textmatch.normalize("ＥＲＣ２０"), "erc20")
        self.assertEqual(textmatch.normalize("  Ethereum  "), "ethereum")

    def test_standard_separators(self):
        for text in ("ERC-20", "ERC 20", "erc—20", "ERC_20"):
            self.assertIn("erc20", textmatch.normalize(text), text)


class TestStandards(unittest.TestCase):
    def test_common_token_standards(self):
        self.assertEqual(chains_of("ERC20")[0], "ethereum")
        self.assertEqual(chains_of("TRC20")[0], "tron")
        self.assertEqual(chains_of("BEP20")[0], "bsc")
        self.assertEqual(chains_of("BEP2")[0], "bnb-beacon-chain")
        self.assertEqual(chains_of("SPL")[0], "solana")

    def test_bep2_and_bep20_never_collide(self):
        """这两个只差一个字符，但是两条不同的链。"""
        self.assertNotEqual(chains_of("BEP2")[0], chains_of("BEP20")[0])

    def test_with_token_prefix(self):
        self.assertEqual(chains_of("USDT-TRC20")[0], "tron")
        self.assertEqual(chains_of("USDT (ERC-20)")[0], "ethereum")


class TestChineseNames(unittest.TestCase):
    def test_common_chinese(self):
        self.assertEqual(chains_of("波场")[0], "tron")
        self.assertEqual(chains_of("以太坊")[0], "ethereum")
        self.assertEqual(chains_of("比特币")[0], "bitcoin")
        self.assertEqual(chains_of("币安智能链")[0], "bsc")
        self.assertEqual(chains_of("以太坊经典")[0], "ethereum-classic")

    def test_longest_match_wins(self):
        """"以太坊经典"不能退化成"以太坊"。"""
        self.assertEqual(chains_of("以太坊经典"), ["ethereum-classic"])
        self.assertEqual(chains_of("bitcoin cash"), ["bitcoin-cash"])
        self.assertEqual(chains_of("polygon zkevm"), ["polygon-zkevm"])


class TestAmbiguity(unittest.TestCase):
    def test_binance_chain_is_ambiguous(self):
        signals = textmatch.match_text("币安链")
        self.assertTrue(signals)
        self.assertGreater(len(signals[0].chains), 1)
        self.assertIn("确认", signals[0].warning)

    def test_token_only_terms_resolve_to_nothing(self):
        signals = textmatch.match_text("USDT")
        self.assertTrue(all(not s.chains for s in signals))
        self.assertTrue(any("币种" in s.detail for s in signals))


class TestWordBoundaries(unittest.TestCase):
    def test_short_alias_not_matched_inside_words(self):
        """"one"/"op"/"eth" 这类短词不能在别的单词里误命中。"""
        self.assertEqual(chains_of("money"), [])
        self.assertEqual(chains_of("shopping"), [])
        self.assertEqual(chains_of("something"), [])

    def test_short_alias_matched_standalone(self):
        self.assertEqual(chains_of("ETH")[0], "ethereum")
        self.assertEqual(chains_of("BTC")[0], "bitcoin")


class TestFuzzy(unittest.TestCase):
    def test_typo_is_caught_with_low_confidence(self):
        signals = textmatch.match_text("Etherium")
        self.assertTrue(signals)
        self.assertEqual(signals[0].kind, "fuzzy")
        self.assertIn("ethereum", signals[0].chains)
        self.assertLess(signals[0].confidence, 0.6)
        self.assertIn("人工核对", signals[0].warning)

    def test_exact_match_does_not_use_fuzzy(self):
        self.assertNotEqual(textmatch.match_text("ethereum")[0].kind, "fuzzy")


class TestSentences(unittest.TestCase):
    def test_finds_network_inside_a_sentence(self):
        self.assertEqual(chains_of("请用 TRC20 网络给我转 100 USDT")[0], "tron")
        self.assertEqual(chains_of("网络：BNB Smart Chain (BEP20)")[0], "bsc")

    def test_ocr_style_text(self):
        text = "提币\n币种 USDT\n网络 Tron (TRC20)\n手续费 1 USDT"
        self.assertEqual(chains_of(text)[0], "tron")


if __name__ == "__main__":
    unittest.main()
