"""链知识库的数据完整性测试。

这些测试的目的是：以后往 chains.py 里加链时，别名冲突、重复 chainId、
地址形态写错这类问题会立刻暴露出来，而不是等到用户转错币才发现。
"""

import unittest

from chainmatch import chains, textmatch


class TestRegistryIntegrity(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [c.id for c in chains.CHAINS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_chain_has_required_fields(self):
        for chain in chains.CHAINS:
            self.assertTrue(chain.id, chain)
            self.assertTrue(chain.name_en, chain.id)
            self.assertTrue(chain.native, chain.id)
            self.assertTrue(chain.aliases, chain.id)
            self.assertIn(chain.family,
                          {"evm", "utxo", "cosmos", "substrate", "move", "other"}, chain.id)

    def test_evm_chain_ids_are_unique(self):
        seen = {}
        for chain in chains.CHAINS:
            if chain.evm_chain_id is None:
                continue
            self.assertNotIn(chain.evm_chain_id, seen,
                             f"{chain.id} 与 {seen.get(chain.evm_chain_id)} 的 chainId 冲突")
            seen[chain.evm_chain_id] = chain.id

    def test_evm_chains_are_reachable_by_chain_id(self):
        for chain in chains.CHAINS:
            if chain.evm_chain_id is not None:
                self.assertEqual(chains.by_evm_chain_id(chain.evm_chain_id), chain.id)

    def test_addr_kinds_are_known(self):
        known = {
            "evm", "tron", "solana", "ton", "hex64", "near", "ada", "ss58", "icp",
            "btc-base58", "btc-bech32", "ltc-base58", "ltc-bech32", "doge", "dash",
            "zec-transparent", "bch-cashaddr", "xrp", "xlm", "algo", "hedera",
            "filecoin", "tezos", "eos-name", "kaspa", "xmr", "neo", "stacks",
            "waves", "flow", "multiversx", "bnb-beacon", "bech32-cosmos",
        }
        for chain in chains.CHAINS:
            for kind in chain.addr_kinds:
                self.assertIn(kind, known, f"{chain.id} 使用了未知的地址形态 {kind}")

    def test_bech32_prefixes_map_back(self):
        for chain in chains.CHAINS:
            for hrp in chain.bech32_hrp:
                self.assertIn(chain.id, chains.by_bech32_hrp(hrp))


class TestAliasCollisions(unittest.TestCase):
    def test_no_alias_points_to_two_chains_unless_declared_ambiguous(self):
        """一个别名指向多条链时，必须显式登记在 AMBIGUOUS_TERMS 里。"""
        declared = {textmatch.normalize(t) for t in chains.AMBIGUOUS_TERMS}
        owners: dict[str, list[str]] = {}
        for chain in chains.CHAINS:
            for alias in chain.aliases:
                owners.setdefault(textmatch.normalize(alias), []).append(chain.id)
        for alias, ids in owners.items():
            unique = sorted(set(ids))     # 同一条链内的写法冗余（brc20/brc-20）无所谓
            if len(unique) > 1:
                self.assertIn(alias, declared,
                              f"别名“{alias}”同时属于 {unique}，请登记为歧义词或改名")

    def test_ambiguous_terms_reference_real_chains(self):
        for term, ids in chains.AMBIGUOUS_TERMS.items():
            for chain_id in ids:
                self.assertIn(chain_id, chains.BY_ID, f"歧义词 {term} 指向了不存在的链 {chain_id}")

    def test_token_only_terms_are_not_chain_aliases(self):
        """USDT 之类的币种名不能同时是某条链的别名。"""
        all_aliases = {textmatch.normalize(a) for c in chains.CHAINS for a in c.aliases}
        for term in chains.TOKEN_ONLY_TERMS:
            self.assertNotIn(textmatch.normalize(term), all_aliases, term)

    def test_every_alias_resolves_to_its_own_chain(self):
        """每条链的每个别名，单独输入时都应该能解析回这条链。"""
        for chain in chains.CHAINS:
            for alias in chain.aliases:
                if textmatch.normalize(alias) in {
                    textmatch.normalize(t) for t in chains.AMBIGUOUS_TERMS
                }:
                    continue
                signals = textmatch.match_text(alias)
                resolved = {c for s in signals for c in s.chains}
                self.assertIn(chain.id, resolved, f"别名“{alias}”没能解析回 {chain.id}")


class TestLookups(unittest.TestCase):
    def test_label_is_human_readable(self):
        self.assertIn("波场", chains.label("tron"))
        self.assertIn("TRX", chains.label("tron"))
        self.assertEqual(chains.label("unknown-chain"), "unknown-chain")

    def test_by_addr_kind(self):
        evm = chains.by_addr_kind("evm")
        self.assertIn("ethereum", evm)
        self.assertIn("bsc", evm)
        self.assertNotIn("tron", evm)
        self.assertNotIn("bitcoin", evm)

    def test_search(self):
        self.assertTrue(chains.search("trc20"))
        self.assertTrue(chains.search("波场"))
        self.assertEqual(chains.search(""), list(chains.CHAINS))
        self.assertEqual(chains.search("这条链不存在"), [])

    def test_major_chains_are_present(self):
        for chain_id in ("bitcoin", "ethereum", "bsc", "tron", "solana",
                         "polygon", "arbitrum", "ton", "avalanche-c", "base"):
            self.assertIn(chain_id, chains.BY_ID)


if __name__ == "__main__":
    unittest.main()
