# V3 Stage 6B Incremental Human Re-review Evidence Packet

Classification: **Ready for Incremental Human Review**

> This packet contains frozen evidence and retrieval highlights only. No semantic decision is made or suggested.

## Snapshot and execution identity

- Snapshot ID: `20260720T094346Z_c7663365`
- Snapshot DB path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`
- Snapshot DB SHA-256: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Artifact root: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts`
- Git branch: `codex/v3-domain-completion`
- Git HEAD: `8287c8d92378b87290274d02605cdc704cb8c470`
- Review set: exactly 5 Query–Video pairs / 41 complete transcript chunks
- Chunk ordering: 0-based index assigned by `(start_time ASC, end_time ASC, retrieval_unit_id ASC)` because the frozen schema has no stored `chunk_index` column.
- Raw segment indices: 0-based positions in the authoritative `subtitle-raw.json` array.

## Retrieval highlight method

Each query was scored against only the transcript chunks of the current video. Lexical uses the existing trigram FTS5 phrase/BM25 semantics; Dense uses the pinned Qwen query embedding and frozen normalized vectors; Hybrid uses the existing RRF formula (`rrf_k=60`). Highlights are navigation aids only and are not judgments.

## Q02 / Video 3

### Video metadata

- Query ID: `Q02`
- Query text: `RAG`
- Video ID: `3`
- BVID: `BV1ToTy6tEyc`
- Video title: AI Agent面试，简历上的项目做这几个方向面试官追着你聊
- Uploader: 海云日记
- Duration: 183 seconds (00:03:03.000)
- Favorite folder: 2026找工作学习 (`3876418799`)
- Archived: `false`
- Ignored: `false`
- Subtitle source: `asr`
- Raw subtitle artifact path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1ToTy6tEyc/subtitle-raw.json`
- Raw subtitle SHA-256: `643519a6df6a8f81e5634c30e6b3c18aae18dd509874b2440700b772f74a0fec`
- Raw subtitle segment count: 32
- Transcript chunk count: 2

### Complete transcript chunks

#### Chunk 0

- retrieval_unit_id: `transcript_chunk:bilibili:BV1ToTy6tEyc:p1:chunk_db2140411e47b1910c10e0edadb9889d`
- chunk_index: `0`
- time: `0.030–111.360s` (`00:00:00.030–00:01:51.360`)
- raw segments: `0–18` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `1`, score `0.333340167999`
- hybrid: rank `1`, score `0.016393442623`
- content_quality_warning: `asr_machine_transcription_may_contain_recognition_errors`

```text
多人A线的简历里面写什么项目就集体卡住了，对吧？ 他觉得自己拿不出手啊，真的是能力不够，是方向没选对吗？ 面试官看简历基本上30秒是吧？ 你的项目有没有技术出身？ 能不能让他想问，那基本上结束了啊，那个人项目要证明的是什么？ 证明的是你独立设计架构的能力啊。 问遇到问题有排查思路，听到就选题有取舍方向，怎么选给大个前提啊，这些都是我筛出来的。 第一，它的技术链路够长，面试有深度。 第二有业务落地场景。 啊，我可给大家推荐几个方向。 第一个就是什么桌面端的个人数字数字员工就这样AI直接操作本地文件知道吧？ 然后浏览器ID和这个终端从这个操作的系统权限管理到跨应用的状态同步到任务规划，每一个都能展聊对吧？ 你可以讲一技能对模糊指令的这种消策略，或者多应用切换的上下文啊，这个其实是可以。 所啊第二个就是比如说代码审查自动化重构系读代码库识别环外围道给重构，建议它设计St解析代码理解上下文等等这块也可以啊。 那第三呢就是浏览器自主的这个任务编排执行系统啊，就是web it像让AI像人一样浏览网页，填表提交数据。 现在大厂都在压这个方向，比如说computer use，当时都在搞，就这块道的解析，任务的拆解，重复重试全都可以讲，很不错啊，还有还就是多元深度研究证据链啊，第部啊多元交叉验证带引用的研究报告啊，信息可靠性评估怎么做观点冲，怎么调和，怎么溯源都可以比R高一个维度。 还有一些比较高阶的，大家也可以参考。 如果你想做更深一点，就是比如说时序异常检测跟因定位系统对吧？ 你结合这个时间序列分析和因果图像，让A键自动发现指标异常追溯跟因模块啊，运维监控赛道这个需需求很大。
```

#### Chunk 1

- retrieval_unit_id: `transcript_chunk:bilibili:BV1ToTy6tEyc:p1:chunk_2f991db2158c86a13785c279becfb40c`
- chunk_index: `1`
- time: `104.110–181.980s` (`00:01:44.110–00:03:01.980`)
- raw segments: `18–31` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `2`, score `0.325195193291`
- hybrid: rank `2`, score `0.016129032258`
- content_quality_warning: `asr_machine_transcription_may_contain_recognition_errors`

```text
你结合这个时间序列分析和因果图像，让A键自动发现指标异常追溯跟因模块啊，运维监控赛道这个需需求很大。 面试时候可以聊异常策略、误告机制啊，因果图构建方法，还有话就是游戏nc的生成和社会仿真的交互啊，用A键架构模拟角色交互，每个C有独立记忆目标状态，A的通讯记忆管理涌现基本上也是剩一个台阶。 然后还有什么多模态的内容理解和资产系统，比如说多模态ra文本图像视频统一索引对吧？ 语义桥接联合推理，很多都不虚的。 然后包括内容电商都可以所见在赏。 然后呢智能体的库存博弈，包括动态定价啊，这块是A进的决策系统啊，强化学习这些都可以加啊。 你包括如果怎么去包装含金量呢，对吧？ 你要写数据，比如说你做个web部A的日均处理多少，网页长任务率多少，完全是两个效果对吧？ 这些都可以参参加。 那A进的ban的非常非常快啊，大家需要这个。 如果你是在社招想找工作，往这A进的方向靠，或者说呃呃校招都可以。 校招我接了很多本科、硕士、博士对吧？ 很多都慢慢他们都开始在实习了，包括社招的最近对吧，你这些年薪啊，这些几十万，包括甚至上百万的人都在找我辅导的。 大家基本A金的这块是很高的一个方向啊，所以说大家需要可以呃抓紧找我辅导。
```

### Human decision

- [ ] R_evidence
- [ ] N
- [ ] Retain U_title because content is unusable

Reason:

Relevant supporting chunk IDs:

Optional useful interval:

## Q07 / Video 44

### Video metadata

- Query ID: `Q07`
- Query text: `Claude Code 记忆机制`
- Video ID: `44`
- BVID: `BV1ekdhBnEra`
- Video title: Claude Code 官方教程，Anthropic官方教程，Claude Code in action，使用Claude Code看官方教程就足够了
- Uploader: 爱在一毛钱
- Duration: 3609 seconds (01:00:09.000)
- Favorite folder: 2026找工作学习 (`3876418799`)
- Archived: `false`
- Ignored: `false`
- Subtitle source: `ai`
- Raw subtitle artifact path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1ekdhBnEra/subtitle-raw.json`
- Raw subtitle SHA-256: `7d27457c766a242101b176ef0c23eae7b6ead710921ad03295f705908ccee95e`
- Raw subtitle segment count: 21
- Transcript chunk count: 1

### Complete transcript chunks

#### Chunk 0

- retrieval_unit_id: `transcript_chunk:bilibili:BV1ekdhBnEra:p1:chunk_e43b86a8d3559be8d77bc287f2fdedd7`
- chunk_index: `0`
- time: `0.100–36.680s` (`00:00:00.100–00:00:36.680`)
- raw segments: `0–20` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `1`, score `0.434104204178`
- hybrid: rank `1`, score `0.016393442623`
- content_quality_warning: `raw_subtitle_partial_coverage_36.680_of_3609_seconds`

```text
您好 欢迎您的到来 我叫史蒂文格雷德 是ANTHROPIC的技术团队成员 在这门课程中 我们将帮助您快速掌握源代码的相关知识 在深入探讨任何技术性内容之前 我想先给大家简要介绍一下 我们将会学习的内容 这门课程分为四个部分 首先我们将花一些时间来准确了解 什么是编码辅助工具 接下来我们将重点了解源代码本身 并弄清楚它是如何在市场上 众多的编码辅助工具中脱颖而出的 一旦我们明确了这一点 我们就将通过实际操作来了解 如何在典型的项目中使用源代码 并积累一些实践经验 最后我们将总结一下 如何在自己的项目中充分利用源代码
```

### Human decision

- [ ] R_evidence
- [ ] N
- [ ] Retain U_title because content is unusable

Reason:

Relevant supporting chunk IDs:

Optional useful interval:

## Q07 / Video 45

### Video metadata

- Query ID: `Q07`
- Query text: `Claude Code 记忆机制`
- Video ID: `45`
- BVID: `BV1XrEZ6NEuD`
- Video title: 五分钟带你看懂黑客松冠军的 Claude Code 配置
- Uploader: 奇思妙想CYC
- Duration: 908 seconds (00:15:08.000)
- Favorite folder: 2026找工作学习 (`3876418799`)
- Archived: `false`
- Ignored: `false`
- Subtitle source: `ai`
- Raw subtitle artifact path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1XrEZ6NEuD/subtitle-raw.json`
- Raw subtitle SHA-256: `86c45b6b32e980ed313d8ed1d056d88984c5055b4638134e0c4af58c860972c4`
- Raw subtitle segment count: 394
- Transcript chunk count: 8

### Complete transcript chunks

#### Chunk 0

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_99ad2ebd57cbae4c157bcf88dab53e5a`
- chunk_index: `0`
- time: `0.080–116.190s` (`00:00:00.080–00:01:56.190`)
- raw segments: `0–56` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `4`, score `0.40067538619`
- hybrid: rank `4`, score `0.015625`
- content_quality_warning: `none`

```text
Hello 大家好 我是奇思妙想西Y希 现在GITHUB上有个仓库 已经有18万的start了 他是去年n shy黑客松冠军的得主写的 他把他所有的工作流程配置以及踩坑经验 全部开源出来了 所以我们今天不讲理论 不讲概念 我们就带大家实际去看一看 是一个仓库长什么样 然后有什么可以从中学习的 所以如果大家对这一期的内容感兴趣的话 欢迎先点赞关注收藏 那我们话不多说 直接开始吧 OK然后我们首先呢就是我们要去打开这个星 cloud code的仓库 我们就去搜索 然后就看到第一个搜索结果 这个GITHUB仓库 然后点击进来就是这一个ECC的桌子 然后他现在这一个仓库已经快接近190000start了 然后很多朋友像我第一次点击进来的时候 都会发现这个仓库太大了 然后很乱 不知道从何看起 所以大家不要慌 接下来我会带大家一步步的过一下 然后他可以选择不同的语言 比如说英语啊 然后还有我们中文版的 对我们可以点击中文版 然后就可以看到这是一个and shy黑客松马拉松 黑客马拉松的或圣子的CLO完整集合 然后它配备了一套像技能体系啊 行为啊 机优化 持续学习等各种开发模式 然后呢这一个仓库只有两 这个仓库就是它只包含了一些原始的代码 然后它还提供了两个指南 一个是精简指南 一个是详细指南 然后另一个是安全的 这一个是比较进阶的 我们就先不讲了 所以这一系列呢我们就会做三期内容 第一期呢就是今天这一期会教大家 先把整一个仓库给看一遍 然后下一期呢会带大家过一下 这一个精简的指南 在下一期会带大家过一下这个详细的指南 OK那我们先看一下这一个仓库 左边这里有很多的文件夹 然后其实重要的只有那么几个
```

