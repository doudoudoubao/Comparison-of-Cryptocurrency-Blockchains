"""端到端对比测试：这些用例对应真实的转账场景。"""

import unittest

from chainmatch import DIFFERENT, POSSIBLY_SAME, SAME, UNKNOWN, compare_inputs, identify

USDT_ETH = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDT_TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
WBTC_ETH = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
BTC_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"


class TestSameChain(unittest.TestCase):
    def test_standard_and_chinese_name(self):
        result = compare_inputs("USDT-TRC20", "波场")
        self.assertEqual(result.verdict, SAME)
        self.assertEqual(result.a.top, "tron")

    def test_name_and_address(self):
        result = compare_inputs("TRC20", USDT_TRON)
        self.assertEqual(result.verdict, SAME)

    def test_english_and_chinese(self):
        self.assertEqual(compare_inputs("Bitcoin", "比特币").verdict, SAME)
        self.assertEqual(compare_inputs("BTC", BTC_ADDR).verdict, SAME)

    def test_alias_variants(self):
        for left, right in [
            ("BEP20", "币安智能链"),
            ("BSC", "BNB Smart Chain"),
            ("matic", "Polygon"),
            ("AVAXC", "Avalanche C-Chain"),
            ("arbitrum one", "ARB"),
        ]:
            self.assertEqual(compare_inputs(left, right).verdict, SAME, f"{left} vs {right}")

    def test_same_chain_still_advises_verification(self):
        result = compare_inputs("USDT-TRC20", "波场")
        self.assertTrue(result.advice)
        self.assertTrue(any("小额" in a for a in result.advice))


class TestDifferentChain(unittest.TestCase):
    def test_erc20_vs_trc20(self):
        result = compare_inputs("ERC20", "TRC20")
        self.assertEqual(result.verdict, DIFFERENT)
        self.assertTrue(any("永久丢失" in r for r in result.risks))

    def test_address_vs_wrong_network_name(self):
        result = compare_inputs(USDT_TRON, "ERC20")
        self.assertEqual(result.verdict, DIFFERENT)

    def test_bep2_vs_bep20_is_called_out(self):
        result = compare_inputs("BEP20", "BEP2")
        self.assertEqual(result.verdict, DIFFERENT)
        self.assertTrue(any("BEP2" in r and "BEP20" in r for r in result.risks))

    def test_evm_to_evm_risk_is_described_as_recoverable(self):
        """EVM 之间转错，资产还在源链上，风险描述必须和跨体系区分开。"""
        result = compare_inputs("以太坊", "币安智能链")
        self.assertEqual(result.verdict, DIFFERENT)
        joined = " ".join(result.risks)
        self.assertIn("找回", joined)
        self.assertNotIn("永久丢失", joined)

    def test_cross_family_risk_is_permanent(self):
        joined = " ".join(compare_inputs("以太坊", "波场").risks)
        self.assertIn("永久丢失", joined)

    def test_exit_code_is_nonzero(self):
        from chainmatch.report import EXIT_CODES
        self.assertEqual(EXIT_CODES[compare_inputs("ERC20", "TRC20").verdict], 1)


class TestUncertain(unittest.TestCase):
    def test_two_evm_addresses_are_not_declared_same(self):
        """两个 0x 地址不能被说成"同一条链"——这是本工具最重要的一条底线。"""
        result = compare_inputs(USDT_ETH, WBTC_ETH)
        self.assertEqual(result.verdict, POSSIBLY_SAME)
        self.assertNotEqual(result.verdict, SAME)
        self.assertTrue(any("EVM" in r for r in result.risks))

    def test_identical_evm_address_is_still_not_proof(self):
        result = compare_inputs(USDT_ETH, USDT_ETH)
        self.assertEqual(result.verdict, POSSIBLY_SAME)

    def test_chain_name_plus_evm_address(self):
        result = compare_inputs("以太坊", USDT_ETH)
        self.assertEqual(result.verdict, POSSIBLY_SAME)
        self.assertIn("ethereum", result.shared)

    def test_token_names_only(self):
        result = compare_inputs("USDT", "USDC")
        self.assertEqual(result.verdict, UNKNOWN)
        self.assertTrue(any("币种" in a for a in result.advice))


class TestPaymentUri(unittest.TestCase):
    def test_eip681_chain_id_wins_over_scheme(self):
        """ethereum:…@56 其实是 BSC，不能被 scheme 里的 "ethereum" 带偏。"""
        result = compare_inputs(f"ethereum:{USDT_ETH}@56", "BSC")
        self.assertEqual(result.verdict, SAME)
        self.assertEqual(result.a.top, "bsc")

    def test_eip681_detects_mismatch(self):
        result = compare_inputs(f"ethereum:{USDT_ETH}@56", "ERC20")
        self.assertEqual(result.verdict, DIFFERENT)

    def test_caip10(self):
        result = compare_inputs(f"eip155:137:{USDT_ETH}", "Polygon")
        self.assertEqual(result.verdict, SAME)

    def test_tron_uri(self):
        self.assertEqual(compare_inputs(f"tron:{USDT_TRON}", "波场").verdict, SAME)

    def test_bitcoin_uri_with_params(self):
        result = compare_inputs(f"bitcoin:{BTC_ADDR}?amount=0.01", "比特币")
        self.assertEqual(result.verdict, SAME)


class TestBadInput(unittest.TestCase):
    def test_broken_address_never_reports_safe(self):
        broken = USDT_TRON[:-1] + "X"
        result = compare_inputs(broken, "TRC20")
        self.assertFalse(result.is_safe)
        self.assertTrue(any("校验" in r for r in result.risks))

    def test_empty_input(self):
        self.assertEqual(compare_inputs("", "").verdict, UNKNOWN)

    def test_garbage_input(self):
        self.assertEqual(compare_inputs("!!!???", "@@@").verdict, UNKNOWN)

    def test_missing_image_file_does_not_crash(self):
        result = compare_inputs("img:/no/such/file.png", "ERC20")
        self.assertEqual(result.verdict, UNKNOWN)
        self.assertTrue(result.a.warnings)


class TestIdentify(unittest.TestCase):
    def test_single_input(self):
        result = identify(USDT_TRON)
        self.assertEqual(result.top, "tron")
        self.assertTrue(result.certain)
        self.assertEqual(result.addresses, [USDT_TRON])

    def test_evm_address_is_not_certain(self):
        result = identify(USDT_ETH)
        self.assertFalse(result.certain)
        self.assertEqual(result.family_hint, "evm")
        self.assertGreater(len(result.candidates), 10)

    def test_sentence_with_address_and_network(self):
        result = identify(f"网络 TRC20，地址 {USDT_TRON}")
        self.assertEqual(result.top, "tron")
        self.assertTrue(result.certain)


class TestSymmetry(unittest.TestCase):
    def test_order_does_not_change_verdict(self):
        pairs = [
            ("ERC20", "TRC20"), ("USDT-TRC20", "波场"), (USDT_ETH, WBTC_ETH),
            ("USDT", "USDC"), ("以太坊", USDT_ETH), ("BEP20", "BEP2"),
        ]
        for left, right in pairs:
            self.assertEqual(
                compare_inputs(left, right).verdict,
                compare_inputs(right, left).verdict,
                f"{left} vs {right}")


if __name__ == "__main__":
    unittest.main()
