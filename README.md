# 虚拟币链对比 · chaincmp

转账前核对：**两边是不是同一条链？**

给它两个输入——链的名称、代币标准、收款地址，或者钱包/交易所的**收款码截图**——
它会判断两者是否属于同一条链，并说明转错的后果。

专门用来避免这类事故：

- USDT 从 **ERC20** 转到了一个 **TRC20** 地址 → 币直接丢了
- 对方发来 **BEP2** 地址，你选了 **BEP20** 网络 → 名字只差一个字符，链完全不同
- 两个 `0x` 开头的地址长得一模一样，于是以为"地址对得上就没问题" → 地址一样**不代表**链一样

```
$ python3 chaincmp.py "USDT-TRC20" "波场"
✅ 同一条链

$ python3 chaincmp.py "ERC20" "TRC20"
❌ 不是同一条链 —— 跨过去的资产无法恢复，会永久丢失

$ python3 chaincmp.py 收款码.png "BEP20"
```

---

## 快速开始

不需要安装，不需要联网，**核心功能零依赖**，只要有 Python 3.10+：

```bash
git clone https://github.com/doudoudoubao/Comparison-of-Cryptocurrency-Blockchains.git
cd Comparison-of-Cryptocurrency-Blockchains
python3 chaincmp.py "USDT-TRC20" "波场"
```

想先看看它能干什么：

```bash
python3 chaincmp.py --demo      # 跑一遍典型场景
python3 chaincmp.py --help
```

---

## 怎么用

### 1. 名称 vs 名称

中文、英文、交易所写法、代币标准都认：

```bash
python3 chaincmp.py "BEP20" "币安智能链"      # ✅ 同一条链
python3 chaincmp.py "BEP20" "BEP2"           # ❌ 不是同一条链
python3 chaincmp.py "matic" "Polygon"        # ✅ 同一条链
python3 chaincmp.py "Etherium" "以太坊"       # ⚠️ 拼错了也能猜出来，但会提醒你核对
```

### 2. 名称 vs 地址

地址会做**真实的校验和验证**（Base58Check / Bech32 / EIP-55 / CRC16 / SS58），
打错一位就会被抓出来：

```bash
$ python3 chaincmp.py "TRC20" TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t

 A  TRC20                                         [文本]
    → 波场 Tron (TRX)   置信度 97%
      · 名称/标准“trc20” → 波场 Tron (TRX)

 B  TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t            [文本]
    → 波场 Tron (TRX)   置信度 97%
      · 波场地址（Base58Check 校验通过，版本字节 0x41）

 结论   ✅ 同一条链
        两边都是 波场 Tron (TRX)
 置信度 ███████████████████░ 97%

 → 建议
   · 网络一致，可以继续；转账前再逐字核对收款地址的前 6 位和后 6 位
   · 建议先小额试转一笔，到账后再转大额
```

### 3. 图片（收款码截图 / 钱包截图）

参数是图片路径时自动走图片识别，会读两样东西：

- **二维码**里的支付 URI（最可靠：`ethereum:0x…@56` 里的 `@56` 直接写明了是 BSC）
- **截图上的文字**（OCR），比如交易所提币页上的"网络 TRC20"

```bash
python3 chaincmp.py 我的收款码.png 对方收款码.jpg
python3 chaincmp.py wallet.png "BEP20"
python3 chaincmp.py img:./a.png img:./b.png     # 用 img: 前缀强制按图片处理
```

