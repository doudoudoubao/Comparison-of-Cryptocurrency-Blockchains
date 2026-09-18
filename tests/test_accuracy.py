"""准确性回归测试。

这里的每条用例都对应一个真实踩过的坑。识别准确性是这个工具的全部价值——
判断错了比没有判断更危险，所以这些用例只增不减。
"""

import unittest

from chainmatch import compare_inputs, identify

# 各大交易所提币页上实际出现过的网络名写法
REAL_NETWORK_NAMES = {
    # 代号
    "BTC": "bitcoin", "ETH": "ethereum", "TRX": "tron", "BSC": "bsc", "BNB": "bsc",
    "MATIC": "polygon", "POL": "polygon", "AVAXC": "avalanche-c", "SOL": "solana",
    "DOT": "polkadot", "ATOM": "cosmos", "XRP": "ripple", "XLM": "stellar",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "DOGE": "dogecoin", "TON": "ton",
    "ETC": "ethereum-classic", "FTM": "sonic", "KLAY": "kaia", "EGLD": "multiversx",
    "CORE": "core", "MNT": "mantle", "XDAI": "gnosis", "GLMR": "moonbeam",
    # 全称与带括号的写法
    "BNB Smart Chain (BEP20)": "bsc", "Ethereum (ERC20)": "ethereum",
    "Tron (TRC20)": "tron", "Polygon (MATIC)": "polygon",
    "Arbitrum One (ARB)": "arbitrum", "Optimism (OP Mainnet)": "optimism",
    "BNB Beacon Chain (BEP2)": "bnb-beacon-chain", "AVAX C-Chain": "avalanche-c",
    "zkSync Era": "zksync-era", "X Layer": "xlayer", "opBNB": "opbnb",
    # 带币种前缀
    "USDT-ERC20": "ethereum", "USDT-BEP20": "bsc", "USDT-Polygon": "polygon",
    "USDT-TRC20": "tron",
    # 中文
    "以太坊": "ethereum", "波场": "tron", "币安智能链": "bsc", "比特币": "bitcoin",
    "以太坊经典": "ethereum-classic", "火币生态链": "heco", "比特现金": "bitcoin-cash",
    "雪崩": "avalanche-c", "唯链": "vechain", "门罗币": "monero", "恒星币": "stellar",
}

# 不该被认成链名的普通文本——多半是 OCR 把界面文字一起读进来了
ORDINARY_TEXT = (
    "scroll down to see more options",
    "cash flow statement for this quarter",
    "the base amount before fees",
    "core team meeting at 3pm",
    "please dash to the bank before it closes",
    "ocean waves sound nice tonight",
    "one more thing before you go",
    "sonic the hedgehog game",
    "we are near the office now",
    "a ton of work to do today",
    "click here to open the app",
    "转账金额 100.00 元 手续费 2 元",
    "收款人 张三 备注 房租",
    "订单编号 20260918001 已完成",
)


class TestRealNetworkNames(unittest.TestCase):
    def test_all_real_names_resolve_correctly(self):
        wrong = {
            text: (expected, identify(text).top)
            for text, expected in REAL_NETWORK_NAMES.items()
            if identify(text).top != expected
        }
        self.assertEqual(wrong, {}, f"这些交易所写法识别错了：{wrong}")


class TestCommonWordAliases(unittest.TestCase):
    """Base / Core / Flow / Scroll 这些链名本身就是常用英文词。"""

    def test_ordinary_sentences_are_not_confidently_matched(self):
        confident = [text for text in ORDINARY_TEXT if identify(text).certain]
        self.assertEqual(confident, [], f"普通句子被当成了链名：{confident}")

    def test_the_word_alone_is_still_the_chain(self):
        for word, expected in [
            ("Base", "base"), ("CORE", "core"), ("Flow", "flow"), ("Scroll", "scroll"),
            ("Blast", "blast"), ("Dash", "dash"), ("Waves", "waves"), ("NEAR", "near"),
            ("TON", "ton"), ("Sonic", "sonic"), ("OP", "optimism"), ("Sui", "sui"),
        ]:
            result = identify(word)
            self.assertEqual(result.top, expected, word)
            self.assertTrue(result.certain, word)

    def test_network_context_restores_confidence(self):
        for text, expected in [
            ("网络 Base", "base"), ("Base 主网", "base"),
            ("Withdraw to Base network", "base"), ("提币网络 Scroll", "scroll"),
            ("Sonic 链", "sonic"), ("转账到 Dash 网络", "dash"),
        ]:
            self.assertEqual(identify(text).top, expected, text)