#### Chunk 1

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_439b503c27065996de2a0519ecf73328`
- chunk_index: `1`
- time: `113.750–232.100s` (`00:01:53.750–00:03:52.100`)
- raw segments: `56–109` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `7`, score `0.353437036276`
- hybrid: rank `7`, score `0.014925373134`
- content_quality_warning: `none`

```text
然后其实重要的只有那么几个 比如说重要的是有类似于skills这一个文件夹 然后里面就包含了各种不同skills的定义 我们可以随便点击一两个进来看 这是一个skill的定义 我们待会也可以找几个 然后来学习一下像这一个黑客松的冠军 他平时是怎么去写他的这些skill的 然后除了skill呢 另一个就是这个规则的文件夹 它里面也写好了各种不同的规则呃 可能是一些写代码的 比如说这是C加加的写代码的规则 java的规则 Python的规则 我这一个桌子他都帮我们定义好了 对然后另一个就是这一个hook是一个钩子 也是比较重要的文件夹 然后这一个command呢也是一个比较重要的文件夹 command呢就是可以帮我们把呃 一些行为定义成一个指令 然后去执行 那我们待会也可以来看一下作者 他是怎么去写他这些COMMCOMMAND命令的 然后还有另一个比较重要 就是这一个A准文档 A准 它就是呃 我们前几天有讲到一些多A准协作的教程 然后这个A醇它就相当于呃去定义了不同角色 然后我们可以到时候跟CCO说 去执行这一个爵士 然后他提前把这一个爵士的身份定义 全部给定义好了 这就是我们今天主要详细要来讲的几个文件夹 一个是skills文件夹 一个是comments文件夹 一个是A选文件夹 一个是rules文件夹 一个是fox文件夹 还有一个NCP配置的文件夹 然后其他的还有一些辅助的文件夹 我们就了解有这些就好了 如果大家哪些看不懂的 就可以发给我们的AI 让他帮我们解释一下 OK然后我们第一个呢先来讲讲skills 我们前面也做了一个skills的教程 如果大家还没看过的 可以去看我们的前几篇 然后skills呢它本质上就是一个markdown文件 他会写清楚说是谁职责 以及遇到某一类的任务要去怎么做 然后怎么去召唤一个skill
```

#### Chunk 2

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_49328fdfae596efa1502b42f652a62db`
- chunk_index: `2`
- time: `230.420–350.350s` (`00:03:50.420–00:05:50.350`)
- raw segments: `109–159` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `5`, score `0.372544318438`
- hybrid: rank `5`, score `0.015384615385`
- content_quality_warning: `none`

```text
然后怎么去召唤一个skill 就是简单的去打一个斜杠 然后把自己skill的名字打出来 我我们的CLO就可以执行这个skills了 前面我做了教程之后呢 就很多朋友问说要怎么去定义好 去写一个skills 所以我们今天就来看一看 这一个黑客松冠军的作者 他是怎么去写好这些skills 我们在他的文件夹里看能不能学到一些内容 那为了让更多朋友呢能有更加好的阅读体验呢 我做了这一个网页版的 把这个仓库变成一个HTML版本 那我们就可以更加直观的在这里 看到整一个残酷的文件 比如说这一个agent里面就有这么多的ND 然后还有这一个command me command文件夹 然后还有一个hooks 还有一个skills等等对 然后我就呃把这些全部给搞到这里 然后我接下来会讲几个skills 然后看一看作者是怎么写的 比如说我们看一下这一个嗯 Article 看一下这个article writing skills 这一个就是作者写的一个写文章的skills 然后我还做了一个中文版 我们来看一看这个skills得怎么写呃 首先呢每一个skills呢都有一个名字 然后有它的描述对 然后这是一个skills的比较规范化的写法 然后接下来呢一个更加重要的就是说 这个skills要何时去启启用 然后作者自己写的几个它启用的时间点 我们可以看一看 比如说什么起草博客文章啊 怎么把笔记采访稿整理成完整文章 等其他时候的时候就启动启用这个skills对 然后下面一点就是核心规则 比如说先给具体的东西啊 实物粒子产出物故事截图或代码 然后再给例子 然后最后再说句子要保持简洁 然后用证据去替代形容词 然后还要说一些 比如说不捏造事实啊 可信度 或者用案例去限制我们的模型去乱输出对 然后除了去提规则之后 我们还也可以写一些语气的处理对
```

#### Chunk 3

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_af2bc7999cfeb875f009dd2814a640cf`
- chunk_index: `3`
- time: `347.060–464.810s` (`00:05:47.060–00:07:44.810`)
- raw segments: `159–209` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `8`, score `0.316025555134`
- hybrid: rank `8`, score `0.014705882353`
- content_quality_warning: `none`

```text
我们还也可以写一些语气的处理对 然后这里也还可以去在一个skill里面去嵌套 另一个skill 比如说他这里说先运行这个BRAINBOSKILL 我们待会可以来看一下这skill长什么样对 然后另一点也比较重要的 就是一个skill不止要交一个模型 说要去做什么 另一点更重要的是要让他禁止去做什么 要不然他很容易就是没我们没有给他禁止 他就很容易去乱做 所以我们可以在这些情况下让他去删掉 或者重写 比如说嗯写到这些什么 在当今快速变化的时代啊 或者去虚假的自我剖析啊 然后去不推动论点的人物背景铺垫啊 就是我们一些呃不想让它出现的情况 我们就可以在skill里面也去禁止他写 然后除了这些规则 比如说禁止写什么 要写什么 规范是什么之后呢 我们另一点更加重要的就是 我们要告诉他整个流程 比如说这里就把流程给他写好了 比如说去明确受众的目的和目的 建立应大纲 然后去以致些去开头 然后在后面去展开 然后再去删掉 写好之后再去删掉一些像模板啊 或者自吹自擂的内容对 所以这一步就是去把整个流程给它规范好 然后下面呢是一个结构指南 就是根据不同的啊文章的类型 比如说技术指南类啦 随笔类 观点类 通讯类的去规定不同的限制对 然后在最后呢再去让他说 在交稿前去确定不同的内容对 所以这就是一个比较规范的skill的写法 就是先写他的名字 他的描述什么时候去启用 然后它的核心规则有什么的 然后他禁止什么咳 它的核心规则有什么 然后会在这skill里面是禁止一些内容的出现 然后再把它的流程给写好 然后还可以根据你不不同的类型的内容
```

#### Chunk 4

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_ea8044f2469fae24438baa08c450d346`
- chunk_index: `4`
- time: `461.470–579.550s` (`00:07:41.470–00:09:39.550`)
- raw segments: `209–260` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `3`, score `0.403339475393`
- hybrid: rank `3`, score `0.015873015873`
- content_quality_warning: `none`

```text
然后还可以根据你不不同的类型的内容 去做不同类型的规范对 然后也可以去嵌套另外的skill 比如说这里讲到这个brain boys skill 我们来看一看对这一个是他原本的这个skill 然后们也看一看中文版 the brain boys skill呢 是说从真实的素材里面去构建持久的声音档案 然后在所有的场景里面去复用这一个档案 不用每次都去从头推导风格 然后在什么时候去激活呢 比如说用户需要用特定的声音去创作内容 或者说在X啊linking上要去更新一些写作 或者说已经知道了某一个作者的语气 然后我们想要把这一个语气去适配到 不同的平台 不同的渠道就可以用这一个skills 那我们再看一下这一个收集工作流 它的流程 它的流程就是帮我们写好了这样子的流程 然后也写好了 在整一个过程中呢 要去提取什么样的内容 节奏和句子长度大小写规范 括号用法等等 然后最后呢会输出一个什么 输出一个可以复用的这样一个声音单块的块对 然后还有一些默认风格啊 一些硬性禁令啊 持久化规则等等对 所以这一个skills呢 就是想要可以去参考别人的写作风格 然后建立自己的声音档案 所以这里作者呢他其实写了很多 很多个不一样的skill 有内容生产的 有写代码的 然后有一些工作化流程的规范 所以大家感兴趣的话 都可以点击每一个去查看一下嗯 OK然后讲完这之后呢 我们就来看一看这个A准文件夹 A准文件夹呢 里面定义了很多不同的角色和身份 我们可以找到这里 对它定义了不同的身份和角色 那我们就挑几个来看 比如说这一个code reviewer 就是一个代码的审查员对 这也是他原本写的 那我们也可以来看看我们的中文版嗯 就首先我们要去定义它的一个名字
```

#### Chunk 5

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_582449e973e0580328ce7f5f308d7f7d`
- chunk_index: `5`
- time: `577.010–695.940s` (`00:09:37.010–00:11:35.940`)
- raw segments: `260–308` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `1`, score `0.436084985733`
- hybrid: rank `1`, score `0.016393442623`
- content_quality_warning: `none`

```text
就首先我们要去定义它的一个名字 然后他的一个描述对 然后他有可以使用什么工具 然后一些提示词的防御极限啊 就是你这一个角色他不能做什么 然后可以做什么 然后定义好他是一个一名高级的代码审查员 怎么样 然后审查的流程是怎么样的 然后对这些就都是一些细节 所以当我们定义好一个角色以及他的身份 他能做的事情 以及他做的事情的一些规范之后呢 我们以后在当要使用这一个爵士的时候 我们就很简单的在cloud口里面说调用这一个角色 然后他就会帮我们把这些所有的规范 他的身份 他的指令全部都给我们规范好 我们就可以直接使用就好了 所以这一个也是一个非常重要的概念 就是这个A选的文件夹 作者呢也在里面 帮我们写好了很多很多不同的身份角色 所以大家感兴趣的话 也可以自己去多看几个 然后了解一下 但是整一个呢都是按照着一个比较相同的规范 来写这些爵士和身份的 嗯OK那我们接下来来看一下这个command命令 command命令就是跟有点像 但是它是一个在CLO里面的命令 然后比如说在这里他写好了一个plan点ND 这是我们的plan命令 然后当我们执行这个命令的时候呢 它就可以执行一系列的操作 然后我们也在这一个planning nd文档里面去写好 我们这一个命令的规范 比如还有这个 对所以其实有很多skills啊 命令啊 还有爵士 有些东西是比较重复的 所以有些时候呢我们就需要说定义好一个爵士 让他去执行 有些时候也可以不用 就是我们直接的用一个斜杠命令 让他去执行就好了 OK然后另一个呢是作者这里有一个rules文件夹 然后它里面会分不同的编程语言呢
```

#### Chunk 6

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_21a0ee4eec41ba99914a55c847971c70`
- chunk_index: `6`
- time: `693.380–812.430s` (`00:11:33.380–00:13:32.430`)
- raw segments: `308–354` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `2`, score `0.425556480885`
- hybrid: rank `2`, score `0.016129032258`
- content_quality_warning: `none`