图片功能需要额外的库，见下面的[图片识别](#图片识别可选)。

### 4. 只识别一个输入

```bash
$ python3 chaincmp.py -i 0xdAC17F958D2ee523a2206206994597C13D831ec7

 输入  0xdAC17F958D2ee523a2206206994597C13D831ec7   [文本]
    → EVM 兼容链之一（41 条候选，无法确定具体是哪条）   置信度 90%
      · 0x 开头的 40 位地址（以太坊系格式），EIP-55 校验通过

 ⚠ 提醒
   · 同一个 0x 地址在所有 EVM 链上都存在，光看地址无法判断是哪条链
```

### 5. 其他命令

```bash
python3 chaincmp.py --list           # 列出支持的 79 条链和它们的所有写法
python3 chaincmp.py --list tron      # 按关键字过滤
python3 chaincmp.py --check          # 看图片识别能力是否就绪
python3 chaincmp.py --json A B       # JSON 输出，便于脚本调用
python3 chaincmp.py -v A B           # 显示全部证据和候选链
```

---

## 结论怎么读

| 结论 | 含义 | 退出码 |
|---|---|---|
| ✅ **同一条链** | 两边都唯一指向同一条链 | `0` |
| ❌ **不是同一条链** | 两边指向了不同的链，**转账会出事** | `1` |
| ⚠️ **无法确定** | 候选有重叠但信息不足（例如两个 `0x` 地址） | `2` |
| ❓ **信息不足** | 至少一边没识别出链（例如只写了"USDT"） | `3` |

退出码可以直接用在脚本里：

```bash
if python3 chaincmp.py "$NETWORK" "$ADDRESS" >/dev/null; then
    echo "网络一致，继续"
else
    echo "网络对不上，中止"; exit 1
fi
```

**"无法确定"是一个有用的结论，不是失败。** 在转账这件事上，把"可能一样"说成"一样"
比说"不知道"危险得多，所以本工具在证据不足时一定会明说。

### 风险提示是分级的

不同的转错后果不一样，工具会区分：

```
$ python3 chaincmp.py "以太坊" "币安智能链"
❌ 不是同一条链
⚠ 以太坊 与 币安智能链 都是 EVM 链、地址格式相同，转错后资产会停留在源链的
  同一个地址上：如果你掌握该地址私钥，通常还能在源链找回；但如果收款方是交易所
  充值地址，多半无法找回

$ python3 chaincmp.py "以太坊" "波场"
❌ 不是同一条链
⚠ 以太坊 与 波场 属于完全不同的地址体系，跨过去的资产无法恢复，会永久丢失
```

---

## 它能识别什么

**79 条链**，每条都收录了中文名、英文名、代币标准和交易所里的写法：

| 类别 | 链 |
|---|---|
| 主流 | 比特币、以太坊、币安智能链(BSC)、波场、Solana、TON、XRP、Cardano、Polkadot |
| EVM L2 / 侧链 | Arbitrum、Optimism、Base、Polygon、zkSync Era、Linea、Scroll、Mantle、Blast、opBNB… |
| 交易所常见 | AVAXC、HECO、OKTC、X Layer、Cronos、Kaia、Core、Berachain |
| Cosmos 生态 | Cosmos、Osmosis、Celestia、Injective、Sei、Kava、THORChain、Terra / Terra Classic |
| UTXO 系 | 莱特币、狗狗币、比特现金、Dash、Zcash、门罗币、Kaspa |
| 其他 | Aptos、Sui、NEAR、Stellar、Algorand、Hedera、Filecoin、Tezos、EOS、Neo、Flow… |

识别的输入形态：

- **代币标准**：ERC20 / ERC-20 / ＥＲＣ２０、TRC20、BEP20、BEP2、SPL、Jetton、HRC20…
- **链名**：`以太坊` `以太坊经典` `波场` `币安智能链` `Arbitrum One` `AVAXC` `马蹄链`…
- **地址**：`0x…`、`T…`、`bc1…`、`cosmos1…`、`addr1…`、`r…`、`G…`、`EQ…` 等 28 种形态
- **支付 URI**：`ethereum:0x…@56`（EIP-681）、`eip155:137:0x…`（CAIP-10）、`bitcoin:bc1…?amount=`、`tron:T…`
- **整句话**：`请用 TRC20 网络给我转 100 USDT`、交易所提币页的整屏 OCR 文本

它也会主动指出这些坑：

- `USDT`、`USDC` 只是币种，**不是链**
- `币安链` 有歧义（BEP2 的 Beacon Chain？还是 BEP20 的 BSC？）
- `3` 开头的 P2SH 地址曾被 BTC / BCH / LTC 共用
- 旧版 BCH 地址与 BTC 地址格式完全相同
- Terra 2.0 和 Terra Classic 的地址前缀都是 `terra1`
- XRP / XLM / EOS / TON / Hedera 转交易所还需要 Tag / Memo
- 测试网地址（`tb1…`）
- `0x` + 64 位十六进制**多半是交易哈希**，不是收款地址
- 不带 `0x` 的 64 位十六进制、以及 12/24 个英文单词，**可能是私钥或助记词**——
  会立刻警告你停止分享，而不是拿去比对

### 一个输入里有多条链时，它会说出来

交易所提币页上常同时列着 TRC20 / ERC20 / BEP20，聊天记录里也常一次贴两条链的地址。
这种情况下**不靠分数高低替你选**，而是直接指出来：

```
$ python3 chaincmp.py "ERC20: 0xdAC17F95… TRC20: TR7NHqje…" "TRC20"

 A  → 同时出现了多条链的信息（EVM 兼容链 / 波场 Tron (TRX) /
      以太坊 Ethereum (ETH)），需要你指明用哪一条

 ⚠ 风险
   · 输入 A 里同时出现了 … 的信息，下面的结论只是就其中一种可能而言，
     请先把输入缩小到你真正要用的那条链
```

---

## 图片识别（可选）

核心功能零依赖；只有"从图片里读内容"需要额外的库：

```bash
pip install -r requirements-optional.txt

# OCR 引擎要单独装（pytesseract 只是封装）：
sudo apt install tesseract-ocr tesseract-ocr-chi-sim   # Ubuntu/Debian
brew install tesseract tesseract-lang                  # macOS

# pyzbar 在 Linux 上还需要：
sudo apt install libzbar0
```

装完用 `python3 chaincmp.py --check` 确认。后端会按可用性自动降级：

- 二维码：pyzbar → OpenCV → `zbarimg` 命令行
- 文字：pytesseract → `tesseract` 命令行

**不想装也能用**：把截图里的网络名或地址复制出来，直接作为文本参数传进去，
识别与对比效果完全相同。工具在缺库时会明确告诉你缺什么、怎么装、怎么绕过，
而不是报错退出。

> 图片里的文件名（如 `usdt-trc20.png`）只会被当作**弱线索**，永远不会单独作为
> 判定依据——文件名太容易误导了。

### 关于图片识别的实际能力（实测）

**二维码是最可靠的**。收款码里通常带着 chainId，这是最精确的信号：

```
$ python3 chaincmp.py 收款码.png "BSC"
 A  → 币安智能链 BNB Smart Chain (BNB)   置信度 99%
      · 二维码 → 支付 URI 写明 chainId=56 → 币安智能链
```

注意上面这张码的内容是 `ethereum:0x…@56`——前缀写着 ethereum，实际却是 BSC。
工具按 chainId 判断，不会被前缀带偏。

**OCR 读网络名很准，读地址不可靠**。实测 tesseract 会把
`TR7NHqjeKQx…` 读成 `TR7 NHgjeKOx…`（`q`→`g`、`Q`→`O`）。这种情况下校验和一定过不去，
工具**不会**拿这个错地址去比对，而是明说：

```
 ⚠ 风险
   · 输入 A：图里的地址没能可靠读出来——OCR 常把 q/g、Q/O、0/O、l/1 认错。
     本次判断只用到了网络名，并没有核对地址，请手动复制地址再比一次
```

所以：**用图片核对网络没问题，核对地址请手动复制**。这是 OCR 的固有限制，
工具能做的是不隐瞒它。

---

## 作为 Python 库使用

```python
from chainmatch import compare_inputs, identify

result = compare_inputs("USDT-TRC20", "波场")
print(result.verdict)      # 'same'
print(result.headline)     # '两边都是 波场 Tron (TRX)'
print(result.risks)        # 风险提示列表
print(result.advice)       # 行动建议列表

# 只识别一个
res = identify("0xdAC17F958D2ee523a2206206994597C13D831ec7")
print(res.top)             # 'ethereum'（最高候选）
print(res.certain)         # False —— EVM 地址无法唯一定链
print(res.family_hint)     # 'evm'
print(len(res.candidates)) # 41
```

`verdict` 的取值为 `same` / `different` / `possibly_same` / `unknown`，
对应常量 `SAME` / `DIFFERENT` / `POSSIBLY_SAME` / `UNKNOWN`。

---

## 工作原理

每个输入都会被拆成若干条**证据（Signal）**，每条证据带一个置信度：

| 证据 | 置信度 | 例子 |
|---|---|---|
| 支付 URI 里的 chainId | 0.99 | `@56` → BSC |
| 名称 / 代币标准精确匹配 | 0.97 | `trc20` → 波场 |
| 地址校验和通过 | 0.85–0.97 | `T…` 通过 Base58Check |
| 地址格式（跨链通用） | 0.90 | `0x…` → 全部 41 条 EVM 链 |
| 歧义名称 | 0.50 | `币安链` |
| 模糊匹配（疑似写错） | 0.45 | `Etherium` |
| 常用英文词出现在句子里 | 0.45 | `scroll down…` 里的 `scroll` |
| 地址校验和失败 | 0.40 + 报警 | 打错一位的地址 |
| 文件名线索 | ≤0.45 | `usdt-trc20.png` |

多条证据按 `p = 1 - Π(1 - pᵢ)` 合成。指向多条链的证据（`0x` 地址指向所有 EVM 链）
会让候选保持为多条，**如实反映"信息不够"**，而不是随便挑一条最流行的链。

几个刻意的设计取舍：

- **不联网**。不查链上数据、不调任何 API，所以离线可用、没有隐私泄露，
  代价是无法验证"这个地址在链上是否真的有活动"。
- **宁可说不知道**。两个 `0x` 地址只会得到"无法确定"，不会被凑成"同一条链"。
- **校验和优先报警**。地址打错或被剪贴板木马替换，比选错链更危险，会单独提示。
- **最长匹配优先**。`以太坊经典` 不会被识别成 `以太坊`，`bitcoin cash` 不会退化成 `bitcoin`。
- **矛盾的证据不靠分数决胜负**。一个输入里同时出现两条链的信息时，分数只差 0.01
  就替用户选一条，是这个工具最不该做的事——它会直接说"这里有多条链"。
- **Base / Core / Flow / Scroll 这些链名也是常用英文词**。单独输入时当然按链名理解；
  夹在 `scroll down to see more` 这种句子里、且上下文没提到网络时则大幅降权，
  否则 OCR 一张截图就会误判。
- **拼接断行地址必须过校验和**。OCR 常把地址断成几截，拼回去只在校验和通过时才采信；
  全小写 EVM 地址、Solana 地址本身不带校验和，拼错了看不出来，那就宁可不认——
  绝不凭空造出一个"看起来没问题"的地址。

---

## 测试

```bash
python3 -m unittest discover -s tests -t .
```

全部测试覆盖：

- Keccak-256 / EIP-55 / Base58Check / Bech32 / SS58 的**标准测试向量**
- 各链地址的正确识别与**损坏地址的拒绝**
- 名称匹配、最长匹配优先、词边界（`money` 不能命中 `one`）
- 端到端对比场景与**结论对称性**（换顺序不改变结论）
- 图片降级路径，以及用 mock 驱动的 OCR / 二维码解析

`tests/test_accuracy.py` 是准确性回归测试，每条用例都对应一个真实踩过的坑：

- 各大交易所提币页上的真实网络名写法（含中文、括号、币种前缀）
- 普通英文句子不能被当成链名
- 一个输入里出现多条链时必须报出来
- 私钥 / 助记词 / 交易哈希必须被警告，而不是拿去比对
- OCR 破坏（全大写、地址断行）下的识别与**不凭空造地址**

`tests/test_image_real.py` 会真的生成截图和二维码、真的跑 OCR 与解码，验证
"发图片"这条路真能用；没装可选依赖的机器上自动跳过。

链知识库有专门的完整性测试：新增链时，别名冲突、chainId 重复、地址形态写错
都会让测试失败。

## 新增一条链

只改 `chainmatch/chains.py` 一个文件，加一行即可；地址识别、名称匹配、展示都会自动生效：

```python
_c("mychain", "MyChain", "我的链", "MYC", "evm",
   "myc|mychain|我的链|我的鏈|mychain mainnet",
   evm_chain_id=12345, addr_kinds=("evm",),
   note="需要提醒用户的注意事项"),
```

然后跑一遍测试确认没有别名冲突。

---

## 局限与免责声明

- 这是一个**格式与名称层面**的核对工具，不查链上数据，**不能替代人工核对**。
- 同一条链不代表同一个代币：还要核对**代币合约地址**，谨防同名假币。
- 大额转账请务必**先小额试转**。
- 交易所充值页面上的「网络 / Network」一栏，才是最终依据。
- 本工具按原样提供，不对任何资产损失负责。

## 许可证

MIT
