# Stage 3R Track A Auto Refresh Human Review Packet

## Summary

Target Video Recall: 20/20
Complete Gold Group Coverage: 11/20
Bundle Hit: 1/20
Router distribution: `{'lexical': 0, 'hybrid': 20, 'dense': 0, 'other': 0}`

## Failure Cases

### C2C_16019b3c36a8945b

MSE 和交叉熵分别适合什么任务，遇到异常值或类别不平衡时该怎么选？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_184029a79aa6685c1db1e6d934fd250856986fd8d8af8148f355d95ce6bc5939', 'candidate_690e14ea5935f49d5ed2c4b6262f473eb20945b8a8cf6f19862fcf5dfbd3ca54', 'candidate_3a1a216c72fedb73aa39e98feb4ec417625a532f7243e3f9797be2a6daf2c7d7', 'candidate_5439cd2ea959747745697671081861dbc61aed3961b75ab927634c19cb1632ad', 'candidate_1136a5c6ea1a0762de7c0c1ec6be69bcf65736070a7e63d6f30ffca2b121a580', 'candidate_442249d307a8eaab114001fc5bad2d585612c686331e9c08ce6b2883144b33e4']`; selector miss: `complete_gold_group_available_but_not_selected`

### C2C_a1c0207a1bc56a91

终端、命令行和命令有什么区别，初学者运行命令时怎样避免误删文件？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_ed1b31fbabf24e7ff2e2ddd306cd200550c0716feaa4704b3a8117149556ea37', 'candidate_c65369aa6ac71614d649341edfb520248e29ba88532fbcfe2b76fd4c03a25713', 'candidate_82c640b64a428bbbcbf540e1df4983960dd189a67d1063e31d0c4f1904372f1e', 'candidate_5b9a0fa766e31abe79284a4e5220caa4588ce0f0f5c1465e1e26bc986b43c740', 'candidate_7c45c51992c77b0501e5aeddf025361ff248d2de492306bc7ba3186d87a350f5', 'candidate_806973e90ebf3191d50c67af9a4bc23e79ecab14ab6a6facc729804386607081']`; selector miss: `complete_gold_group_available_but_not_selected`

### C3C_41cfa020e8d664c5

AI 编程时代为什么 PRD 更重要，AI 和人分别应该负责什么？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_0511b7f0c1424841d17d04cbdcdea244398e2b7191517cc5ecaa56221bb601a1', 'candidate_491ed1a8b68c0aaf6bd5cd6699cb298045fd782ad6ec6403ee4370b09875e9fa', 'candidate_a2096e7c0b35960894081afff00583937d676ccc444cf7955cbedf868b86d757', 'candidate_d2e642144454f55d6f110cad6eb23deb7d24b5c411b3abbbfbd52c429c51dea5', 'candidate_2f548094a8ae93efa45d9940dd74e5696000465d9f80f970e0504489bec88163', 'candidate_af891045591712dd03d6b387ff65040fe900016fb4e01e5da3a6d87b1292dec9']`; selector miss: `complete_gold_group_available_but_not_selected`

### C3C_56b2c368638a31c3

在已有项目中使用 OpenSpec 后，是否实际减少了需求返工，视频给出了什么使用结果？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `273`; Gold segments reachable: `4/22`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### C3C_62e28b33eec87c37

这个 worker 是否已有实际运行后的测试提效结果？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `281`; Gold segments reachable: `5/14`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### C3C_98e93af3d9519c76

Home Rail 当前适合什么任务、使用前有哪些限制，又计划向什么方向发展？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `215`; Gold segments reachable: `50/66`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### C3C_f57e1f0cc83cd5dd

这套 Agent 回归测试闭环实施后，手动测试占用的时间是否真的从约 90% 降了下来？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_b63716aa1120d41721166bcdee84a15fe9c15dcb66024a8ec8d019039395f9ca', 'candidate_172fc3fcafa8efc10850eb35003bd7c2f47c02d7291c66a889ac356d9cd36727', 'candidate_21aa5d6c94c4fcede7739ad0d7b924e8b8a46192e99092065d549552636d535f', 'candidate_1f40cfecd70f93073b878346a9b8eb83ed36f9d46e7dd6c9d067cbe70521d06f', 'candidate_710723ea0362e2015ad0e47c7b81e280d578374ead16cbf3cab72a986f152e13', 'candidate_5d11ad20b1b683bb8e3f157d2fb0ace54fa1e8b3ceaf10d8e8e025935a51dfe8']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_0492bb2ae33b5cec

Python 的数字类型有哪些，它们之间应怎样进行安全的类型转换？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_6af57fb04a0c485e99721fd97201d832117bf93bd85a447898303aad7353870b', 'candidate_569c96b164d311837a3b71dee29ffb038d0f243c1b77c2ae6ed36d475a4ebe90', 'candidate_071e9426453a0ba6696952d64dd9226479775f2d8bc08b93cedffebbebdbba6f', 'candidate_56722445d8c8c81a1baa2d1e76661e78d2dc2acf7934e1f47b7db08672d22254', 'candidate_6844961122ab7f7779cc8127b8ad74f74fc864c9ee1f9f0c908e9cc21f44d983', 'candidate_68fec0e9570ebb156d0112200066cfd6559a4cf30a77da567d9a9d7f5240027e']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_185d322d5f9a00b3

如何把一个应用从原型推进到云部署，并建立自动化测试和回滚机制？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `3`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `228`; Gold segments reachable: `12/27`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_2b331035debc8160

