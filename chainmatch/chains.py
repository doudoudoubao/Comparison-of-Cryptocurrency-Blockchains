"""链知识库：链名、别名、代币标准、地址形态的单一数据源。

`alias` 字段用 "|" 分隔，尽量收录三类写法：

1. 官方名与中文名（Ethereum / 以太坊 / 以太幣）
2. 代币标准（ERC20 / TRC20 / BEP20 / SPL …）
3. 交易所充提页面上的网络名（AVAXC / Arbitrum One / opBNB …）

新增链时只改这一个文件：地址识别、名称匹配、展示都从这里读。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chain:
    """一条区块链。"""

    id: str
    name_en: str
    name_zh: str
    native: str
    family: str                       # evm / utxo / cosmos / substrate / move / other
    aliases: tuple[str, ...]
    standards: tuple[str, ...] = ()   # 代币标准，仅用于展示
    evm_chain_id: int | None = None   # EIP-155 chainId，用于解析 EIP-681 二维码
    addr_kinds: tuple[str, ...] = ()  # 关联的地址形态，见 address.py
    bech32_hrp: tuple[str, ...] = ()  # bech32 地址的人类可读前缀
    note: str = ""

    @property
    def label(self) -> str:
        """人类可读的链名，例如 "以太坊 Ethereum (ETH)"。"""
        if self.name_zh and self.name_zh != self.name_en:
            return f"{self.name_zh} {self.name_en} ({self.native})"
        return f"{self.name_en} ({self.native})"


def _c(chain_id, en, zh, native, family, alias, **kw) -> Chain:
    return Chain(
        id=chain_id,
        name_en=en,
        name_zh=zh,
        native=native,
        family=family,
        aliases=tuple(a.strip() for a in alias.split("|") if a.strip()),
        **kw,
    )


# --------------------------------------------------------------------------
# 链表
# --------------------------------------------------------------------------

CHAINS: tuple[Chain, ...] = (
    # ---- UTXO / 比特币系 ----
    _c("bitcoin", "Bitcoin", "比特币", "BTC", "utxo",
       "btc|xbt|bitcoin|比特币|比特幣|比特币网络|比特币主网|bitcoin mainnet|btc network|"
       "omni|omni layer|usdt-omni|brc20|brc-20|runes|ordinals|taproot|segwit",
       standards=("Omni", "BRC-20", "Runes"),
       addr_kinds=("btc-base58", "btc-bech32"), bech32_hrp=("bc",),
       note="BRC-20 / Runes / Ordinals / Omni 都寄生在比特币主网，底层仍是 BTC 网络"),
    _c("litecoin", "Litecoin", "莱特币", "LTC", "utxo",
       "ltc|litecoin|莱特币|萊特幣|litecoin network",
       addr_kinds=("ltc-base58", "ltc-bech32"), bech32_hrp=("ltc",)),
    _c("dogecoin", "Dogecoin", "狗狗币", "DOGE", "utxo",
       "doge|dogecoin|狗狗币|狗狗幣|狗币|柴犬币主网",
       addr_kinds=("doge",)),
    _c("bitcoin-cash", "Bitcoin Cash", "比特现金", "BCH", "utxo",
       "bch|bitcoin cash|bitcoincash|比特现金|比特現金|bch network",
       addr_kinds=("bch-cashaddr", "btc-base58")),
    _c("dash", "Dash", "达世币", "DASH", "utxo",
       "dash|达世币|達世幣|dash network", addr_kinds=("dash",)),
    _c("zcash", "Zcash", "大零币", "ZEC", "utxo",
       "zec|zcash|大零币|大零幣|zcash network", addr_kinds=("zec-transparent",),
       bech32_hrp=("zs",)),
    _c("monero", "Monero", "门罗币", "XMR", "other",
       "xmr|monero|门罗币|門羅幣|monero network", addr_kinds=("xmr",)),
    _c("kaspa", "Kaspa", "卡斯帕", "KAS", "other",
       "kas|kaspa|卡斯帕", addr_kinds=("kaspa",)),

    # ---- 以太坊与 EVM 系 ----
    _c("ethereum", "Ethereum", "以太坊", "ETH", "evm",
       "eth|ether|ethereum|以太坊|以太幣|以太坊主网|以太坊网络|erc20|erc-20|erc 20|erc721|erc-721|"
       "erc1155|erc-1155|ethereum mainnet|eth mainnet|eth主网|以太坊主網|mainnet eth",
       standards=("ERC-20", "ERC-721", "ERC-1155"), evm_chain_id=1,
       addr_kinds=("evm",)),
    _c("bsc", "BNB Smart Chain", "币安智能链", "BNB", "evm",
       "bsc|bnb|bep20|bep-20|bep 20|bnb smart chain|binance smart chain|币安智能链|幣安智能鏈|"
       "币安智能链主网|bsc主网|bnb chain|bsc network|smart chain",
       standards=("BEP-20",), evm_chain_id=56, addr_kinds=("evm",),
       note="交易所写作 BEP20 / BSC / BNB Smart Chain，与 BEP2 的 BNB Beacon Chain 不是同一条链"),
    _c("bnb-beacon-chain", "BNB Beacon Chain", "币安信标链", "BNB", "other",
       "bep2|bep-2|bep 2|beacon chain|bnb beacon chain|币安信标链|幣安信標鏈|binance chain bep2",
       standards=("BEP-2",), addr_kinds=("bnb-beacon",), bech32_hrp=("bnb",),
       note="老的币安链（BEP2），地址以 bnb1 开头，已停止出块，切勿与 BSC 混淆"),
    _c("polygon", "Polygon PoS", "Polygon", "POL", "evm",
       "matic|pol|polygon|polygon pos|matic network|polygon network|polygon主网|马蹄链|馬蹄鏈|polygonpos|polygon matic",
       standards=("ERC-20",), evm_chain_id=137, addr_kinds=("evm",),
       note="原生代币已由 MATIC 更名为 POL"),
    _c("polygon-zkevm", "Polygon zkEVM", "Polygon zkEVM", "ETH", "evm",
       "polygon zkevm|zkevm polygon|polygon zk", evm_chain_id=1101, addr_kinds=("evm",)),
    _c("arbitrum", "Arbitrum One", "Arbitrum One", "ETH", "evm",
       "arb|arbitrum|arbitrum one|arbitrum主网|arb one|arbitrum network|arbitrum-one",
       evm_chain_id=42161, addr_kinds=("evm",)),
    _c("arbitrum-nova", "Arbitrum Nova", "Arbitrum Nova", "ETH", "evm",
       "arbitrum nova|arb nova|arbnova", evm_chain_id=42170, addr_kinds=("evm",)),
    _c("optimism", "OP Mainnet", "Optimism", "ETH", "evm",
       "op|optimism|op mainnet|optimism主网|op主网|optimistic ethereum|optimism network",
       evm_chain_id=10, addr_kinds=("evm",)),
    _c("base", "Base", "Base", "ETH", "evm",
       "base|base mainnet|base chain|base network|base主网|coinbase base",
       evm_chain_id=8453, addr_kinds=("evm",)),
    _c("avalanche-c", "Avalanche C-Chain", "雪崩 C 链", "AVAX", "evm",
       "avax|avaxc|avax-c|avalanche|avalanche c|avalanche c-chain|c-chain|雪崩|雪崩链|"
       "avalanche cchain|avax c chain|avaxcchain|avaxccchain|avalanche c chain",
       evm_chain_id=43114, addr_kinds=("evm",),
       note="仅 C 链兼容 EVM；X 链 / P 链地址以 X- / P- 开头，互不相同"),
    _c("cronos", "Cronos", "Cronos", "CRO", "evm",
       "cro|cronos|cronos chain|克罗诺斯", evm_chain_id=25, addr_kinds=("evm",)),
    _c("sonic", "Sonic", "Sonic", "S", "evm",
       "ftm|fantom|fantom opera|sonic|sonic chain|sonic labs|幽灵链",
       evm_chain_id=146, addr_kinds=("evm",),
       note="Fantom Opera 已升级更名为 Sonic（旧 chainId 250，新链 146）"),
    _c("zksync-era", "zkSync Era", "zkSync Era", "ETH", "evm",
       "zksync|zksync era|zks|zksync2|zksync-era|zksyncera|zke", evm_chain_id=324, addr_kinds=("evm",)),
    _c("linea", "Linea", "Linea", "ETH", "evm",
       "linea|linea mainnet", evm_chain_id=59144, addr_kinds=("evm",)),
    _c("scroll", "Scroll", "Scroll", "ETH", "evm",
       "scroll|scroll mainnet", evm_chain_id=534352, addr_kinds=("evm",)),
    _c("mantle", "Mantle", "Mantle", "MNT", "evm",
       "mnt|mantle|mantle network", evm_chain_id=5000, addr_kinds=("evm",)),
    _c("blast", "Blast", "Blast", "ETH", "evm",
       "blast|blast network", evm_chain_id=81457, addr_kinds=("evm",)),
    _c("starknet", "Starknet", "Starknet", "STRK", "other",
       "strk|starknet|stark net", addr_kinds=("hex64",),
       note="Starknet 地址是 0x 开头的 64 位十六进制，与 EVM 的 40 位地址不同"),
    _c("celo", "Celo", "Celo", "CELO", "evm",
       "celo|celo network", evm_chain_id=42220, addr_kinds=("evm",)),
    _c("gnosis", "Gnosis Chain", "Gnosis 链", "XDAI", "evm",
       "xdai|gnosis|gnosis chain|gno chain", evm_chain_id=100, addr_kinds=("evm",)),
    _c("moonbeam", "Moonbeam", "Moonbeam", "GLMR", "evm",
       "glmr|moonbeam", evm_chain_id=1284, addr_kinds=("evm",)),
    _c("kaia", "Kaia", "Kaia", "KAIA", "evm",
       "klay|klaytn|kaia|klaytn network|kaia mainnet", evm_chain_id=8217, addr_kinds=("evm",),
       note="Klaytn 与 Finschia 合并后更名为 Kaia"),
    _c("metis", "Metis", "Metis", "METIS", "evm",
       "metis|metis andromeda", evm_chain_id=1088, addr_kinds=("evm",)),
    _c("opbnb", "opBNB", "opBNB", "BNB", "evm",
       "opbnb|op bnb|opbnb mainnet", evm_chain_id=204, addr_kinds=("evm",),
       note="opBNB 是 BSC 的 L2，与 BSC 主网不是同一条链"),
    _c("heco", "HECO Chain", "火币生态链", "HT", "evm",
       "heco|hrc20|hrc-20|huobi eco|火币生态链|火幣生態鏈|heco chain",
       standards=("HRC-20",), evm_chain_id=128, addr_kinds=("evm",)),
    _c("oktc", "OKT Chain", "OKT 链", "OKT", "evm",
       "okt|oktc|okc|okexchain|okex chain|okt chain|krc20|krc-20|欧易链|欧科链",
       standards=("KIP-20",), evm_chain_id=66, addr_kinds=("evm",)),
    _c("xlayer", "X Layer", "X Layer", "OKB", "evm",
       "xlayer|x layer|x-layer|okb chain", evm_chain_id=196, addr_kinds=("evm",)),
    _c("core", "Core", "Core 链", "CORE", "evm",
       "core|core chain|coredao|core dao|core blockchain|core dao chain", evm_chain_id=1116, addr_kinds=("evm",)),
    _c("berachain", "Berachain", "Berachain", "BERA", "evm",
       "bera|berachain", evm_chain_id=80094, addr_kinds=("evm",)),
    _c("ethereum-classic", "Ethereum Classic", "以太坊经典", "ETC", "evm",
       "etc|ethereum classic|以太坊经典|以太經典|etc network",
       evm_chain_id=61, addr_kinds=("evm",)),
    _c("ethereum-pow", "EthereumPoW", "以太坊 PoW", "ETHW", "evm",
       "ethw|ethereumpow|ethereum pow|eth pow", evm_chain_id=10001, addr_kinds=("evm",)),
    _c("aurora", "Aurora", "Aurora", "ETH", "evm",
       "aurora|aurora chain", evm_chain_id=1313161554, addr_kinds=("evm",)),
    _c("astar", "Astar", "Astar", "ASTR", "evm",
       "astr|astar|astar network", evm_chain_id=592, addr_kinds=("evm", "ss58")),
    _c("conflux", "Conflux eSpace", "Conflux", "CFX", "evm",
       "cfx|conflux|conflux espace|树图链", evm_chain_id=1030, addr_kinds=("evm",),
       note="Core Space 地址以 cfx: 开头，与 eSpace 的 0x 地址是两套空间"),
    _c("vechain", "VeChain Thor", "唯链", "VET", "evm",
       "vet|vechain|vechain thor|唯链|唯鏈|vtho", addr_kinds=("evm",),
       note="地址格式与以太坊相同，但不属于 EVM 主流互通网络"),
    _c("iotex", "IoTeX", "IoTeX", "IOTX", "evm",
       "iotx|iotex", evm_chain_id=4689, addr_kinds=("evm",), bech32_hrp=("io",)),
    _c("harmony", "Harmony", "Harmony", "ONE", "evm",
       "harmony|harmony one|harmony network", evm_chain_id=1666600000,
       addr_kinds=("evm",), bech32_hrp=("one",)),
    _c("chiliz", "Chiliz Chain", "Chiliz", "CHZ", "evm",
       "chz|chiliz|chiliz chain", evm_chain_id=88888, addr_kinds=("evm",)),
    _c("zetachain", "ZetaChain", "ZetaChain", "ZETA", "evm",
       "zeta|zetachain", evm_chain_id=7000, addr_kinds=("evm",), bech32_hrp=("zeta",)),
    _c("manta", "Manta Pacific", "Manta", "MANTA", "evm",
       "manta|manta pacific", evm_chain_id=169, addr_kinds=("evm",)),

    # ---- 波场 ----
    _c("tron", "Tron", "波场", "TRX", "other",
       "trx|tron|波场|波場|波场链|trc20|trc-20|trc 20|trc10|trc-10|tron network|tron主网|"
       "波场网络|波场主网|tronlink|usdt-trc20",
       standards=("TRC-20", "TRC-10"), addr_kinds=("tron",),
       note="USDT-TRC20 最常用的网络，地址以 T 开头"),

    # ---- Solana / Move / 其他公链 ----
    _c("solana", "Solana", "索拉纳", "SOL", "other",
       "sol|solana|索拉纳|spl|spl-token|spl token|solana network|solana主网|sol主网",
       standards=("SPL",), addr_kinds=("solana",)),
    _c("ton", "The Open Network", "TON", "TON", "other",
       "ton|toncoin|the open network|ton network|jetton|tep74|tep-74|ton主网|电报链",
       standards=("Jetton",), addr_kinds=("ton",)),
    _c("aptos", "Aptos", "Aptos", "APT", "move",
       "apt|aptos|aptos network", addr_kinds=("hex64",)),
    _c("sui", "Sui", "Sui", "SUI", "move",
       "sui|sui network|sui主网", addr_kinds=("hex64",)),
    _c("near", "NEAR Protocol", "NEAR", "NEAR", "other",
       "near|near protocol|nep141|nep-141", standards=("NEP-141",),
       addr_kinds=("near", "hex64")),
    _c("cardano", "Cardano", "卡尔达诺", "ADA", "other",
       "ada|cardano|卡尔达诺|艾达币|cardano network", addr_kinds=("ada",), bech32_hrp=("addr",)),
    _c("polkadot", "Polkadot", "波卡", "DOT", "substrate",
       "dot|polkadot|波卡|波卡链|polkadot network", addr_kinds=("ss58",)),
    _c("kusama", "Kusama", "Kusama", "KSM", "substrate",
       "ksm|kusama", addr_kinds=("ss58",)),
    _c("ripple", "XRP Ledger", "瑞波", "XRP", "other",
       "xrp|ripple|瑞波|瑞波币|xrpl|xrp ledger|xrp主网", addr_kinds=("xrp",),
       note="转入交易所通常必须填写 Tag / Memo，否则无法入账"),
    _c("stellar", "Stellar", "恒星币", "XLM", "other",
       "xlm|stellar|恒星币|恒星幣|stellar network", addr_kinds=("xlm",),
       note="转入交易所通常必须填写 Memo"),
    _c("algorand", "Algorand", "Algorand", "ALGO", "other",
       "algo|algorand|asa", standards=("ASA",), addr_kinds=("algo",)),
    _c("hedera", "Hedera", "Hedera", "HBAR", "other",
       "hbar|hedera|hedera hashgraph", addr_kinds=("hedera",)),
    _c("filecoin", "Filecoin", "Filecoin", "FIL", "other",
       "fil|filecoin|文件币", addr_kinds=("filecoin",)),
    _c("tezos", "Tezos", "Tezos", "XTZ", "other",
       "xtz|tezos|fa12|fa-1.2|fa2", standards=("FA1.2", "FA2"), addr_kinds=("tezos",)),
    _c("eos", "EOS", "EOS", "EOS", "other",
       "eos|eos network|柚子币", addr_kinds=("eos-name",),
       note="账户名形式的地址，转账通常需要 Memo"),
    _c("waves", "Waves", "Waves", "WAVES", "other",
       "waves|waves network", addr_kinds=("waves",)),
    _c("neo", "Neo", "小蚁", "NEO", "other",
       "neo|小蚁|neo n3|nep5|nep-5|nep17|nep-17", standards=("NEP-17",),
       addr_kinds=("neo",)),
    _c("icp", "Internet Computer", "互联网计算机", "ICP", "other",
       "icp|internet computer|dfinity", addr_kinds=("icp",)),
    _c("stacks", "Stacks", "Stacks", "STX", "other",
       "stx|stacks|sip10|sip-10", standards=("SIP-010",), addr_kinds=("stacks",)),
    _c("multiversx", "MultiversX", "MultiversX", "EGLD", "other",
       "egld|elrond|multiversx|esdt", standards=("ESDT",),
       addr_kinds=("multiversx",), bech32_hrp=("erd",)),
    _c("flow", "Flow", "Flow", "FLOW", "other",
       "flow|flow blockchain|flow network", addr_kinds=("flow",)),

    # ---- Cosmos 生态 ----
    _c("cosmos", "Cosmos Hub", "Cosmos", "ATOM", "cosmos",
       "atom|cosmos|cosmos hub|宇宙链|ibc", addr_kinds=("bech32-cosmos",),
       bech32_hrp=("cosmos",)),
    _c("osmosis", "Osmosis", "Osmosis", "OSMO", "cosmos",
       "osmo|osmosis", addr_kinds=("bech32-cosmos",), bech32_hrp=("osmo",)),
    _c("celestia", "Celestia", "Celestia", "TIA", "cosmos",
       "tia|celestia", addr_kinds=("bech32-cosmos",), bech32_hrp=("celestia",)),
    _c("injective", "Injective", "Injective", "INJ", "cosmos",
       "inj|injective", addr_kinds=("bech32-cosmos", "evm"), bech32_hrp=("inj",)),
    _c("sei", "Sei", "Sei", "SEI", "cosmos",
       "sei|sei network", addr_kinds=("bech32-cosmos", "evm"), bech32_hrp=("sei",)),
    _c("kava", "Kava", "Kava", "KAVA", "cosmos",
       "kava|kava network", addr_kinds=("bech32-cosmos", "evm"), bech32_hrp=("kava",)),
    _c("thorchain", "THORChain", "雷神链", "RUNE", "cosmos",
       "rune|thorchain|thor chain", addr_kinds=("bech32-cosmos",), bech32_hrp=("thor",)),
    _c("terra", "Terra", "Terra 2.0", "LUNA", "cosmos",
       "terra 2|terra2|terra 2.0|phoenix-1", addr_kinds=("bech32-cosmos",),
       bech32_hrp=("terra",)),
    _c("terra-classic", "Terra Classic", "Terra 经典链", "LUNC", "cosmos",
       "lunc|ustc|terra classic|columbus-5", addr_kinds=("bech32-cosmos",),
       bech32_hrp=("terra",),
       note="Terra Classic 与 Terra 2.0 地址前缀相同（terra1），必须靠网络名区分"),
)

# --------------------------------------------------------------------------
# 歧义词：同一个说法可能指多条链，必须让用户二次确认
# --------------------------------------------------------------------------

AMBIGUOUS_TERMS: dict[str, tuple[str, ...]] = {
    "币安链": ("bsc", "bnb-beacon-chain"),
    "幣安鏈": ("bsc", "bnb-beacon-chain"),
    "binance chain": ("bsc", "bnb-beacon-chain"),
    "binance": ("bsc", "bnb-beacon-chain"),
    "币安": ("bsc", "bnb-beacon-chain"),
    "luna": ("terra", "terra-classic"),
    "terra": ("terra", "terra-classic"),
    "avalanche x": ("avalanche-c",),
    "layer2": ("arbitrum", "optimism", "base", "zksync-era", "linea", "scroll"),
    "l2": ("arbitrum", "optimism", "base", "zksync-era", "linea", "scroll"),
    "二层": ("arbitrum", "optimism", "base", "zksync-era", "linea", "scroll"),
}

# 这些链名本身就是常用英文词。单独输入时当然是链名（用户输入 "Base" 就是指 Base），
# 但夹在一整句话里时（"scroll down to see more"、"cash flow statement"）几乎都不是，
# 所以在没有网络相关上下文的长文本里要大幅降权，否则 OCR 一张截图就会误判。
COMMON_WORD_ALIASES: frozenset[str] = frozenset({
    "base", "core", "flow", "scroll", "blast", "dash", "waves", "wave", "one", "op",
    "near", "ton", "sonic", "mantle", "terra", "aurora", "manta", "neo", "sui", "sei",
    "metis", "kava", "celo", "linea", "arb", "s", "rune", "iron", "sky",
})

# 出现这些词说明上下文确实在讲转账网络，此时常用词别名不必降权
CHAIN_CONTEXT_HINTS: tuple[str, ...] = (
    "网络", "链", "主网", "协议", "提币", "充值", "转账", "地址", "钱包", "收款",
    "network", "chain", "mainnet", "address", "wallet", "withdraw", "deposit",
    "transfer", "erc", "trc", "bep", "token", "layer",
)

# 只是代币、不指向任何链的词：出现它们时要提醒用户"这不是链名"
TOKEN_ONLY_TERMS: frozenset[str] = frozenset({
    "usdt", "usdc", "tether", "泰达币", "泰達幣", "busd", "dai", "fdusd", "tusd",
    "usde", "pyusd", "wbtc", "weth", "shib", "pepe", "doge币", "稳定币", "u",
})

# --------------------------------------------------------------------------
# 索引
# --------------------------------------------------------------------------

BY_ID: dict[str, Chain] = {c.id: c for c in CHAINS}


def get(chain_id: str) -> Chain:
    return BY_ID[chain_id]


def label(chain_id: str) -> str:
    chain = BY_ID.get(chain_id)
    return chain.label if chain else chain_id


def by_family(family: str) -> tuple[str, ...]:
    return tuple(c.id for c in CHAINS if c.family == family)


def by_addr_kind(kind: str) -> tuple[str, ...]:
    """返回使用某种地址形态的所有链 id。"""
    return tuple(c.id for c in CHAINS if kind in c.addr_kinds)


def by_evm_chain_id(chain_id: int) -> str | None:
    for c in CHAINS:
        if c.evm_chain_id == chain_id:
            return c.id
    # Fantom Opera 的旧 chainId，仍有钱包在用
    return {250: "sonic"}.get(chain_id)


def by_bech32_hrp(hrp: str) -> tuple[str, ...]:
    return tuple(c.id for c in CHAINS if hrp in c.bech32_hrp)


def alias_index() -> dict[str, tuple[str, ...]]:
    """别名 -> 链 id 列表（含歧义词）。"""
    index: dict[str, list[str]] = {}
    for chain in CHAINS:
        for alias in chain.aliases:
            index.setdefault(alias, []).append(chain.id)
    for term, ids in AMBIGUOUS_TERMS.items():
        index.setdefault(term, []).extend(i for i in ids if i not in index.get(term, []))
    return {k: tuple(v) for k, v in index.items()}


def search(keyword: str) -> list[Chain]:
    """按关键字模糊查找链，供 --list 使用。"""
    keyword = keyword.strip().lower()
    if not keyword:
        return list(CHAINS)
    hits = []
    for chain in CHAINS:
        haystack = " ".join((chain.id, chain.name_en, chain.name_zh, chain.native) + chain.aliases)
        if keyword in haystack.lower():
            hits.append(chain)
    return hits