```text
然后它里面会分不同的编程语言呢 帮我们写好了它不同的规则 然后当我们需要用到 比如说需要用到go类啊或者java的时候 我们就可以去到这里的规则里面 然后让我们的cloud口去参考这些MD文档 然后去符合这个规则去写出我们的代码 OK那我们最后看一下这一个hook指令 能说hook就是一个触发器 我们确定好规则 然后当coud co每次做成某件事的之前或之后呢 自动去执行一个操作 然后这一个仓库里呢他定义了20多个户口 然后大家都可以去看一看 比如说我们可以看到这个pre compact at 就是说在再去compact at之前呢 然后去执行一些什么命令 然后session star就是在开启一个上下文之前呢 他去执行一些什么命令 然后这些who可能是一个比较智能化的操作 大家就可以在这里看一下 这个坐姿他是怎么写的 然后大家如果有相应的修改要求的话 就发这个给CLO看 然后再根据他这样子写的规范去修 改成我们自己想要的就可以了 OK然后刚讲完了这么多的内容 有朋友都在问 那要怎么安装到我们电脑上呢 有两种方式 第一种就是我们通过plugin1键安装 可以把你我们刚讲的所有skills啊 command hook全部安装到我们的cluoub call里面去 比较建议的方式是我们看到哪一个好的 再去导入 导入到我们的cloud里面 按需去复制 所以我们是先把这一个给克隆下来 我来演示一下 给大家看 比如说我们先进入到桌面 然后去把这一个给克隆下来 OK然后克隆下来之后呢 我们就进入到这一个仓库里面 然后比如说我们看到一个skill好用的 比如说我们看到里面有一个我们刚那个article Article writing skills
```

#### Chunk 7

- retrieval_unit_id: `transcript_chunk:bilibili:BV1XrEZ6NEuD:p1:chunk_376fdbf26b0aef0edc05d525f5e1a796`
- chunk_index: `7`
- time: `811.030–902.660s` (`00:13:31.030–00:15:02.660`)
- raw segments: `354–393` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `6`, score `0.361521333456`
- hybrid: rank `6`, score `0.015151515152`
- content_quality_warning: `none`

```text
Article writing skills 我们可以进入到一个skill文件夹 然后就可以看到这里 都是我们刚讲的那些那些skills 比如说我们看到一个叫做article writing 那里面就有这一个skill点ND对 那我们是要把整一个文件夹给复制过去就好了 所以我们就比如说我们看到这一个article writing的 The skill 我们想要我们就把这一个整一个给复制到 cloud co的skill里面 哦我们得退出来 在这个everything cloud co的位置里 然后去复制 对他现在就把我们这里面的skill的article writing 这skill复制到cloud那边了 那我们再来复制一个 那我们可以试验一下我们刚加载的那几个 有没有正确的加载到skills里面 比如说我们刚那个是叫article writing 对我们看一下哦 现在已经有了有这个article writing skills 那还有另一个是叫boys嗯 Boss friend 看有没有哦 brain boys也有了对 然后现在这两个就已经成功的加载进去了 所以大家可以去GITHUB仓库里面 然后看哪一个skill是我们所要的 然后就把它复制到看我们相应的位置 然后就可以在这里使用了 对这期的内容就到这里啦 这一期我们先简单的过一过整个残酷的内容 然后下面几期呢我们会更加详细的讲讲 他的几个进阶的指南 所以如果大家对此期内容感兴趣的话 欢迎给个一键三连 那如果你能给我一个大大的关注的话 那就是对我最大的鼓励和支持 谢谢大家
```

### Human decision

- [ ] R_evidence
- [ ] N
- [ ] Retain U_title because content is unusable

Reason:

Relevant supporting chunk IDs:

Optional useful interval:

## Q07 / Video 93

### Video metadata

- Query ID: `Q07`
- Query text: `Claude Code 记忆机制`
- Video ID: `93`
- BVID: `BV15HXCBkEKY`
- Video title: Claude Code 源码分析与复刻实现
- Uploader: LLM张老师
- Duration: 2257 seconds (00:37:37.000)
- Favorite folder: 2026找工作学习 (`3876418799`)
- Archived: `false`
- Ignored: `false`
- Subtitle source: `ai`
- Raw subtitle artifact path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV15HXCBkEKY/subtitle-raw.json`
- Raw subtitle SHA-256: `82a2f8fcf766cdb18fb890b02e798ca3e9c444a3ee2b5bc8a035887b09aeeab6`
- Raw subtitle segment count: 1082
- Transcript chunk count: 20

### Complete transcript chunks

#### Chunk 0

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_3c183aac860b1338233719ef2f7634ac`
- chunk_index: `0`
- time: `0.000–118.050s` (`00:00:00.000–00:01:58.050`)
- raw segments: `0–58` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `4`, score `0.498295515776`
- hybrid: rank `4`, score `0.015625`
- content_quality_warning: `none`

```text
大家晚上好 好久没录视频了 最近比较忙 今天不是发生一件大事吗 啊来凑个热闹 就是club code啊 它的0.88这个版本更新的时候 不小心把NPM的那个map文件放上去了 这样的话人们就把这个反向的把它的源源代码给它弄出来了 嗯全是typescript 然后呢搞笑的是什么呢 这个一小时之前他把代码又改了哈 可能是可能是官方收到了 但是互联网上全都是 所以大家自己去下载一下就行呃 这个视频讲什么呢 讲一下什么 他的这个crown code这个源代码分析出来以后 你看下它的架构是什么样的啊 我们来分析分析 也是AI帮我分析的啊 那你代码是看不完的那么快 当然还有它的难点 或者说它现在呃在行业当中已经可以实现的地方 以及张老师自己的实现方式呃 今天我们就来复刻一下它 首先我们看一看什么是agent的loop嗯 最近比较火的一个词agent loop 以及基于他的这种harness啊 因为cloud code本质上它就是一个agent loop agent loop的意思呢也非常简单 就是一个大的while循环 什么叫做while while循环 就当第一轮我的一个提示词进去给大语言模型之后 那大言模型会输出个结果对吧 说这个结果如果是对的的话 那我们就结束这一轮对话也结束了 像普通的一个聊天一样 那如果不对的话呢 就进入第二轮 然后再给LOM 然后再再输出结果 然后再判断啊 直到这个中间某个过程结束了 或者是他到了一个最大的轮数 比如说我们设定25轮 那这个就不能太长吧 你不能永远的烧token 就作为临时的一个结果就结束了嗯 那其中怎么工作的呢 这个里面有比如说每一轮用户问题以及系统提示词 以及我们所有的工具 或者是可以调用的skills等等 在这里面扔给它 然后假如说这个问题是 那你帮我查一下 我本地我的电脑上这个有没有一个叫呃什么什么名的文件啊对吧 然后跳给大模型了 这时候大模型返返回的结果是什么结果呢
```

#### Chunk 1

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_66a23e51c93b56c062fb8a83a9eedeab`
- chunk_index: `1`
- time: `115.930–234.010s` (`00:01:55.930–00:03:54.010`)
- raw segments: `58–113` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `8`, score `0.467603713274`
- hybrid: rank `8`, score `0.014705882353`
- content_quality_warning: `none`

```text
这时候大模型返返回的结果是什么结果呢 因为他训练过了 他知道找文件的这个应该调用什么样的工具 比如说叫做bash 然后呃或者是GRAP这个工具 这个工具是个命令行工具 它就可以在本地电脑或者是服务器上去搜某个文件名 那它返回的是这个工具 这个工具呢本地的执行一下啊 执行结果对不对对了 那我就结束 不对的话 我告诉模型说 哎你看上一步的结果检查出来这个 但并没有你要的 然后模型说改一改 说那你用下一个工具等等 这样的不断的循环 这个loop本身就是agent loop 那呃cloud code有什么呢 在这个里面这是一个单智能体的感觉 cloud code呢就是把它下面呃加上很多多智能体 就是我一个任务 可能这个主智能体我拆分拆分成多部任务 然后呢呃给分配给三个子智能体 你分配额分别去干什么什么 无论是并行还是串行等等 嗯最新的这种teams swarm 这些模式本质上都是一样 就是由一个智能体把任务分发下去 那这个是我们从架构层面上来看 它今天不是有代码的吗 所以从代码层面上能看到具体怎么实现的 那我们先把它讲完 这个里面呃涉及到很多很多的细节 也是cloud code做的最早打磨的最好的 要比呃我觉得比MANUS啊和其他的啦都都更codex什么更细致的东西 就这个里面有系统提示词 上下文的压缩 有这个工具 随着工具的增长 买MCP等等 这个越来越多 那么如何高效的去呃去去把工具的名字告诉模型 而不是去污染模型上下文 MCP也是一样 然后现在已经变成动态的工具搜索了 比如说你有100个工具 那你不能一每一轮把100个工具都给单元模型 告诉他这个任务我有100个工具 然后每个工具分别怎么用的 然后模型把这些全读下来 那5万个token就没有了 他不断的在调这些的部分 就是把模型的名字 不是把工具的名字和一个一句话的描述扔给他
```

#### Chunk 2

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_19a3ee676e51c6fa8da4f3e3c3f12c1f`
- chunk_index: `2`
- time: `231.230–350.550s` (`00:03:51.230–00:05:50.550`)
- raw segments: `113–162` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `2`, score `0.509135067463`
- hybrid: rank `2`, score `0.016129032258`
- content_quality_warning: `none`

```text
不是把工具的名字和一个一句话的描述扔给他 然后呢让模型看一下啊 那我这100个里面我可能要调用第二个和第12个 然后呢再去把第二个和第12个的工具的详细的内容 再分别动态拿出来啊 这种东西就是harness 还有呃记忆对吧 记忆你多少轮 这个过程当中 用户的一些话语 比如说强调了这个东西要记住他就写入本地的markdown文件 然后记忆如果多了行数太大 那记忆文件太大怎么办 再把记忆文件抽成memory点MD呃 每一行都是一个索引 然后这个索引呢指向了一个另外一个文件 那个文件那个markdown文件是整体的记忆的一个完整的内容 所以他不断的就做这个抽象和索引都干的这个事儿 再有就是上下文压缩 随着你这个对话越来越长 你越来越多的时候嗯 如何缓解上下文这个暴涨的问题呢 嗯三个方向啊 第一个方向是最简单的模型 现在已经从256K 128K已经变到一个million了 所以它比较大啊 这是最暴力的方式 第二个方式呢就是嗯肯定是超过上下文以后做压缩 就你有很多很多轮长对话之后 他做一个压缩 这个压缩呢也并不是一个非常简单的 把所有的对话128K的对话扔给达模型 你做个简单压缩 这个里面把重要的部分挑出来 不重要的部分去掉 比如说工具调用的结果 那些raw这些那些roll的结果啊 roll怎么row的意思就是嗯就是很多不重要信息的结果 比如说一个工具调用回来生成了一堆这个列表 那其实我不要的这个列表 我只要列表中的某一个文件 那么这个中程中间的过程工具的列表结果就不重要了 所以要把这部分扔掉 只指压缩重要的部分 这样解锁噪音嘛 最大化我们这个token的信息密度对吧 最小划伤啊 这些事这个关于音记忆的压缩 那么另外一部分呢就是把这个上下文长的时候
```