RAG 从 demo 到 production 还缺哪些能力，以及何时应该自建而不是采购？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_cd4c0ce11a19e43e2fd039466b90d228372d6ab826261e66572ac448085810c5', 'candidate_5ffbcab0bf19a2918343514e2287241a827ef96f57dacb0b2a7f425744b74385', 'candidate_60d24bacb0836a0d10469eea6c61d8fcd4c5198ad163628d4626bd376478e276', 'candidate_9342c2a46d1e1f5acd3c098cdd03c87b9840909df2bbf8b9555a0768b38bf749', 'candidate_0d6dc10002a8378c0a11bb368b65334f6e299c2cc5ae48a3fb358c83ae1b20ac', 'candidate_89644d7b064ae5912ea78ba55f6fd7611627fc0844caea1590922b232939b36c']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_53862aba0bd0bfcb

为什么 Agent 的有用记忆在持续整合后会变坏？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `2`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `308`; Gold segments reachable: `7/8`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_5725899059df795c

Cursor 的 RAG 式代码检索与 Claude Code 的命令式探索各自怎样工作、代价是什么？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_6ab4bf29be3e808cbe3cec43c2909bea72532d1e0c79554962b4513a26040217', 'candidate_b74fdcb00c5d61e4642fffeb536541666eb51fdda87a48d5332513c7b867d025', 'candidate_ca09f4fbf225cc3e2f01193677eff9f4a756cc2fb7dfd9221e57404b511553f2', 'candidate_dd0bd50b8cb3743635c21052e8ff2576d2ab78d8a04d426495ccaf0bc8e7452a', 'candidate_ac17851445f6736e065387675ebd45d13bcf714b1e4495daa7cf650382fc7551', 'candidate_2383ac8c11191bbea2887c6ae08fe9556fadfc4fdb9ea97e9e3108278797b826']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_593dade03883828e

Skill 上线前怎样验证路由和内容质量，上线后又怎样防止上下文债务？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `268`; Gold segments reachable: `26/27`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_8228254ff69d7b3b

怎样区分 Agent 的能力上限与稳定性，如何把两类指标用于开发和发布门槛，并怎样设计无歧义且含正反例的测试集？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `265`; Gold segments reachable: `7/8`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_958161474678bd3f

SFT 中 completion-only 和 NEFTune 各有什么作用，选择与调参时有哪些风险？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `269`; Gold segments reachable: `9/38`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_9a49204f52a114c8

RAG 上生产前需要补齐哪些工程能力，又该怎样设计离线与在线质量评测？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `2`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_2f83f7404e799320b144fbb01dc42e30eb5328ff46c1ac11d22164d17fdd812c', 'candidate_a751c5c3852cbc43d3368418f1571cd5d12fc6c855570aeef05fa37fdd50d11e', 'candidate_901b9b7571b2f71bbbe2e4ee00bbbf5bbee33b31a16aa0269ab59e64658c8efb', 'candidate_9eb1034bb3abebeed4fdd12fb82482a14f8c926347beaa3d0c331e2468c52f6e', 'candidate_32bc7bd7afda1324a3e66f320afbd1a44ab026c09fdad0df962611f7b683029c', 'candidate_9bebb36aff99d6f2c7af12947ff78f234dde179a5cbcc0875b4c4c6dcfb45fac']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_9d9b5b9460d0ce51

SFT 中 chat template 和 completion-only 分别解决什么问题，如何用 TRL 将两者组合进训练流程？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `1`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_a97ab0afee31fa84b0f4d24db9e4b72b5692bfa82de739f701d47074442f7d8f', 'candidate_e76c16c32b26cf1221c8f2685c8615c79a514d600627e880a1b70386ed3e8a0a', 'candidate_089f74173ed376b855e73413e29a2b67bf71fb5ecd2ca17c0466be98e49b9ac0', 'candidate_a1428e578e4ffeca4c9316991b550dce24ad545872aae46a48ec706da8ca36af', 'candidate_d086aca6617d89e89f9dd2e084a05eb591a6837680ad9eeb8ae5aaefe37d0eda', 'candidate_e873cb63c3705c64e768f6f18897b8caa084593083347e5a57bb8faae225e27e']`; selector miss: `complete_gold_group_available_but_not_selected`

### V2C_C0C_a48a04ab33a1ad95

这个视频是否完整演示了从原型、前后端开发到云部署的应用构建流程？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `4`
Complete Gold Group Available: `False`; Bundle Hit: `False`
Primary Failure Attribution: `candidate_builder_failure`
Builder candidate count: `246`; Gold segments reachable: `27/44`; missing complete group: `target_video_retrieved_without_complete_gold_group`

### V2C_C0C_c72788577931ce36

Agent 长期记忆为什么会在持续整合中变坏，系统设计上应如何避免？

Router: `hybrid`; effective mode: `hybrid`
Target video: `True` / rank `2`
Complete Gold Group Available: `True`; Bundle Hit: `False`
Primary Failure Attribution: `deterministic_selector_failure`
Available complete Gold Groups: `['G1']`; selected evidence: `['candidate_baf0bcb9722de85f7153cc426e3a315f9386d250aacdc6e6401302acddd20d81', 'candidate_58f0f293c4b24578231ce9dd8682bdde9675b902679004ad3c3bddcc0297807b', 'candidate_6ce9ce932e807db6a1a1b5d862dd64796cc0383a1f43d35a8d1265ace060dcea', 'candidate_f42414ad4bf19eb0cedd85405efa11a65995e01a2ca5fc5fdf24ec1f1e8b10a0', 'candidate_b3a15ccf16d22fe962fb9424842ecd87761033c306dd76b0505cfc8c0974dd5c', 'candidate_86c71b2b829fc66b8521a3235cb11fac86ed901691e79ceb65c84439748143d7']`; selector miss: `complete_gold_group_available_but_not_selected`

