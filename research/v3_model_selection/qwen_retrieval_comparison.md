# Qwen Retrieval Comparison Evidence

Judged by: Codex Repository Executor. Basis: direct entity/topic match in the title and short excerpt is `Relevant`; same retrieval domain but not the requested entity is `Partially Relevant`; unrelated evidence is `Not Relevant`; insufficient evidence is `Unclear`.

All excerpts are whitespace-normalized and limited to 72 characters. Chunk timestamps and unit identities are copied unchanged from formal `retrieval_units`.

## `MCP`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_634ab524cadf197c27463d06` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1350.140–1468.200s | 0.548667 | 嗯uv to list 我现在安装了一个m l x whisper 当然还有manner u哈 去做PDF的一个精准的一个pass pass呃  | Partially Relevant |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | video | [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型 | — | 0.542068 | [Title] [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型外壳”（简介附原文链接） | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV14pXZBMEh9:p1:chunk_66e6a42d19c6477205653536` | transcript_chunk | Claude用不了的时候，GLM-5.1能顶上吗？ | 116.470–236.090s | 0.539608 | 只不过这个全都是AI版本的 这个系统真的很复杂 我给它的完整提示词 里面包含了像素风的前端记忆系统 弹幕互动角色扮演 还有总的一个gm管理系统  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.533773 | …记忆他的评价指标表现出来的话 最后呢是我们的一个数据结果表格的分析 然后大家感兴趣也可以去读一下 好以上呢就是本期视频的全部内容了 然后我也是 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_da39154f9ba5dd5fefd3d98f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 0.040–118.360s | 0.532788 | …OI专门为人类设计 因为人类不擅长记忆命令 而更擅长使用图形工具 而AI则正好相反 大模型在诞生的时候就学习过大量代码 命令行等语料数据 因此 | Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_2161f52c75ef74ca992bfc3e` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 461.760–579.190s | 0.644566 | 理解skill的核心概念 是把某一类任务需要的知识流程和工具 组织成一个可以按需加载的能力 然后可以看一些skill的最佳实践和设计指南 学习s | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.617278 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV1AuzkBREhx:p1:chunk_bd38bab47f32c042b83c8b17` | transcript_chunk | AI到底是如何进行编程的？抓包拆解Claude Code | 0.080–119.360s | 0.612752 | 安吉的m cp scale到底是什么 你一定听过很多关于他们的理论 但你的理解一定是正确的吗 比如MCP的解析式大模型上下文协议 它可以和各种外 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_b054f1bd553c27a5e404f8c7` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 695.800–814.920s | 0.610988 | 而且我还可以协助AI进行修复 而MCP对人类来说更像是一个黑盒 整个运行过程都是在agent的内部的 如果运行出错 很难在本地复现问题 调试的难 | Relevant |
| 5 | `video:bilibili:BV1qTYizcEN3:p1` | video | 什么是Function Calling与MCP协议？它们为何要这样设计？ | — | 0.569442 | [Title] 什么是Function Calling与MCP协议？它们为何要这样设计？ [Uploader] 堂吉诃德拉曼查的英豪 [Desc | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_6c982f17915950d79bd4ab0f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 579.040–698.380s | 6.137341 | 填上校验码就登录完成了 然后我们可以使用这个命令查看一下open cloud上面的医术列表 或者使用这个命令给我自己创建一个新的仓库 我们看到这 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_b054f1bd553c27a5e404f8c7` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 695.800–814.920s | 5.988809 | 而且我还可以协助AI进行修复 而MCP对人类来说更像是一个黑盒 整个运行过程都是在agent的内部的 如果运行出错 很难在本地复现问题 调试的难 | Relevant |
| 3 | `video:bilibili:BV1G29EBGE8b:p1` | video | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | — | 5.908486 | [Title] 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ [Uploader] 技术爬爬虾 [Description] CLI | Relevant |
| 4 | `video:bilibili:BV1k6E167Ext:p1` | video | 推荐一些Pi Agent插件 | — | 5.795395 | …https://github.com/cap153/config/tree/main/pi/.pi 视频中提到的插件或项目： https:// | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_2161f52c75ef74ca992bfc3e` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 461.760–579.190s | 5.672535 | …资料可以放在reference里面 哪些内容应该拆成脚本或者模板 最后是关于怎么测评 你写的prompt和skill 可以看看OpenAI官方 | Not Relevant |

## `LangGraph`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_634ab524cadf197c27463d06` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1350.140–1468.200s | 0.548667 | 嗯uv to list 我现在安装了一个m l x whisper 当然还有manner u哈 去做PDF的一个精准的一个pass pass呃  | Not Relevant |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | video | [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型 | — | 0.542068 | [Title] [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型外壳”（简介附原文链接） | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV14pXZBMEh9:p1:chunk_66e6a42d19c6477205653536` | transcript_chunk | Claude用不了的时候，GLM-5.1能顶上吗？ | 116.470–236.090s | 0.539608 | 只不过这个全都是AI版本的 这个系统真的很复杂 我给它的完整提示词 里面包含了像素风的前端记忆系统 弹幕互动角色扮演 还有总的一个gm管理系统  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.533773 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_da39154f9ba5dd5fefd3d98f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 0.040–118.360s | 0.532788 | CLI这个计算机世界里面最古老的交互方式正在迎来一次新的爆发 飞书钉钉起微 谷歌stripe在最近两周内都不约而同地开源了自己的CLI产品 越来 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1wMQjBCEpZ:p1` | video | [开源] RAG 项目框架及源码详解 | — | 0.640199 | [Title] [开源] RAG 项目框架及源码详解 [Uploader] 蹦跶波 [Description] 项目地址：https://git | Not Relevant |
| 2 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_6ee6e323f7c52d555f45c8a5` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 117.200–235.760s | 0.608785 | 不然的话会引起上下文爆炸 所以呢就是目前还是一个这样的结构 然后来看一下核心的这个代码 主要是通过这个long graph 就是build的re | Relevant |
| 3 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_4ff3cfedbfaf47add9b4f51f` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 0.400–119.640s | 0.607948 | 大家好呀 这期视频呢我就给大家讲解一下 我这个项目的整体架构 还有一些核心代码的梳理吧 然后这个呢也是AI帮我做的一个presentation呃 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1tM9UBSEdg:p1:chunk_845aaa1a31d54f67fd21841c` | transcript_chunk | 面试官问：怎么设计企业智能客服 Agent？ | 232.420–351.189s | 0.598442 | 但会漏掉精确的ts s999这个串唉 精确串项链看不见 对客服场景到处都是订单号 SKU错误码向量都看不见 BM25关键词搜捕这个洞 Anthr | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_6cfb0d1a909308f49e45ec87` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 115.300–233.370s | 0.589217 | 这些功能就涉及到tools的注册调用 执行相关的技术 以及怎么把这些tools调用 串成一个可控的执行流程 所以那段时间我就开始系统性的学习 任 | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1wMQjBCEpZ:p1` | video | [开源] RAG 项目框架及源码详解 | — | 8.888116 | [Title] [开源] RAG 项目框架及源码详解 [Uploader] 蹦跶波 [Description] 项目地址：https://git | Not Relevant |
| 2 | `video:bilibili:BV1sNJW6dE54:p1` | video | 6月13日 | — | 8.639192 | …后通过录音复盘把答不上来的问题吃透，循环提升。 [Summary Detailed Notes] 视频首先纠正了两个常见的学习误区：第一，不必 | Not Relevant |
| 3 | `video:bilibili:BV1co9yBhEvW:p1` | video | 分享我转 AI 方向的学习路径和工作转变 | — | 8.168976 | …AI团队工作方向分为AI基建、内部AI工具、帮助其他团队AI提效，后两者需跨团队沟通与方案设计。 AI带来的职业冲击：取代80%工作导致成就感 | Not Relevant |

## `RAG`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_634ab524cadf197c27463d06` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1350.140–1468.200s | 0.548667 | 嗯uv to list 我现在安装了一个m l x whisper 当然还有manner u哈 去做PDF的一个精准的一个pass pass呃  | Not Relevant |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | video | [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型 | — | 0.542068 | [Title] [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型外壳”（简介附原文链接） | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV14pXZBMEh9:p1:chunk_66e6a42d19c6477205653536` | transcript_chunk | Claude用不了的时候，GLM-5.1能顶上吗？ | 116.470–236.090s | 0.539608 | 只不过这个全都是AI版本的 这个系统真的很复杂 我给它的完整提示词 里面包含了像素风的前端记忆系统 弹幕互动角色扮演 还有总的一个gm管理系统  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.533773 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_da39154f9ba5dd5fefd3d98f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 0.040–118.360s | 0.532788 | CLI这个计算机世界里面最古老的交互方式正在迎来一次新的爆发 飞书钉钉起微 谷歌stripe在最近两周内都不约而同地开源了自己的CLI产品 越来 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_0171f0e2944707b88f4f0e98` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 467.280–582.430s | 0.802475 | 还有一些REDIS啊 还有一些数据库之类的 这三个文件就不是很重要 OK这个也是呃 然后呢这一块是RERANK的一个逻辑啊 RERANK呢就相当 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_56a682c288a4e9b5098f4b2d` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 117.050–236.290s | 0.771883 | 这就会带来很多问题 首先模型可能无法读取所有的内容 因为每个模型都只能存储一定量的信息 我们通常称这个量为上下文窗口大小 如果你的产品手册字数过 | Relevant |
| 3 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_da080a304bd25c7141eb58fa` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 0.040–118.720s | 0.763769 | 你是否想做一个靠谱的知识客服 或者是搭建一个能回答问题的知识库 那你就一定绕不开一个技术 Rag 它的全称是retrieval augmente | Relevant |
| 4 | `video:bilibili:BV1vQwJzTEdz:p1` | video | [开源] Agentic RAG项目实战 | — | 0.747330 | [Title] [开源] Agentic RAG项目实战 [Uploader] 蹦跶波 [Description] 感觉传统RAG马上就要成为过 | Relevant |
| 5 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_d72012964d580f8b66161fb4` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 702.510–821.010s | 0.747294 | 他这个意思表达够不够明确 包括ogenttic rag中 他如果检索到的呛可回答的那种并不全面 还会做多次检索 生成多个query 就是更加灵活 | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV11wEb6uEwB:p1` | video | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | — | 6.110143 | [Title] 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 [Uploader] Stellar鱼 [Description] -  | Relevant |
| 2 | `video:bilibili:BV17ZXpB4Ezi:p1` | video | Demo很爽，生产很难 | — | 6.097405 | [Title] Demo很爽，生产很难 [Uploader] LLM-X-生生不息版 [Description] “RAG两天就搭完了”和“调了 | Relevant |
| 3 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_b917c48e1a3bb102a6e7253c` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 1285.260–1368.560s | 5.852730 | …失或者回答有错误 或者数据错误 我就不练了 下面这些包括这些问题去做一个分类 然后你通过这些分类 你的你的运营可以对这些分类做检测 查看这个是 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1tM9UBSEdg:p1:chunk_845aaa1a31d54f67fd21841c` | transcript_chunk | 面试官问：怎么设计企业智能客服 Agent？ | 232.420–351.189s | 5.844912 | …没看懂关键点 每个chunk在embed之前 先用high哭生成这块内容 在原文档里上下文是啥 几十个token append到chunk上  | Not Relevant |
| 5 | `video:bilibili:BV18NLx6fEAq:p1` | video | Claude Code 为什么不用 RAG？ | — | 5.839672 | [Title] Claude Code 为什么不用 RAG？ [Uploader] Hucci写代码 [Description] 这个视频解释了 | Relevant |

## `FAISS`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_634ab524cadf197c27463d06` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1350.140–1468.200s | 0.548667 | 嗯uv to list 我现在安装了一个m l x whisper 当然还有manner u哈 去做PDF的一个精准的一个pass pass呃  | Not Relevant |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | video | [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型 | — | 0.542068 | [Title] [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型外壳”（简介附原文链接） | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV14pXZBMEh9:p1:chunk_66e6a42d19c6477205653536` | transcript_chunk | Claude用不了的时候，GLM-5.1能顶上吗？ | 116.470–236.090s | 0.539608 | 只不过这个全都是AI版本的 这个系统真的很复杂 我给它的完整提示词 里面包含了像素风的前端记忆系统 弹幕互动角色扮演 还有总的一个gm管理系统  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.533773 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_da39154f9ba5dd5fefd3d98f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 0.040–118.360s | 0.532788 | CLI这个计算机世界里面最古老的交互方式正在迎来一次新的爆发 飞书钉钉起微 谷歌stripe在最近两周内都不约而同地开源了自己的CLI产品 越来 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_e7c7b57edb4933ff48f32501` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 1747.800–1865.790s | 0.640600 | 写了几百行代码吧 然后它的具体的功能呢 就是实现了一个比较高效的存储 它主要目的是想取代一下JSON文件和这个 这也这也是个向量数据库嘛 叫做F | Relevant |
| 2 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_65cd61b4ec6821b1ac8686f6` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 233.760–352.320s | 0.637360 | 这个就是它的一个公式 如果大家对这个感兴趣的话 也可以去查一查 然后呢接下来就是这个向量库的一个简写啊 向量库的一个检索 首先就是向量库的这个服 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_3881ab737aaa6464eaf96677` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 465.030–580.400s | 0.615040 | 而是专门的embedding模型 如果你想知道哪些embedding模型最好用的话 可以看一下这个m tap排行榜 它会对各种embedding | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_0171f0e2944707b88f4f0e98` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 467.280–582.430s | 0.606278 | 还有一些REDIS啊 还有一些数据库之类的 这三个文件就不是很重要 OK这个也是呃 然后呢这一块是RERANK的一个逻辑啊 RERANK呢就相当 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_5717a8f5434b964d9689c565` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 2212.680–2330.350s | 0.601743 | embedding向量 然后我们去计算这个这一页的embedding向量 跟这个summer embedding向量的一个相似度 然后相似度如果 | Partially Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1hr6EBBEhM:p1` | video | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | — | 5.445666 | …为未来优化方向；③有人提到embedding不支持设置API URL，主播由此动手修改代码实现了远程embedding API的支持。这些is | Partially Relevant |

## `Claude Code`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_68715fd5098466f0de74bca1` | transcript_chunk | 10分钟app开发全流程 | 616.914–651.960s | 0.595350 | this far—you’ve beaten ninety nine point nine nine percent of folks! But | Not Relevant |
| 2 | `video:bilibili:BV1eZSoBCEra:p1` | video | 15分钟掌握 Claude Code 的95%（新手入门） | — | 0.592106 | [Title] 15分钟掌握 Claude Code 的95%（新手入门） [Uploader] GoldenSpiderAI [Descrip | Relevant |
| 3 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_3809b3a3749b8b750014dd81` | transcript_chunk | 10分钟app开发全流程 | 362.205–397.250s | 0.588140 | they’ve been split into two! Front end features are nearly done, so now, | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_1a6e4044139086d9c8531d73` | transcript_chunk | 10分钟app开发全流程 | 256.281–290.700s | 0.580343 | Well, keep watching, and you’ll find out! The subject combos have an iss | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_17d828131b5c1dcbfa21c7cd` | transcript_chunk | 10分钟app开发全流程 | 225.900–258.148s | 0.580068 | Switch to Craft, and based on the prototype wireframes, generate the fro | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1KJ61BBEB1:p1` | video | 15分钟Claude Code小白入门 | — | 0.715166 | [Title] 15分钟Claude Code小白入门 [Uploader] 第四种黑猩猩CHIMP [Description] 一个入门教程  | Relevant |
| 2 | `video:bilibili:BV1ekdhBnEra:p1` | video | Claude Code 官方教程，Anthropic官方教程，Claude Code in action | — | 0.696985 | [Title] Claude Code 官方教程，Anthropic官方教程，Claude Code in action，使用Claude Co | Relevant |
| 3 | `video:bilibili:BV1XrEZ6NEuD:p1` | video | 五分钟带你看懂黑客松冠军的 Claude Code 配置 | — | 0.669270 | [Title] 五分钟带你看懂黑客松冠军的 Claude Code 配置 [Uploader] 奇思妙想CYC [Description] Gi | Relevant |
| 4 | `video:bilibili:BV18NLx6fEAq:p1` | video | Claude Code 为什么不用 RAG？ | — | 0.658204 | [Title] Claude Code 为什么不用 RAG？ [Uploader] Hucci写代码 [Description] 这个视频解释了 | Relevant |
| 5 | `video:bilibili:BV1D1DTBaEBC:p1` | video | 51万行源码泄露！GitHub史上最快10万星项目诞生 | — | 0.656094 | [Title] 51万行源码泄露！GitHub史上最快10万星项目诞生 [Uploader] 第四种黑猩猩CHIMP [Description] | Not Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1ekdhBnEra:p1` | video | Claude Code 官方教程，Anthropic官方教程，Claude Code in action | — | 7.712802 | [Title] Claude Code 官方教程，Anthropic官方教程，Claude Code in action，使用Claude Co | Relevant |
| 2 | `video:bilibili:BV1KJ61BBEB1:p1` | video | 15分钟Claude Code小白入门 | — | 7.474042 | [Title] 15分钟Claude Code小白入门 [Uploader] 第四种黑猩猩CHIMP [Description] 一个入门教程  | Relevant |
| 3 | `video:bilibili:BV1eZSoBCEra:p1` | video | 15分钟掌握 Claude Code 的95%（新手入门） | — | 7.327111 | [Title] 15分钟掌握 Claude Code 的95%（新手入门） [Uploader] GoldenSpiderAI [Descrip | Relevant |
| 4 | `video:bilibili:BV18NLx6fEAq:p1` | video | Claude Code 为什么不用 RAG？ | — | 7.134855 | [Title] Claude Code 为什么不用 RAG？ [Uploader] Hucci写代码 [Description] 这个视频解释了 | Relevant |
| 5 | `video:bilibili:BV1AuzkBREhx:p1` | video | AI到底是如何进行编程的？抓包拆解Claude Code | — | 6.894179 | [Title] AI到底是如何进行编程的？抓包拆解Claude Code [Uploader] 鲁班大叔_007 [Description] L | Relevant |

## `Codex`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_634ab524cadf197c27463d06` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1350.140–1468.200s | 0.548667 | 嗯uv to list 我现在安装了一个m l x whisper 当然还有manner u哈 去做PDF的一个精准的一个pass pass呃  | Partially Relevant |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | video | [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型 | — | 0.542068 | [Title] [Harness自动优化]01期-Meta-Harness-斯坦福爆火论文-别只卷模型，来“自动发明模型外壳”（简介附原文链接） | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV14pXZBMEh9:p1:chunk_66e6a42d19c6477205653536` | transcript_chunk | Claude用不了的时候，GLM-5.1能顶上吗？ | 116.470–236.090s | 0.539608 | 只不过这个全都是AI版本的 这个系统真的很复杂 我给它的完整提示词 里面包含了像素风的前端记忆系统 弹幕互动角色扮演 还有总的一个gm管理系统  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.533773 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_da39154f9ba5dd5fefd3d98f` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 0.040–118.360s | 0.532788 | CLI这个计算机世界里面最古老的交互方式正在迎来一次新的爆发 飞书钉钉起微 谷歌stripe在最近两周内都不约而同地开源了自己的CLI产品 越来 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1ukRrBMEfp:p1` | video | 用了三个月Codex，我不想回Claude Code了 | — | 0.581273 | [Title] 用了三个月Codex，我不想回Claude Code了 [Uploader] HexUp [Description] 之前的视频 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_547ffa3c97c5fe36fa1a74a3` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 204.640–318.880s | 0.572510 | 还有magic 这是后来是摸索出来的一个magic这样一个工具哈 它可以把很多帧拼起来去做一个contact sets 我待会会稍微简单讲一下哈 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1ukRrBMEfp:p1:chunk_ec3e99c121f8185de7585267` | transcript_chunk | 用了三个月Codex，我不想回Claude Code了 | 0.040–113.380s | 0.506267 | 之前的视频我聊了三个工具怎么选 一段时间过去了 我的看法变了 现在我强烈推荐codex作为首选的agent的应用 这个是OpenAI官方推出的A | Relevant |
| 4 | `transcript_chunk:bilibili:BV1SrLG6oEax:p1:chunk_ba2d31f9e153c32f94fbe7f9` | transcript_chunk | [M芯片与AI计算] 02 Coding Agent 时代的 MacOS 装机配置与心流体验的获得，实用 | 1578.220–1697.090s | 0.498213 | 哦对这个这个这个写错了 去看一下他的他关联的一个路径 然后啊对 对大概都是U这全局的local c l u VP对 然后不建议在全局的Pytho | Partially Relevant |
| 5 | `video:bilibili:BV1QUXGBXER9:p1` | video | [Modern Agent] 15 Codex 通用工具设计，subagents，apply_patch | — | 0.468517 | [Title] [Modern Agent] 15 Codex 通用工具设计，subagents，apply_patch，exec_comman | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1ukRrBMEfp:p1` | video | 用了三个月Codex，我不想回Claude Code了 | — | 5.512328 | [Title] 用了三个月Codex，我不想回Claude Code了 [Uploader] HexUp [Description] 之前的视频 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1ukRrBMEfp:p1:chunk_ec3e99c121f8185de7585267` | transcript_chunk | 用了三个月Codex，我不想回Claude Code了 | 0.040–113.380s | 5.224499 | 之前的视频我聊了三个工具怎么选 一段时间过去了 我的看法变了 现在我强烈推荐codex作为首选的agent的应用 这个是OpenAI官方推出的A | Relevant |
| 3 | `video:bilibili:BV1ZA93BtEKW:p1` | video | [Modern Agent] 16 Claude Code 记忆（Memory）系统设计，记忆语义分类， | — | 5.184398 | …充电的同学后台私信 github 账户，我邀请进来）： https://github.com/wdkns/modern_genai_bilib | Partially Relevant |
| 4 | `video:bilibili:BV1K2546oEkg:p1` | video | 开源一个 PPT Skill｜压进了我 10 年的设计经验 | — | 5.078301 | … 开源一个 PPT Skill｜压进了我 10 年的设计经验 [Uploader] 歸藏的AI工具箱 [Description] 来了！藏师傅 | Not Relevant |
| 5 | `video:bilibili:BV1QUXGBXER9:p1` | video | [Modern Agent] 15 Codex 通用工具设计，subagents，apply_patch | — | 5.067695 | [Title] [Modern Agent] 15 Codex 通用工具设计，subagents，apply_patch，exec_comman | Relevant |

## `OpenAI Agents SDK`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_68715fd5098466f0de74bca1` | transcript_chunk | 10分钟app开发全流程 | 616.914–651.960s | 0.605991 | this far—you’ve beaten ninety nine point nine nine percent of folks! But | Not Relevant |
| 2 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_3809b3a3749b8b750014dd81` | transcript_chunk | 10分钟app开发全流程 | 362.205–397.250s | 0.599522 | they’ve been split into two! Front end features are nearly done, so now, | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_3ae13d16e1e0f2cb448dcffc` | transcript_chunk | 10分钟app开发全流程 | 0.000–40.144s | 0.595387 | The Gaokao’s wrapped up again—next up is college application! So, I whip | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_1a6e4044139086d9c8531d73` | transcript_chunk | 10分钟app开发全流程 | 256.281–290.700s | 0.590405 | Well, keep watching, and you’ll find out! The subject combos have an iss | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1Tejc6oEik:p1:chunk_fa0e54a4651d5bbbb15f9d43` | transcript_chunk | 10分钟app开发全流程 | 288.660–327.138s | 0.586733 | now let you pick up to three scores—plus that arrow! Just removed it—mak | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1dw526tEMA:p1` | video | 【2026/Agent】一期讲透！理论+代码从ToolCall到Harness、Claw，告诉你Agen | — | 0.675961 | [Title] 【2026/Agent】一期讲透！理论+代码从ToolCall到Harness、Claw，告诉你Agent的一切 [Upload | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV1V39eBHERZ:p1:chunk_d3555403e54cc4bbbef1b7d4` | transcript_chunk | 我做了个 AI 面试官，专练大厂 Vibe Coding 题 | 1157.260–1275.370s | 0.670816 | 这个比如这个问题 大家可以看一下 大家看是不是做的特别好吧 你好 作为这个大厂的专家对吧 他给我们每一个点进行了打分 所以说其实我们可以在我们的 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1nkdqByEtR:p1:chunk_d3fe767f1917e4a1646cf326` | transcript_chunk | 李宏毅 \| Harness Engineer教程，有时候语言模型不是不够聪明，只是没有人类好好引导 | 1858.850–1976.750s | 0.668724 | 那是一个靠官方写好的工具 然后那个工具呢就有一些限制 你可能是没有办法做的 然后我从来没有办法让COWORD上的小新 成功的把一个影片上传到YO | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV1QdzCB3Eu2:p1:chunk_a01b4c13c8d9694631277338` | transcript_chunk | 强推！(2026最新版) 李宏毅最新课程：智能体AI【AI Agent】71集全！人工智能/机器学习/深 | 1276.210–1390.849s | 0.668486 | 那用AI来训练模型 那其实这个运作的过程 就是你的目标就是要过strong baseline 然后你提供给LLN训练资料 还写一个程序 用这些训 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1mcAfzqEnE:p1:chunk_594bad778e8508fb4c2f4b79` | transcript_chunk | 【Learn Claude Code 源码详解】- 本地启动 Agent | 114.679–232.749s | 0.667268 | 当然我们不可能通过这个project去真的去实 去实现一个生产级别的agent的 但是我们可以了解它的原理 可以深入 就像我们当初呃去深入额理解 | Partially Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `MCP 协议`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1qTYizcEN3:p1` | video | 什么是Function Calling与MCP协议？它们为何要这样设计？ | — | 0.711846 | [Title] 什么是Function Calling与MCP协议？它们为何要这样设计？ [Uploader] 堂吉诃德拉曼查的英豪 [Desc | Relevant |
| 2 | `transcript_chunk:bilibili:BV1qTYizcEN3:p1:chunk_4e9e44df49e6a90f98be452e` | transcript_chunk | 什么是Function Calling与MCP协议？它们为何要这样设计？ | 2077.289–2193.930s | 0.667523 | 这些普通的一些前后端应用等等 而NCP协议它是用于标准化这些应用程序 像LM提供上下文的一个一个协议 上下文 这里指的就是说模型决策的时候 它可 | Relevant |
| 3 | `transcript_chunk:bilibili:BV1qTYizcEN3:p1:chunk_b2cd7d9b4bcda464e5fc5033` | transcript_chunk | 什么是Function Calling与MCP协议？它们为何要这样设计？ | 2422.060–2538.740s | 0.647316 | 大家看文档的时候会发现 它现在已经更新成了这个STREAMABLEHTTP协议 但是去年11月的时候 他还不是这样的 他是HTTP加SSE传输的 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1qTYizcEN3:p1:chunk_bba9a7b0f972e16f9c3c5fee` | transcript_chunk | 什么是Function Calling与MCP协议？它们为何要这样设计？ | 1964.840–2080.489s | 0.646771 | 所以说总而言之 我们还是需要一个全新的一个方案 一个架构 一个协议去解决我们最初遇到的问题 让大模型掉工具 那我现在画出来的这个架构 其实已经是 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_beb8f45eab8efd241aea9343` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 701.780–819.569s | 0.636534 | 火了大概一年多的时间 然后很多公司他都在建立自己的MCP特有的hub 在公司内部去实现这种工具的复用 那么我们来看一下这个NCP 其实所谓协议它 | Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1qTYizcEN3:p1` | video | 什么是Function Calling与MCP协议？它们为何要这样设计？ | — | 0.607123 | [Title] 什么是Function Calling与MCP协议？它们为何要这样设计？ [Uploader] 堂吉诃德拉曼查的英豪 [Desc | Relevant |
| 2 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_2161f52c75ef74ca992bfc3e` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 461.760–579.190s | 0.596303 | 理解skill的核心概念 是把某一类任务需要的知识流程和工具 组织成一个可以按需加载的能力 然后可以看一些skill的最佳实践和设计指南 学习s | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1qTYizcEN3:p1:chunk_aebdc39512df027d7627316f` | transcript_chunk | 什么是Function Calling与MCP协议？它们为何要这样设计？ | 3232.870–3351.500s | 0.579900 | NCP协议会取代function call y之类的说法 他想表达的意思可能更倾向于说 这个NCP协议 它会逐渐取代原有的这个 function | Relevant |
| 4 | `transcript_chunk:bilibili:BV1AuzkBREhx:p1:chunk_bd38bab47f32c042b83c8b17` | transcript_chunk | AI到底是如何进行编程的？抓包拆解Claude Code | 0.080–119.360s | 0.570216 | 安吉的m cp scale到底是什么 你一定听过很多关于他们的理论 但你的理解一定是正确的吗 比如MCP的解析式大模型上下文协议 它可以和各种外 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_2a4f02bb7201e42859fabb15` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 3948.860–4066.830s | 0.540903 | 我们可以看一下这个F1score的计算原理 那我们也会发现在这个160线落空 local点PY里面也有这个代码 那么F1的计算呢 就是通过这样的 | Not Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV1k6E167Ext:p1` | video | 推荐一些Pi Agent插件 | — | 2.904366 | …ies] Pi · AI Agent 平台 · 视频核心介绍的命令行 AI 代理工具，支持插件扩展。 pi-web-access · 插件 · | Relevant |

## `LangGraph 工作流`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_6294255f1520d80ab3d7993e` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 691.680–811.510s | 0.623276 | hub这类管理内部skill和MCP的通用服务 这个方向可以做的事情其实非常多 然后第三个方向呢是帮助其他团队做AI体校 去了解他们的业务 给出 | Not Relevant |
| 2 | `transcript_chunk:bilibili:BV15CwBzsEmt:p1:chunk_fcc262f7a16c52b66aa10992` | transcript_chunk | 【个人AI科研工作流分享】如何8天实现能24小时在小红书收获近千赞藏评的小研究 | 2310.650–2376.120s | 0.605656 | 第二个呢take个位就是如果你有个idea的话 先让deep research看看相关工作 然后确认自己不是一时嗨了 然后此处应该有一个那个停车 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV14fTc6TEi5:p1:chunk_54e9db0bf5e695f1ec1b124e` | transcript_chunk | 【中配】【Coding Agent】如何将 Pi 打造成终极编程智能体 | 449.980–561.880s | 0.599770 | 镜像仓库时必须经历的非常令人头疼的麻烦 你不必为每一次勾肩都痛苦的重复无数次 o as流程 只需在低坡控制面板中登录一次镜像仓库 然后就一劳永逸 | Partially Relevant |
| 4 | `video:bilibili:BV1hYwDzSE7A:p1` | video | 先对齐意图再写代码！OpenSpec让AI编程不再翻车｜AI编程实战 #04 | — | 0.594400 | [Title] 先对齐意图再写代码！OpenSpec让AI编程不再翻车｜AI编程实战 #04 [Uploader] Web3布道师Noah [D | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_baacf9186c1bb39b1348144f` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 577.730–695.720s | 0.587100 | 然后是关于RG 这也是很多企业内部在做的一件事情 主要是和知识库检索相关 比如说公司里面有很多内部文档 或者是一些业务知识库 这些内容呢模型本身 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_6cfb0d1a909308f49e45ec87` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 115.300–233.370s | 0.677863 | 这些功能就涉及到tools的注册调用 执行相关的技术 以及怎么把这些tools调用 串成一个可控的执行流程 所以那段时间我就开始系统性的学习 任 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1wBfvBnEkY:p1:chunk_537aaeea13d658af1063c223` | transcript_chunk | PI: pi-ai & pi-agent-core | 462.590–581.490s | 0.585876 | 而且呢这个经常情况下呢 这个open cloud跟人类用户在这个channel里面对话的时候 他不是一问一答 而是多轮问答 所以呢他的这个wor | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_4ff3cfedbfaf47add9b4f51f` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 0.400–119.640s | 0.585738 | 大家好呀 这期视频呢我就给大家讲解一下 我这个项目的整体架构 还有一些核心代码的梳理吧 然后这个呢也是AI帮我做的一个presentation呃 | Relevant |
| 4 | `video:bilibili:BV1wMQjBCEpZ:p1` | video | [开源] RAG 项目框架及源码详解 | — | 0.585268 | [Title] [开源] RAG 项目框架及源码详解 [Uploader] 蹦跶波 [Description] 项目地址：https://git | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1Up756vEK7:p1:chunk_43325752379b753734434299` | transcript_chunk | 为什么复杂 Agent 越来越采用 DAG Workflow，而不是简单的 ReAct 循环？ | 0.160–99.740s | 0.576148 | 字节一面 为什么复杂agent越来越采用daa g workflow 而不是简单的react循环 90%的人搞错了 复杂agent拼的不是推理能 | Partially Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `RAG 检索增强生成`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_da080a304bd25c7141eb58fa` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 0.040–118.720s | 0.574216 | 你是否想做一个靠谱的知识客服 或者是搭建一个能回答问题的知识库 那你就一定绕不开一个技术 Rag 它的全称是retrieval augmente | Relevant |
| 2 | `transcript_chunk:bilibili:BV1TxwQz5E4B:p1:chunk_3a7dbb088e58ce55f6ab56ca` | transcript_chunk | 龙虾退散潮，我做了一期OpenClaw理性入门教程｜下 | 2129.100–2230.633s | 0.563541 | 以及进一步增强的QMD混合检索 那这其中 SQLite更适合轻量级 默认可用的本地索引场景 LanceDB更适合做Embedding 向量存储和 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_c985b56f7378cb5de7fc542d` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 467.710–587.389s | 0.553920 | 最后模型在基于以上所有的这些信息生成回复 也就对应检索增强生成这三个步骤非常好理解 有了rag之后 模型他回答你的问题的时候 就可以带上很多真实 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_6126233a2261fa54ca8eee45` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 2562.109–2681.689s | 0.540475 | 筛选等于零 然后这个筛选重新computer我们的段的热度啊 以上就这么做的 然后重建一个堆 接下来呢我们来看一下这个检索和生成额 也是我们最后 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1FPTT6uEd2:p1:chunk_3f60438f6f6f6a4c6e46b503` | transcript_chunk | 手把手教你做高质量 AIAgent 开源项目，为面试上大分！ | 728.579–843.500s | 0.539704 | 然后最后一点让AI帮你产出 说当前这个pr能体现你的哪些核心能力 这个就是一份完整的让AI帮你产出 技术方案的一份提示词 给出技术方案之后 下一 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_d72012964d580f8b66161fb4` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 702.510–821.010s | 0.789956 | 他这个意思表达够不够明确 包括ogenttic rag中 他如果检索到的呛可回答的那种并不全面 还会做多次检索 生成多个query 就是更加灵活 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_da080a304bd25c7141eb58fa` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 0.040–118.720s | 0.766473 | 你是否想做一个靠谱的知识客服 或者是搭建一个能回答问题的知识库 那你就一定绕不开一个技术 Rag 它的全称是retrieval augmente | Relevant |
| 3 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_0171f0e2944707b88f4f0e98` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 467.280–582.430s | 0.763240 | 还有一些REDIS啊 还有一些数据库之类的 这三个文件就不是很重要 OK这个也是呃 然后呢这一块是RERANK的一个逻辑啊 RERANK呢就相当 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_c985b56f7378cb5de7fc542d` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 467.710–587.389s | 0.754850 | 最后模型在基于以上所有的这些信息生成回复 也就对应检索增强生成这三个步骤非常好理解 有了rag之后 模型他回答你的问题的时候 就可以带上很多真实 | Relevant |
| 5 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_c4957fec396229e980b26e42` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 351.210–469.950s | 0.748244 | 你的向量的 这个生产 一个是知识的来源 比方说这里提到 可以通过用户的一些线上反馈的问题 agent的去判断这个问题的类型是怎样的 然后做一个知 | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `video:bilibili:BV11nSjB2ErQ:p1` | video | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | — | 9.374771 | …rmer、LangChain 、RAG 等大模型核心知识点！简直不要太爽！ [Uploader] 李宏毅-机器学习课堂 [Descriptio | Relevant |

## `FAISS 向量索引`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_65cd61b4ec6821b1ac8686f6` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 233.760–352.320s | 0.689469 | 这个就是它的一个公式 如果大家对这个感兴趣的话 也可以去查一查 然后呢接下来就是这个向量库的一个简写啊 向量库的一个检索 首先就是向量库的这个服 | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_6d1a0464d7b61ea108439377` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 818.380–937.740s | 0.651770 | 可以引入一个图to rag 去做一个关系性的这种检索 因为本身的rag它还是基于向量的 他这种方式就导致了 它可能会漏掉一些这种呛克之间的关系性 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_6398a334473756d05bb86c53` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 232.780–351.470s | 0.635783 | 它一共是包含分片和索引两个环节 另外一个是回答部分 这一部分当然是发生在用户提问之后了 在用户问完问题之后 我们便会触发回答问题的各个环节 分别 | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_3881ab737aaa6464eaf96677` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 465.030–580.400s | 0.612862 | 而是专门的embedding模型 如果你想知道哪些embedding模型最好用的话 可以看一下这个m tap排行榜 它会对各种embedding | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1oKdxBzEVz:p1:chunk_38acbadc76d383b3a527f4cd` | transcript_chunk | Hermes Agent 详细讲解 & 本地部署和基于 OpenClaw 迁出的全流程 | 691.800–811.380s | 0.602224 | 他是为这个长期陪伴型的数字AI员工来设计的 他的这个记忆包括短期上下文 其实就是当前对话消息 这个很简单 还有就是向量检索和全文检索嗯 大家如果 | Partially Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1wMQjBCEpZ:p1:chunk_65cd61b4ec6821b1ac8686f6` | transcript_chunk | [开源] RAG 项目框架及源码详解 | 233.760–352.320s | 0.704527 | 这个就是它的一个公式 如果大家对这个感兴趣的话 也可以去查一查 然后呢接下来就是这个向量库的一个简写啊 向量库的一个检索 首先就是向量库的这个服 | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_3881ab737aaa6464eaf96677` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 465.030–580.400s | 0.688634 | 而是专门的embedding模型 如果你想知道哪些embedding模型最好用的话 可以看一下这个m tap排行榜 它会对各种embedding | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV11wEb6uEwB:p1:chunk_6d1a0464d7b61ea108439377` | transcript_chunk | 如何优化你简历的RAG项目，工业级RAG项目是怎么做的 | 818.380–937.740s | 0.624182 | 可以引入一个图to rag 去做一个关系性的这种检索 因为本身的rag它还是基于向量的 他这种方式就导致了 它可能会漏掉一些这种呛克之间的关系性 | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV1JLN2z4EZQ:p1:chunk_6398a334473756d05bb86c53` | transcript_chunk | RAG 工作机制详解——一个高质量知识库背后的技术全流程 | 232.780–351.470s | 0.620680 | 它一共是包含分片和索引两个环节 另外一个是回答部分 这一部分当然是发生在用户提问之后了 在用户问完问题之后 我们便会触发回答问题的各个环节 分别 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1hr6EBBEhM:p1:chunk_e7c7b57edb4933ff48f32501` | transcript_chunk | 手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】 | 1747.800–1865.790s | 0.619949 | 写了几百行代码吧 然后它的具体的功能呢 就是实现了一个比较高效的存储 它主要目的是想取代一下JSON文件和这个 这也这也是个向量数据库嘛 叫做F | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `Claude Code 上下文压缩`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_56b9fd7c974d37fe193c2596` | transcript_chunk | Claude Code 源码分析与复刻实现 | 1382.940–1501.510s | 0.663656 | 然后以后同一个session或者是子智能体 它可以动态调用 然后最最简单就是context collapse 就是对话折叠啊 折叠完成这个这个折 | Relevant |
| 2 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_19a3ee676e51c6fa8da4f3e3` | transcript_chunk | Claude Code 源码分析与复刻实现 | 231.230–350.550s | 0.630424 | 不是把工具的名字和一个一句话的描述扔给他 然后呢让模型看一下啊 那我这100个里面我可能要调用第二个和第12个 然后呢再去把第二个和第12个的工 | Relevant |
| 3 | `transcript_chunk:bilibili:BV1TfRfBJEZw:p1:chunk_f2dd606dcfa50c60d754c96b` | transcript_chunk | 解读Deepseek V4带来的杠杆机会，顺便聊聊我实践出的Token Efficiency | 349.930–467.590s | 0.622082 | 性能就直接下降 即便是个小任务 超过200K上下文也是非常常见的事 但1000K上下文意味着什么 如果你有合理的编排 那么每个被分解后的小任务  | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_ccecc343d9822f3cbe66c8af` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 1164.210–1282.990s | 0.619278 | 这个我觉得long chan的这篇文章比ENTHOPPIC这篇写的要更好一点 首先什么是上下文工程 我觉得简单来说其实就是在agent的循环运行 | Not Relevant |
| 5 | `transcript_chunk:bilibili:BV1fNw9ziEYk:p1:chunk_3fbb408dc17157bce3c9a309` | transcript_chunk | 【注意力残差】10分钟看懂 马斯克盛赞的Kimi最新技术 | 467.140–584.820s | 0.613665 | 还有这样一种角度 模型的深度实际上也就是另外一种时间 那么这篇论文里把RNN也放在这里 进行了一种阐述 它其实是都是相通的 我们来看 那这其实就 | Not Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_1db9841940bf824e9e9dc5dc` | transcript_chunk | Claude Code 源码分析与复刻实现 | 1267.170–1385.980s | 0.620715 | 就是权限最这个最紧的那个人会赢 他这个propermission mode要要要踹很多地方 比如说你当前运行的模式 你是plan模式啊 还是au | Relevant |
| 2 | `video:bilibili:BV1z6SXBzEYh:p1` | video | Claude Code 的记忆机制到底强在哪？六维记忆体系深度解析，一节视频讲透指令记忆、长期记忆、Se | — | 0.606440 | [Title] Claude Code 的记忆机制到底强在哪？六维记忆体系深度解析，一节视频讲透指令记忆、长期记忆、Session Memory | Relevant |
| 3 | `transcript_chunk:bilibili:BV1iVoVBgERD:p1:chunk_d51e55d0a9204c6a5a914d7c` | transcript_chunk | 对罗福莉的3.5小时访谈：AI范式已然巨变！OpenClaw、智能体框架、Agent范式很吃Post-t | 700.750–820.620s | 0.598660 | 我呃code它是一个泛化性非常强的一个场景 就是你针对他去做了非常多a agent的设计也好 或者说模型的训练也好 它都是都是有价值的 但并不代 | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_19a3ee676e51c6fa8da4f3e3` | transcript_chunk | Claude Code 源码分析与复刻实现 | 231.230–350.550s | 0.595975 | 不是把工具的名字和一个一句话的描述扔给他 然后呢让模型看一下啊 那我这100个里面我可能要调用第二个和第12个 然后呢再去把第二个和第12个的工 | Relevant |
| 5 | `video:bilibili:BV18NLx6fEAq:p1` | video | Claude Code 为什么不用 RAG？ | — | 0.589859 | [Title] Claude Code 为什么不用 RAG？ [Uploader] Hucci写代码 [Description] 这个视频解释了 | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `Agent 运行很多轮以后怎样避免上下文越来越长`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_ccecc343d9822f3cbe66c8af` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 1164.210–1282.990s | 0.695538 | 这个我觉得long chan的这篇文章比ENTHOPPIC这篇写的要更好一点 首先什么是上下文工程 我觉得简单来说其实就是在agent的循环运行 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1TfRfBJEZw:p1:chunk_f2dd606dcfa50c60d754c96b` | transcript_chunk | 解读Deepseek V4带来的杠杆机会，顺便聊聊我实践出的Token Efficiency | 349.930–467.590s | 0.682764 | 性能就直接下降 即便是个小任务 超过200K上下文也是非常常见的事 但1000K上下文意味着什么 如果你有合理的编排 那么每个被分解后的小任务  | Relevant |
| 3 | `transcript_chunk:bilibili:BV1iVoVBgERD:p1:chunk_e3ecad1fff51d2458ecfebe2` | transcript_chunk | 对罗福莉的3.5小时访谈：AI范式已然巨变！OpenClaw、智能体框架、Agent范式很吃Post-t | 2094.890–2213.160s | 0.654274 | 它就为长上下文的能力和效率 效率很关键 效率我们待会再谈 就长上下文的能力和效率 已经做好了充分的准备 这个是在我们没有去受到这么大冲击的事情  | Relevant |
| 4 | `transcript_chunk:bilibili:BV1iVoVBgERD:p1:chunk_140968d664d3edbe11b39182` | transcript_chunk | 对罗福莉的3.5小时访谈：AI范式已然巨变！OpenClaw、智能体框架、Agent范式很吃Post-t | 1979.230–2099.130s | 0.645314 | 嗯所以他是改变了整个研究的节奏 对效率和方式都会发生 我觉得很根本性的变化 嗯这对你们后来带来了什么样的改变 在你经历了春节和春节之后的整个的冲 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_19a3ee676e51c6fa8da4f3e3` | transcript_chunk | Claude Code 源码分析与复刻实现 | 231.230–350.550s | 0.643265 | 不是把工具的名字和一个一句话的描述扔给他 然后呢让模型看一下啊 那我这100个里面我可能要调用第二个和第12个 然后呢再去把第二个和第12个的工 | Partially Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_ccecc343d9822f3cbe66c8af` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 1164.210–1282.990s | 0.693991 | 这个我觉得long chan的这篇文章比ENTHOPPIC这篇写的要更好一点 首先什么是上下文工程 我觉得简单来说其实就是在agent的循环运行 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_c2ee3adabf15dda4ceeae26c` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 1050.000–1169.130s | 0.688143 | 但是最终却发现退回到单agent的架构设计 然后去进一步优化提示词 优化工具等描述 反而会达到更好的效果 所以他在这里总结了三种情况下使用多ag | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_9d72b674cca17e140cfdfb99` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 934.550–1053.560s | 0.675139 | 嗯我贴错了吗 agent呢从reacts agent的开始 它后面大概分出了两条线 一个是侧重规划的agent的 一个是侧重反思的agent的类 | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_bdfd182c29f9b33a50fe33fe` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 816.210–936.180s | 0.671903 | 也就是说这是一个循环的过程 人类在思考自己的任务目标 再根据目标进行行动 在观察自己的行动的结果 在这个不断与环境进行交互的过程中 去逐步达成你 | Partially Relevant |
| 5 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_e2bddbc2e1e85022febc33bb` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 1281.630–1401.320s | 0.660878 | 选择上下文 压缩上下文以及隔离上下文四个部分 这一块儿大家可以下会之后详细阅读 我就不展开了 好了 讲了这么多 现在终于还是回到了我的初心 ag | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `怎样让模型在工具执行失败后换一种办法继续完成任务`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_66a23e51c93b56c062fb8a83` | transcript_chunk | Claude Code 源码分析与复刻实现 | 115.930–234.010s | 0.683022 | 这时候大模型返返回的结果是什么结果呢 因为他训练过了 他知道找文件的这个应该调用什么样的工具 比如说叫做bash 然后呃或者是GRAP这个工具  | Relevant |
| 2 | `transcript_chunk:bilibili:BV1atjU6KEJF:p1:chunk_796808c59d72ba8890b8b1a1` | transcript_chunk | 2026-06-20 AI 编程中的测试和 Loop | 3604.000–3723.000s | 0.678614 | 我觉得就是过程中把它当成一个任务 任务执行完就丢弃就行了 我最终我看我用那个的目的 只是为了让我去跑一个一一整夜 一稳定的去跑一个一一整夜的任务 | Not Relevant |
| 3 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_9803a925502fb174588c6b85` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 6030.680–6119.260s | 0.668932 | 二 把橘色的积木从蓝色的积木上面拿起来 好讲到这边 其实这堂课呢也可以停在这边 不过这边多补充一件事 就在几周之前 有一篇新的论文叫做the d | Partially Relevant |
| 4 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_49ac6c87ad049097f9b557ba` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 3480.949–3600.050s | 0.662907 | 什么样的挑战呢 我们刚才使用工具的方法是 每一个工具它都到要有对应的文字描述 告诉语 告诉语言模型说这个工具要怎么被使用 但假设工具很多怎么办呢 | Relevant |
| 5 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_a7a2996fe53f9ea799cf2729` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 3598.010–3715.260s | 0.656446 | 发现这个function运作的非常的顺利 然后就可以把这个function当做一个工具 放到他的工具包里面 那之后这个工具就有可能在选择工具的时 | Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1nkdqByEtR:p1:chunk_efe9b27c36cd02014362a183` | transcript_chunk | 李宏毅 \| Harness Engineer教程，有时候语言模型不是不够聪明，只是没有人类好好引导 | 347.720–466.809s | 0.669847 | 看看档案里面有什么再改它 然后最后我还告诉他什么叫做完成 告诉他说 所谓的完成就是有一些specific的criteria 有一些既定的标准 你 | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV15HXCBkEKY:p1:chunk_66a23e51c93b56c062fb8a83` | transcript_chunk | Claude Code 源码分析与复刻实现 | 115.930–234.010s | 0.615911 | 这时候大模型返返回的结果是什么结果呢 因为他训练过了 他知道找文件的这个应该调用什么样的工具 比如说叫做bash 然后呃或者是GRAP这个工具  | Relevant |
| 3 | `transcript_chunk:bilibili:BV1QdzCB3Eu2:p1:chunk_fcd44784ccd67760b3f99608` | transcript_chunk | 强推！(2026最新版) 李宏毅最新课程：智能体AI【AI Agent】71集全！人工智能/机器学习/深 | 3466.080–3584.410s | 0.610767 | 得到的正确率是最高的 可以完胜 当时其他号称可以直接听语音的模型哦 所以使用工具可能可以带来很大的帮助 但使用工具也有其他的挑战 什么样的挑战呢 | Relevant |
| 4 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_49ac6c87ad049097f9b557ba` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 3480.949–3600.050s | 0.604873 | 什么样的挑战呢 我们刚才使用工具的方法是 每一个工具它都到要有对应的文字描述 告诉语 告诉语言模型说这个工具要怎么被使用 但假设工具很多怎么办呢 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1AuzkBREhx:p1:chunk_a7866eccf1647c60d6586ef1` | transcript_chunk | AI到底是如何进行编程的？抓包拆解Claude Code | 698.800–790.000s | 0.604760 | 而你在这里一个参数都没传好 这样他就能够基于现有的信息能够进行判案了 能够判断这个病情到底是在哪里了 OK这个时候他就会给我们返回 实际的问题的 | Not Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `如何通过外部资料检索增强模型回答`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1QdzCB3Eu2:p1:chunk_4fd071af0ebcf44084bb167c` | transcript_chunk | 强推！(2026最新版) 李宏毅最新课程：智能体AI【AI Agent】71集全！人工智能/机器学习/深 | 2199.100–2314.870s | 0.630317 | 你需要有一个检索的模组 这个检索的模组只从过去所有的经验中检索出 跟现在要回答的问题有关系的经验 然后呢语言模型只根据这些有关系的经验 还有现在 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1TxwQz5E4B:p1:chunk_3a7dbb088e58ce55f6ab56ca` | transcript_chunk | 龙虾退散潮，我做了一期OpenClaw理性入门教程｜下 | 2129.100–2230.633s | 0.621912 | 以及进一步增强的QMD混合检索 那这其中 SQLite更适合轻量级 默认可用的本地索引场景 LanceDB更适合做Embedding 向量存储和 | Relevant |
| 3 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_15f0e563b3a7f0ce15a49ddb` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 2201.430–2320.140s | 0.620204 | 这个检索的模组只从过去所有的经验中检索出 跟现在要回答的问题有关系的经验 然后呢语言模型只根据这些有关系的经验 还有现在的问题来进行回答 来产生 | Relevant |
| 4 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_83eab60da6736e3c30eb4cbc` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 3830.870–3948.950s | 0.616722 | 所以语言模型 今天是有自己一定程度的判断力的 它也不是完全相信工具 就像你今天不完全相信语言模型的输出一样 他也不完全相信他的工具的输出 他还是 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1Wu5f6GEr6:p1:chunk_83fd2d493cdc27af0b139ac6` | transcript_chunk | 最新字节大模型开发暑期实习一面面试精讲 | 1174.100–1292.880s | 0.616098 | 然后第三个RLHF 其实啊也就是对应着这个扳机这一块啊 那其实RRHF和DPO也就是强化学习 也就是说通过人类的标注告诉它啊 人类告诉他什么样的 | Partially Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1QdzCB3Eu2:p1:chunk_4084f1257c3163d84a68a365` | transcript_chunk | 强推！(2026最新版) 李宏毅最新课程：智能体AI【AI Agent】71集全！人工智能/机器学习/深 | 3815.970–3935.930s | 0.703715 | 语言模型继续做文字接龙的时候 他就知道说这显然有问题 这个API给我的答案是1万度 这是不合理的 怎么可能比太阳上的温度还高呢 可见工具输出有错 | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_83eab60da6736e3c30eb4cbc` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 3830.870–3948.950s | 0.691803 | 所以语言模型 今天是有自己一定程度的判断力的 它也不是完全相信工具 就像你今天不完全相信语言模型的输出一样 他也不完全相信他的工具的输出 他还是 | Relevant |
| 3 | `transcript_chunk:bilibili:BV11nSjB2ErQ:p1:chunk_15f0e563b3a7f0ce15a49ddb` | transcript_chunk | LLM大模型入门！一口气带你学完AI agent、transformer、LangChain 、RAG  | 2201.430–2320.140s | 0.658871 | 这个检索的模组只从过去所有的经验中检索出 跟现在要回答的问题有关系的经验 然后呢语言模型只根据这些有关系的经验 还有现在的问题来进行回答 来产生 | Relevant |
| 4 | `transcript_chunk:bilibili:BV1QdzCB3Eu2:p1:chunk_4fd071af0ebcf44084bb167c` | transcript_chunk | 强推！(2026最新版) 李宏毅最新课程：智能体AI【AI Agent】71集全！人工智能/机器学习/深 | 2199.100–2314.870s | 0.657167 | 你需要有一个检索的模组 这个检索的模组只从过去所有的经验中检索出 跟现在要回答的问题有关系的经验 然后呢语言模型只根据这些有关系的经验 还有现在 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1zSDMBUE5o:p1:chunk_c985b56f7378cb5de7fc542d` | transcript_chunk | 近年AI应用技术串讲与优质文档分享｜Agent、Skill、OpenClaw、Harness…… | 467.710–587.389s | 0.630658 | 最后模型在基于以上所有的这些信息生成回复 也就对应检索增强生成这三个步骤非常好理解 有了rag之后 模型他回答你的问题的时候 就可以带上很多真实 | Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |

## `如何组织可恢复的多阶段 Agent 工作流`

### Baseline Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_baacf9186c1bb39b1348144f` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 577.730–695.720s | 0.605219 | 然后是关于RG 这也是很多企业内部在做的一件事情 主要是和知识库检索相关 比如说公司里面有很多内部文档 或者是一些业务知识库 这些内容呢模型本身 | Partially Relevant |
| 2 | `transcript_chunk:bilibili:BV1kMVt6mEgr:p1:chunk_6a951e1bf0cea9c059a458db` | transcript_chunk | 17分钟学会 Pi Agent 90% 核心功能：轻量级终端编码助手教程 | 696.580–813.850s | 0.597222 | 你想恢复原样 那就得用git或者安装检查点之类的扩展了 但因为pi本身并不支持直接撤销文件更改 但在运行任何操作之前 最好确保所有文件都已经提交 | Relevant |
| 3 | `transcript_chunk:bilibili:BV1co9yBhEvW:p1:chunk_6294255f1520d80ab3d7993e` | transcript_chunk | 分享我转 AI 方向的学习路径和工作转变 | 691.680–811.510s | 0.582675 | hub这类管理内部skill和MCP的通用服务 这个方向可以做的事情其实非常多 然后第三个方向呢是帮助其他团队做AI体校 去了解他们的业务 给出 | Not Relevant |
| 4 | `transcript_chunk:bilibili:BV1TfRfBJEZw:p1:chunk_3e28e59f7daba5c5bee38e3f` | transcript_chunk | 解读Deepseek V4带来的杠杆机会，顺便聊聊我实践出的Token Efficiency | 580.910–698.550s | 0.582484 | 而不是被人来迭代的 因此我我给AI实现了一整套基于CLI的编排 构建系统 编排中的agent呀 prompt的片段呀 资源啊 都是可以复用的组合 | Relevant |
| 5 | `transcript_chunk:bilibili:BV1G29EBGE8b:p1:chunk_b054f1bd553c27a5e404f8c7` | transcript_chunk | 为什么巨头都在做CLI(命令行界面)？比MCP有哪些优势？ | 695.800–814.920s | 0.580945 | 而且我还可以协助AI进行修复 而MCP对人类来说更像是一个黑盒 整个运行过程都是在agent的内部的 如果运行出错 很难在本地复现问题 调试的难 | Partially Relevant |

### Qwen Dense

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `transcript_chunk:bilibili:BV16GjU6jEdP:p1:chunk_93e1fdef81f943a02d48d872` | transcript_chunk | [多Agent编排Skill自进化] 蚂蚁爆火论文-Skill-MAS：把多 Agent 编排能力写成可 | 230.830–349.680s | 0.668110 | 先在同一个任务内 把高分轨迹和低分轨迹分组比较 他们从哪个编排决策开始分叉 是拆任务漏了约束还是代理角色不清 还是汇总节点没有校验 然后再把多个 | Relevant |
| 2 | `transcript_chunk:bilibili:BV1ffTL6YEXj:p1:chunk_fb1ddb2afc4473a2fa0828f9` | transcript_chunk | Loop Engineering落地实践 提高项目测试效率 测试 -> AGENT -> 研发 | 615.520–714.850s | 0.646414 | 那肯定效果更好嘛 然后再来 就是说我们最后我们这个worker在做了这么多 它的一个效率 我们会怎么去评估 就第一个就是说 我们可能会去评估他的 | Partially Relevant |
| 3 | `transcript_chunk:bilibili:BV1Up756vEK7:p1:chunk_43325752379b753734434299` | transcript_chunk | 为什么复杂 Agent 越来越采用 DAG Workflow，而不是简单的 ReAct 循环？ | 0.160–99.740s | 0.645268 | 字节一面 为什么复杂agent越来越采用daa g workflow 而不是简单的react循环 90%的人搞错了 复杂agent拼的不是推理能 | Relevant |
| 4 | `video:bilibili:BV1Up756vEK7:p1` | video | 为什么复杂 Agent 越来越采用 DAG Workflow，而不是简单的 ReAct 循环？ | — | 0.644441 | [Title] 为什么复杂 Agent 越来越采用 DAG Workflow，而不是简单的 ReAct 循环？ [Uploader] 龙哥搞算法 | Relevant |
| 5 | `transcript_chunk:bilibili:BV15bKn6iEmF:p1:chunk_7d7e2ad7e9d9d11de5830510` | transcript_chunk | Agent落地的两大命门：约束机制+数据飞轮 | 0.040–82.300s | 0.623767 | agent呢目前企业级的落地 总体而言是有两大块比较成功 一大块就是所谓的IJ这块 IJ的这套东西 现在绝不仅仅是你能把一个demo的流程跑通  | Partially Relevant |

### Current Lexical

| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| — | — | — | No result | — | — | — | Unclear |