#### Chunk 3

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_df3fd590b6cb85a0207876fe5585d68b`
- chunk_index: `3`
- time: `346.390–466.170s` (`00:05:46.390–00:07:46.170`)
- raw segments: `162–220` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `3`, score `0.500108838081`
- hybrid: rank `3`, score `0.015873015873`
- content_quality_warning: `none`

```text
那么另外一部分呢就是把这个上下文长的时候 不要所有的任务在一个智能体做 把一部分的子任务丢给其他智能体 比如说这一个就专门做我搜索一下文件 我我看一下其中这个某一个功能对不对 然后看好了以后 他可能消耗了50万头根 但他的结果只有55万token或者是五五千token 他回到这个主循环里来 然后再继续往下做啊 大概就这样嗯 还有第四个忘了 第四部分呢就更暴力的就是你开多个cloud code窗口对吧 每一个窗口物理隔离它上下文基本上就这四种方法 他在做 那么这些都是我们所常知的啊 这些东西 那么随着cloud code这个代码开源之后啊 可以通过读代码把他的所有东西给拿出来看一下 这就是刚才我说的所有的harness的部分的一些细节的拆解啊 结果已发到视频的下面 先怎么样啊 这个张老师讲的东西都是干货啊 我们先看一下 咱们自己实现一个啊 已经实现了 并且这个是开源的啊 就叫山来看看这个东西是不是长得跟克拉克很像啊 只不过我们把它变成绿色的了哈哈那我可以问他啊 问题啊 我在哪个目录下嗯 目录下好 这个时候什么东西呢 我问了一个问题 这个就相当于第一个round one 它交给大言模型了 然后呢嗯他告诉我啊 在这个目录下对吧 在这个目录下 这个中间有一个这个过程 就是当我把这句话在turn1交给大模型的时候 大模型输出的是什么东西呢 我隐隐藏起来 大模型输出的是呃PWD啊 这个工具啊 PWD这是个工具 就是打印一下当前的文件夹 那么打印出来以后 这个结果再提交出来啊 就是这个是对的了 就一个循环 round1就结束了 就这个东西哎 告诉我在这好 那你可以继续问他 假如说我们现在把它当成cc啊 把它当成cloud code来用啊 这个是张老师的cloud code 叫SHCLOUD总结这个啊
```

#### Chunk 4

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_941778e77da44f9f290be7c7b66d22f8`
- chunk_index: `4`
- time: `462.110–576.760s` (`00:07:42.110–00:09:36.760`)
- raw segments: `220–283` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `10`, score `0.458532005548`
- hybrid: rank `10`, score `0.014285714286`
- content_quality_warning: `none`

```text
叫SHCLOUD总结这个啊 rebel对吧 对比一下谁呢 对比一下open cloud好 这个可能是个比较长的一个任务 我们让他在这待着嗯 也是一样 就是这个是第二轮对话了 虽然说跟第一轮没关系 你看他就是调用了工具了 file read啊 Read me 点MD 这个时候呢相当于这我把这句话丢给模型 然后模型返回了一个工具 叫做用请用file read来读文件 读哪些文件呢 嗯读read me和一些比较重要的这个呃 比如说cloud md等等 这是模型选择的 他已经能读我当前文件夹下所有的文件了 然后他用了一个web search的一个工具去搜open cloud是什么 然后搜到了以后去fetch一下对吧 这个open cloud到底是什么东西 然后呢看到其他的open cloud这个GITHUB的地址 所以他现在在搜集信息 那么两部分信息 第一部分是我本地的文件对吧 我这个rapper讲的是什么 然后第二部分呢是open cloud是什么 它两部分这工具调用结果回来以后 他最后一步再对比 所以你看这里面有多少个循环呢 呃它虽然不是很精确 但是至少五六个循环了 相当于在这诶一轮一轮一轮一轮一轮不断这么循环 那举个例子 假如说这是个比较重的任务 那么其中假如说这部分任务非常重 他是一个深度搜索的感觉 对吧 是地深度调研的感觉 那么这几步我们就可以把它扔给一个子智能体 让他去做 你去搜吧 你搜100个网页也好 你把你搜到的结果给我总结回来 然后提回来放到这来 我来做下一步的用处 这就是cloud code 这个叫呃 怎么说 这个叫dispatch 一个子智能体啊 这样的感觉啊 这个东西还很多啊 他在调用我们本地文件啊 这go logo等等等等等 我要把我自己移到这边来啊 跟cc club code的用法差不多 所以啊张老师这个也是开源的 大家可以看看 在这啊 coco lab删括呃
```

#### Chunk 5

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_f063d9f63c25462d9fb4a5f560cc504b`
- chunk_index: `5`
- time: `574.800–692.950s` (`00:09:34.800–00:11:32.950`)
- raw segments: `283–342` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `6`, score `0.476494848728`
- hybrid: rank `6`, score `0.015151515152`
- content_quality_warning: `none`

```text
coco lab删括呃 虽然叫cloud 像open cloud一样 其实它就是一个cloud code cc 我觉得他们是一样的东西啊 不要被语言所迷惑 包括harness这个词 其实它也就是打磨的意思啊 所以不要被打磨所 不要被新词所疑惑啊 就是打磨的意思 我们先放在这儿啊 你看我还超过了最大这个token数了 没关系 先放在这啊 那我们先回来看一下这个源代码所导出来的 这个cloud code的核心架构是什么 最主要的就是这个红色部分就是一个它叫query loop啊 其实就是agent loop嗯 一个主要的循环 这里面是重要的文件 我用AI独立变成文件 文件非常大 50多万行 那么主要几个大文件呢 他写的也比较长 因为本身他自己也是cloud cc写的cc啊 所以我们用cc时间长的人有一种感觉就是近似曾相识它的优势的地方 它的这个呃劣势的地方啊都类似 比如说有一些主文件拉的非常长 有8000多行额上万行都有 有一些呢就是针对这个测试 比如针对这种呃特殊的这个呃race condition等等 他就做的非常强 因为模型机器训练的时候 在这段特别针对性 你你你开发什么项目 用CC写啊 大家感觉都差不多哈 所以这跟loop就我跟人刚讲的差不多 首先它分了几层进来的时候呢 就是呃它叫query engine 其实就是入口这个文件 那么入口文件就是管理对话对吧 然后就是刚进来之前 你要查一下当前的相遇数组以及当前的文件缓存以及用量追踪 这些放在最前面 因为用量追踪就是你一旦超量了 你就不能往下走了 他要让你付费吗 所以这些是最先级的 放在最前面 然后呢进入主循环 主循环 他最近这个两周开始加了这个流式了 输出了以前都不是流式的 就你要等 比如token很长 你要等到最后他转转转转 然后刷刷出来
```

#### Chunk 6

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_77bdde695c7283776ce8117d99eca818`
- chunk_index: `6`
- time: `691.919–811.120s` (`00:11:31.919–00:13:31.120`)
- raw segments: `342–404` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `16`, score `0.408946454525`
- hybrid: rank `16`, score `0.013157894737`
- content_quality_warning: `none`

```text
然后刷刷出来 最近是一行一行一行给我们往外刷 所以他先是API的流式输出啊 就是那个SIC嗯 Server side event s c 然后呢检查这个工具使用 然后工具使用结果的回填 这个是主循环所反映的 跟我当前所展示的这个差不多 检查工具工具循环啊 然后再回来看看结果 这个就是张老师的cloud code所给你的输出啊 当然了 没有打磨也不太好看 但是一样的哎 这个是删cloud是什么东西啊 是一个go的CRA客户端啊 他能做什么什么什么什么什么 然后呢open cloud啊 什么什么什么什么 主要看这个对话这个表格核心差异语言 Go node js Open collation Node js 我们终端为主啊 偶尔有有进程守护进程 它就是一个本质上是个消息网关 然后有三个频道接了slack telegram和line 这个呢接了what's up等等啊 这个我也加了飞书啊 还没上来嗯 深度的Mac os集成 这是普通工具 哒哒哒哒哒一堆一堆对吧 这个本质上来说其实简单说差不多啊 这上面还有用量统计 就这个任务花了三美金 当然我们调这个模型的比较贵 你替换成这个便宜点的模型或者开源模型啊 就会便宜一些 所以非常简单 你可以问他很多很多问题啊 我现在哎这么问吧 问点什么呢 嗯打开这个呵呵 打开chrome啊 浏览器 浏览器先拿到前面来 拿到前面来拿到桌面前面来啊 这个时候他调用了本另外一个工具 什么工具就是控制苹果电脑这个工具啊 叫做这个OS啊 Os script 然后对吧 hum每一个loop确认啊 你就点个yes 他才能执行 哎 这不掉出来了 它就跑到前面来了 然后呢 你还可以让它干嘛呢
```

#### Chunk 7

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_753493f2b747347b5e50615f90ed17eb`
- chunk_index: `7`
- time: `809.620–922.550s` (`00:13:29.620–00:15:22.550`)
- raw segments: `404–459` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `14`, score `0.418782234192`
- hybrid: rank `14`, score `0.013513513514`
- content_quality_warning: `none`

```text
你还可以让它干嘛呢 这个有装了play rim c p以后 就能完全控制自己电脑呃 MCP嗯 很多很多都可以叫 比如说跟open cloud是一样的啊 我们叫做啊发设置一个提醒 设置一个提醒啊 5分钟后提醒我站起来走走 我之前试过这个 然后呢他就会调用一样的这句话提交给大圆模型 大元模型根据我的七种提示词和上下文来告诉我 你要用一个工具啊 也是这个工具叫tell application 这也是苹果内置的一个工具 什么工具呢 就是我的它弹出来了 就是我的这个这个提醒这个东西 他弹这个一会儿他会设置一个新的提醒啊 啊哈哈哈 就站起来走走啊 5分钟之后对 现在是我的时间 5分钟之后啊 一切都能做 我们回到我们要讲的主主要内容来 然后第三部分是系统提示词的组装 这个部分的说法非常多啊 这里面总结比较简单 更多要看代码什么呢 就是提示提示词啊 就MACY也说过这个事 提示系统提示词涉及到kv catch 那么系统提示词里我们知道经常会注入动态的东西 比如当前的时间 比如说这个他们叫dynamic boundary 就是动态的一些边界 动态上下文 这个啥意思呢 就是你当前时间就是个动态上下文 然后还有很多可能加载的工具 skills等等 动态上下文 这些东西在系统提示的组装的时候 要根据模型的缓存机制进行组装 现在模型的缓存机制已经跟以前不同了啊 不是就最简单的前面就给catch住 现在模型呢也提供API提供了叫做呃叫这个参数忘了 就是专门管理catch的参数 并且能允许你在提示词里面加入一个字段 叫做catch heat 就是中间这个部分 你加入了字段之后 这部分可以让你动态的 就是不让模型catch住 所以能大量的节省的这个上下文
```

#### Chunk 8

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_ea682a82997e49897fef9c9c68fa4d82`
- chunk_index: `8`
- time: `920.010–1038.250s` (`00:15:20.010–00:17:18.250`)
- raw segments: `459–511` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `17`, score `0.395494043827`
- hybrid: rank `17`, score `0.012987012987`
- content_quality_warning: `none`

```text
所以能大量的节省的这个上下文 这个是模型大模型的API端和我们自己做API的时候是两边同时啊 这个提供的一个能力 所以这个其实蛮重要的啊 很多人是不注意这个的 我们我自己之前也没注意到嗯 然后是嗯之前都准备好了之后就开始组装请求 比如说这个请求组装也很有意思 实际就是这组装完以后就是要把所有东西发给LOM一个API了 怎么请求呢 就是有个beta header 就是请求头是什么啊 可能装一些APIT等等 然后呃工具的schema对工具的这个格式啊 然后我们的提示词和catch这样的 然后进入循环控制 就是对吧 max output就是最大的这个循环次数 然后一自动压缩 就这个就是整体上前面是从准备到进入循环 然后来回这么循环 这个和我刚才讲的那个agent loop是一个意思 再简化点就是aden loop 那谁在用它呢 它这里面有几个东西啊 一个是刚才我们说的这个CRI 就是额这个东西 这个东西会消费的对吧 你用CLCODE就是CRA是一个消费端 然后SDK我们知道co code SDK也是在消费端 然后他可以现在可以远程了对吧 就云端就是你可以在CRI里面打这个叫做remote control啊 就remote control他就跑到云端去了嗯 server mode就是服务器端啊 这个spring节点 这我还不知道是什么啊 remote control啊 就是刚才说的remote control 这个是WEBSOCKET 另外这里面都是消费端 就是这个A证循环之后 谁去用它啊 谁都行 你要用CRA 你就CRA用 你要是这个app用 就app用这个意思 然后呢主要他讲讲了一个就是关于工具的运行时 这个东西是harness的一部分嗯 工具要注册 就是现在CLO里面自带了大概二三十种工具 这个每种工具要提前注册呃 简单来说就是刚才我说的feature gate里面要排序
```