class TestConflictingEvidence(unittest.TestCase):
    """一个输入里出现多条链时，不能靠分数差 0.01 替用户选一条。"""

    def test_two_addresses_of_different_chains(self):
        text = ("ERC20: 0xdAC17F958D2ee523a2206206994597C13D831ec7\n"
                "TRC20: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        result = identify(text)
        self.assertTrue(result.conflicts)
        self.assertFalse(result.certain)
        self.assertTrue(any("不同链" in w for w in result.warnings))

    def test_exchange_page_listing_several_networks(self):
        result = identify("○ TRC20   ● ERC20   ○ BEP20(BSC)")
        self.assertTrue(result.conflicts)
        self.assertFalse(result.certain)

    def test_conflict_surfaces_in_comparison_risks(self):
        text = ("ERC20 0xdAC17F958D2ee523a2206206994597C13D831ec7 "
                "TRC20 TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        result = compare_inputs(text, "TRC20")
        self.assertTrue(any("同时出现" in r for r in result.risks))
        self.assertFalse(result.is_safe)

    def test_normal_inputs_are_not_flagged_as_conflicting(self):
        for text in (
            "USDT-TRC20",
            "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "网络 TRC20，地址 TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "ERC20 0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "ethereum:0xdAC17F958D2ee523a2206206994597C13D831ec7@56",
            "以太坊主网 ERC-20 网络",
            "Avalanche C-Chain (AVAX C)",
        ):
            self.assertEqual(identify(text).conflicts, (), text)


class TestSensitiveInput(unittest.TestCase):
    """用户可能把不该给的东西贴进来。"""

    def test_mnemonic_is_warned_about(self):
        words = "abandon " * 11 + "about"
        result = identify(words)
        self.assertTrue(any("助记词" in w for w in result.warnings))

    def test_ordinary_twelve_word_sentence_is_not_flagged(self):
        text = "please send the money to my wallet address as soon as possible"
        self.assertFalse(any("助记词" in w for w in identify(text).warnings))

    def test_private_key_shaped_input_is_warned_about(self):
        key = "4c0883a69102937d6231471b5dbb6204fe512961708279f2f3f0e1c0cbb2a2d1"
        self.assertTrue(any("私钥" in w for w in identify(key).warnings))

    def test_transaction_hash_is_not_silently_called_an_address(self):
        tx = "0x5c504ed432cb51138bcf09aa5e8a410dd4a1e204ef84bfed1be16dfba1b22060"
        result = identify(tx)
        self.assertFalse(result.certain)
        self.assertTrue(any("交易哈希" in w for w in result.warnings))


class TestOcrDamage(unittest.TestCase):
    """OCR 会把地址断行、把整行变成大写。"""

    def test_uppercase_evm_address(self):
        result = identify("0XDAC17F958D2EE523A2206206994597C13D831EC7")
        self.assertEqual(result.family_hint, "evm")
        self.assertIn("0XDAC17F958D2EE523A2206206994597C13D831EC7", result.addresses)

    def test_address_split_by_spaces_is_rejoined(self):
        result = identify("TR7NHqjeKQxGT Ci8q8ZY4pL8ot SzgjLj6t")
        self.assertEqual(result.top, "tron")
        self.assertEqual(result.addresses, ["TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"])

    def test_rejoin_never_invents_an_address(self):
        """没有校验和可验的拼接结果一律不采信，随机文本更不能拼出地址。"""
        for text in (
            "hello world this is just a normal sentence with many words",
            "abc def ghi jkl mno pqr stu vwx yz1 234 567 890",
            "0xdac17f958d2ee523a22 06206994597c13d831ec7",   # 全小写，无校验和
        ):
            self.assertEqual(identify(text).addresses, [], text)


class TestSafetyGate(unittest.TestCase):
    """is_safe 是给脚本用的闸门，必须偏保守。"""

    def test_clear_match_is_safe(self):
        self.assertTrue(compare_inputs("USDT-TRC20", "波场").is_safe)

    def test_checksum_failure_is_never_safe(self):
        broken = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6X"
        self.assertFalse(compare_inputs(broken, "TRC20").is_safe)

    def test_two_evm_addresses_are_never_safe(self):
        usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        self.assertFalse(compare_inputs(usdt, usdt).is_safe)

    def test_different_chains_are_never_safe(self):
        self.assertFalse(compare_inputs("ERC20", "TRC20").is_safe)


if __name__ == "__main__":
    unittest.main()