#### Chunk 9

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_50e4b2781a6a4d369820cbb90ca4c4f4`
- chunk_index: `9`
- time: `1034.550–1153.940s` (`00:17:14.550–00:19:13.940`)
- raw segments: `511–567` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `15`, score `0.411019533873`
- hybrid: rank `15`, score `0.013333333333`
- content_quality_warning: `none`

```text
简单来说就是刚才我说的feature gate里面要排序 并且工具尽量要固定顺序 因为你固定顺序跟系统提示词这个prompt catch也有关系 并且工具呃其实有很长的描述 描述部分都不放在里头 描述部分放在另外一个地方 给的是工具名字和一句的简单的介绍 然后把这些东西20多个 你想想30多个工具嗯 名字加介绍加起来 这个大概比如说几百个token 那20多个工具 几千个token了对吧 所以呢呃就不能太大的 就30多个工具 几千个token了 所以他放的给系统提示词里面放的是这样的一些东西啊 然后是关于如何去呃 orchestra就是编排这些工具 就是并发安全 并发安全啊 读写分离执行 这个是一些harness部分 就是有一些工具呢是危险的 有些工具是不危险的 那不危险工具可以默认执行 危险的工具需要用户点确认对吧 就是刚才我们在这点的yes和NO这个道理点确认 还有一些工具呢是默认呃 这个不能执行的 你一定就是你pass掉 也也让你确认一下 然后呢还有他把工具分为两类 就是读写分离啊 就是读的工具和写的工具 它们分成两类 这可能在编排的时候不能同时进行的 意思就是一旦有写的工具在写的时候判断到了 那么读的工具就给lock住先不读 写完了这个读的工具才去会去读 这就是我们在运用cc的时候 你发现他经常会给你编排来改了一个文件之后 另一个session直接读出来了 是为什么呢 是因为它能他能知道这个文件在写的状态 所以他就不去读 然后关于使用工具 他也会做很多的校验 比如说现在cc就已经很复杂了 我们里面有这种这个这个工具对吧 呃命令命令就是斜线斜杠的命令 有skills 还有plugin啊 还有MCP等等 所以它呢要校验这个还包括还有hook 所以他要校验这个优先级以及权限这一系列的东西啊 这1OOTEL是呃
```

#### Chunk 10

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_e7f59bf55985379189eaf726ee7c82e3`
- chunk_index: `10`
- time: `1151.580–1270.389s` (`00:19:11.580–00:21:10.389`)
- raw segments: `567–621` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `1`, score `0.515091896057`
- hybrid: rank `1`, score `0.016393442623`
- content_quality_warning: `none`

```text
这1OOTEL是呃 这个是审计 所以这一系列东西的校验它写在to execution这个逻辑里面 然后所有的工具要统一的协议 这个方便统一管理 就是呼叫加上检查他的权限 然后呢render就是在UI上怎么显示出来 不同的工具展示的UI效果不同啊 CUI上 然后是否是只读啊 就这些东西细节就不看了 然后streaming to execute 就是在流逝中并发执行啊 进度渲染 这个是很牛逼的 就是你的工具的结果 它是随着逐步的输出去渲染出来嗯 这个涉及到这么多不同的工具 每种工具我觉得分不同的类型渲染出来的 这个过渲染过程还是不一样的啊 非常不同嗯 所以这些东西是呃克扣的 它可能比较比我认为比codex等等其他的工具要做的更深更好的地方 所以现在也有源代码了啊 咱也不知道源代码是不是最丰富的 有了它之后就可以完全很快的让AI帮我们实现出来一模一样的功能呃 当然他有个限制 因为克拉code是code是open哎这个这个ANTHROPIC自己的 所以它只支持ANTHIC的API 然后他有管理mc p server的进程对吧 像PLAYRIGHTMCP等等呃 本地文件系统 然后它能启动一个shell子进程好了 这些就啊不说了嗯 整体这面是个总结 就是红色部分就是agent loop 也就是消息驱动 所有东西都是一个消息 多个消息组成了一个长的session 就这样的意思呃 具体拆分下来以后 关于权限那上限为压缩 然后这个不同工具skills等等不同体系不同的这个呃分类呃 以及多A制的子系统 这些是详细的展开 我刚才在里面基本上已经说了一下 那我可以再过一下 比如说权限竞争 因为cloud code已经非常复杂了 他有好多设置权限的地方 所以他们权限不同的一个进来之后 你有不同的设置的时候 那就是涉及到一个竞争关系 那么谁赢呢 就是权限最这个最紧的那个人会赢
```

#### Chunk 11

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_1db9841940bf824e9e9dc5dcf50caab3`
- chunk_index: `11`
- time: `1267.170–1385.980s` (`00:21:07.170–00:23:05.980`)
- raw segments: `621–678` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `7`, score `0.474045276642`
- hybrid: rank `7`, score `0.014925373134`
- content_quality_warning: `none`

```text
就是权限最这个最紧的那个人会赢 他这个propermission mode要要要踹很多地方 比如说你当前运行的模式 你是plan模式啊 还是auto模式 还是bypass permission模式对吧 这个时候涉及到权限的确认 然后呢有的时候你在hook里面呃 会设置权限 然后classifier这个是它内部定义好了 就是要用用模型来分析某些工具是不是需要人类确认 是不是需要全信确认 所以这两个完全来路不同 然后第三个呢是bash classifier 就是最危险的是bash命令 也就是说你在命令行里面 其实它可以运行任何的这种batch命令对吧 它可以RM啊 remove the whole folder啊 这样的话呢就是危险的命令 这种命令是默认这肯定是不准许执行的嗯 还有规则引擎就是事先写好的一些规则对吧 我们写好就是我们在这个cloud的点CONJASON里面定义的那些CONFIG 有一些你可以让执行 有些不执行 这是以写死的引擎 然后呢 所以这些东西在一起要通过一个atomic竞争的关系 看哪个风险 这个哪个是把关把最好的 然后去执行 那么这个是权限竞争 就是权限管理这个方向 然后上下文压缩 刚才简单说下 它有五层上下文压缩 从源代码来看嗯 第一个就是snip compact 那么以前旧的这个工具的结果只保留结构 不保留内容啊 这个很很合理 旧的工具的结果很可能已经没有用了 然后micro compact就是V压缩 什么意思呢 这个把旧的这个工具结果 然后通知catch诶 这个有意思了 就是strip strip就是给它呃剪裁剪裁变小 缩一下身 然后把一些结果放到cs里面去 cash可能在内存 也可能在文件啊 这个不确定得读一下代码 但是这个catch处就是他认为这个部分是有用的 我先不在主线上面也压缩掉 我不丢失它 我给放到旁边 然后以后同一个session或者是子智能体
```

#### Chunk 12

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_56b9fd7c974d37fe193c25965e8836f8`
- chunk_index: `12`
- time: `1382.940–1501.510s` (`00:23:02.940–00:25:01.510`)
- raw segments: `678–726` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `9`, score `0.462519079447`
- hybrid: rank `9`, score `0.014492753623`
- content_quality_warning: `none`

```text
然后以后同一个session或者是子智能体 它可以动态调用 然后最最简单就是context collapse 就是对话折叠啊 折叠完成这个这个折叠字面上意思应该就是压缩的意思 然后就是触发 比如说触到85% 他就触发这个额压缩进行摘要啊 这个是p t l point啊 错误处罚嗯 这个不太知道什么意思嗯哦就是关于上下文的压缩 但是其实体现起来很多人说codex上下文压缩比这个克劳code要好 因为克拉扣压缩的时候非常慢 codex是一个进展式压缩 其实它在你使用的过程当中不断压缩 我认为codex这个这个体验是好 但是他后端应该应用的更大的这个算力在这并行 在你跟他对话的同时 他在对你压缩嗯 然后这个四个不同的扩展啊 其实本质上来说差不多过就是命令命令 命令就是这个东西啊 命令你自己定义的 然后skills也是这个动态去发现的 然后plugins插件 还有MCP client这些东西本质上都是markdown啊 就就就听我的一句话就行了 本质上来说都是markdown 这些markdown它有不同的这个功能 比如说command就是快速的索引一个markdown文件 你把它这个markdown文件设置成斜杠review 那么就是呃他就触发去读这个markdown文件里的内容 这个文件写好了 如何去review我的代码 这个意思 那skills呢比这个嗯一个markdown文件来说 它复杂一点 它会有一个标题 一个简介啊 这个东西扔给大模型的系统提示词 然后有一个详细很长的内容 这个就是关于他的skills的内容 比如说这个skills如何使用飞书的在线文档 那这个东西模型可能不太知道 或者说他训练的时候没有训练到最新的飞书文档版本 那么飞书就可以写一个skill 就告诉模型啊 你要访问哪个网址 然后调用什么样的CRI工具或者API工具
```

#### Chunk 13

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_033400d2416f01fb98e970ccf5645a22`
- chunk_index: `13`
- time: `1498.490–1618.110s` (`00:24:58.490–00:26:58.110`)
- raw segments: `726–775` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `19`, score `0.385635197163`
- hybrid: rank `19`, score `0.012658227848`
- content_quality_warning: `none`

```text
然后调用什么样的CRI工具或者API工具 然后能访问什么样的文文件权限 什么样的写 这里头甚至于有一些skills会给你再套几个Python脚本啊 告诉你如何正确的调用 甚至是CAR的命令行工具 这就是skills plugins呢本质上就是这些东西的快速安装啊 没啥 然后MCP我不讲了嗯 然后子智能系统这个是它的一个特色嗯 但是也比较简单 它子制能力系统所有的memory或者说的session不是内存里 就是文件里啊 然后他们智能体之间的通讯是通过文件通讯 就是这个MAD box也是存在文件里的啊 这个在哪呢 你就可以这么看它一下 看你自己的目录下的这个cloud对吧 cloud目录 然后咳咳 应该是这个里头嗯 agents back UPS嗯好了 应该去每一个session里面啊 每一个session里面你看这个memory 你的plans plugins 每一个session里面去找啊 今天时间不多就不找了 这就开始有感兴趣进去看看 你就能研究明白它了 匹配代码嗯 他的多智能体的编排是比较呃 看代码来看啊 这个版本代码来看也比较简单的 其实和没有张老师做的香浓更复杂一些好 我手机已经收到这个提示了啊 这个提示这个这个提示走走哈哈 电脑上我现在把提示关掉了 嗯好基本上就是这一些大块的东西 然后有一个彩蛋 因为明天是4月1号这个愚人节 所以呢他准备这个新版本有几个新功能 一个是虚拟宠物 虚拟宠物它命呢有18种命名宠物 就是像你刚登进来的时候 刚登录进来的时候就这个东西一样啊 就虚拟宠物 然后每个人整个形象 然后看你运气能不能选到这个最好的宠物 具体怎么实现的 不知道
```

#### Chunk 14

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_160ee763a7ef01fcef9011783340d532`
- chunk_index: `14`
- time: `1617.610–1737.175s` (`00:26:57.610–00:28:57.175`)
- raw segments: `775–827` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `5`, score `0.48282584548`
- hybrid: rank `5`, score `0.015384615385`
- content_quality_warning: `none`

```text
不知道 但现在用不了 他没有开那个端口 然后呢这是一个常驻智能体啊 这个东西其实我从字面上理解就是一个open cloud 因为cloud code也在走open cloud这条线 就是嗯现在我们不是要长期给它打开嘛 对吧 你打开一次 你每次进来还得cloud code cloud打开 那么它把它做成一个进程 24小时运行的 这样你可以通过其他的端呃去连接它 那么其实就是本质上就是open cloud这样的一个模式 然后远程规划其实就是把这个一些任务 你看30分钟啊 浏览器审批就是把这些任务从本地拉到云端 所以你看他们的他这个方向呢就是本地的进程24小时运行 同时配合运转好了 基本上这些东西了 那么嗯这个是刚才张老师讲的这个香cloud啊 就是我的一个呃架构基本上差不多啊 这个是在它开源之前 我就已我就已经做的差不多了 所以感觉非常之像 我让AI读了一下两个代码库呃 有我超越克洛克的地方 有cloud code远远超于我的地方可以学习过来的 有人说张老师 你怎么你怎么这么不要脸啊 你怎么说你比cloud code还厉害啊 那么他确实是啊 我靠这个香农和香cloud这两个rap做完之后呃 确实是啊 就自己也在用 好用啊 就是不一样 就是你爱钻研的话 这个东西实际上是没啥问题的 那么一个是山call啊 一个是呃香农cloud这个啊 诶不对啊 不是这个这个是我的这个不是开源版 哎呀没关系 你也看不着 这个是相同啊 开源版大家点个星呃 下面来去介绍一下啊 就更牛逼的功能了 那么这个功能实际上是呃运行的CLI对吧 那么这个CRI呢我先退出来 刚才我是这么进来的 实际上这个CRI呢可以直接这么问他一句话也行啊
```

#### Chunk 15

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_dcfeac9f8029ec3aae5e9e50b5becf85`
- chunk_index: `15`
- time: `1732.870–1852.659s` (`00:28:52.870–00:30:52.659`)
- raw segments: `827–878` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `20`, score `0.341502428055`
- hybrid: rank `20`, score `0.0125`
- content_quality_warning: `none`

```text
实际上这个CRI呢可以直接这么问他一句话也行啊 一样的就是一个工具 那么实际上如果你不这么做 他是go写的代码 go代码最适合作为一个进程运行起来 实际上它就是一个demo这个进程 所以呢我现在电脑里面已经运行了一个这样的进程 这个进程就是刚才ANTHROPIC所彩蛋里面所要做的24小时的进程 那我现在已经正常运行了 那我怎么用它呢 实际上我可以通过比如说slack 我可以通过飞书往我的电脑里面传东西 就跟open cloud效果是一样的 然后电脑里面就会操作我的电脑 比如说帮我打开这个打开那个干什么的 并且我们可以通过一个客户端啊 这个是一个客户端 这个是一个苹果端的一个啊app native app好 他在干嘛呢 它在连接本地的引擎 就这个引擎 这个引擎就是刚才给大家看的这个东西 它只不过不通过CRI我给它常驻进程了 在运行的 那么嗯我发个消息啊 咱们来试验试验 就是打开浏览器嗯 进入推特吧 x com发一条推嗯 我在直播啊 就是这个东西就回到我们刚才讲的agent loop里面来 先给大模型大模型分析一下啊 你到底需要什么工具啊 第一个工具就是browser navigate这个工具 这个工具呢是我写好的工具 所以啊这个浏览器其实已经打开了啊 我就放在这 我手也不动它 大家看看它打开了twitter 然后呢他再点击就是看这一部分呃 在不断的调用这工具 然后我在直播啊 看左边这块 它显示我在直播 然后呢他会找到那个按钮 点击八 然后帮我把这个推特给他发出去 就是我在直播 发完之后他会确认一下 那么其实这每一轮这个过程 这个就是所谓的harness地方啊 这个我要harness了
```

#### Chunk 16

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_4686d34faf248ffc2278406d584311d5`
- chunk_index: `16`
- time: `1851.699–1969.899s` (`00:30:51.699–00:32:49.899`)
- raw segments: `878–941` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `18`, score `0.394194364548`
- hybrid: rank `18`, score `0.012820512821`
- content_quality_warning: `none`

```text
这个我要harness了 为啥呢 因为他打了两次 我在直播 这个有的时候成功 有的时候失败 这个是需要harness的地方啊 哈利这个词我看我总说为啥呢 因为我在讽刺这个这个这个词 因为他是作为工程师呃 每天都在脑子里 东西现在被重新包装出来了 你说诶你看他自我反思啊 自我重新调整变成正确的 这个说明你看还是很强的啊 推文已经完成 已经发布到X了 嗯然后我们可以让他做很多事情打开 比如说打开slack slack是一个呃一个软件 就是你苹果电脑装的软件 那么它呢就运行一个命令 你看自动把我这个slack给打开了啊 就是打开了我的slack 很有意思很有意思嗯 然后那既然打开了 我们就可以干嘛呢 可以在这 假如说你现在这个select是你手机上的飞数一样的道理 那个我电脑的terminal啊 就有一个叫GHOSTY ghosty terminal在干什么嗯 在干什么哈 假如说你现在不在电脑上 那你在手机上 那你就问一下我的电脑是ghost determinal在干什么 大家注意一下 我已经这个是你常驻进程的一个东西 他已经收到收到了我来自select的一个消息对吧 一个消息 那么你就在这个电脑上嗯 你这个智能体24小时运行的 它就在运行了啊 我看看他回复我了 在干嘛呢啊他正在调用这个工具 实际上这个就是一个啊WEBSOCKET的过程啊 跟cloud code一样 超越cloud code地方 大家一定记住张老师不是跟随别人的人 汤老师是超越永远站在顶峰的人啊 哈哈哈啊 根据进程可以看到啊 运行一个绘画 两个绘画对吧 为啥两个绘画呢 因为我两个tab 两个绘画当前运行的CRI呃 这cloud dangerously skip permissions 该进程占用了多少内存 运行了6分钟 没问题啊 很好 然后你可以再继续问他 这个假如你在手机上
```

#### Chunk 17

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_8c7008df05716685d4863ae3a792149b`
- chunk_index: `17`
- time: `1968.639–2085.310s` (`00:32:48.639–00:34:45.310`)
- raw segments: `941–999` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `13`, score `0.427465319633`
- hybrid: rank `13`, score `0.013698630137`
- content_quality_warning: `none`

```text
这个假如你在手机上 我电脑内存情况 额你不知道你电脑什么情况 你你就可以问他 你电脑内存情况 甚至于你可以让他监控你的文件夹 什么文件夹动了 然后第一时间对吧 给我给我发个消息 或者是那个你设一些定时任务 你什么定时任务呃 设定时任务 设定时任务每隔啊5分钟嗯 咱干点什么呢 咱们每隔5分钟 每隔一分钟啊 每隔一分钟 这样的话我们直播时候看的比较快了 打开一次呃slack 并且放到前面 并且放到屏幕前 咳好 那我一会就把它这个放到屏幕后面去啊 我看看每每隔一分钟他会有个定时任务嘛对吧 我看看任务设置成功没 如果设置成功的话 他每一分钟他就嘣把我这个屏幕就给调前面来了 看一下 这也是creating schedule 好了 设置完任务了好 那我就给他放到底下去 一会儿看他弹不弹出来 我们先回到这个里面来嗯 所以化繁为简 我们看了很多公众号 我们看了很多文章 我们也看了很多开源的实现嗯 走捷径的占90% 为什么呢 你用color code s DK作为底层 你实现一个东西没问题 这个很好 他的目的就是这样 但是这不是所谓的这个 你可以去呃深度理解甚至是微调的这个多智能体框架对吧 嗯你是一个应用层 你不是做A阵层的 如果是像MANUS等等这样的公司做A证层 或者你自己的公司要自己的A证的工具的话 怎么办呢 嗯你一定要了解底层的机制 像我一样把这些东西画出来 都知道每一个东西是干什么的 同时呢把它应用进来 现在有AI了 其实张老师已经半年多不再写一行代码了 全是口喷啊对吧 现在口喷都有点懒了
```

#### Chunk 18

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_e840baa35a5e839e74c4312fe411d8d5`
- chunk_index: `18`
- time: `2084.350–2202.270s` (`00:34:44.350–00:36:42.270`)
- raw segments: `999–1057` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `12`, score `0.437242895365`
- hybrid: rank `12`, score `0.013888888889`
- content_quality_warning: `none`

```text
现在口喷都有点懒了 已经额交付的速度非常快 所以说重要不值钱的代码就变得不值钱嗯 测试变得也不值钱 因为你循环的非常快 值钱的是经验 值钱的是你愿意花的时间去读 去研究别人东西 这个时间是变成值钱了 同样的一个东西出来 这个开源代码出来了 我相信现在很多人都在看 让不同的人看有不同的结果 有的人可能马上上来 我要给我AI分析一下 然后跟我代码互动 这个对比一下 改一下等等 那其实我第一步先画图 我画图画出来了啊 模块分析出来了 针对每一块我可以让他继续画图 对不对 那么我现在有的是什么他没有的 他有什么我没有的 我需要改的 这个就非常这个呃循序渐进啊 你对知己知彼百战百胜 那么最基本原理是这个之后每一步可以去延伸的部分非常多 你只要做了 你只要做用自己做的东西之后 你就会发现诶这一步当中诶 我这个工具结果不对 我要改一改 就像刚才我们用的时候对吧 这个呃发推的时候诶 刚才进入发推的时候 第一次不是发错了吗 发了两次 我在直播 我在直播 但是他最后调整回来了 这个过程也是我在中间做的所谓的harness啊 其实就是工程系统工程嗯 那么harness是什么呢 就是周围着周边所有的细节 这个东西就是harness 哎呀这个刚才没给我弹出来啊 我们我们来看看为啥没弹出来嗯 定时任务里有没有嗯 那有啊有定时哦 那没关系 那就可能是我当时在按别的东西放在那可以 那么就可以做很多很多很有意思的东西 这个嗯这个智能体研究张老师研究很透了 而且我还有一本书没有看到的话 可以上我的主页上去看讲多智能体的这本书嗯 这两个合在一起可以做很多很多的事情啊 这个今天主要是来分析这个开源代码
```

#### Chunk 19

- retrieval_unit_id: `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_07d864c68b27dfd6e932dd49bac8354e`
- chunk_index: `19`
- time: `2199.450–2254.760s` (`00:36:39.450–00:37:34.760`)
- raw segments: `1057–1081` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `11`, score `0.448228627443`
- hybrid: rank `11`, score `0.014084507042`
- content_quality_warning: `none`

```text
这个今天主要是来分析这个开源代码 但是如果你觉得呃cloud cod开源代码你可以直接用 因为那个是node js的 大家可能更熟悉一些 嗯没问题 那个但是他有很多东西是它封装好的 并且只支持安SP1家的这种 比如说它的流式输出 比如说他接AAPI接口 而张老师的香浓和香靠这两个东西啊 香靠在哪呢 这两个东西咳删挂在这 我这两个是支持多语言的 包括本地的欧拉玛 这两个大家可以截图 然后去关注看一下 这个是长期更新啊 大家一定要点start呃 之后这个产品即将发布啊 欢迎大家来使用好了 今天就讲这么多啊 这个跟着张老师一起学习AI多智能体 无论是原理理论还是技术工程实践啊 世界第一 拜拜
```

### Human decision

- [ ] R_evidence
- [ ] N
- [ ] Retain U_title because content is unusable

Reason:

Relevant supporting chunk IDs:

Optional useful interval:

## Q07 / Video 108

### Video metadata

- Query ID: `Q07`
- Query text: `Claude Code 记忆机制`
- Video ID: `108`
- BVID: `BV1KJ61BBEB1`
- Video title: 15分钟Claude Code小白入门
- Uploader: 第四种黑猩猩CHIMP
- Duration: 929 seconds (00:15:29.000)
- Favorite folder: 2026找工作学习 (`3876418799`)
- Archived: `false`
- Ignored: `false`
- Subtitle source: `ai`
- Raw subtitle artifact path: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1KJ61BBEB1/subtitle-raw.json`
- Raw subtitle SHA-256: `5ddf3aeba702b5daf48fb4ce3456dca884b373110f4c09391f07c85e967d494b`
- Raw subtitle segment count: 523
- Transcript chunk count: 10

### Complete transcript chunks

#### Chunk 0

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_54e64f84d9428632fb2c2847bfa5e0a7`
- chunk_index: `0`
- time: `0.040–101.160s` (`00:00:00.040–00:01:41.160`)
- raw segments: `0–61` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `9`, score `0.403840869665`
- hybrid: rank `9`, score `0.014492753623`
- content_quality_warning: `none`

```text
今天这期视频啊 我们只讲一件事情 就是普通人怎么用cross code 把自己需要的工具直接做出来 很多人听到code这个单词啊 写代码觉得跟自己完全就没有关系 但其实cloud code除了超强的这种写代码能力之外 他还能做很多日常的任务 比如说数据分析啊 比如说这个每日资讯的爬虫啊 比如说文件管理等等 甚至连修图P视频这种活啊 它也能帮你把流程搭起来 因为它啊不是某一个具体的工具 它是一个圆工具 什么叫做圆工具呢 就是可以搭建其他工具的工具 你用大白话讲清楚自己的需求 比如说我想做一个网站 我想搭建一个自动化的工作流 我想有一个小助手 每天帮我整理资料 他就能帮你一步一步把这些东西搭出来 能跑能用 最后呢还能帮你去迭代 现在每天的新工具啊越来越多 更新的也越来越快 反而会让我们更容易掉进这种效率陷阱里面 学一堆的零碎的工具 越学越忙 效率越学越低 所以我觉得啊 普通人更应该去学这种顶级的通用的工具 学会一次之后啊 以后想要啥就可以做啥 这期视频啊是cloud code的入门视频 我会带你从零上手 先用5分钟时间呢先讲清楚怎么去安装配置cloud 当然已经安装好的同学可以直接跳过这5分钟 第二部分呢我会教大家第一次启动cloud怎么用 怎么去提需求 然后会带大家去做几个案例 比如说从零开始构建一精美的笔记软件 一些除了写代码之外的 其他的生活当中的使用场景 最后呢再补充一些我自己总结的使用经验 使用建议 帮你少踩坑 用的更加的顺畅 就算你完全没有写过代码 完全没有用过cloud code 类似的软件也能跟得上 重要的不是用的好不好 重要的是先用起来好 我们开始啊 首先呢我们要来安装cloud code 那基本上呢至少有3~4种方法可以使用cloud code 我们今天只讲最适合新手 最省心的一种方法 就是在像vs code 或者像cursor 这样的AI编程软件当中去使用cloud code
```

#### Chunk 1

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_051ba1a477f51be2efa660c945528d61`
- chunk_index: `1`
- time: `98.560–192.240s` (`00:01:38.560–00:03:12.240`)
- raw segments: `61–116` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `8`, score `0.417567372322`
- hybrid: rank `8`, score `0.014705882353`
- content_quality_warning: `none`

```text
这样的AI编程软件当中去使用cloud code 这个呢有两个原因 第一个呢 就是因为现在这些编程软件的进步速度非常快 不断的推出非常有趣的这些新功能 我们可以在使用cloud code 同时呢能结合这些编程软件推出的新功能 第二点呢就是cloud code原生其实是在终端里面跑 终端大概就是长这样子 就是一堆文字的 这样的窗口 新手一上来呢 其实对着这些窗口啊 很容易直接劝退 但像vs code和cursor这样的编程软件呢 其实界面就更加友好 在这个界面上面点点鼠标就可以操作了 我们这个视频里面以vs code为例啊 你可以直接去这个vs code官网 然后去下载这个vs code的安装包 然后一键安装 完全免费的 安装好之后就可以直接打开vs code 可以点击这里的open project 新建一个文件夹 名字叫做cloud code test 创建 让这个文件夹信任这个vs code里面的工具 好了 你看我们刚才建的这个holo code test 这个文件夹已经打开了 安装完这个vs code软件之后呢 接下来第二步就是我们要来正式开始安装cloud code Clo code 安装呢其实也不难啊 我们先去这个node js的官网去下载安装这个node js 然后你可以用比较简单的下载程序包 安装的方式去安装 安装完node js之后呢 我们再回到vs code 打开这里的terminal终端 接着呢我们把这条命令直接复制进终端 直接按回车确定 输入一下密码 让系统就会自动开始安装cloud code了 因为我这里已经安装过了 所以呢就不再去演示了 这个视频里面用到的所有命令 所有提示词呢我都会放在黑猩猩基地里 我真心觉得呢大家不必害怕这样的终端界面 或者是像类似于这样的终端界面 看起来很专业 很复杂 全是文字 但你看他看到了我们的操作 只是一些简单的复制粘贴的操作而已
```

#### Chunk 2

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_112126b86cc5eaa4e3b80fba0929aeaf`
- chunk_index: `2`
- time: `189.780–286.300s` (`00:03:09.780–00:04:46.300`)
- raw segments: `116–169` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `7`, score `0.418906450272`
- hybrid: rank `7`, score `0.014925373134`
- content_quality_warning: `none`

```text
只是一些简单的复制粘贴的操作而已 然后再给大家分享一个比较实用的技巧 就是我一般会在web coding的时候呢 在旁边开一个其他的AI聊天窗口 比如说GEMINIHHBT豆包前吻 哪个熟悉的 你都可以在安装过程当中有任何的报错 任何按钮找不到啦 哪一步卡住了 你都可以截图或者复制错误的信息 然后直接粘贴过来 它基本上都能帮你瞬间解决掉这个问题 到这一步为止呢 其实lor code已经安装好了 我们可以直接在这个终端里面输入cloud这个单词 然后新人这个目录 当你看到这个cloud code logo的时候 说明你这个cloud code已经安装成功了 我们先退出 但对于小白来说啊 我觉得其实最好再安装一个cloud code的插件 可以提供一个更好的交互界面 我们在这里插件这里搜索cloud code 然后看到这个cloud code for vs code之后呢 这里这里有个按钮 直接一键安装就可以了 然后安装完成之后 你会在这里发现有一个cloud code的这个小图标 我们直接点击打开 然后我们最终就得到了一个在vs code的编程软件 里面的带插件的cloud code 到这一步的时候呢 你cloud code的整个安装流程就完成了 好安装完成之后呢 还有最后一个关键的问题 就是cloud code里面用什么模型 这个搞定之后啊 你就可以真正的开始使用cloud code Cloud code 本质上呢是一个终端里面的这个智能开发工具 所以他自己啊不产生智能 背后必须接一个大模型的服务 官方默认的呢是走这个ANTHROPIC的cloud模型 但因为海外服务 大家都知道这个众所周知的原因 很多人都会遇到网络啊 支付啊 账号啊 稳定性一堆的这个限制问题 但如果你这些自己都能轻松搞定 那你可能也不需要我这期的入门视频了 所以更常见 也更适合大多数人的方案呢 是直接接国内的大模型接口
```

#### Chunk 3

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_ece402d72c989bf7098eb473934922c9`
- chunk_index: `3`
- time: `284.120–387.560s` (`00:04:44.120–00:06:27.560`)
- raw segments: `169–224` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `10`, score `0.396136581898`
- hybrid: rank `10`, score `0.014285714286`
- content_quality_warning: `none`

```text
是直接接国内的大模型接口 价格更便宜 稳定性更好 能力也完全够用 比如说制服的gm 比如说mini max kimi等等 为了让整个这个大模型接口的配置过程 也更适合小白更友好 我推荐一个接口的管理工具叫做cc switch 大家可以去搜一下这个cc switch的这个 下载和使用教程 它的作用也很直接啊 就是你可以购买多个服务商的不同的模型 比如说有时候这个模型比较便宜啦 有时候那个模型可以有一些优惠的政策啦 cc switch可以帮助你去管理所有的这些不同的模型 如果你想切换哪个模型 你就直接点一下这个启用按钮就好了 非常方便 顺便说一嘴啊 它除了可以管理cloud code的这个接口以外 它还可以管理codex和GEMINI的这个开发工具的 背后的接口 具体怎么使用呢 第一步啊 你要先去这些大模型的官方网站 他们的购买页面去购买他们的coding plan 买完之后呢 然后可以去到他们的这个API key的管理页面 去创建一个新的API key 然后把这个API key复制出来 先放好 因为等一下要用 一般都是在用户中心的APIT管理页 或者是类似的这样的页面里面 第二步啊 打开刚刚的这个cc switch 然后这里有一个添加服务商的按钮 然后先选择你的品牌 然后把你刚刚复制的这个API key复制进来 然后添加就行了 添加好之后呢 你就可以在这个首页 然后用这个启用按钮 启用你刚才新添加的这个coding plan的这个接口 这些都完成之后呢 就重启你的cloud code 然后你这个整个cloud code 以及它后端的这个模型接口都可以生效了 好了到这里为止啊 就cloud code所有安装配置流程都已经全部用完了 我们回到vs code这个软件里面 打开这个cloud code 接下来我们就来体验一下 为什么很多人说他是2025年 甚至到现在2026年还是最强的AI工具
```

#### Chunk 4

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_959208cdff26ea49a06cb85c15a4f044`
- chunk_index: `4`
- time: `385.000–487.560s` (`00:06:25.000–00:08:07.560`)
- raw segments: `224–277` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `6`, score `0.435420811176`
- hybrid: rank `6`, score `0.015151515152`
- content_quality_warning: `none`

```text
甚至到现在2026年还是最强的AI工具 先介绍一下这个看起来酷酷的 这个界面的主要功能 左边的是项目文件夹 这个就是我们刚开始建立的这个项目文件夹 C c test 然后中间呢是编辑器 到时候如果有文件生成 你想看某一个具体的文件内容 就会在这个中间显示 右边呢是cloud code核心的聊天窗口 也是你主要跟cloud code交互的地方 正好我们刚刚添加了我们自己的 这个大模型接口 所以呢我们可以在这里直接问他 你现在使用的是什么模型 他回答的就是我们刚刚添加的这个形的模型 从刚刚这个这么小的例子当中 你可以体会到我们在使用cloud code的过程当中啊 不管你有什么样的问题 都可以直接问cloud code 然后这里呢还有一种更帅的方式 因为CD code里面它自带了很多实用的功能 这些功能呢都可以用斜杠 加一些这个英文单词来调取 比如说你输入斜杠 然后后面加上这个model 它就会显示你现在正在使用的模型 和其他可选的这个模型选项 当然还有很多其他的这个斜杠功能 但我的建议呢是 你完全不需要在现在这个阶段去死记硬背 慢慢用起来 你自然就会记住了 我们的思路呢也是后面用到什么 我们再会去讲什么好 我们接下来呢来试着用cloud code 做我们的第一个应用 在开始做应用之前 我最后再讲一个关键关键的功能叫做plan mode 你可以在这里看到 现在呢这个模式叫做ask before edit 就是每次这个cloud code想要编辑的文件呢 它都会可以问你一下 同不同意 你按一下 它就会变成这个cloud code自动去编辑的模式 你再下呢就会出现这个plan mode plan mode呢是整个cloud code里面极其重要的一个知识点 它的核心价值呢是他不让AI立刻帮你去写代码 而是让你和AI来回的去讨论这个方案 把方案定下来之后呢 再去写代码 很多时候你想让cloud code去真正改代码之前
```

#### Chunk 5

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_103b7d6200582f07d27c2f8a2d4dbe83`
- chunk_index: `5`
- time: `485.100–598.120s` (`00:08:05.100–00:09:58.120`)
- raw segments: `277–330` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `5`, score `0.452986359596`
- hybrid: rank `5`, score `0.015384615385`
- content_quality_warning: `none`

```text
很多时候你想让cloud code去真正改代码之前 你希望他真正理解你的需求 真正理解你想要去做什么 这就是play mode的这个用途 先确定他的计划是否符合你的预期再去执行 很多人抱怨说这个AI智能体agent不可靠 然后会乱改东西 也实现不了我的需求 但大部分时候都是这个plan不够好的问题 如果你能正确的合理的使用这个play mode智能起啊 大部分时候都会按照你的要求来做事 还有一点就是如果你不知道什么时候要选play mode 什么时候不选play mode 那我的建议啊 就是所有时候所有场景都把play mode给勾选上好 接下来我们就开始我们的第一个案 我的提示词是这样子的 我想开发一款高级的笔记应用 用户能够在一个强大的编辑器当中去记录笔记 能够将笔记保存到这个文件夹中 并按照自己的意愿进行整理 甚至还能结合一些AI的功能 然后请你为这款应用撰写一份 PRD的产品文档 然后cloud code呢会反向来问你这个具体笔记软件的 一些这个具体的需求 他有了我们的这个回答之后呢 他可以更具体更准确的去编写这个产品文档 好需求文档写完了 我们先选择我们手动去看看这个需求文档 需求文档如我们所想一样 就是写的非常全面 包括了产品概述 技术的架构 然后功能的需求 我们主要来看一下这个核心的功能点 第一个呢就是一个笔记的编辑器 然后是笔记的管理 第三点呢是智能写作的辅助的功能 它还帮我们设想了一些拓展功能 在后续版本当中可以再添加 但说实话 这种PRD呢当然写的很好 但对于小白或非技术人员来说呢 真的是太完整太大太全了 对我们来说呢 最稳的方式就是一次只做一个小版本 然后测试再确认再加入下一个功能 所以呢我跟他说 第一个版本让我们先完成这个前端的部分 做一个本地能运行的demo 然后把这个模式改成play mode发送 在CROCODE执行的过程当中 他经常会向你问一些问题以及申请一些权限
```

#### Chunk 6

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_8419798454f3f641d3d14c4ac85ca4f7`
- chunk_index: `6`
- time: `594.600–700.740s` (`00:09:54.600–00:11:40.740`)
- raw segments: `330–387` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `2`, score `0.47982019186`
- hybrid: rank `2`, score `0.016129032258`
- content_quality_warning: `none`

```text
他经常会向你问一些问题以及申请一些权限 然后呢 如果你你想一步步每次都确认一下 你就每次都点yes 因为我已经用过cloud很多次了 所以我一般都直接让它默认帮我执行 因为我觉得一步步去确认比较麻烦 所以我就选择yes 在这个项目当中都会给你这个缺陷 Color code 大概花了10分钟的时间 帮我们实现了这个第一个版本 我们看了一下他这个历史的聊天记录啊 最后还去确认了一下 一开始设计的这个功能表当中 是不是把这些所有功能没有遗漏的去完成了 最后呢帮我们在本地运行了一个服务 让我们打开这个网址去看一下最终的效果 打开之后这个效果呢我觉得就非常好了 因为我正好要跟大家去讲 怎么样在这个web coin当中去debug 因为debug是web coin当中非常非常重要的一部分 我本来还想说要自己设计一个这个错误 然后来教大家怎么去这个debug的方式 然后正好这里给了我们一个错误 好我们现在看到了 我们打不开这个网站了 那怎么办呢 根本就不用慌 我们可以直接把这里的错误信息 全部复制给cloud code 当然有时候呢也可以截图 他这里直接提供了这个复制按钮 点击复制 然后直接把这个错误信息复制给cloud code 让他帮我们去修复好 他说修复完成了 我们再回到这个网页哦 果然修复完成了 你把错误信息直接复制给cloud cod 但9%有时情况下 cloud code都能帮你去直接修复 我们来具体看一下 cloud code为我们生成的这个笔记软件 光从页面上来看呢 这个第一个版本已经非常像样了 中间应该是这个核心的主要的编辑区域 然后左边的是这个文件夹的管理文件的管理区 我们来新建一个笔记 随便试一下markdown格式 标题序列号也没问题 虽然有一个小bug呢 但是这么复杂的一个笔记软件 这么高级的一个笔记软件 能在10分钟之内完成 还是让人感觉到很爽很爽 这里啊 我再给一个我自己日常使用的一个小建议
```

#### Chunk 7

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_147b335f8cc5fe711c992350e8784ef7`
- chunk_index: `7`
- time: `698.160–800.380s` (`00:11:38.160–00:13:20.380`)
- raw segments: `387–443` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `4`, score `0.458053559065`
- hybrid: rank `4`, score `0.015625`
- content_quality_warning: `none`

```text
我再给一个我自己日常使用的一个小建议 前面也顺带提到过 就是在使用cloud code 或者是在这个使用web coding的时候 旁边一定要开一个这个独立的AI聊天助手 你随便选一个主流的大模型都行 这样做呢其实有两个很现实的好处 第一个呢就是随时救火 你遇到不明白的按钮啊 报错啊 流程可以直接把问题丢给他 问 gold code是这两年最强的代码智能体之一 主流的大模型啊 基本上都能知道它的常见的用法 更常见的一些坑 所以呢能给你立即的解释清楚 第二点就是提高复杂任务的这个成功率 有时候一个项目做不成 是一开始方案就不够稳定 但cloud code给出他的方案之后 我们再用另外一个模型做一次交叉的验证 往往能补出你没想到的一些风险点 一些边界的条件 甚至给出更简单的这些替代的路径 具体来说呢 你可以把cloud code刚刚生成的这个计划 直接复制粘贴进来 然后问他这么两个 一个呢 就是这份计划当中最大的风险跟缺点是什么 另外一个啊就是有没有更稳妥 更简单 成功率更高的实现路径 然后把GEMINI生成的这个方案再粘贴回给cloud code 让cloud code基于新的建议更新计划 并且继续执行 我们开头的时候说了 这个cloud code呢是一个顶级的通用AI工具 之所以叫通用工具呢 是因为它除了写代码之外 还可以做很多其他的日常任务 我给大家演示几个例子啊 比如说呢我打开一个新的文件夹 然后呢这个文件夹里面有之前我的三个视频 我现在呢想把它们转换一下格式 并且提取视频里面的音频 这对普通小白来说呢 其实是一个蛮复杂的一个技术性的工作 但我现在可以直接在这个文件夹里面打开cloud code 我可以直接跟cloud code说 帮我检查一下当前目录下所有的mp4文件 把他们转化一个格式 并且提取他们的音频 单独存到一个audio文件夹里面 保留原来的源文件 我们直接发送给CLCODE
```

#### Chunk 8

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_80198986dfbacdbd8615cfb53c0c1f48`
- chunk_index: `8`
- time: `797.580–909.920s` (`00:13:17.580–00:15:09.920`)
- raw segments: `443–507` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `1`, score `0.485834181309`
- hybrid: rank `1`, score `0.016393442623`
- content_quality_warning: `none`

```text
我们直接发送给CLCODE 我们看到啊 因为我们缺少一些视频转换的工具 CLCODE会发现这个问题 然后自动帮我们去下载 安装这个视频转换的工具 好任务全都完成了 我们来看一下 他给我们新建了两个文件夹 一个是audio文件夹里面有三个对应的音频 然后是一个MOV文件夹 里面有三个MOV的视频 你们看啊 这样一个视频转换跟音频提取的任务 就我轻轻松松的搞定了 再来一个案例啊 再比如说我有一个比如说这样的一个文件夹 里面全是杂乱的这个图片跟视频 然后呢我想让cloud code帮我去整理一下这个文件夹 直接跟cloud code说 根据文件的类型跟日期 帮我把文件夹里的杂乱文件 分别对应到文件夹里 发送给CROCODE Clcode 反而会来问你说 按什么方式去组织这样的文件啊 比如说我就选一个按类型跟日期 好任务完成了 我们来看一下 有三张图片的 好像没有被整理进去 但没关系啊 我们先不管它 我们来看一下他帮我们整理的结构 在这个图片文件夹下呢 那个24年3月份有一个文件 25年4月份有11个文件 25年1月份有一个文件 然后等等等等 我们来看一下 还是真实的 这个文件夹里面OK没有问题啊 他整理的还挺好的 然后速度也挺快的 基本上就花了20秒钟时间吧 但是他有时候也会有一些小问题啊 比如说这三张图片没有真理性 但如果你让他再去整理一遍的话 他应该也会帮你把三张图片进去分类 当然这样的场景呢有很多 我就不在这里一一举例了 大家可以自己去体验一下 自己去探索一下好了 视频到这里为止啊 我们已经完成了一整套的cloud code 最关键的入门 我们一开始装好了cloud code 接好了模型 在vs code里面跑起来 用plan模式啊 从零开始做出了一个高级的笔记软件硬 然后正好在录制的过程中啊 我们还碰到了一个bug 所以我们还学了一下怎么用这个cloud code去debug
```

#### Chunk 9

- retrieval_unit_id: `transcript_chunk:bilibili:BV1KJ61BBEB1:p1:chunk_9096426df09a76b637f54ee323c74a21`
- chunk_index: `9`
- time: `906.680–928.680s` (`00:15:06.680–00:15:28.680`)
- raw segments: `507–522` (0-based)
- raw boundary match: `true`
- raw text reconstruction match: `true`
- lexical: rank `null`, score `null`
- dense: rank `3`, score `0.478850245476`
- hybrid: rank `3`, score `0.015873015873`
- content_quality_warning: `none`

```text
所以我们还学了一下怎么用这个cloud code去debug 最后呢 我们还展示了两个日常生活当中会碰到的 这个任务 dollar code呢其实还有很多其他的高阶的玩法 大家应该也听说过 比如说MCP啊 比如说skill啊 比如说sub agent这些呢我们之后也会介绍 但我想说的是啊 这些其实都不重要 重要的就是你自己先玩起来 先用起来好了 今天视频就到这里了 我是迪自黑心李超 我们下次见
```

### Human decision

- [ ] R_evidence
- [ ] N
- [ ] Retain U_title because content is unusable

Reason:

Relevant supporting chunk IDs:

Optional useful interval:

## Stop boundary

This packet stops before any human semantic decision, Gold update, Gold lock, or formal Stage 6B evaluation.
